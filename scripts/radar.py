"""Roda no GitHub Actions (a cada 3h ou pelo botão "Varrer agora" do app).

1. Varre os "Mais vendidos" das categorias do config.json.
2. Calcula retorno estimado = preço x comissão e guarda os melhores em db.json -> "sugestoes".
3. Confere preço/estoque das ofertas que estão na vitrine e desativa as que saíram do ar.
"""
import time
import unicodedata

from comum import ML_API, carregar_cfg, carregar_db, desconto, log, salvar_db


def normalizar(txt):
    txt = unicodedata.normalize("NFKD", txt).encode("ascii", "ignore").decode().lower()
    return " ".join(txt.replace(",", " ").split())


def resolver_categorias(ml, cfg):
    """Converte {"nome da categoria": comissão} em {ID: {nome, comissao}} usando a API do ML."""
    if cfg.get("categorias"):  # formato antigo com IDs, ainda aceito
        return cfg["categorias"]
    lista = ml.get("/sites/MLB/categories") or []
    por_nome = {normalizar(c["name"]): c for c in lista}
    resultado = {}
    for nome, comissao in cfg.get("comissoes", {}).items():
        if not comissao:
            continue
        c = por_nome.get(normalizar(nome))
        if not c:
            log(f"Categoria não encontrada no ML: '{nome}' (confira o nome no config.json)")
            continue
        resultado[c["id"]] = {"nome": c["name"], "comissao": comissao}
    log(f"{len(resultado)} categorias ativas.")
    return resultado


def nota(d, cfg):
    """Pontuação de 0 a 100 que equilibra quanto você ganha, o quanto chama atenção e o quanto já vende."""
    p = cfg.get("pontuacao", {})
    ret = min(d["retorno"] / p.get("retorno_referencia", 40), 1)
    desc = min(d["desconto"] / p.get("desconto_referencia", 50), 1)
    pop = max(0, (21 - d["posicao"]) / 20)
    total = (p.get("peso_retorno", 0.4) * ret + p.get("peso_desconto", 0.3) * desc
             + p.get("peso_popularidade", 0.3) * pop)
    faixa = p.get("faixa_preco", [30, 500])
    if not faixa[0] <= d["preco"] <= faixa[1]:
        total *= p.get("penalidade_fora_faixa", 0.6)
    return round(total * 100)


def varrer(ml, cfg, db):
    agora = time.time()
    repetir = agora - cfg.get("dias_para_repetir", 7) * 86400
    db["vistos"] = {k: v for k, v in db["vistos"].items() if v > agora - 30 * 86400}
    # sugestões velhas que você não respondeu saem da lista
    db["sugestoes"] = [s for s in db["sugestoes"]
                       if s.get("sugerido_em", agora) > agora - cfg.get("sugestao_expira_dias", 2) * 86400]
    ja_listados = {s["id"] for s in db["sugestoes"]} | {o["id"] for o in db["ofertas"] if o.get("ativo")}

    candidatos, vistos_agora = [], set()
    for cat_id, info in resolver_categorias(ml, cfg).items():
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
    for d in candidatos:
        d["nota"] = nota(d, cfg)
    candidatos.sort(key=lambda d: d["nota"], reverse=True)

    # no máximo N por categoria, para variar os nichos
    limite_cat = cfg.get("max_por_categoria", 2)
    por_cat, novos = {}, []
    for d in candidatos:
        if por_cat.get(d["categoria"], 0) >= limite_cat:
            continue
        por_cat[d["categoria"]] = por_cat.get(d["categoria"], 0) + 1
        novos.append(d)
        if len(novos) >= cfg.get("max_sugestoes_por_varredura", 20):
            break

    for d in novos:
        db["vistos"][d["id"]] = agora
    db["sugestoes"] = sorted(db["sugestoes"] + novos, key=lambda d: d.get("nota", 0), reverse=True)
    log(f"{len(novos)} sugestões novas ({len(candidatos)} passaram no filtro). "
        "Por categoria: " + ", ".join(f"{k} {v}" for k, v in por_cat.items()))


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
