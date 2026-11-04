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
            if r.status_code in (403, 404):
                return None
            r.raise_for_status()
            return r.json()
        return None

    def detalhes(self, id_, tipo):
        """Título, preço, preço original, foto e URL de um produto (catálogo) ou anúncio."""
        if tipo == "PRODUCT":
            p = self.get(f"/products/{id_}")
            if not p:
                return None
            bb = p.get("buy_box_winner") or {}
            if not bb.get("price"):
                return None
            fotos = p.get("pictures") or [{}]
            return {"id": id_, "tipo": tipo, "titulo": p.get("name", ""),
                    "preco": bb["price"], "original": bb.get("original_price"),
                    "foto": fotos[0].get("url"),
                    "url": p.get("permalink") or f"https://www.mercadolivre.com.br/p/{id_}"}
        if tipo == "ITEM":
            i = self.get(f"/items/{id_}")
            if not i or i.get("status") != "active":
                return None
            fotos = i.get("pictures") or [{}]
            return {"id": id_, "tipo": tipo, "titulo": i.get("title", ""),
                    "preco": i.get("price"), "original": i.get("original_price"),
                    "foto": fotos[0].get("secure_url") or i.get("thumbnail"),
                    "url": i.get("permalink")}
        return None
