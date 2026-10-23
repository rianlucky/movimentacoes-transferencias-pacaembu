"""Cálculos do painel Movimentações — sem Streamlit, usados pelo app.py e pela validação
(_neon/validacao/validar_paineis.py).

Fontes (Neon, migrações 032/033):
  core.v_movimentacoes_base         um evento do histórico de movimentação (Oracle 00024) por linha
  core.v_movimentacoes_cargo_ativo  ativos de hoje por cargo/diretoria/área/categoria/nível + mediana do cargo

Classificação: regra de negócio V3 (18/09/2026, decisão do Rian, mantida em 23/10/2026) — ver CONTEXT.md.
Todo evento cai num balde; "Movimentações" = Promoção + Aumentos Salariais + Transferências. Acordo
Coletivo fica fora (Descartado) e o ambíguo entre Acordo Coletivo e Mérito fica visível à parte (A revisar).
"""
from __future__ import annotations

from datetime import date

import pandas as pd

NAO_INFORMADO = "Não informado"

# ── Classificação (V2 de 17/09/2026, regras derivadas dos dados brutos e validadas contra a curadoria
# manual `movimentacao_verificado`) ─────────────────────────────────────────────────────────────────
MOTIVOS_NUCLEO_TRIVIAL = {
    "MÉRITO": "Mérito",
    "ENQUADRAMENTO": "Enquadramento",
    "EQUIPARAÇÃO SALARIAL": "Equiparação Salarial",
    "RECLASSIFICAÇÃO": "Reclassificação",
    "ESPONTÂNEO": "Espontâneo",
    "AUMENTO DE CARGA HORÁRIA": "Aumento de Carga Horária",
}
MOTIVO_ADMISSAO = "ADMISSÃO DE NOVO COLABORADOR"

# Decisão do Rian, 24/09/2026: motivo já diz "Promoção" (orçada ou não) — vira Promoção direto, mesmo
# quando o texto do cargo anterior e atual vem igual na fonte (falha de captura, não ausência de promoção:
# a amostra tinha reajustes de 22% a 57%).
MOTIVOS_PROMOCAO_EXPLICITA = {"PROMOÇÃO", "PROMOÇÃO ORÇADA", "PROMOÇÃO NÃO ORÇADA"}

TIPOS_AUMENTO = ["Promoção", "Mérito", "Enquadramento", "Equiparação Salarial", "Alteração de Cargo"]
MOTIVOS_AUMENTO = ["Mérito", "Promoção", "Enquadramento", "Equiparação Salarial", "Alteração de Cargo", "Reclassificação"]

# ── Regra V3 (18/09/2026): 3 baldes que somam "Movimentações" ──────────────────────────────────────
NUCLEOS_AUMENTO_SALARIAL = ["Mérito", "Enquadramento", "Equiparação Salarial", "Reclassificação", "Espontâneo",
                            "Aumento de Carga Horária"]
BALDES_MOVIMENTACAO = ["Promoção", "Aumentos Salariais", "Transferências"]
A_REVISAR = "A revisar"
DESCARTADO = "Descartado"

# Cargo não mudou mas o % passa disso: dado suspeito (ex.: Presidente com salário anterior de R$ 998).
# Sai dos gráficos de % e R$, continua no detalhamento marcado.
LIMITE_ABSURDO_PCT = 100.0

# % de reajuste que se repete entre pelo menos N pessoas (cargo igual, motivo genérico) = lote de
# Acordo Coletivo, não Mérito individual.
LIMITE_LOTE_REPETICOES = 3

# Decisão do Rian, 24/09/2026: CC/local/departamento com cargo igual e reajuste ≤ 10% = efeito da tabela
# salarial da mudança de local → Transferência pura (não entra no ambíguo Acordo Coletivo/Mérito).
MOTIVOS_TRANSFERENCIA_SALARIO = {"ALTERAÇÃO DE CENTRO DE CUSTO", "TRANSFERÊNCIA DE LOCAL", "TRANSFERÊNCIA DE DEPARTAMENTO"}
LIMITE_TRANSFERENCIA_PURA_PCT = 10.0

# Calendário de Convenção Coletiva por localidade (17/09/2026, informado pelo Rian) — só desempata
# Acordo Coletivo × Mérito quando o motivo não diz. MS ainda sem cidade confirmada.
_SP_HINTS = (
    "SAO_PAULO", "RIO_PRETO", "ARARAQUARA", "RIBEIRAO_PRETO", "BAURU", "CATANDUVA",
    "ITAPETININGA", "LEME", "TATUI", "BOTUCATU", "PIRATININGA", "BALSAMO",
    "PRESIDENTE_PRUDENTE", "VOTUPORANGA", "ARACATUBA", "TAUBATE", "LINS", "AVARE", "BADY_BASSITT",
)
_MT_HINTS = ("CUIABA", "PRIMAVERA_DO_LESTE", "SINOP", "LUCAS_RIO_VERDE", "SORRISO", "MARILANDIA")
_PR_HINTS = ("LONDRINA", "ARAPONGAS", "CIANORTE", "PONTA_GROSSA", "PALOTINA", "CHATEAUBRIAND")
_MS_HINTS: tuple[str, ...] = ()
_DF_HINTS = ("BRASILIA",)
_MG_HINTS = ("ITUIUTABA", "UBERLANDIA")
_CALENDARIO_CC = {
    "SP": ("05", "06"), "MT": ("05", "06", "07"), "PR": ("06", "07"),
    "MS": ("11", "12"), "DF": ("05", "06"), "MG": ("09", "10"),
}


def _uf_provavel(descricao_local: str | None) -> str | None:
    if not descricao_local:
        return None
    loc = descricao_local.upper()
    if "CHATEAUBRIAND" in loc:
        return "PR"  # Assis Chateaubriand é Paraná — checar ANTES de "ASSIS" (Assis, SP)
    if "ASSIS" in loc or any(h in loc for h in _SP_HINTS):
        return "SP"
    for uf, hints in (("MT", _MT_HINTS), ("PR", _PR_HINTS), ("MS", _MS_HINTS), ("DF", _DF_HINTS), ("MG", _MG_HINTS)):
        if any(h in loc for h in hints):
            return uf
    return None


def _bate_calendario_cc(descricao_local: str | None, mes_data_efetiva: str | None) -> bool:
    meses = _CALENDARIO_CC.get(_uf_provavel(descricao_local))
    return bool(meses) and mes_data_efetiva in meses


def _mudou(anterior: pd.Series, atual: pd.Series) -> pd.Series:
    """True quando os dois valores diferem; nulo com nulo = não mudou (IS DISTINCT FROM do Postgres)."""
    ambos_nulos = anterior.isna() & atual.isna()
    iguais = (anterior == atual).fillna(False)
    return ~(ambos_nulos | iguais)


def classificar(df: pd.DataFrame) -> pd.DataFrame:
    """Regra V3. Roda na base INTEIRA (a assinatura de lote conta repetições de % entre todas as pessoas),
    nunca no recorte filtrado."""
    motivo = df["motivo"].fillna("").str.upper()
    cargo_mudou = _mudou(df["descricao_cargo_anterior"], df["descricao_cargo_atual"])
    cc_mudou = _mudou(df["centro_custo_anterior"], df["centro_custo_atual"])
    salario_mudou = _mudou(df["salario_anterior"], df["salario_atual"])

    nucleo = pd.Series(pd.NA, index=df.index, dtype="object")
    nucleo[motivo.str.contains("CONVENÇÃO COLETIVA", na=False)] = "Acordo Coletivo"
    for motivo_bruto, rotulo in MOTIVOS_NUCLEO_TRIVIAL.items():
        nucleo[motivo == motivo_bruto] = rotulo
    nucleo[motivo == MOTIVO_ADMISSAO] = "Admissão"
    nucleo[motivo.isin(MOTIVOS_PROMOCAO_EXPLICITA)] = "Promoção"

    restante = nucleo.isna()
    nucleo[restante & cargo_mudou & salario_mudou] = "Promoção"
    nucleo[restante & cargo_mudou & ~salario_mudou] = "Alteração de Cargo"

    ambiguo = restante & ~cargo_mudou & salario_mudou
    transferencia_pura = (ambiguo & motivo.isin(MOTIVOS_TRANSFERENCIA_SALARIO)
                          & (df["percentual_reajuste"].abs() <= LIMITE_TRANSFERENCIA_PURA_PCT))
    ambiguo = ambiguo & ~transferencia_pura

    # Sinal principal: % que se repete entre várias pessoas (lote aplicado por obra/frente).
    # Sinal secundário: calendário de Convenção Coletiva da localidade. Qualquer um basta.
    pct_ambiguo = df.loc[ambiguo, "percentual_reajuste"].round(2)
    repeticoes = pct_ambiguo.value_counts()
    bate_lote = pct_ambiguo.map(lambda v: repeticoes.get(v, 0) >= LIMITE_LOTE_REPETICOES if pd.notna(v) else False)
    bate_calendario = pd.Series(
        [_bate_calendario_cc(loc, mes) for loc, mes in zip(df.loc[ambiguo, "descricao_local"], df.loc[ambiguo, "mes_numero"])],
        index=df.index[ambiguo], dtype=bool,
    )
    acordo = bate_lote.reindex(df.index[ambiguo], fill_value=False).astype(bool) | bate_calendario
    nucleo.loc[acordo[acordo].index] = "Acordo Coletivo"
    nucleo.loc[acordo[~acordo].index] = "A revisar (Acordo Coletivo ou Mérito)"

    df = df.copy()
    df["cargo_mudou"], df["cc_mudou"], df["salario_mudou"] = cargo_mudou, cc_mudou, salario_mudou
    df["nucleo_movimentacao"] = nucleo

    # Balde final (V3):
    #   Promoção (com ou sem transferência junto)      -> Promoção
    #   Mérito/Enquadramento/Equiparação/...           -> Aumentos Salariais
    #   Transferência pura ou + Alteração de Cargo      -> Transferências
    #   Acordo Coletivo (mesmo com transferência)      -> Descartado (fora de tudo)
    #   Ambíguo não resolvido                          -> A revisar (fora do total, visível)
    #   Alteração de Cargo pura (sem CC, sem salário)   -> Alteração de Cargo (sem card)
    balde = pd.Series(pd.NA, index=df.index, dtype="object")
    balde[nucleo == "Promoção"] = "Promoção"
    balde[nucleo.isin(NUCLEOS_AUMENTO_SALARIAL)] = "Aumentos Salariais"
    balde[nucleo == "Acordo Coletivo"] = DESCARTADO
    balde[nucleo == "A revisar (Acordo Coletivo ou Mérito)"] = A_REVISAR
    balde[nucleo == "Admissão"] = "Admissão"
    resta = balde.isna()
    balde[resta & cc_mudou] = "Transferências"
    balde[resta & ~cc_mudou & (nucleo == "Alteração de Cargo")] = "Alteração de Cargo (sem card)"
    balde[resta & ~cc_mudou & nucleo.isna()] = "Sem evento"
    df["balde"] = balde

    tem_nucleo = nucleo.notna()
    tipo = pd.Series("Sem evento", index=df.index, dtype="object")
    tipo[cc_mudou & tem_nucleo] = "Transferência + " + nucleo[cc_mudou & tem_nucleo]
    tipo[cc_mudou & ~tem_nucleo] = "Transferência"
    tipo[~cc_mudou & tem_nucleo] = nucleo[~cc_mudou & tem_nucleo]
    df["tipo_movimentacao"] = tipo

    pct = df["percentual_reajuste"]
    df["alerta_absurdo"] = (~cargo_mudou) & pct.notna() & (pct.abs() > LIMITE_ABSURDO_PCT)
    return df


def _categoria(s: pd.Series) -> pd.Series:
    """Eventos vêm em CAIXA ALTA ("OBRAS"), ativos não ("Obras"): mesma grafia para o filtro casar."""
    return s.fillna(NAO_INFORMADO).str.strip().str.capitalize().replace({"Não informado": NAO_INFORMADO})


def preparar(base: pd.DataFrame) -> pd.DataFrame:
    """core.v_movimentacoes_base → eventos classificados (sem os "Sem evento")."""
    df = base.copy()
    for c in ("salario_anterior", "salario_atual"):
        df[c] = pd.to_numeric(df[c], errors="coerce")
    # % sobre o salário ANTERIOR (convenção de RH; o `percentual` da fonte é sobre o novo — 18/09/2026)
    df["valor_reajuste"] = df["salario_atual"] - df["salario_anterior"]
    df["percentual_reajuste"] = df["valor_reajuste"] / df["salario_anterior"] * 100
    df["data_efetiva"] = pd.to_datetime(df["data_efetiva"], errors="coerce")
    df["data_admissao"] = pd.to_datetime(df["data_admissao"], errors="coerce")
    df = df.dropna(subset=["data_efetiva"])
    df["mes"] = df["data_efetiva"].dt.to_period("M").dt.to_timestamp()
    df["mes_numero"] = df["data_efetiva"].dt.strftime("%m")
    df["categoria_atribuicao"] = _categoria(df["categoria_atribuicao"])
    for c in ("diretoria", "area", "gerenciamento_nivel_cargo", "descricao_cargo_atual"):
        df[c] = df[c].fillna(NAO_INFORMADO)
    df["pessoa_ativa_hoje"] = df["pessoa_ativa_hoje"].fillna(False).astype(bool)
    df = classificar(df)
    return df[df["tipo_movimentacao"] != "Sem evento"].reset_index(drop=True)


def preparar_ativos(ativos: pd.DataFrame) -> pd.DataFrame:
    df = ativos.copy()
    df["categoria_atribuicao"] = _categoria(df["categoria_atribuicao"])
    df["ativos"] = pd.to_numeric(df["ativos"]).astype(int)
    df["mediana_salario_cargo"] = pd.to_numeric(df["mediana_salario_cargo"], errors="coerce")
    for c in ("diretoria", "area", "gerenciamento_nivel_cargo", "descricao_cargo"):
        df[c] = df[c].fillna(NAO_INFORMADO)
    return df


# ── período ─────────────────────────────────────────────────────────────────────────────────────────
def data_referencia(df: pd.DataFrame) -> date:
    return df["data_efetiva"].max().date()


def inicio_padrao(ref: date) -> date:
    """Dia 1 do mesmo mês do ano anterior (padrão da Central)."""
    return date(ref.year - 1, ref.month, 1)


def no_periodo(df: pd.DataFrame, ini: date, fim: date) -> pd.DataFrame:
    return df[(df["data_efetiva"] >= pd.Timestamp(ini)) & (df["data_efetiva"] <= pd.Timestamp(fim))]


def meses(ini: date, fim: date) -> pd.DatetimeIndex:
    return pd.date_range(pd.Timestamp(ini).to_period("M").to_timestamp(), pd.Timestamp(fim).to_period("M").to_timestamp(), freq="MS")


def mes_atual_e_anterior(df: pd.DataFrame, ref: date) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Mês de `ref` (até o dia de ref) e o mês anterior inteiro."""
    ini = pd.Timestamp(ref).to_period("M").to_timestamp()
    ant = ini - pd.DateOffset(months=1)
    atual = df[(df["data_efetiva"] >= ini) & (df["data_efetiva"] <= pd.Timestamp(ref))]
    anterior = df[(df["data_efetiva"] >= ant) & (df["data_efetiva"] < ini)]
    return atual, anterior


# ── aba Movimentações (V3) ──────────────────────────────────────────────────────────────────────────
def movimentacoes(df: pd.DataFrame) -> pd.DataFrame:
    """Só os 3 baldes que compõem "Movimentações"."""
    return df[df["balde"].isin(BALDES_MOVIMENTACAO)]


def totais(df: pd.DataFrame) -> dict:
    n = df["balde"].value_counts()
    t = {b: int(n.get(b, 0)) for b in BALDES_MOVIMENTACAO}
    t["Movimentações"] = sum(t[b] for b in BALDES_MOVIMENTACAO)
    t[A_REVISAR] = int(n.get(A_REVISAR, 0))
    t[DESCARTADO] = int(n.get(DESCARTADO, 0))
    return t


def evolucao_baldes(df: pd.DataFrame, ini: date, fim: date) -> tuple[pd.DataFrame, pd.DataFrame]:
    """(mes, balde, qtd) com zeros nos meses sem evento + (mes, total, acumulado)."""
    mov = movimentacoes(no_periodo(df, ini, fim))
    grade = pd.MultiIndex.from_product([meses(ini, fim), BALDES_MOVIMENTACAO], names=["mes", "balde"])
    por = mov.groupby(["mes", "balde"]).size().reindex(grade, fill_value=0).rename("qtd").reset_index()
    tot = por.groupby("mes", as_index=False)["qtd"].sum().rename(columns={"qtd": "total"})
    tot["acumulado"] = tot["total"].cumsum()
    return por, tot


def contagem(df: pd.DataFrame, campo: str, ordem: list[str] | None = None) -> pd.DataFrame:
    t = df.groupby(campo).size().rename("qtd").reset_index()
    if ordem:
        t = t.set_index(campo).reindex([o for o in ordem if o in set(t[campo])]).reset_index()
    else:
        t = t.sort_values("qtd", ascending=False)
    return t.reset_index(drop=True)


def headcount(ativos: pd.DataFrame) -> int:
    return int(ativos["ativos"].sum())


def taxa_movimentacao(df: pd.DataFrame, ativos: pd.DataFrame) -> float | None:
    """Pessoas distintas com movimentação (3 baldes) ÷ ativos de hoje no mesmo filtro."""
    hc = headcount(ativos)
    return movimentacoes(df)["id_funcionario"].nunique() / hc if hc else None


def cargos_sem_movimentacao(df: pd.DataFrame, ativos: pd.DataFrame) -> int:
    return len(set(ativos["descricao_cargo"]) - set(movimentacoes(df)["descricao_cargo_atual"]))


def pessoas_por_tipo(df: pd.DataFrame) -> pd.DataFrame:
    """Pessoas distintas com ao menos um evento de cada tipo (não é sequência no tempo)."""
    mov = movimentacoes(df)
    linhas = [("Qualquer movimentação", mov["id_funcionario"].nunique()),
              ("Mérito", mov.loc[mov["nucleo_movimentacao"] == "Mérito", "id_funcionario"].nunique()),
              ("Promoção", mov.loc[mov["nucleo_movimentacao"] == "Promoção", "id_funcionario"].nunique()),
              ("Transferência", mov.loc[mov["cc_mudou"], "id_funcionario"].nunique())]
    return pd.DataFrame(linhas, columns=["tipo", "pessoas"])


def cargos_menos_reconhecidos(df: pd.DataFrame, ativos: pd.DataFrame, minimo_ativos: int = 3, n: int = 20) -> pd.DataFrame:
    """Cargos com pelo menos `minimo_ativos` ativos hoje e menos aumentos no período."""
    aum = df[df["nucleo_movimentacao"].isin(MOTIVOS_AUMENTO)].groupby("descricao_cargo_atual").size()
    t = ativos.groupby("descricao_cargo")["ativos"].sum().rename("ativos").to_frame()
    t["aumentos"] = aum.reindex(t.index).fillna(0).astype(int)
    t = t[t["ativos"] >= minimo_ativos].sort_values(["aumentos", "ativos"], ascending=[True, False])
    return t.head(n).reset_index().rename(columns={"descricao_cargo": "cargo"})


# ── aba Aumentos Salariais ──────────────────────────────────────────────────────────────────────────
def aumentos(df: pd.DataFrame, tipos: list[str]) -> tuple[pd.DataFrame, pd.DataFrame]:
    """(todos os eventos dos tipos escolhidos, os mesmos sem os % implausíveis)."""
    bruto = df[df["nucleo_movimentacao"].isin(tipos)]
    return bruto, bruto[~bruto["alerta_absurdo"]]


def resumo_por(df: pd.DataFrame, campo: str) -> pd.DataFrame:
    """Quantidade, % médio e R$ médio de aumento por `campo`."""
    return (df.groupby(campo, as_index=False)
              .agg(qtd=("id_historico_movimentacao", "size"), pct_medio=("percentual_reajuste", "mean"),
                   valor_medio=("valor_reajuste", "mean"))
              .sort_values("qtd", ascending=False).reset_index(drop=True))


def evolucao_pct(df: pd.DataFrame) -> pd.DataFrame:
    return df.groupby(["mes", "nucleo_movimentacao"], as_index=False)["percentual_reajuste"].mean()


def primeira_promocao(df_sem_periodo: pd.DataFrame, ini: date, fim: date) -> pd.DataFrame:
    """Primeira promoção de cada pessoa em TODO o histórico; ficam as que caem no período.
    (O painel antigo pegava a primeira dentro do período, o que contava a 2ª/3ª promoção como 1ª.)"""
    promo = df_sem_periodo[(df_sem_periodo["nucleo_movimentacao"] == "Promoção") & df_sem_periodo["data_admissao"].notna()]
    if promo.empty:
        return promo.assign(meses_ate_promocao=pd.Series(dtype=float))
    p = promo.sort_values("data_efetiva").groupby("id_funcionario", as_index=False).first()
    p["meses_ate_promocao"] = ((p["data_efetiva"].dt.year - p["data_admissao"].dt.year) * 12
                               + (p["data_efetiva"].dt.month - p["data_admissao"].dt.month))
    p = p[p["meses_ate_promocao"] >= 0]
    return no_periodo(p, ini, fim)


def compressao(df: pd.DataFrame, ativos: pd.DataFrame) -> dict:
    """Novo salário dos promovidos × mediana de quem está ativo hoje no cargo de destino (cargo inteiro)."""
    prom = df[(df["nucleo_movimentacao"] == "Promoção") & df["salario_atual"].notna()]
    mediana = ativos.drop_duplicates("descricao_cargo").set_index("descricao_cargo")["mediana_salario_cargo"]
    comp = prom.assign(mediana=prom["descricao_cargo_atual"].map(mediana)).dropna(subset=["mediana"])
    comp = comp[comp["mediana"] > 0]
    pos = comp["salario_atual"] / comp["mediana"]
    return {"promovidos": len(prom), "comparaveis": len(comp), "sem_comparavel": len(prom) - len(comp),
            "abaixo_mediana": (pos < 1).mean() if len(comp) else None,
            "posicao_mediana": pos.median() if len(comp) else None}


# ── aba Transferências ──────────────────────────────────────────────────────────────────────────────
def transferencias(df: pd.DataFrame) -> pd.DataFrame:
    """Qualquer mudança de centro de custo, mesmo junto de Promoção/Mérito/Acordo Coletivo."""
    return df[df["cc_mudou"]]


def resumo_transferencias(tr: pd.DataFrame, ativos: pd.DataFrame) -> dict:
    hc = headcount(ativos)
    pessoas = tr["id_funcionario"].nunique()
    return {"eventos": len(tr), "pessoas": pessoas, "pct_transferidos": pessoas / hc if hc else None,
            "efetividade": tr.drop_duplicates("id_funcionario")["pessoa_ativa_hoje"].mean() if pessoas else None}
