"""Gera o vídeo vertical (1080x1920) de cada oferta aprovada que ainda não tem vídeo.

Sem áudio de propósito: a música você escolhe no próprio TikTok (sons em alta
ajudam no alcance e evitam problema de direito autoral).
Layout respeita a zona segura do TikTok (topo, rodapé da legenda e ícones laterais).
"""
import io
import math
import subprocess
import sys
import textwrap
import time

import requests
from PIL import Image, ImageDraw, ImageFilter, ImageFont

from comum import RAIZ, VIDEOS_DIR, brl, carregar_cfg, carregar_db, exportar_vitrine, log, salvar_db

W, H, FPS = 1080, 1920, 30
FONTES = RAIZ / "fonts"


def fonte(peso, tam):
    return ImageFont.truetype(str(FONTES / f"Poppins-{peso}.ttf"), tam)


def hex_rgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def ease_out(t):  # 0..1 -> 0..1 com desaceleração
    t = max(0.0, min(1.0, t))
    return 1 - (1 - t) ** 3


def ease_back(t):  # "pop" que passa um pouco e volta
    t = max(0.0, min(1.0, t))
    c = 1.70158
    return 1 + (c + 1) * (t - 1) ** 3 + c * (t - 1) ** 2


def baixar_foto(url):
    try:
        if url and not url.startswith("http"):  # caminho local (testes)
            return Image.open(url).convert("RGBA")
        r = requests.get(url, timeout=30, headers={"User-Agent": "Mozilla/5.0"})
        r.raise_for_status()
        return Image.open(io.BytesIO(r.content)).convert("RGBA")
    except Exception as e:  # noqa: BLE001
        log(f"  foto indisponível ({e}); usando placeholder")
        img = Image.new("RGBA", (800, 800), (235, 235, 240, 255))
        ImageDraw.Draw(img).text((400, 400), "?", fill=(160, 160, 170), font=fonte("Bold", 300), anchor="mm")
        return img


def caixa(tamanho, raio, cor):
    img = Image.new("RGBA", tamanho, (0, 0, 0, 0))
    ImageDraw.Draw(img).rounded_rectangle((0, 0, tamanho[0] - 1, tamanho[1] - 1), raio, fill=cor)
    return img


def texto_img(txt, fnt, cor, sombra=False):
    x0, y0, x1, y1 = fnt.getbbox(txt)
    pad = 12
    img = Image.new("RGBA", (x1 - x0 + pad * 2, y1 - y0 + pad * 2), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    if sombra:
        d.text((pad - x0 + 4, pad - y0 + 6), txt, font=fnt, fill=(0, 0, 0, 120))
    d.text((pad - x0, pad - y0), txt, font=fnt, fill=cor)
    return img


def colar(base, img, cx, cy, escala=1.0, alpha=1.0):
    """Cola img centralizada em (cx, cy) com escala e opacidade."""
    if escala <= 0.01 or alpha <= 0.01:
        return
    if escala != 1.0:
        img = img.resize((max(1, int(img.width * escala)), max(1, int(img.height * escala))), Image.LANCZOS)
    if alpha < 1.0:
        a = img.getchannel("A").point(lambda v: int(v * alpha))
        img = img.copy()
        img.putalpha(a)
    base.alpha_composite(img, (int(cx - img.width / 2), int(cy - img.height / 2)))


def gerar_video(of, destino, cfg):
    v = cfg.get("video", {})
    fundo1 = hex_rgb(v.get("cor_fundo_topo", "#1B1035"))
    fundo2 = hex_rgb(v.get("cor_fundo_base", "#07060D"))
    destaque = hex_rgb(v.get("cor_destaque", "#FFD60A"))
    vermelho = hex_rgb(v.get("cor_desconto", "#FF3B4E"))
    dur = float(v.get("duracao_s", 7))
    n_frames = int(dur * FPS)
    num = of["numero"]

    # ---------- fundo estático (gradiente + brilho atrás do produto)
    fundo = Image.new("RGBA", (W, H))
    px = ImageDraw.Draw(fundo)
    for y in range(H):
        t = y / H
        px.line([(0, y), (W, y)], fill=tuple(int(fundo1[i] * (1 - t) + fundo2[i] * t) for i in range(3)) + (255,))
    brilho = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ImageDraw.Draw(brilho).ellipse((90, 200, 990, 1080), fill=destaque + (70,))
    fundo.alpha_composite(brilho.filter(ImageFilter.GaussianBlur(140)))

    # ---------- elementos
    pilula = caixa((520, 96), 48, destaque + (255,))
    t_p = texto_img(f"ACHADINHO #{num}", fonte("Bold", 52), (20, 16, 30))
    pilula.alpha_composite(t_p, ((pilula.width - t_p.width) // 2, (pilula.height - t_p.height) // 2 + 2))

    card_lado, card_y = 740, 240
    card = caixa((card_lado, card_lado), 56, (255, 255, 255, 255))
    sombra_card = Image.new("RGBA", (card_lado + 160, card_lado + 160), (0, 0, 0, 0))
    sombra_card.alpha_composite(caixa((card_lado, card_lado), 56, (0, 0, 0, 150)), (80, 80))
    sombra_card = sombra_card.filter(ImageFilter.GaussianBlur(30))
    foto = baixar_foto(of["foto"])
    foto.thumbnail((card_lado - 90, card_lado - 90), Image.LANCZOS)
    if foto.width < card_lado - 200:  # foto pequena: amplia
        f = (card_lado - 110) / max(foto.width, foto.height)
        foto = foto.resize((int(foto.width * f), int(foto.height * f)), Image.LANCZOS)

    badge = None
    if of.get("desconto"):
        badge = Image.new("RGBA", (250, 250), (0, 0, 0, 0))
        ImageDraw.Draw(badge).ellipse((0, 0, 249, 249), fill=vermelho + (255,))
        tb = texto_img(f"-{of['desconto']}%", fonte("Bold", 80), (255, 255, 255))
        badge.alpha_composite(tb, ((250 - tb.width) // 2, (250 - tb.height) // 2 + 4))
        badge = badge.rotate(-12, resample=Image.BICUBIC, expand=True)

    titulo = of.get("titulo_curto") or of["titulo"]
    linhas = textwrap.wrap(titulo, 30)[:2]
    if len(textwrap.wrap(titulo, 30)) > 2:
        linhas[-1] = linhas[-1].rstrip(" ,.-") + "…"
    t_linhas = [texto_img(l, fonte("Bold", 56), (255, 255, 255), sombra=True) for l in linhas]

    t_antigo = None
    if of.get("desconto") and of.get("original"):
        f_ant = fonte("Medium", 50)
        t_antigo = texto_img(f"de {brl(of['original'])}", f_ant, (180, 175, 195))
        x_ini = 12 + int(f_ant.getlength("de "))
        y_mid = t_antigo.height // 2 + 4
        ImageDraw.Draw(t_antigo).line((x_ini, y_mid, t_antigo.width - 12, y_mid), fill=vermelho + (255,), width=6)
    t_preco = texto_img(brl(of["preco"]), fonte("Bold", 120), destaque, sombra=True)

    cta = caixa((860, 110), 55, (255, 255, 255, 255))
    t_cta = texto_img(f"LINK NA BIO  •  Nº {num}", fonte("Bold", 50), (20, 16, 30))
    cta.alpha_composite(t_cta, ((cta.width - t_cta.width) // 2, (cta.height - t_cta.height) // 2 + 2))

    # ---------- render frame a frame -> ffmpeg
    destino.parent.mkdir(parents=True, exist_ok=True)
    cmd = ["ffmpeg", "-y", "-loglevel", "error",
           "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-",
           "-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo",
           "-shortest", "-c:v", "libx264", "-preset", "veryfast", "-crf", "21",
           "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "64k", "-movflags", "+faststart", str(destino)]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    card_cy = card_y + card_lado // 2
    y_titulo = card_y + card_lado + 75
    for i in range(n_frames):
        t = i / FPS
        fr = fundo.copy()
        # pílula desce do topo
        e = ease_out(t / 0.45)
        colar(fr, pilula, W / 2, 165 - (1 - e) * 140, alpha=e)
        # card + foto: pop e zoom lento contínuo
        e = ease_back(t / 0.6)
        if e > 0.01:
            colar(fr, sombra_card, W / 2, card_cy + 24, e)
            colar(fr, card, W / 2, card_cy, e)
            zoom = 1.0 + 0.06 * (t / dur)
            colar(fr, foto, W / 2, card_cy, e * zoom)
        # selo de desconto
        if badge:
            e = ease_back((t - 0.6) / 0.35)
            colar(fr, badge, (W - card_lado) / 2 + 40, card_y + 30, e)
        # título sobe
        for k, tl in enumerate(t_linhas):
            e = ease_out((t - 0.5 - k * 0.1) / 0.5)
            colar(fr, tl, W / 2, y_titulo + k * 72 + (1 - e) * 60, alpha=e)
        y_preco = y_titulo + len(t_linhas) * 72 + 25
        if t_antigo:
            e = ease_out((t - 0.85) / 0.4)
            colar(fr, t_antigo, W / 2, y_preco, alpha=e)
            y_preco += 100
        # preço: pop + pulsar
        e = ease_back((t - 1.05) / 0.4)
        pulso = 1 + 0.035 * math.sin(max(0, t - 1.6) * 5) if t > 1.6 else 1
        colar(fr, t_preco, W / 2, y_preco + 10, e * pulso)
        # CTA com quique
        e = ease_out((t - 1.5) / 0.4)
        quique = abs(math.sin(max(0, t - 2.2) * 3.2)) * 14 if t > 2.2 else 0
        colar(fr, cta, W / 2, 1505 - quique + (1 - e) * 80, alpha=e)

        proc.stdin.write(fr.convert("RGB").tobytes())
    proc.stdin.close()
    if proc.wait() != 0:
        raise RuntimeError("ffmpeg falhou")


def legenda(of, cfg):
    tags = " ".join(cfg.get("hashtags", ["#achadinhos", "#ofertas", "#mercadolivre"]))
    preco = (f"de {brl(of['original'])} por {brl(of['preco'])} ({of['desconto']}% OFF)"
             if of.get("desconto") else f"por {brl(of['preco'])}")
    nome = of.get("titulo_curto") or of["titulo"]
    return (f"Achadinho #{of['numero']} 🔥 {nome[:80]} {preco}. "
            f"Link na bio, procura o nº {of['numero']} 🔗 {tags}")


def main():
    cfg = carregar_cfg()
    db = carregar_db()
    feitos = 0
    for of in db["ofertas"]:
        if of.get("video") or of.get("video_expirado") or not of.get("ativo", True):
            continue
        destino = VIDEOS_DIR / f"{of['numero']}.mp4"
        if not destino.exists():
            log(f"Renderizando #{of['numero']} — {of['titulo'][:50]}")
            t0 = time.time()
            gerar_video(of, destino, cfg)
            log(f"  ok em {time.time() - t0:.0f}s ({destino.stat().st_size / 1e6:.1f} MB)")
        of["video"] = f"videos/{of['numero']}.mp4"
        of["legenda"] = legenda(of, cfg)
        feitos += 1

    # apaga vídeos antigos para o repositório não crescer demais
    limite = time.time() - cfg.get("apagar_videos_apos_dias", 20) * 86400
    for of in db["ofertas"]:
        if of.get("video") and of.get("criado_em", time.time()) < limite:
            (RAIZ / "docs" / of["video"]).unlink(missing_ok=True)
            of["video"] = None
            of["video_expirado"] = True

    salvar_db(db)
    exportar_vitrine(db, cfg)
    log(f"{feitos} vídeo(s) prontos.")


if __name__ == "__main__":
    sys.exit(main())
