"""Roda no GitHub Actions (a cada 3h ou pelo botão "Varrer agora" do app).

1. Varre os "Mais vendidos" das categorias do config.json.
2. Calcula retorno estimado = preço x comissão e guarda os melhores em db.json -> "sugestoes".
3. Confere preço/estoque das ofertas que estão na vitrine e desativa as que saíram do ar.
"""
import time

from comum import ML_API, carregar_cfg, carregar_db, desconto, log, salvar_db


def varrer(ml, cfg, db):
    agora = time.time()
    repetir = agora - cfg.get("dias_para_repetir", 7) * 86400
    db["vistos"] = {k: v for k, v in db["vistos"].items() if v > agora - 30 * 86400}
    # sugestões velhas que você não respondeu saem da lista
    db["sugestoes"] = [s for s in db["sugestoes"]
                       if s.get("sugerido_em", agora) > agora - cfg.get("sugestao_expira_dias", 2) * 86400]
    ja_listados = {s["id"] for s in db["sugestoes"]} | {o["id"] for o in db["ofertas"] if o.get("ativo")}

    candidatos, vistos_agora = [], set()
    for cat_id, info in cfg["categorias"].items():
        h = ml.get(f"/highlights/MLB/category/{cat_id}")
        itens = (h or {}).get("content", [])
        tipos = sorted({str(c.get("type")) for c in itens})
        log(f"{info['nome']}: {len(itens)} mais vendidos (tipos: {', '.join(tipos) or '-'})")
        for pos, c in enumerate(itens, 1):
            cid = c.get("id")
            if (not cid or cid in vistos_agora or cid in ja_listados
                    or db["vistos"].get(cid, 0) > repetir):
                continue
            vistos_agora.add(cid)
            d = ml.detalhes(cid, c.get("type"))
            time.sleep(0.15)
            if not d or not d.get("preco"):
                continue
            ml.motivos["lido com sucesso"] = ml.motivos.get("lido com sucesso", 0) + 1
            d.update(categoria=info["nome"], comissao=info["comissao"], posicao=pos,
                     retorno=round(d["preco"] * info["comissao"], 2),
                     desconto=desconto(d["preco"], d.get("original")), sugerido_em=agora)
            if d["retorno"] < cfg.get("min_retorno_reais", 0):
                ml.motivos["retorno abaixo do mínimo"] = ml.motivos.get("retorno abaixo do mínimo", 0) + 1
            elif d["desconto"] < cfg.get("min_desconto_pct", 0):
                ml.motivos["desconto abaixo do mínimo"] = ml.motivos.get("desconto abaixo do mínimo", 0) + 1
            else:
                candidatos.append(d)

    log("Diagnóstico: " + (", ".join(f"{k}: {v}" for k, v in ml.motivos.items()) or "nenhum item analisado"))
    candidatos.sort(key=lambda d: d["retorno"], reverse=True)
    novos = candidatos[:cfg.get("max_sugestoes_por_varredura", 10)]
    for d in novos:
        db["vistos"][d["id"]] = agora
    db["sugestoes"] = sorted(db["sugestoes"] + novos, key=lambda d: d["retorno"], reverse=True)
    log(f"{len(novos)} sugestões novas ({len(candidatos)} passaram no filtro).")


def conferir_vitrine(ml, cfg, db):
    validade = time.time() - cfg.get("oferta_valida_dias", 15) * 86400
    for of in db["ofertas"]:
        if not of.get("ativo"):
            continue
        if of.get("criado_em", 0) < validade:
            of["ativo"] = False
            of["motivo"] = "expirou"
            continue
        atual = ml.detalhes(of["id"], of["tipo"])
        time.sleep(0.15)
        if not atual:
            of["ativo"], of["motivo"] = False, "saiu do ar"
            log(f"#{of['numero']} saiu do ar")
            continue
        subiu = atual["preco"] > of["preco_postado"] * (1 + cfg.get("tolerancia_aumento_pct", 10) / 100)
        of["preco"], of["original"] = atual["preco"], atual.get("original")
        of["desconto"] = desconto(of["preco"], of["original"])
        if subiu:
            of["ativo"], of["motivo"] = False, "preço subiu"
            log(f"#{of['numero']} preço subiu, saiu da vitrine")


def main():
    cfg = carregar_cfg()
    db = carregar_db()
    ml = ML_API()
    varrer(ml, cfg, db)
    conferir_vitrine(ml, cfg, db)
    db["ultima_varredura"] = time.time()
    salvar_db(db)


if __name__ == "__main__":
    main()
