"""Painel Movimentações — promoções, aumentos salariais e transferências (Pacaembu Construtora).

Três páginas na barra lateral:
  Visão geral          totais da regra V3 (Promoção + Aumentos Salariais + Transferências), taxa, onde acontecem
  Aumentos salariais   % e R$ de aumento por tipo, diretoria e nível; 1ª promoção; compressão salarial
  Transferências       qualquer mudança de centro de custo
Fonte: core.v_movimentacoes_base e core.v_movimentacoes_cargo_ativo no Neon (usuário de banco só de leitura),
carregadas pelo sync central (Oracle HCM, relatório 00024). Cálculos em metricas.py.

    streamlit run app.py
"""
from __future__ import annotations

import io
import json
from datetime import date, datetime
from pathlib import Path

import pandas as pd
import psycopg2
import streamlit as st

import auth
import metricas as m
import painel_padrao as pp

ASSETS = Path(__file__).resolve().parent / "assets"

AZUL, AMARELO, VERMELHO, VERDE = "#064D66", "#FAB900", "#F02727", "#22C55E"
CINZA, CINZA_ESCURO, AZUL_CLARO = "#6B7280", "#1F2937", "#8FB8C8"
CORES_BALDE = {"Promoção": AMARELO, "Aumentos Salariais": AZUL, "Transferências": AZUL_CLARO}
CORES_TIPO = {"Promoção": AMARELO, "Mérito": AZUL, "Enquadramento": "#2FA4C7", "Equiparação Salarial": AZUL_CLARO,
              "Alteração de Cargo": VERMELHO}
SEM_DADOS = "Sem movimentações no filtro selecionado."

st.set_page_config(page_title="Movimentações · Pacaembu Construtora", page_icon=str(ASSETS / "icone-movimentacoes.png"),
                   layout="wide")

# login antes de qualquer dado (mesma tabela acesso.app_users dos outros painéis)
auth.exigir_login()
auth.exigir_acesso_ao_painel("movimentacoes")  # matriz de acessos (acesso.v_permissoes)


# ----------------------------------------------------------------------------- dados

@st.cache_data(ttl=600, show_spinner="Carregando dados…")
def carregar() -> tuple[pd.DataFrame, pd.DataFrame, datetime | None]:
    with psycopg2.connect(st.secrets["neon"]["database_url"], connect_timeout=10) as conn, conn.cursor() as cur:
        cur.execute("SELECT * FROM core.v_movimentacoes_base")
        base = pd.DataFrame(cur.fetchall(), columns=[d[0] for d in cur.description])
        cur.execute("SELECT * FROM core.v_movimentacoes_cargo_ativo")
        ativos = pd.DataFrame(cur.fetchall(), columns=[d[0] for d in cur.description])
        cur.execute("SELECT max(concluido_em) FROM ops.v_ultima_carga "
                    "WHERE schema_nome = 'core' AND tabela = 'oracle_hcm_historico_movimentacao'")
        carga = cur.fetchone()[0]
    return m.preparar(base), m.preparar_ativos(ativos), carga


MESES_PT = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"]


def _mes_txt(d) -> str:
    return f"{MESES_PT[d.month - 1]}/{d:%y}"


def _registros(df: pd.DataFrame) -> list[dict]:
    return json.loads(df.to_json(orient="records", date_format="iso"))


def _int(v) -> str:
    return "—" if v is None or pd.isna(v) else f"{int(round(v)):,}".replace(",", ".")


def _num(v, casas=1) -> str:
    return "—" if v is None or pd.isna(v) else f"{v:,.{casas}f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _pct(v, casas=0) -> str:
    """v em fração (0,25 = 25%)."""
    return "—" if v is None or pd.isna(v) else f"{_num(v * 100, casas)}%"


def _reais(v) -> str:
    return "—" if v is None or pd.isna(v) else f"R$ {_num(v, 0)}"


def _delta_mes(atual: int, anterior: int, ref: date) -> tuple[str, str]:
    """Nota do card: quantos no mês da data final e a diferença para o mês anterior."""
    mes = _mes_txt(ref)
    if anterior == atual:
        return f"{mes}: {_int(atual)} · estável vs mês ant.", CINZA
    return f"{mes}: {_int(atual)} · {'+' if atual > anterior else '−'}{_int(abs(atual - anterior))} vs mês ant.", CINZA


def _escala(cores: dict, presentes) -> dict:
    dom = [k for k in cores if k in set(presentes)]
    return {"domain": dom, "range": [cores[k] for k in dom]}


def _excel(df: pd.DataFrame, nome: str, key: str) -> None:
    buffer = io.BytesIO()
    df.to_excel(buffer, index=False, engine="openpyxl")
    st.download_button("Exportar para Excel", data=buffer.getvalue(), file_name=nome, key=key, icon=":material/download:",
                       mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")


# ----------------------------------------------------------------------------- gráficos

def combo_baldes(por: pd.DataFrame, tot: pd.DataFrame) -> dict:
    """Barras empilhadas por balde com o total do mês em cima + acumulado no período (linha, eixo à direita)."""
    ordem_x = [_mes_txt(d) for d in tot["mes"]]
    x = {"field": "mes_txt", "type": "ordinal", "sort": ordem_x, "axis": {"labelAngle": 0, "title": None}}
    barras = por.assign(mes_txt=[_mes_txt(d) for d in por["mes"]], ordem=[list(CORES_BALDE).index(b) for b in por["balde"]])
    linha = tot.assign(mes_txt=ordem_x)
    escala = {"domain": [0, max(1, float(tot["total"].max()) * 1.15)], "nice": False}
    return {"resolve": {"scale": {"y": "independent", "color": "independent"}},
            "layer": [
                {"data": {"values": _registros(barras)}, "layer": [
                    {"mark": {"type": "bar", "cornerRadiusTopLeft": 2, "cornerRadiusTopRight": 2},
                     "encoding": {"x": x, "y": {"field": "qtd", "type": "quantitative", "stack": "zero", "scale": escala,
                                                "axis": {"grid": True, "title": "Movimentações no mês"}},
                                  "color": {"field": "balde", "scale": _escala(CORES_BALDE, por["balde"]),
                                            "legend": {"orient": "top", "title": None}},
                                  "order": {"field": "ordem", "sort": "ascending"},
                                  "tooltip": [{"field": "mes_txt", "title": "Mês"}, {"field": "balde", "title": " "},
                                              {"field": "qtd", "title": "Movimentações"}]}},
                    {"mark": {"type": "text", "dy": -8, "fontSize": 10, "fontWeight": 700, "color": CINZA_ESCURO},
                     "encoding": {"x": x, "y": {"aggregate": "sum", "field": "qtd", "type": "quantitative", "scale": escala},
                                  "text": {"aggregate": "sum", "field": "qtd", "type": "quantitative"}}},
                ]},
                {"data": {"values": _registros(linha)},
                 "mark": {"type": "line", "strokeWidth": 2, "strokeDash": [4, 3], "color": CINZA, "point": {"filled": True, "size": 30, "color": CINZA}},
                 "encoding": {"x": x, "y": {"field": "acumulado", "type": "quantitative",
                                            "axis": {"orient": "right", "grid": False, "title": "Acumulado no período", "titleColor": CINZA}},
                              "tooltip": [{"field": "mes_txt", "title": "Mês"}, {"field": "acumulado", "title": "Acumulado"}]}},
            ]}


def barras_h(t: pd.DataFrame, campo: str, valor: str, cor, rotulo: str | None = None, ordenar: bool = True,
             tooltip: list | None = None) -> dict:
    t = t.copy()
    t["txt"] = t[rotulo] if rotulo else t[valor].map(_int)
    y = {"field": campo, "type": "nominal", "sort": "-x" if ordenar else list(t[campo]), "axis": {"labelLimit": 240, "title": None}}
    xq = {"field": valor, "type": "quantitative", "axis": None}
    return {"data": {"values": _registros(t)}, "layer": [
        {"mark": {"type": "bar", "cornerRadiusEnd": 5, "color": cor}, "encoding": {"y": y, "x": xq, "tooltip": tooltip or [
            {"field": campo, "title": " "}, {"field": "txt", "title": "Valor"}]}},
        {"mark": {"type": "text", "align": "left", "dx": 4, "fontSize": 11, "fontWeight": 700, "color": CINZA_ESCURO},
         "encoding": {"y": y, "x": xq, "text": {"field": "txt"}}},
    ], "padding": {"right": 70}}


def linhas_pct(t: pd.DataFrame, ini: date, fim: date) -> dict:
    """% médio de aumento por mês, uma linha por tipo."""
    t = t.assign(mes_txt=[_mes_txt(d) for d in t["mes"]], txt=[f"{_num(v)}%" for v in t["percentual_reajuste"]])
    ordem_x = [_mes_txt(d) for d in m.meses(ini, fim)]
    return {"data": {"values": _registros(t)},
            "mark": {"type": "line", "strokeWidth": 2.5, "point": {"filled": True, "size": 40}},
            "encoding": {"x": {"field": "mes_txt", "type": "ordinal", "sort": ordem_x, "axis": {"labelAngle": 0, "title": None}},
                         "y": {"field": "percentual_reajuste", "type": "quantitative", "axis": {"grid": True, "title": "% médio de aumento"}},
                         "color": {"field": "nucleo_movimentacao", "scale": _escala(CORES_TIPO, t["nucleo_movimentacao"]),
                                   "legend": {"orient": "top", "title": None}},
                         "tooltip": [{"field": "mes_txt", "title": "Mês"}, {"field": "nucleo_movimentacao", "title": "Tipo"},
                                     {"field": "txt", "title": "% médio"}]}}


def par_qtd_valor(df: pd.DataFrame, campo: str, rotulo: str) -> None:
    """Lado a lado, mesmo agrupador: quantidade (com o % médio no rótulo) | R$ médio de aumento."""
    t = m.resumo_por(df, campo)
    t["txt_qtd"] = [f"{_int(q)} · {_num(p)}%" for q, p in zip(t["qtd"], t["pct_medio"])]
    t["txt_valor"] = t["valor_medio"].map(_reais)
    altura = max(160, 32 * len(t))
    tip = [{"field": campo, "title": rotulo}, {"field": "qtd", "title": "Aumentos"},
           {"field": "txt_qtd", "title": "Qtd · % médio"}, {"field": "txt_valor", "title": "R$ médio"}]
    c1, c2 = st.columns(2)
    with c1:
        pp.grafico(f"Quantidade por {rotulo.lower()} (rótulo: qtd · % médio)",
                   barras_h(t, campo, "qtd", AZUL, rotulo="txt_qtd", tooltip=tip), altura, aviso=SEM_DADOS)
    with c2:
        pp.grafico(f"R$ médio de aumento por {rotulo.lower()}",
                   barras_h(t, campo, "valor_medio", AMARELO, rotulo="txt_valor", tooltip=tip), altura, aviso=SEM_DADOS)


# ----------------------------------------------------------------------------- página

try:
    df, ativos_base, carga = carregar()
except Exception as exc:  # noqa: BLE001
    st.error("Não consegui ler a base do Neon. Confira o bloco [neon] em .streamlit/secrets.toml.", icon=":material/error:")
    st.caption(f"{type(exc).__name__}")
    st.stop()

ref = m.data_referencia(df)

pp.logo(ASSETS / "icone-movimentacoes.png", "Movimentações")
navegacao = st.navigation([
    st.Page(lambda: pagina_geral(), title="Visão geral", icon=":material/dashboard:", url_path="visao-geral", default=True),
    st.Page(lambda: pagina_aumentos(), title="Aumentos salariais", icon=":material/payments:", url_path="aumentos"),
    st.Page(lambda: pagina_transferencias(), title="Transferências", icon=":material/swap_horiz:", url_path="transferencias"),
])

opcoes = lambda c: sorted(df[c].dropna().unique())  # noqa: E731
with pp.barra_lateral(fonte="Neon (Oracle HCM, sync diário)", atualizado_em=carga):
    st.markdown("**Período**")
    _padrao = (m.inicio_padrao(ref), ref)
    _escolha = st.date_input("Período", value=_padrao, min_value=df["data_efetiva"].min().date(), max_value=ref,
                             format="DD/MM/YYYY", label_visibility="collapsed")
    per_ini, per_fim = (_escolha if isinstance(_escolha, (tuple, list)) and len(_escolha) == 2 else _padrao)
    st.markdown("**Filtros**")
    sel = {
        "diretoria": st.multiselect("Diretoria", opcoes("diretoria"), placeholder="Todas"),
        "area": st.multiselect("Área", opcoes("area"), placeholder="Todas"),
        "categoria_atribuicao": st.multiselect("Categoria", opcoes("categoria_atribuicao"), placeholder="Todas"),
        "gerenciamento_nivel_cargo": st.multiselect("Nível de cargo", opcoes("gerenciamento_nivel_cargo"), placeholder="Todos"),
    }
    st.caption("Diretoria e área são as do centro de custo do evento (numa transferência, o destino). "
               "Os filtros valem também para os ativos de hoje, base da taxa de movimentação.")

rotulos = {"diretoria": "Diretoria", "area": "Área", "categoria_atribuicao": "Categoria", "gerenciamento_nivel_cargo": "Nível"}
pp.cabecalho("Movimentações de pessoal" if navegacao.title == "Visão geral" else navegacao.title, atualizado_em=carga,
             filtros={"Período": f"{per_ini:%d/%m/%Y} a {per_fim:%d/%m/%Y}", **{rotulos[c]: v for c, v in sel.items()}},
             legenda=f"Eventos com data efetiva até {ref:%d/%m/%Y} · histórico de movimentação do Oracle HCM")

base, ativos = df, ativos_base
for col, vals in sel.items():
    if vals:
        base, ativos = base[base[col].isin(vals)], ativos[ativos[col].isin(vals)]
periodo = m.no_periodo(base, per_ini, per_fim)

AJUDA_V3 = ("Regra V3: todo evento cai num tipo. Movimentações = Promoção + Aumentos Salariais + Transferências. "
            "Acordo coletivo fica de fora e os casos ambíguos entre acordo coletivo e mérito ficam em “A revisar”.")
AJUDA_TAXA = "Pessoas distintas com alguma movimentação no período ÷ ativos de hoje no mesmo filtro."


def _sem_dados(d: pd.DataFrame, aviso: str = SEM_DADOS) -> bool:
    if d.empty:
        st.info(aviso, icon=":material/info:")
        return True
    return False


# ================================================================ visão geral
def pagina_geral() -> None:
    t = m.totais(periodo)
    atual, anterior = m.mes_atual_e_anterior(m.movimentacoes(base), per_fim)
    pp.secao("Movimentações no período")
    c = st.columns(4)
    for col, balde, rot, ajuda in zip(c, ["Promoção", "Aumentos Salariais", "Transferências", "Movimentações"],
                                      ["Promoções", "Aumentos salariais", "Transferências", "Movimentações"],
                                      [None, None, None, AJUDA_V3]):
        with col:
            if balde == "Movimentações":
                nota, cor = _delta_mes(len(atual), len(anterior), per_fim)
            else:
                nota, cor = _delta_mes(int((atual["balde"] == balde).sum()), int((anterior["balde"] == balde).sum()), per_fim)
            pp.kpi(rot, _int(t[balde]), nota, cor, ajuda=ajuda)
    c = st.columns(4)
    with c[0]:
        pp.kpi("Pessoas movimentadas", _int(m.movimentacoes(periodo)["id_funcionario"].nunique()), "pessoas distintas", CINZA)
    with c[1]:
        pp.kpi("Taxa de movimentação", _pct(m.taxa_movimentacao(periodo, ativos), 1),
               f"sobre {_int(m.headcount(ativos))} ativos hoje", CINZA, ajuda=AJUDA_TAXA)
    with c[2]:
        pp.kpi("Cargos sem movimentação", _int(m.cargos_sem_movimentacao(periodo, ativos)),
               f"de {_int(ativos['descricao_cargo'].nunique())} cargos com ativos", CINZA)
    with c[3]:
        pp.kpi("A revisar", _int(t[m.A_REVISAR]), f"{_int(t[m.DESCARTADO])} de acordo coletivo fora", CINZA,
               ajuda="Aumento sem troca de cargo que a regra não conseguiu separar entre acordo coletivo e mérito. "
                     "Fica fora dos totais e aparece no detalhamento abaixo.")

    mov = m.movimentacoes(periodo)
    if _sem_dados(mov):
        return
    por, tot = m.evolucao_baldes(base, per_ini, per_fim)
    pp.grafico("Movimentações por mês e tipo", combo_baldes(por, tot), 340, aviso=SEM_DADOS)

    pp.secao("Onde acontecem")
    g1, g2 = st.columns(2)
    with g1:
        t_dir = m.contagem(mov, "diretoria")
        pp.grafico("Por diretoria", barras_h(t_dir, "diretoria", "qtd", AZUL), max(220, 30 * len(t_dir)), aviso=SEM_DADOS)
    with g2:
        t_niv = m.contagem(mov, "gerenciamento_nivel_cargo")
        pp.grafico("Por nível de cargo", barras_h(t_niv, "gerenciamento_nivel_cargo", "qtd", AZUL_CLARO),
                   max(220, 30 * len(t_niv)), aviso=SEM_DADOS)
    g1, g2 = st.columns([2, 3])
    with g1:
        pp.grafico("Pessoas atingidas por tipo", barras_h(m.pessoas_por_tipo(periodo), "tipo", "pessoas", AZUL, ordenar=False),
                   190, aviso=SEM_DADOS)
        st.html('<div class="nota">Pessoas distintas com ao menos um evento de cada tipo no período. Não é uma sequência '
                'no tempo: uma pessoa pode ter transferência sem ter tido mérito antes.</div>')
    with g2:
        st.html('<div class="titulo-graf">Cargos com menos aumentos no período</div>')
        cr = m.cargos_menos_reconhecidos(periodo, ativos)
        if not _sem_dados(cr, "Sem cargos com 3 ou mais ativos no filtro."):
            st.dataframe(cr, hide_index=True, width="stretch", height=min(38 + 35 * len(cr), 320),
                         column_config={"cargo": st.column_config.TextColumn("Cargo", width="medium"),
                                        "ativos": st.column_config.NumberColumn("Ativos hoje", format="%d", width="small"),
                                        "aumentos": st.column_config.NumberColumn("Aumentos", format="%d", width="small")})
            st.html('<div class="nota">Cargos com 3 ou mais ativos hoje, do que teve menos aumentos (promoção, mérito, '
                    'enquadramento, equiparação, alteração de cargo, reclassificação) para o que teve mais.</div>')

    pp.secao("Detalhamento")
    det = periodo[periodo["balde"].isin(m.BALDES_MOVIMENTACAO + [m.A_REVISAR])].sort_values("data_efetiva", ascending=False)
    tabela = det.rename(columns={"nome_funcionario": "Colaborador", "descricao_cargo_atual": "Cargo", "diretoria": "Diretoria",
                                 "area": "Área", "balde": "Tipo (V3)", "tipo_movimentacao": "Detalhe", "motivo": "Motivo (Oracle)",
                                 "data_efetiva": "Data"})[
        ["Data", "Colaborador", "Cargo", "Diretoria", "Área", "Tipo (V3)", "Detalhe", "Motivo (Oracle)"]]
    st.dataframe(tabela, hide_index=True, width="stretch", height=380,
                 column_config={"Data": st.column_config.DateColumn(format="DD/MM/YYYY")})
    _excel(tabela, "movimentacoes.xlsx", "excel_mov")


# ================================================================ aumentos salariais
def pagina_aumentos() -> None:
    pp.secao("% de aumento salarial")
    tipos = st.pills("Tipos na análise", m.TIPOS_AUMENTO, selection_mode="multi", default=m.TIPOS_AUMENTO,
                     help="Vale para todos os cards e gráficos desta página.")
    bruto, aum = m.aumentos(periodo, tipos or [])
    n_absurdos = len(bruto) - len(aum)
    c = st.columns(4)
    with c[0]:
        pp.kpi("Aumentos no período", _int(len(aum)), f"{_int(aum['id_funcionario'].nunique())} pessoas", CINZA)
    with c[1]:
        pp.kpi("% médio de aumento", f"{_num(aum['percentual_reajuste'].mean())}%" if len(aum) else "—",
               f"mediana {_num(aum['percentual_reajuste'].median())}%" if len(aum) else "", CINZA,
               ajuda="Sobre o salário anterior: (novo − anterior) ÷ anterior.")
    with c[2]:
        pp.kpi("R$ médio de aumento", _reais(aum["valor_reajuste"].mean()), "por evento", CINZA)
    with c[3]:
        pp.kpi("Impacto mensal na folha", _reais(aum["valor_reajuste"].sum()), "soma dos aumentos, por mês", CINZA,
               ajuda="Soma de (salário novo − anterior) dos aumentos do período: quanto a folha mensal cresceu com eles.")

    with st.expander("Sobre a política de remuneração (PLREMU-01)", icon=":material/info:"):
        st.markdown(
            "**Mérito**: sem troca de cargo; requer mín. 6 meses no cargo e avaliação de performance positiva; percentual "
            "recomendado de até **15% em 1 ano** (ou 8% a cada 6 meses).\n\n"
            "**Promoção**: com troca de cargo e faixa salarial; requer mín. 1 ano de casa (ou 1 ano desde a última "
            "promoção/enquadramento) e avaliação positiva; limite de **25% de reajuste**. Acima disso, a política prevê "
            "aplicação faseada em no mínimo 6 meses.\n\n"
            "**Enquadramento**: ajuste individual quando o salário está abaixo do início da faixa salarial do cargo.\n\n"
            "**Alteração de Cargo**: reclassificação para outro cargo sem precisar mudar o salário, porque o valor atual "
            "já está dentro da faixa do novo cargo.\n\n"
            "**Aumento Coletivo** (fora deste indicador): reajuste anual por Convenção Coletiva, calculado e aplicado pela "
            "Folha e Benefícios, fora do processo de Comissão de Gente.\n\n"
            "Faixa salarial de referência: cargos administrados entre 80% e 120% da mediana de mercado.")

    if _sem_dados(aum, "Sem aumentos dos tipos escolhidos no filtro."):
        return
    if n_absurdos:
        st.warning(f"{_int(n_absurdos)} evento(s) com % implausível (cargo igual e aumento acima de {m.LIMITE_ABSURDO_PCT:.0f}%) "
                   "ficaram fora dos cards e gráficos: provável erro de cadastro. Continuam no detalhamento, marcados.",
                   icon=":material/warning:")
    pp.grafico("% médio de aumento por mês e tipo", linhas_pct(m.evolucao_pct(aum), per_ini, per_fim), 300, aviso=SEM_DADOS)

    pp.secao("Por tipo, diretoria e nível")
    par_qtd_valor(aum, "nucleo_movimentacao", "Tipo")
    par_qtd_valor(aum, "diretoria", "Diretoria")
    par_qtd_valor(aum, "gerenciamento_nivel_cargo", "Nível")

    pp.secao("Promoções")
    c1, c2 = st.columns(2)
    with c1:
        prim = m.primeira_promocao(base, per_ini, per_fim)
        if not _sem_dados(prim, "Sem primeiras promoções no filtro."):
            pp.kpi("Tempo médio até a 1ª promoção", f"{_num(prim['meses_ate_promocao'].mean(), 0)} meses",
                   f"{_int(len(prim))} pessoas tiveram a 1ª promoção no período", CINZA,
                   ajuda="Meses entre a admissão e a primeira promoção de cada pessoa em todo o histórico. Entram as "
                         "pessoas cuja primeira promoção caiu no período.")
            t = prim.groupby("gerenciamento_nivel_cargo", as_index=False)["meses_ate_promocao"].mean()
            t["txt"] = [f"{_num(v, 0)} meses" for v in t["meses_ate_promocao"]]
            pp.grafico("Meses até a 1ª promoção, por nível", barras_h(t, "gerenciamento_nivel_cargo", "meses_ate_promocao", AZUL,
                                                                     rotulo="txt"), max(160, 30 * len(t)), aviso=SEM_DADOS)
    with c2:
        cp = m.compressao(periodo, ativos_base)
        if cp["comparaveis"]:
            pp.kpi("Promovidos abaixo da mediana do cargo", _pct(cp["abaixo_mediana"]),
                   f"{_int(cp['comparaveis'])} promovidos comparados", CINZA,
                   ajuda="Novo salário do promovido × mediana salarial de quem está ativo hoje no cargo de destino. "
                         "Promovido em cargo sem ativos hoje fica de fora.")
            pp.kpi("Posição dos promovidos", _pct(cp["posicao_mediana"]), "do salário mediano do cargo de destino (mediana)", CINZA)
        else:
            st.info("Sem promoções comparáveis no filtro.", icon=":material/info:")

    pp.secao("Detalhamento")
    det = bruto.sort_values("data_efetiva", ascending=False).assign(
        pct=lambda x: x["percentual_reajuste"].round(1),
        revisar=lambda x: x["alerta_absurdo"].map({True: "% implausível", False: ""}))
    tabela = det.rename(columns={"data_efetiva": "Data", "nome_funcionario": "Colaborador", "descricao_cargo_anterior": "Cargo anterior",
                                 "descricao_cargo_atual": "Cargo atual", "diretoria": "Diretoria", "nucleo_movimentacao": "Tipo",
                                 "motivo": "Motivo (Oracle)", "salario_anterior": "Salário anterior", "salario_atual": "Salário novo",
                                 "pct": "% aumento", "revisar": "Revisar"})[
        ["Data", "Colaborador", "Cargo anterior", "Cargo atual", "Diretoria", "Tipo", "Motivo (Oracle)",
         "Salário anterior", "Salário novo", "% aumento", "Revisar"]]
    st.dataframe(tabela, hide_index=True, width="stretch", height=380,
                 column_config={"Data": st.column_config.DateColumn(format="DD/MM/YYYY"),
                                "Salário anterior": st.column_config.NumberColumn(format="R$ %.2f"),
                                "Salário novo": st.column_config.NumberColumn(format="R$ %.2f"),
                                "% aumento": st.column_config.NumberColumn(format="%.1f%%")})
    _excel(tabela, "aumentos_salariais.xlsx", "excel_aum")


# ================================================================ transferências
def pagina_transferencias() -> None:
    tr = m.transferencias(periodo)
    r = m.resumo_transferencias(tr, ativos)
    atual, anterior = m.mes_atual_e_anterior(m.transferencias(base), per_fim)
    pp.secao("Transferências no período")
    c = st.columns(4)
    with c[0]:
        nota, cor = _delta_mes(len(atual), len(anterior), per_fim)
        pp.kpi("Transferências", _int(r["eventos"]), nota, cor,
               ajuda="Qualquer mudança de centro de custo, mesmo junto de promoção, mérito ou acordo coletivo. Por isso o "
                     "número é maior que o card Transferências da Visão geral, que só conta a transferência pura.")
    with c[1]:
        pp.kpi("Pessoas transferidas", _int(r["pessoas"]), "pessoas distintas", CINZA)
    with c[2]:
        pp.kpi("% transferidos", _pct(r["pct_transferidos"], 1), f"sobre {_int(m.headcount(ativos))} ativos hoje", CINZA)
    with c[3]:
        ef = r["efetividade"]
        pp.kpi("Seguem na empresa", _pct(ef), "dos transferidos estão ativos hoje",
               VERDE if ef is not None and ef >= .8 else AMARELO if ef is not None else CINZA)
    if _sem_dados(tr, "Sem transferências no filtro selecionado."):
        return
    g1, g2 = st.columns(2)
    with g1:
        t = m.contagem(tr, "tipo_movimentacao")
        pp.grafico("Por tipo (o que veio junto com a transferência)", barras_h(t, "tipo_movimentacao", "qtd", AZUL),
                   max(200, 30 * len(t)), aviso=SEM_DADOS)
    with g2:
        t = m.contagem(tr, "diretoria")
        pp.grafico("Por diretoria de destino", barras_h(t, "diretoria", "qtd", AZUL_CLARO), max(200, 30 * len(t)), aviso=SEM_DADOS)
    st.html('<div class="nota">Custo de mobilização: não disponível. O histórico de movimentação do Oracle não traz valor de '
            'mudança ou mobilização; se houver uma base com esse custo (RH ou financeiro), ele pode entrar aqui.</div>')

    pp.secao("Detalhamento")
    tabela = tr.sort_values("data_efetiva", ascending=False).assign(
        ativa=lambda x: x["pessoa_ativa_hoje"].map({True: "Ativa", False: "Desligada"})).rename(
        columns={"data_efetiva": "Data", "nome_funcionario": "Colaborador", "diretoria": "Diretoria (destino)",
                 "tipo_movimentacao": "Tipo", "motivo": "Motivo (Oracle)", "descricao_centro_custo_anterior": "CC anterior",
                 "descricao_centro_custo_atual": "CC atual", "ativa": "Situação hoje"})[
        ["Data", "Colaborador", "Diretoria (destino)", "Tipo", "Motivo (Oracle)", "CC anterior", "CC atual", "Situação hoje"]]
    st.dataframe(tabela, hide_index=True, width="stretch", height=380,
                 column_config={"Data": st.column_config.DateColumn(format="DD/MM/YYYY")})
    _excel(tabela, "transferencias.xlsx", "excel_transf")


navegacao.run()
