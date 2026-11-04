"""Troca o 'code' da autorização do Mercado Livre por um refresh token (uso: workflow Autorizar)."""
import os
import sys

import requests

from comum import ML, RAIZ, carregar_cfg

code = os.environ.get("ML_CODE", "").strip()
if "code=" in code:  # aceita a URL inteira colada
    code = code.split("code=", 1)[1].split("&", 1)[0]
if not code:
    sys.exit("Informe o code.")

r = requests.post(f"{ML}/oauth/token", timeout=30, headers={"accept": "application/json"},
                  data={"grant_type": "authorization_code", "code": code,
                        "client_id": os.environ["ML_CLIENT_ID"],
                        "client_secret": os.environ["ML_CLIENT_SECRET"],
                        "redirect_uri": carregar_cfg()["ml_redirect_uri"]})
if r.status_code != 200:
    sys.exit(f"Erro {r.status_code}: {r.text[:300]}\nO code vale poucos minutos e só uma vez: gere outro.")
(RAIZ / "NOVO_REFRESH_TOKEN").write_text(r.json()["refresh_token"])
print("Autorizado! Token salvo.")
