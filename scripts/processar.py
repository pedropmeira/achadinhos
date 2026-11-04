"""Aplica as ações que o app do celular deixou em data/acoes/ (um arquivo por toque).

Um arquivo por ação = o app e os robôs nunca brigam pelo mesmo arquivo.
Ações: aprovar, pular, postado, remover, varrer.
"""
import json
import os
import time

from comum import RAIZ, carregar_db, log, salvar_db

ACOES = RAIZ / "data" / "acoes"


def main():
    db = carregar_db()
    varrer = os.environ.get("EVENTO") in ("schedule", "workflow_dispatch")
    arquivos = sorted(ACOES.glob("*.json")) if ACOES.exists() else []
    for arq in arquivos:
        try:
            a = json.loads(arq.read_text(encoding="utf-8"))
        except ValueError:
            arq.unlink()
            continue
        tipo = a.get("acao")
        if tipo == "varrer":
            varrer = True
        elif tipo in ("aprovar", "pular"):
            sug = next((s for s in db["sugestoes"] if s["id"] == a.get("id")), None)
            db["sugestoes"] = [s for s in db["sugestoes"] if s["id"] != a.get("id")]
            if tipo == "aprovar" and sug and a.get("link"):
                of = {**sug, "numero": db["proximo_numero"], "link": a["link"].strip(),
                      "preco_postado": sug["preco"], "criado_em": time.time(),
                      "ativo": True, "postado": False, "video": None}
                if a.get("titulo_curto"):
                    of["titulo_curto"] = a["titulo_curto"].strip()[:70]
                db["ofertas"].insert(0, of)
                db["proximo_numero"] += 1
                log(f"Aprovado #{of['numero']}: {of['titulo'][:50]}")
        elif tipo in ("postado", "remover"):
            for of in db["ofertas"]:
                if of["numero"] == a.get("numero"):
                    if tipo == "postado":
                        of["postado"] = True
                    else:
                        of["ativo"], of["motivo"] = False, "removido por você"
        arq.unlink()

    # histórico enxuto: mantém só as últimas 300 ofertas
    db["ofertas"] = db["ofertas"][:300]
    salvar_db(db)
    log(f"{len(arquivos)} ação(ões) aplicadas.")
    if os.environ.get("GITHUB_OUTPUT"):
        with open(os.environ["GITHUB_OUTPUT"], "a") as f:
            f.write(f"varrer={'true' if varrer else 'false'}\n")


if __name__ == "__main__":
    main()
