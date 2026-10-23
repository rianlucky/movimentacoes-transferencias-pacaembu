# Contexto do produto

## Retomada em 2026-10-23 (vale sobre as seções abaixo)

- A pausa por dado incompleto acabou: a gold do Neon (`_neon/PLANO_ORACLE_MEDALLION.md`) traz o
  histórico 00024 direto do Oracle, todo dia. Base paliativa, `etl/mirror_historico_mov.py` e
  `etl/mapping_diretoria.py` ficam obsoletos.
- O painel lê só `core.v_movimentacoes_base` e `core.v_movimentacoes_cargo_ativo` (migrações 032/033).
  As seções abaixo que falam de `interno.*`, `fato_movimentacao`, base paliativa ou `skip_auth`
  descrevem a versão anterior.
- Decisões do Rian em 23/10/2026: **manter a regra V3** (a classificação pronta da gold,
  `movimentacao_verificado`, não substitui: ela mistura readmissões ≤ 10 dias e deixa transferências sem
  classe) e **manter o nome da pessoa** no detalhamento.
- Defeito achado e corrigido: o merge por `numero_pessoa` duplicava eventos de quem tem mais de um
  vínculo (+40% de linhas). Ver README, "O que mudou em relação ao painel anterior".

## Neon: onde fica cada coisa (desde a migração 003, 2026-09-24)

| O quê | Onde | Quem escreve | Quem lê |
|---|---|---|---|
| Histórico de movimentação (Databricks) | `core.oracle_hcm_historico_movimentacao` | `etl/mirror_historico_mov.py` (`etl_loader`) | `app.py` (`app_movimentacoes`) |
| Base paliativa (Oracle BIP) | `core.oracle_hcm_historico_movimentacao_paliativo` | `etl/upload_paliativo_historico_mov.py` (`etl_loader`) | `app.py` |
| CC → Diretoria/Área | `core.mapeamento_diretoria`, `core.mapeamento_diretoria_especial` | `etl/upload_mapeamento_diretoria.py` (`etl_loader`) | todos os apps (`grp_app_leitura`) |
| Funcionários (compressão salarial, nível de cargo) | `core_view.funcionario_ativo`, `core_view.funcionario` (sem PII pessoal) | mirror do Headcount Total | `app.py` |
| Login | `public.app_users` | `scripts/grant_access.py` | `auth.py` |

`interno.*` agora são **views de compatibilidade** — não escrever nelas. Mudança de estrutura: só via `_neon/migrations/`, testada antes no branch `dev`. As seções abaixo que citam `interno.*` são históricas.

## Objetivo

Painel consolidado de indicadores de movimentação de pessoal — Promoções,
Aumentos Salariais (Mérito/Enquadramento) e Transferências. Mesmo escopo do
item "Painel de Movimentações" no board Monday "Central de Gente & Dados"
(workspace *Remuneração & Orçamento de Pessoas*, grupo "🔧 Em Desenvolvimento").
Esse item nasceu da fusão de 3 ideias que estavam arquivadas separadamente no
mesmo board ("% Médio de Aumento Salarial", "Taxa de Movimentações",
"% Transferidos no período") — decisão do usuário registrada no próprio board
("mesclei em um dashboard só").

Ferramenta de trabalho para o time de Remuneração — expõe cargo/salário por
pessoa, não é um painel público.

## Origem e reaproveitamento (2026-09-17)

Existe um dashboard anterior no projeto `StreamlitRH` local
(`C:\Dev\Projetos\StreamlitRH\pages\4_Movimentacoes.py`) que já cobria uma
versão desses indicadores, mas lendo direto do Databricks
(`dev.rh_silver.fato_movimentacoes`, camada *silver*/dev) via
`databricks-sql-connector`, sem Neon e sem login. Este projeto novo:

- Migra a fonte para o Neon (`interno.fato_movimentacao`, camada *gold*/prod
  — ver seção seguinte), seguindo a decisão institucional de tirar consulta
  analítica direta do Databricks (bloqueado por política de PAT/M2M) e
  centralizar acesso interno no Neon (mesma decisão já tomada no Headcount
  Total em 2026-09-11).
- Reaproveita o padrão visual, de autenticação e de arquitetura já
  consolidado em 3 painéis irmãos: **Headcount Total**, **Aderência Salarial**
  e **Turnover Comercial** (todos em
  `00 - Central de Gente & Dados`) — tema navy, cartão de login dividido,
  KPI cards em Vega-Lite, `psycopg2` puro, cache de 15 min com fallback pra
  mock local.

## Fonte de dados: `interno.fato_movimentacao` (achado, não construído)

**Não foi necessário construir um pipeline Databricks→Neon novo.** A tabela
`interno.fato_movimentacao` já existe no Neon do projeto "Central de Gente &
Dados", espelhada por completo (truncate + reload) pelo script
`etl/mirror_fatos_to_neon.py` do painel **Headcount Total**, a partir de
`rh.gold.fato_movimentacao` no Databricks. Este projeto só lê essa tabela —
não duplica o pipeline (mesmo padrão que a Aderência Salarial já aplica para
`interno.fato_funcionario_ativo`).

**Atenção — fonte gold, não silver:** `rh.gold.fato_movimentacao` é uma
tabela diferente de `dev.rh_silver.fato_movimentacoes` (plural), que o
dashboard antigo do StreamlitRH usava. Confirmado em 2026-09-17 (inspeção
direta via script Python/psycopg2, ver `CONTEXT_INTERNO.md`): a versão gold
tem uma granularidade mais rica — inclui não só Mérito/Promoção/Enquadramento/
Equiparação, mas também transferências de departamento/local, alterações de
centro de custo, ajustes de convenção coletiva e sincronizações sem alteração
real. **4.088 linhas**, período de `data_efetiva` de 2012 a 2026 (concentração
maior nos últimos ~24 meses).

Colunas relevantes confirmadas: `id_funcionario`, `nome_funcionario`,
`nome_diretoria`, `categoria_atribuicao` (OBRAS/CORPORATIVO/COMERCIAL),
`descricao_cargo_atual`/`descricao_cargo_anterior`, `gerenciamento_nivel_cargo`,
`motivo`, `acao`, `movimentacao_verificado` (classificação já curada, mas nula
em ~36% das linhas), `status` (Ativo/Inativo — snapshot do momento do mirror,
não histórico), `salario_anterior`/`salario_atual` (texto, mas em formato
decimal simples `"3272.09"` — diferente do `"R$ x.xxx,xx"` do dashboard
antigo, não precisa de regex), `valor_reajuste`, `percentual_original` e
`percentual_reajuste_calculado` (também texto decimal, já vem calculado),
`tempo_casa_meses` e `faixa_tempo_casa` (já pré-calculados), `data_admissao`,
`data_efetiva`, `centro_de_custo_anterior`/`atual`, `loaded_at`.

**Dado adicional usado:** `interno.fato_funcionario_ativo` (a mesma tabela
que a Aderência Salarial lê) é consultada só para 2 finalidades: (1) headcount
ativo atual, como denominador de "Taxa de Movimentação" e "% Transferidos no
período"; (2) mediana salarial por cargo, para o indicador de "Compressão
salarial pós-movimentação".

## Decisão: classificação de `motivo` em `tipo_movimentacao` (2026-09-17, V1 — a validar com o time)

A coluna `motivo` tem 36 valores distintos (incluindo ~20 códigos de
convenção coletiva tipo `AC474 CONVENÇÃO COLETIVA 06/2025`). `app.py` agrupa
assim (função `_classificar_tipo`):

| `tipo_movimentacao` | `motivo` incluídos |
| --- | --- |
| Aumento Salarial | MÉRITO, PROMOÇÃO ORÇADA, PROMOÇÃO NÃO ORÇADA (subgrupo "padrão", conforme o board Monday) + ENQUADRAMENTO, EQUIPARAÇÃO SALARIAL, ADEQUAÇÃO DE CARGO/POSIÇÃO, RECLASSIFICAÇÃO (opcionais, atrás de um checkbox na aba) |
| Transferência | TRANSFERÊNCIA DE DEPARTAMENTO, TRANSFERÊNCIA DE LOCAL |
| Convenção Coletiva | qualquer `motivo` contendo "CONVENÇÃO COLETIVA" (reajuste coletivo, não é decisão individual de mérito) |
| Admissão | ADMISSÃO DE NOVO COLABORADOR (1 única linha na base — não é o objetivo desta tabela, existe outra tabela pra isso) |
| Sem evento | `motivo` nulo — corresponde a linhas com `acao = 'SINCRONIZAÇÃO DA POSIÇÃO'` e `descricao_mudanca = 'Sem Alteração'` (sincronização de posição sem mudança real); excluídas de toda análise |
| Outras Movimentações | tudo o mais (ex.: ALTERAÇÃO DE CENTRO DE CUSTO, ALTERAÇÃO DE CARGO/POSIÇÃO, ALTERAÇÃO DE GESTOR, ESPONTÂNEO, AUMENTO DE CARGA HORÁRIA) |

**Isto é uma primeira leitura minha dos dados, não uma regra validada pelo
time de Remuneração.** Em especial: (1) convenção coletiva ficou fora do
cálculo de "% médio de aumento" por não ser uma decisão individual de mérito
— pode estar errado se o indicador do board quiser incluir; (2) "Convênio
Coletivo"/"Alteração de Centro de Custo" respondem por ~44% de todas as
linhas da tabela — se isso distorcer "Taxa de Movimentação", talvez essas
categorias devessem ficar de fora do denominador também. Ajustar assim que o
usuário revisar a aba "Movimentações".

## Decisão: indicador de custo de mobilização — não implementado (2026-09-17)

O item do board pede "previsão de custos de mobilização" nas transferências.
`interno.fato_movimentacao` não tem nenhum valor monetário de mudança/
mobilização. Em vez de inventar uma estimativa, a aba "Transferências" mostra
o card do indicador como "N/D" com uma nota explicando o motivo e pedindo a
fonte certa ao usuário (nunca inventar dado, por instrução explícita do
usuário). Revisar se existe uma base de custo de mobilização em outro lugar
(RH ou financeiro) antes de tentar implementar isso.

## Indicadores extras aprovados pelo usuário (2026-09-17)

Além dos 3 indicadores centrais do board, o usuário aprovou 3 ideias
inspiradas em dashboards de RH da comunidade (perguntadas antes de implementar,
por instrução explícita — nunca assumir que o dado existe):

1. **Tempo médio até a 1ª promoção** (aba Aumentos Salariais): meses entre
   `data_admissao` e a primeira `data_efetiva` com motivo de Promoção, por
   colaborador. Usa só `fato_movimentacao` (a data de admissão já vem
   replicada em cada linha do colaborador).
2. **Funil de movimentação** (aba Movimentações), renomeado para "Pessoas
   atingidas por tipo de movimentação" — decisão de implementação: **não** é
   um funil temporal estrito (não garante que Mérito veio antes de
   Transferência para a mesma pessoa), é uma contagem de cobertura por tipo
   de evento. Documentado explicitamente na UI pra não sugerir uma leitura
   que os dados não sustentam.
3. **Compressão salarial pós-movimentação** (aba Aumentos Salariais): compara
   o `salario_atual` de quem foi promovido com a mediana salarial de quem já
   está ativo no mesmo cargo (`interno.fato_funcionario_ativo`), por nome
   exato de cargo (mesmo tipo de cruzamento usado na Aderência Salarial —
   cargos sem equivalente ficam de fora, contados à parte, nunca descartados
   silenciosamente).

O usuário optou por **não** incluir por ora (fica pra uma fase futura, se
pedido): "Cruzar Méritos e Promoções com crescimento de Headcount" e "Nº de
MPs aprovadas no mês" (esse último sugere existir uma base de *solicitações*
de movimentação, distinta da tabela de movimentações já efetivadas — não
mapeada ainda).

## Decisão: autenticação compartilhada (`app_users`) (2026-09-17)

Perguntado explicitamente (este painel também expõe cargo/salário por
pessoa, mesma preocupação que motivou a Aderência Salarial a cogitar uma
tabela própria em 2026-09-15), o usuário escolheu manter consistência com a
decisão institucional mais recente: usar `app_users` (schema `public`)
compartilhada com Headcount Total e Aderência Salarial — mesma senha em todos
os painéis, sem segregação de acesso por painel (ainda não implementada em
nenhum dos 3 projetos irmãos).

## Decisão: login desabilitado em localhost via secrets (2026-09-17)

Por pedido do usuário ("vamos fazer o fluxo de login completo, mas em
localhost desabilitado, e no passo final de deploy habilitamos"),
`auth.require_login()` verifica `st.secrets["app"]["skip_auth"]`: se `true`,
libera acesso direto com um usuário fictício de desenvolvimento, sem tocar o
Neon. A chave só existe no `.streamlit/secrets.toml` **local** (gitignored);
`.streamlit/secrets.toml.example` documenta que ela nunca deve ir para o
Secrets do Streamlit Cloud. Antes de publicar, checklist mínimo: remover
`skip_auth` do ambiente de produção (ou garantir que não foi colado no
Secrets do Streamlit Cloud).

## Hospedagem (2026-09-17)

Por ora, **só localhost** — o usuário optou por não criar repositório/GitHub/
Streamlit Cloud ainda, decide depois de validar os indicadores com dado real.
Quando for a hora, seguir o mesmo checklist dos painéis irmãos: repo GitHub
próprio, `CONTEXT_INTERNO.md` gitignored antes do primeiro push, Secrets no
Streamlit Community Cloud replicando `.streamlit/secrets.toml` (exceto
`skip_auth`).

## Estilo visual

Mesmo tema navy (`#064D66`) e paleta semântica (`#0ca30c` verde / `#d03b3b`
vermelho / `#eb6834` laranja / `#2a78d6` azul) de Headcount Total e Aderência
Salarial, fixados em `.streamlit/config.toml`. Prioridade de implementação
pedida pelo usuário: widgets nativos do Streamlit primeiro (`st.dataframe`,
`st.metric`, `st.column_config.ProgressColumn`) → Altair/Vega-Lite pra
gráficos e KPI cards → HTML próprio só como último recurso. Nesta V1, não foi
necessário recorrer a tabela HTML customizada (diferente da Aderência
Salarial) — `st.column_config.ProgressColumn` nativo cobriu a barra de %
aumento na tabela detalhada.

Ainda sem logo/ícone próprio do painel (`assets/icone-movimentacoes.png` não
existe) — `auth.py` já trata a ausência sem quebrar (pill de login sem
imagem). Decisão do usuário em 2026-09-17: deixar sem ícone por enquanto, sem
inventar uma identidade visual — revisitar se/quando o usuário enviar um
arquivo próprio.

## Reconstrução da classificação de movimentação (2026-09-17, V2)

A V1 (só `motivo` bruto) foi substituída depois que o usuário pediu pra
refazer a curadoria de `movimentacao_verificado` (campo que ele mesmo
preencheu manualmente, mas que fica nulo em ~36% das linhas). Investigação
feita cruzando `movimentacao_verificado` (onde existe) contra 3 sinais
derivados dos dados brutos — `cargo_mudou` (`descricao_cargo_anterior` ≠
`atual`), `cc_mudou` (`centro_de_custo_anterior` ≠ `atual`), `salario_mudou`
(`salario_anterior` ≠ `atual`) — pra achar uma regra reproduzível. Resultado
(função `_derivar_classificacao` em `app.py`):

**Regras que bateram ~100% com a curadoria manual existente** (validadas por
cruzamento, não são achismo):
- Motivos "nome próprio" (MÉRITO, ENQUADRAMENTO, EQUIPARAÇÃO SALARIAL,
  RECLASSIFICAÇÃO, ESPONTÂNEO, AUMENTO DE CARGA HORÁRIA, qualquer "CONVENÇÃO
  COLETIVA") → núcleo = o próprio nome, sempre (cargo nunca muda nesses
  casos).
- Quando o motivo é genérico ou nulo (ALTERAÇÃO DE CARGO/POSIÇÃO, ADEQUAÇÃO DE
  CARGO/POSIÇÃO, ALTERAÇÃO DE CENTRO DE CUSTO, TRANSFERÊNCIA DE
  DEPARTAMENTO/LOCAL, motivo nulo): núcleo = "Promoção" se cargo **e** salário
  mudaram; "Adequação" se só o cargo mudou.
- Transferência deixou de depender do texto do motivo: **qualquer mudança de
  centro de custo é uma transferência** (`cc_mudou`), combinável com o núcleo
  acima (ex.: "Transferência + Promoção"). Isso corrigiu uma subcontagem
  grande: 1.221 linhas de "ALTERAÇÃO DE CENTRO DE CUSTO" (30% da tabela) não
  eram contadas como transferência antes.

**O que não dá pra derivar só dos dados (ambiguidade real, ~650 linhas,
16%):** quando cargo não mudou mas salário mudou, com motivo genérico —
pode ser "Acordo Coletivo" (reajuste automático por convenção) ou "Mérito"
(decisão individual), e o próprio usuário confirmou que classificou os dois
manualmente sem um critério que os dados sozinhos revelem. Testado e
descartado: (1) data não disambigua (Acordo Coletivo e Mérito aparecem no
mesmo mês em vários casos); (2) `descricao_mudanca` (texto livre) só descreve
transição de cargo ("Auxiliar para Assistente"), sempre "Sem Alteração" nesses
casos — não ajuda.

**Solução adotada:** calendário de Convenção Coletiva por localidade,
informado pelo usuário em 2026-09-17:

| UF | Meses | Cidades reconhecidas em `descricao_local` |
| --- | --- | --- |
| SP | maio/junho | São Paulo, São José do Rio Preto, Araraquara, Ribeirão Preto, Bauru, Catanduva, Itapetininga, Leme, Tatuí, Botucatu, Piratininga, Bálsamo, Presidente Prudente, Votuporanga, Araçatuba, Taubaté, Lins, Avaré, Bady Bassitt, Assis (exceto "Assis Chateaubriand") |
| MT | maio/junho/julho | Cuiabá, Primavera do Leste, Sinop, Lucas do Rio Verde, Sorriso, Nova Marilândia |
| PR | junho/julho | Londrina, Arapongas, Cianorte, Ponta Grossa, Palotina, Assis Chateaubriand |
| MS | novembro/dezembro | Nenhuma localidade da base identificada como MS ainda — calendário cadastrado, pendente o usuário confirmar quais `descricao_local` mapeiam pra MS (não há nenhum palpite meu na lista de cidades vista até agora) |
| DF | maio/junho | Brasília |
| MG | setembro/outubro | Ituiutaba, Uberlândia |

Implementado em `_bate_calendario_cc()`/`_uf_provavel()` (`app.py`), casando
`descricao_local` (por palavras-chave de cidade) com `mes_data_efetiva`.
**Cobertura completa** pra todas as cidades identificadas na base nesta
sessão — só falta o usuário confirmar se alguma delas é de MS (calendário já
cadastrado, sem nenhuma cidade associada ainda). Enquanto uma localidade não
tiver calendário, ela cai no núcleo "A revisar (Acordo Coletivo ou Mérito)"
— fica de fora do indicador de "% médio de aumento" por padrão, mas aparece
à parte em "Movimentações" e na tabela detalhada, nunca descartado
silenciosamente.

## Reclassificação do balde ambíguo por recorrência de % (2026-09-18)

Com o calendário completo, ainda sobravam 593 das 4.088 linhas em "A
revisar" — a maioria (545) em localidade com UF já mapeada, mas em mês fora
da janela de convenção coletiva conhecida. Cheguei a propor assumir "Mérito"
por eliminação nesses casos, mas antes de aplicar investiguei o padrão dos
valores: **70% das 672 linhas do balde ambíguo (antes do calendário) têm um
`percentual_reajuste_calculado` que se repete em 3+ pessoas diferentes** —
o caso mais extremo, 4,60%, aparece em 48 pessoas distintas, espalhadas entre
Obras/Comercial/Corporativo e SP/MT/PR, ao longo de **10 meses seguidos**
(jun/2023 a abr/2024).

Perguntado sobre a origem desse padrão, o usuário confirmou: **é acordo
coletivo aplicado por lote/obra, não um mês único por UF** — cada frente/obra
processa o reajuste conforme o próprio cronograma, por isso o mesmo % aparece
espalhado ao longo de vários meses em vez de concentrado numa janela fixa.
Isso invalida a ideia de "fora do mês do calendário = Mérito por eliminação".

**Regra final** (`_derivar_classificacao`, app.py): dentro do balde ambíguo
(motivo genérico/nulo, cargo não mudou, salário mudou), um `percentual_reajuste_calculado`
que se repete em **3 ou mais pessoas** (`LIMITE_LOTE_REPETICOES`) é tratado
como Acordo Coletivo em lote — sinal principal, mais forte que o calendário.
O calendário por localidade continua como sinal secundário, pra pegar casos
de % único que a recorrência não cobre. Só cai em "A revisar (Acordo
Coletivo ou Mérito)" quando **nenhum dos dois** sinais bate — nesses casos,
realmente não dá pra saber sem consultar a folha.

**Risco assumido, documentado explicitamente:** um % de Mérito genuinamente
comum (ex.: se a empresa usa uma tabela padrão de Mérito por nível) poderia,
em tese, também se repetir 3+ vezes e ser classificado como Acordo Coletivo
por engano. O usuário confirmou que, nesta base, o padrão observado É de
acordo coletivo em lote — mas se no futuro aparecer um % de Mérito
padronizado igualmente recorrente, essa regra vai errar por excesso de
"Acordo Coletivo". Revisar `LIMITE_LOTE_REPETICOES` se isso acontecer.

## Decisão: filtro dos absurdos (2026-09-17)

Descoberta ao investigar outliers de `percentual_reajuste_calculado`: o
cálculo bate exatamente com `(salario_atual - salario_anterior) /
salario_anterior` (0 divergências >1pp em toda a tabela) — os percentuais
extremos (até 5.435%) não são erro de fórmula, é o `salario_anterior` que é
implausível pra o cargo/nível da pessoa.

Investigação caso a caso (32 linhas com % > 150%) separou 3 grupos:
1. **26 casos de Programa de Experiência/Trainee** (`classificacao_funcionario
   = 'EXPERIÊNCIA'`/`'PRAZO DETERMINADO COM CLÁUSULA'`): sempre COM mudança de
   cargo (ex.: Assistente Técnico → Engenheiro Civil Junior, salário indo de
   ~R$ 4.500 pro valor de tabela do cargo pleno, ~R$ 12.902). Padrão real e
   recorrente (mesmo salário final pra várias pessoas diferentes na mesma
   promoção-tipo) — decisão do usuário: **manter junto** do indicador geral de
   Promoção, sem separar em indicador próprio.
2. **2 casos de Conselheiro** com valores idênticos entre si (mesma data, mesmo
   salário anterior/atual) — suspeito de duplicação de dado, mas pode ser
   reajuste de conselho por resolução (legítimo). Não resolvido, ver item 3.
3. **1 caso claro de erro**: "Presidente Executivo do Conselho de
   Administração" (cargo igual antes/depois) com `salario_anterior = R$
   998,00` — valor implausível pro cargo, quase certo erro de captura na
   fonte (Databricks/folha).

**Regra implementada** (`alerta_absurdo`, `LIMITE_ABSURDO_PCT = 100.0`):
cargo **não** mudou E `percentual_reajuste_calculado` > 100% → marcado como
suspeito. Como todo caso legítimo de trainee/promoção grande **tem** mudança
de cargo, essa regra pega os 3 casos problemáticos (e qualquer outro
igual) sem excluir nenhuma promoção real, inclusive as de trainee. Linhas
marcadas ficam **fora** do cálculo de % médio/máximo/mínimo do KPI, mas
continuam visíveis na tabela Detalhamento com a coluna "⚠️ Revisar" —
decisão explícita do usuário: "vamos manter e fazer um filtro dos absurdos
para corrigir esses erros decorrentes a um mal preenchimento", não excluir
manualmente linha por linha.

## Base paliativa — pipeline Databricks quebrado (2026-09-18)

Usuário reportou que o pipeline Databricks (`mirror_historico_mov.py`) parou
de capturar movimentações corretamente. Confirmado comparando com um export
manual do Oracle Fusion (Catálogo BI → relatório
`PIT_ADM_00024_Historico_Movimentacao_Relatorio` → Exportar → Excel,
2.592 linhas, período 2025-09-01 a 2026-09-01, extraído em 2026-09-18):

| Período | Fonte real (Excel) | Neon (Databricks) | Situação |
| --- | --- | --- | --- |
| set/2025 a mai/2026 | 32 a 274/mês | 20 a 230/mês | Defasagem "normal" de 15-25% (esperado, atraso de sincronização) |
| **jun/2026 em diante** | 979, 318, 130, 68/mês | **3, 5, 5, 13/mês** | **Pipeline praticamente parado** |

**Decisão**: enquanto o pipeline não é corrigido nem a integração via API do
Oracle Fusion é liberada (ver seção seguinte — bloqueada por WAF), os exports
manuais do relatório alimentam uma tabela própria,
`interno.oracle_hcm_historico_movimentacao_paliativo`
(`etl/upload_paliativo_historico_mov.py`, truncate+reload a cada export
novo). Mesmas colunas de negócio da tabela principal — colunas de
proveniência (dq_status, hash_registro etc.) recebem valores sentinela
(`dq_status = 'PALIATIVO_MANUAL'`, `origem_tabela =
'EXCEL_MANUAL_ORACLE_FUSION_BIP'`) pra deixar a origem rastreável em
qualquer consulta direta no Neon.

`app.py` (`load_data()`) faz a fonte paliativa **substituir por inteiro** o
mesmo período na fonte Databricks (não é um merge/preenchimento de buracos
— a paliativa provou ser mais completa mesmo nos meses "normais", então o
corte é simples: `data_efetiva < MIN(data_efetiva da paliativa)` vem do
Databricks, o resto vem da paliativa). O corte é calculado dinamicamente a
cada carga (hoje, na prática, 2025-09-01).

**Achado à parte, não investigado a fundo**: março/2026 tem uma inconsistência
própria mesmo dentro do período "normal" — 274 linhas reais, Neon tinha 230,
mas só ~62 batiam de fato por pessoa+data+motivo+CC+salário (212 reais sem
correspondência no Neon, 168 do Neon sem correspondência na base real).
Cheira a duplicidade ou problema de data específico daquele mês no pipeline
antigo — não investigado, fica registrado caso apareça de novo.

**Pendências desta solução paliativa**:
- Reexportar e rodar `etl/upload_paliativo_historico_mov.py` de novo sempre
  que quiser atualizar (é manual — sem automação de calendário/e-mail ainda,
  ver seção "Tentativas de automação" abaixo).
- Cuidado com o limite de 260 caracteres de caminho do Windows: o nome
  original do export (`PIT_ADM_00024_..._Histórico de Movimentação.xlsx`)
  somado ao caminho desta pasta de projeto estoura o `MAX_PATH` clássico —
  o arquivo precisa ser renomeado pra algo curto (ex.: `historico_mov.xlsx`)
  antes de qualquer ferramenta consegui abri-lo (`python.exe`/PowerShell
  enxergam a pasta pelo `Get-ChildItem`, mas `os.path.exists` retorna
  `False` até renomear — mesmo bug já visto com
  `mirror_historico_mov.py`, ver seção seguinte).

## Tentativas de automação da base paliativa (2026-09-18)

Antes de aceitar o export manual, tentei 2 caminhos automatizados — ambos
esbarraram em bloqueios fora do meu controle, registrados aqui pra não
repetir a investigação:

1. **API REST/SOAP do Oracle Fusion BI Publisher** — autenticação Basic
   funciona (confirmei OK contra `/xmlpserver/services/v2/*?wsdl` e
   `/xmlpserver/services/rest/v1/reports`), mas **todo POST cujo caminho ou
   corpo contenha uma barra (`/`) é derrubado por um WAF** (renegociação TLS
   seguida de reset de conexão — assinatura típica de proteção anti-bot tipo
   Akamai, confirmado pelo header `AKGRN` nas respostas). GET com o mesmo
   caminho passa normalmente. Como tanto `POST .../parameters` quanto
   `POST .../run` (os únicos jeitos de obter dado real da API) exigem
   caminho de relatório com barra, a API fica inutilizável a partir desta
   rede — precisa de liberação de WAF/allowlist de IP pelo administrador
   Oracle do lado do Pacaembu, não é algo que eu resolvo ajustando a
   chamada. Testado exaustivamente: 6 variações de codificação de caminho
   (barra literal, `%2F`, `%252F`, com/sem `.xdo`, com/sem `/shared`), com e
   sem corpo, JSON e multipart — todas com o mesmo resultado.
2. **Job de e-mail agendado no BI Publisher** — usuário configurou, mas não
   funcionou na primeira tentativa ("vou estudar melhor depois"). Fica como
   caminho a retomar: se funcionar, dá pra automatizar de verdade (eu tenho
   acesso ao conector Microsoft 365/Outlook nesta sessão pra buscar o
   e-mail e o anexo automaticamente, sem intervenção manual).

## Migração de fonte: `oracle_hcm_historico_movimentacao` (2026-09-18)

Usuário reportou que `interno.fato_movimentacao` não tinha informação
suficiente e apontou uma tabela nova no Databricks:
`rh.silver.oracle_hcm_pit_adm_00024_historico_movimentacao_relatorio` — direto
do Oracle HCM (o sistema citado na política PLREMU-01), camada silver com
`dq_status`/`dq_regras` (regras de qualidade já aplicadas na origem) e chaves
imutáveis (`id_historico_movimentacao`, `hash_registro`).

**Duplicação encontrada e tratada:** a tabela tinha 8.167 linhas — quase 2x
o esperado. Investigação (`silver_batch_id`) revelou 2 reprocessamentos
completos quase idênticos da mesma bronze (`50768a68...`, processado
2026-06-21, 4.072 linhas; `e8c5c84a...`, processado 2026-09-11, 4.082 linhas)
mais 13 linhas genuinamente novas do dia (2026-09-18). Confirmado por join
cruzado: 4.084 pares batendo em pessoa+data+motivo+cargo+CC+salário, só a
chave técnica mudando. Deduplicado em
`etl/mirror_historico_mov.py` (script pequeno mesmo, gitignored
`etl/.oauth_token_cache.json`) via `ROW_NUMBER() OVER (PARTITION BY <chave
de negócio> ORDER BY silver_data_processamento DESC)`, mantendo só a versão
mais recente por evento real. Resultado: **4.095 linhas** — muito próximo do
`fato_movimentacao` antigo (4.088), confirma que é o mesmo universo de
eventos, só que mais limpo.

**Nova tabela no Neon**: `interno.oracle_hcm_historico_movimentacao` (mesmas
colunas da fonte + `dq_regras` como JSONB). App.py migrado pra ler dela como
fonte principal (decisão do usuário, "sim, trocar agora").

**Achado importante — fórmula de `percentual` diferente**: a coluna
`percentual` desta tabela é `(atual − anterior) / atual`, não `/ anterior`
(confirmado: bate em 4.073 de 4.083 linhas testadas, contra só 3.059 pra
fórmula `/anterior`). Isso "comprime" outliers automaticamente (nunca passa
de 100% quando o valor anterior é pequeno) mas não é a convenção padrão de
RH pra "% de aumento". Decisão do usuário: **ignorar essa coluna e recalcular
`/anterior`** em `app.py` (`percentual_reajuste_calculado`, `valor_reajuste`
= `salario_atual - salario_anterior`) — mantém o "filtro dos absurdos"
necessário, mas preserva o significado convencional do indicador.

**Qualidade de dado da fonte**: `dq_status`/`dq_regras` só sinalizaram 2
linhas (`PERCENTUAL_FORA_FAIXA_REFERENCIAL`, limite -100% a 1000% — na
fórmula `/atual` da própria fonte). O caso do R$998→R$55.244 (Presidente)
não foi pego por essa regra porque, na fórmula `/atual`, dá só 98,19% —
mais um motivo pra não confiar cegamente na coluna `percentual` da fonte.

**Colunas que a tabela nova NÃO tem** (existiam em `fato_movimentacao`):
`gerenciamento_nivel_cargo`, `status` (Ativo/Inativo), `nome_diretoria`
bruto, `tempo_casa_meses`/`faixa_tempo_casa`, `movimentacao_verificado`,
`descricao_mudanca`. Resolvido:
- `nome_diretoria`/`nome_area`: já resolvidos via `mapping_diretoria`
  (Neon), não dependia da coluna bruta mesmo antes.
- `gerenciamento_nivel_cargo` e `status`: cruzados em `load_data()` por
  `id_funcionario` (`numero_pessoa` da fonte) contra `interno.fato_funcionario`
  (roster completo, ativos+inativos, já existente no Neon via Headcount
  Total). **Limitação aceita**: é o nível/status ATUAL da pessoa, não
  necessariamente o nível no momento exato daquela movimentação histórica —
  decisão do usuário ("cruzar por pessoa", opção recomendada), sem tabela
  de histórico de nível disponível no momento.
- `tempo_casa_meses`/`movimentacao_verificado`/`descricao_mudanca`: não
  recriados — não eram usados em nenhum cálculo do app (só documentação/
  mock antigos), removidos sem impacto.

**Renomeação de colunas** (`app.py`, bloco de preparo de dados): a tabela
nova usa `numero_pessoa`/`centro_custo_atual`/`centro_custo_anterior`/
`descricao_centro_custo_atual`/`descricao_centro_custo_anterior` em vez de
`id_funcionario`/`centro_de_custo_atual`/`centro_de_custo_anterior`/
`nome_centro_custo_atual`/`nome_centro_custo_anterior` — renomeado logo após
o load pra manter o resto do app (e o mock local) inalterado.

**Nota técnica de ambiente**: o primeiro arquivo do script de mirror
(`mirror_historico_movimentacao_to_neon.py`, nome completo) ficou invisível
pra `python.exe`/PowerShell (mas visível pro Bash e pro próprio Claude Code)
porque o caminho absoluto passava de 260 caracteres (limite clássico do
Windows, `MAX_PATH`). Renomeado pra `mirror_historico_mov.py` — mais um
motivo pra manter nomes de arquivo curtos nesta árvore de pastas (o caminho
do projeto já é longo por si só).

## Regra de negócio V3 — 3 baldes finais (2026-09-18)

O usuário definiu a regra de negócio definitiva por cima do `nucleo_movimentacao`
já existente (função `_derivar_classificacao`, `app.py`), consolidando tudo
num campo novo, `balde_final`:

| `balde_final` | Quando |
| --- | --- |
| **Promoção** | núcleo = Promoção (com ou sem transferência junto) |
| **Aumentos Salariais** | núcleo ∈ {Mérito, Enquadramento, Equiparação Salarial, Reclassificação, Espontâneo, Aumento de Carga Horária} (com ou sem transferência junto) — os 3 últimos foram decisão minha por analogia, confirmada pelo usuário via pergunta explícita |
| **Transferências** | `cc_mudou=True` e núcleo não é Promoção/Aumento Salarial (cobre transferência pura e transferência + Adequação) |
| **Descartado** | núcleo = Acordo Coletivo, mesmo combinado com transferência — decisão do usuário, sai de qualquer indicador |
| **A revisar** | núcleo = "A revisar (Acordo Coletivo ou Mérito)" — decisão do usuário: fica visível à parte (não conta em nenhum dos 3 baldes nem no total de Movimentações), pra não jogar fora Mérito real nem inflar Acordo Coletivo |
| **Adequação (sem card)** | cargo mudou, salário e CC não mudaram — contabilizado (aparece nos totais brutos/tabelas), mas sem KPI próprio |
| **Admissão** / **Sem evento** | Como antes — fora de tudo |

`Movimentações = Promoção + Aumentos Salariais + Transferências` (soma exata
dos 3 baldes principais) — implementado na aba "Aumentos Salariais", que
virou também o painel geral de totais (ver seção seguinte).

## Migração do mapeamento de diretoria/área pro Neon (2026-09-18)

Motivo: a Aderência Salarial quebrou no deploy porque o mapeamento vivia só
num JSON gitignored (`etl/data/cc_mapping.json`) — sem esse arquivo no clone
do Streamlit Cloud, a resolução de diretoria falhava antes até da tela de
login aparecer (bug documentado no CONTEXT.md daquele projeto,
2026-09-15). Decisão do usuário: resolver de vez, subindo o mapeamento pro
Neon em vez de depender de arquivo local em qualquer painel novo.

Criadas 2 tabelas no schema `interno` (`etl/upload_mapeamento_diretoria.py`,
truncate + reload a partir dos mesmos JSONs que já existiam em `etl/data/`):
`interno.mapeamento_diretoria` (546 linhas, default por centro de custo) e
`interno.mapeamento_diretoria_especial` (22 linhas, overrides por pessoa/
posição — mesma estrutura de `special_mappings.json`). `etl/mapping_diretoria.py`
agora consulta o Neon primeiro; só cai pros JSONs locais (se existirem) como
fallback de última instância — nunca quebra o app.

**Não migrado ainda**: Headcount Total e Aderência Salarial continuam lendo
os JSONs locais. Se quiserem, dá pra portar os 2 pra ler do Neon também (a
tabela já existe e serve os 3 painéis) — não fiz isso agora porque não foi
pedido nesta sessão.

## Redesenho da aba "Aumentos Salariais" (2026-09-18)

Virou também o painel de totais gerais do período (pedido do usuário):
- Título "Total Movimentações no Período" + 4 cards (Promoção, Alterações
  Salariais, Transferências, Movimentações = soma dos 3), com uma legenda
  abaixo informando quantos casos de Acordo Coletivo foram descartados e
  quantos ficaram "A revisar" (transparência, sem inflar nem esconder).
- Gráfico de colunas por balde (mês a mês) + linha de acumulado (escala
  própria, eixo direito) — "quantidade de movimentações ao longo do tempo,
  com o total rodando".
- Filtro **checkbox removido**; agora é um multiselect sobre os núcleos
  (Promoção, Mérito, Enquadramento, Equiparação Salarial, Adequação) que
  controla a evolução mensal e os 3 pares de gráfico Qtd+%méd / R$ médio
  (por tipo, por Diretoria, por Nível de Cargo) — unifiquei os 2 pedidos do
  usuário ("filtro de Aumento Salarial/Promoção/Enquadramento" e "evolução
  mostrando Promoção/Adequação/Enquadramento/Equiparação/Mérito") num único
  controle, porque os dois textos descreviam o mesmo conjunto de tipos com
  palavras um pouco diferentes — **checar se essa unificação bate com a
  intenção real**.
- "R$ médio de aumento" = média de `valor_reajuste` (o R$ absoluto do
  reajuste, não o salário final) — assunção minha, não confirmada
  explicitamente.
- Disclaimer de política de remuneração: **placeholder**, sem texto real —
  preciso do conteúdo oficial da política antes disso valer pra uso externo.
- "Tempo médio até 1ª promoção" e "Compressão salarial pós-movimentação"
  (indicadores extras aprovados em 2026-09-17) mantidos, sem alteração.

**Abas "Movimentações" e "Transferências" não foram redesenhadas** — só o
motor de classificação por baixo delas mudou (`balde_final` existe, mas essas
2 abas ainda leem `tipo_movimentacao`/`cc_mudou` como antes). Pode gerar
inconsistência entre o que a aba 1 chama de "Total de Transferências" e o
que a aba 3 mostra, até essas 2 abas serem atualizadas — pendente instrução
do usuário.

## Filtro de período: De/Até, padrão últimos 12 meses (2026-09-18)

Substitui o multiselect de Ano por `st.date_input` em modo intervalo,
filtrando por `data_efetiva`. Padrão: dos últimos 12 meses até a data mais
recente da base — mesmo com histórico voltando a 2012, decisão explícita do
usuário. Filtro de Área adicionado (`nome_area`, resolvido junto com
diretoria via `mapping_diretoria.resolve_diretoria_area`).

## Decisão: correção de diretoria/área via cc_mapping.json (2026-09-17)

Aplicado imediatamente (não ficou só no `.str.strip()` básico) — mesmos 2
JSONs (`etl/data/cc_mapping.json`, `etl/data/special_mappings.json`,
gitignored) e módulo (`etl/mapping_diretoria.py`) copiados do Headcount
Total/Aderência Salarial. Resolve `nome_diretoria`/`nome_area` a partir de
`centro_de_custo_atual` + `descricao_posicao` + `id_funcionario`, substituindo
o valor bruto do mirror (que fica desatualizado depois de reorganizações).
Só aplicado quando `source_name == "Neon"` — no modo mock local, mantém
`nome_diretoria` como veio (já limpo por `.str.strip()`).
