# Changelog

## 2026-10-23 — Retomada: dado direto do Oracle e painel no padrão da Central

- Fonte: a gold do Neon (Oracle HCM → Neon, sync diário) publica o histórico de movimentação inteiro,
  até 20/10/2026. A base paliativa deixou de ser usada.
- Views novas (migrações 032 e 033): `core.v_movimentacoes_base` e `core.v_movimentacoes_cargo_ativo`;
  `app_movimentacoes` lê também `ops.v_ultima_carga`.
- **Correção**: o cruzamento de nível/status por pessoa duplicava eventos de quem tem mais de um vínculo
  (5.513 → 7.740 linhas). Agora é pelo código de atribuição.
- Correções de regra: aba Movimentações conta só os 3 tipos da V3; taxa e % transferidos dividem pelos
  ativos do mesmo filtro; 1ª promoção é a primeira de todo o histórico; "segue na empresa" por pessoa.
- `metricas.py` com a regra V3 (mesma classificação da versão anterior, conferida evento a evento).
- Tela no padrão: `painel_padrao.py`, login novo (`auth.py`), 3 páginas, filtro de período, gráficos
  Vega-Lite com `pp.grafico`, ícone e logo. `skip_auth` removido.
- Validação: `painel_movimentacoes` no `validar_paineis.py` com 8 comparações, todas ✅.
- Hub: card sem o aviso de "pausado".

## 2026-09-24 — Integração à Central de Gente & Dados no Neon (migração 003)

- Histórico de movimentação (Databricks e paliativo Oracle BIP) e mapeamento
  CC→Diretoria/Área saem de `interno` para **`core`** (ver
  `00 - Central de Gente & Dados/PLANO_INTEGRACAO_NEON.md` e
  `_neon/migrations/003_movimentacoes.sql`). Nomes antigos em `interno.*`
  ficam como views de compatibilidade.
- Funcionários passam a ser lidos por **`core_view.funcionario*`** (views sem
  PII pessoal — sem raça/cor, nascimento, contato etc.).
- Painel conecta como **`app_movimentacoes`** (só leitura). Scripts de `etl/`
  conectam como **`etl_loader`** via `etl/.env` — `upload_mapeamento_diretoria.py`
  e `upload_paliativo_historico_mov.py` deixam de ler o `secrets.toml` (que
  agora tem o usuário do painel, sem permissão de escrita).
- `auth.init_db()` só cria `app_users` se ela não existir (o usuário do app não
  tem permissão de CREATE).

## 2026-09-18 (tarde) — Base paliativa: pipeline Databricks confirmado quebrado

- Comparação com export manual do Oracle Fusion confirmou: o pipeline
  Databricks parou de capturar movimentações a partir de **junho/2026**
  (979 movimentações reais em junho, só 3 chegaram no Neon).
- Tentativas de automatizar a extração via API REST/SOAP do Oracle Fusion
  BI Publisher esbarraram num bloqueio de WAF (POST com caminho de pasta é
  sempre derrubado, GET funciona) — não resolvido, requer ação do
  administrador Oracle do lado do Pacaembu. Job de e-mail agendado também
  não funcionou na primeira tentativa.
- Solução adotada: tabela própria `interno.oracle_hcm_historico_movimentacao_paliativo`
  (`etl/upload_paliativo_historico_mov.py`), carregada a partir do export
  manual (Excel) do relatório no Catálogo BI. `app.py` usa essa fonte pra
  substituir por inteiro o período que ela cobre (hoje, set/2025 em
  diante) — não é preenchimento de buraco, é substituição completa, porque
  a paliativa provou ser mais completa mesmo nos meses "normais".
- Pasta `base paliativa/` (onde o Excel é colocado) adicionada ao
  `.gitignore` — contém dado sensível de RH.
- Ver `CONTEXT.md`, seções "Base paliativa" e "Tentativas de automação".

## 2026-09-18 — Regra de negócio V3, migração de fonte e política oficial

- **Nova fonte de dados**: `interno.oracle_hcm_historico_movimentacao`
  (deduplicada de `rh.silver.oracle_hcm_pit_adm_00024_historico_movimentacao_relatorio`,
  8.167 → 4.095 linhas) substitui `interno.fato_movimentacao` como fonte
  principal. Novo pipeline `etl/mirror_historico_mov.py` (Databricks → Neon,
  OAuth user-to-machine). % de aumento recalculado com a convenção padrão de
  RH (`/anterior`), não a fórmula não-convencional da fonte (`/atual`).
- **Diretoria/área migradas para o Neon** (`interno.mapeamento_diretoria` +
  `_especial`, `etl/upload_mapeamento_diretoria.py`) — resolve o risco que
  quebrou o deploy da Aderência Salarial (dependência de JSON gitignored).
- **Regra de negócio V3**: 3 baldes finais (Promoção / Aumentos Salariais /
  Transferências, `Movimentações` = soma dos 3), Acordo Coletivo descartado,
  balde "A revisar" visível à parte. Classificação ambígua (Acordo Coletivo
  vs. Mérito) resolvida por recorrência de % entre pessoas (assinatura de
  lote), com calendário de convenção coletiva por UF como reforço.
- Filtro de período trocado de multiselect de Ano pra intervalo De/Até
  (padrão: últimos 12 meses). Filtro de Área adicionado.
- Aba "Aumentos Salariais" redesenhada: cards de totais gerais, gráfico de
  quantidade por balde + acumulado, filtro único de tipos, pares de gráfico
  Qtd+%médio / R$ médio por tipo/diretoria/nível.
- Disclaimer da política de remuneração (PLREMU-01) com texto real (limites
  de Mérito/Promoção, definições oficiais) — texto integral da política
  salvo só em `CONTEXT_INTERNO.md` (confidencial, gitignored). "Adequação"
  renomeado para "Alteração de Cargo" (termo oficial da política).
- Ver `CONTEXT.md` para o raciocínio completo de cada decisão desta rodada.

## 2026-09-17 — Scaffold inicial do painel

- Estrutura do projeto criada: `app.py`, `auth.py`, `.streamlit/config.toml`,
  `scripts/grant_access.py`, `requirements.txt`, `.gitignore`.
- Confirmado que `interno.fato_movimentacao` já existe no Neon (mirror do
  Headcount Total) — nenhum pipeline ETL novo foi necessário. Ver CONTEXT.md.
- `app.py` com 3 abas: Aumentos Salariais, Movimentações, Transferências —
  cobrindo os 3 indicadores centrais do item "Painel de Movimentações" no
  board Monday, mais 3 indicadores extras aprovados pelo usuário (tempo até
  1ª promoção, pessoas atingidas por tipo de movimentação, compressão
  salarial pós-movimentação).
- Autenticação: reaproveitado `auth.py` do padrão Headcount Total/Aderência
  Salarial, apontando para a tabela `app_users` compartilhada (decisão do
  usuário). Adicionado bypass de login só para desenvolvimento local
  (`st.secrets["app"]["skip_auth"]`).
- Indicador de custo de mobilização (transferências) marcado como "não
  disponível" — sem dado de custo na fonte atual, não implementado por
  instrução explícita do usuário de nunca inventar dado.
- Testado localmente contra o Neon real (dados reais, 4.088 linhas em
  `interno.fato_movimentacao`).
- Documentação inicial: `CONTEXT.md`, `README.md`, `CONTEXT_INTERNO.md`
  (gitignored) criados nesta mesma sessão.
