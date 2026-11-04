"""Funções compartilhadas: config, banco (db.json), formatação e API do Mercado Livre."""
import json
import os
import time
from pathlib import Path

import requests

RAIZ = Path(__file__).resolve().parent.parent
CFG_PATH = RAIZ / "config.json"
DB_PATH = RAIZ / "data" / "db.json"          # banco interno (não é publicado)
VITRINE_PATH = RAIZ / "docs" / "vitrine.json"  # só o que o público vê
VIDEOS_DIR = RAIZ / "docs" / "videos"
ML = "https://api.mercadolibre.com"

DB_PADRAO = {"proximo_numero": 1, "sugestoes": [], "ofertas": [], "vistos": {}, "ultima_varredura": 0}


def carregar_cfg():
    return json.loads(CFG_PATH.read_text(encoding="utf-8"))


def carregar_db():
    db = json.loads(DB_PATH.read_text(encoding="utf-8")) if DB_PATH.exists() else {}
    for k, v in DB_PADRAO.items():
        db.setdefault(k, v if not isinstance(v, (list, dict)) else type(v)())
    return db


def salvar_db(db):
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = DB_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(db, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(DB_PATH)


CAMPOS_PUBLICOS = ("numero", "titulo", "titulo_curto", "preco", "original", "desconto", "foto", "link", "criado_em")


def exportar_vitrine(db, cfg):
    ativos = [{k: o.get(k) for k in CAMPOS_PUBLICOS} for o in db["ofertas"] if o.get("ativo")]
    VITRINE_PATH.write_text(json.dumps({"perfil": cfg.get("nome_perfil", ""), "ofertas": ativos},
                                       ensure_ascii=False), encoding="utf-8")


def brl(v):
    return f"R$ {v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def desconto(preco, original):
    return round((1 - preco / original) * 100) if original and original > preco else 0


def log(msg):
    print(msg, flush=True)


# ------------------------------------------------------------ Mercado Livre
class ML_API:
    """Cliente da API oficial. O refresh token do ML é de uso único:
    a cada renovação o token novo é gravado em NOVO_REFRESH_TOKEN (arquivo)
    para o workflow salvar de volta nos Secrets do GitHub."""

    def __init__(self):
        self.client_id = os.environ["ML_CLIENT_ID"]
        self.client_secret = os.environ["ML_CLIENT_SECRET"]
        self.refresh = os.environ["ML_REFRESH_TOKEN"]
        self.access = None

    def _renovar(self):
        r = requests.post(f"{ML}/oauth/token", timeout=30, headers={"accept": "application/json"},
                          data={"grant_type": "refresh_token", "refresh_token": self.refresh,
                                "client_id": self.client_id, "client_secret": self.client_secret})
        if r.status_code != 200:
            raise SystemExit(f"Falha ao renovar token do ML ({r.status_code}): {r.text[:300]}\n"
                             "Rode o workflow 'Autorizar Mercado Livre' de novo.")
        j = r.json()
        self.access = j["access_token"]
        self.refresh = j["refresh_token"]
        (RAIZ / "NOVO_REFRESH_TOKEN").write_text(self.refresh)

    def get(self, caminho):
        if not self.access:
            self._renovar()
        for tentativa in range(3):
            try:
                r = requests.get(ML + caminho, timeout=30,
                                 headers={"Authorization": f"Bearer {self.access}"})
            except requests.RequestException as e:
                log(f"  rede: {e}")
                time.sleep(2)
                continue
            if r.status_code == 401 and tentativa == 0:
                self._renovar()
                continue
            if r.status_code == 429:
                time.sleep(5)
                continue
            if r.status_code >= 400:
                self._registrar_erro(caminho, r)
                return None
            return r.json()
        return None

    erros_vistos = set()

    def _registrar_erro(self, caminho, r):
        """Mostra no log o primeiro erro de cada tipo de endpoint (para diagnóstico)."""
        tipo = caminho.split("/")[1] + ("/items" if caminho.endswith("/items") or "/items?" in caminho else "")
        chave = (tipo, r.status_code)
        if chave not in self.erros_vistos:
            self.erros_vistos.add(chave)
            log(f"  [API] {r.status_code} em /{tipo}: {r.text[:200]}")

    motivos = {}

    def _motivo(self, m):
        self.motivos[m] = self.motivos.get(m, 0) + 1
        return None

    def _preco_por_anuncios(self, prod_id):
        """Plano B: menor preço entre os anúncios ativos do produto de catálogo."""
        j = self.get(f"/products/{prod_id}/items?limit=10")
        itens = (j or {}).get("results") or []
        itens = [x for x in itens if x.get("price")]
        if not itens:
            return None
        x = min(itens, key=lambda x: x["price"])
        return x["price"], x.get("original_price")

    def detalhes(self, id_, tipo):
        """Título, preço, preço original, foto e URL de um produto (catálogo) ou anúncio."""
        if tipo in ("PRODUCT", None, ""):
            p = self.get(f"/products/{id_}")
            if p:
                bb = p.get("buy_box_winner") or {}
                preco, original = bb.get("price"), bb.get("original_price")
                if not preco:
                    alt = self._preco_por_anuncios(id_)
                    if not alt:
                        return self._motivo("produto sem preço")
                    preco, original = alt
                fotos = p.get("pictures") or [{}]
                return {"id": id_, "tipo": "PRODUCT", "titulo": p.get("name", ""),
                        "preco": preco, "original": original,
                        "foto": fotos[0].get("url") or fotos[0].get("secure_url"),
                        "url": p.get("permalink") or f"https://www.mercadolivre.com.br/p/{id_}"}
            if tipo == "PRODUCT":
                return self._motivo("produto inacessível")
        if tipo in ("ITEM", None, ""):
            i = self.get(f"/items/{id_}")
            if not i:
                return self._motivo("anúncio inacessível")
            if i.get("status") != "active":
                return self._motivo("anúncio inativo")
            fotos = i.get("pictures") or [{}]
            return {"id": id_, "tipo": "ITEM", "titulo": i.get("title", ""),
                    "preco": i.get("price"), "original": i.get("original_price"),
                    "foto": fotos[0].get("secure_url") or i.get("thumbnail"),
                    "url": i.get("permalink")}
        return self._motivo(f"tipo desconhecido: {tipo}")
