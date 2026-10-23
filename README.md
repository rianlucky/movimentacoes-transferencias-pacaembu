# Movimentações — Promoções, Aumentos Salariais e Transferências

Painel da Central de Gente & Dados com as movimentações de pessoal da Pacaembu: promoções, aumentos
salariais (mérito, enquadramento, equiparação…) e transferências. **Painel com login e dado pessoal**
(nome e salário no detalhamento, decisão do Rian em 23/10/2026): acesso pela matriz `acesso.painel`,
código `movimentacoes`, gerência Remuneração e Orçamento de Pessoas.

O raciocínio de cada regra está em `CONTEXT.md`; o histórico de mudanças em `CHANGELOG.md`.

## Rodar localmente

```powershell
pip install -r requirements.txt
streamlit run app.py
```

`.streamlit/secrets.toml` (no `.gitignore`; modelo em `secrets.toml.example`):

```toml
[neon]
database_url = "postgresql://app_movimentacoes:SENHA@HOST/neondb?sslmode=require&channel_binding=require"

[app]
email_suporte = "..."   # mostrado para quem ainda não tem acesso
```

O login é o mesmo dos outros painéis (`auth.py`, tabela `acesso.app_users`). Não há mais modo sem login
(`skip_auth` saiu em 23/10/2026).

## Estrutura

| Arquivo | O que faz |
|---|---|
| `app.py` | tela: 3 páginas (Visão geral, Aumentos salariais, Transferências) |
| `metricas.py` | regra V3 e todos os cálculos, sem Streamlit; usado também por `_neon/validacao/validar_paineis.py` |
| `painel_padrao.py` / `auth.py` | cópias do padrão da Central (barra lateral, cards, gráficos, login) |
| `assets/` | ícone e logo com o nome |
| `_antigo/` | `app.py`, `auth.py` e tema anteriores à migração de 23/10/2026 (fora do git) |
| `etl/`, `scripts/` | **obsoletos**: espelho do Databricks, upload da base paliativa e liberação de acesso antiga. O dado agora chega pelo sync central (Oracle → Neon) e o acesso pela matriz de acessos |

## Dados (Neon, só leitura, usuário `app_movimentacoes`)

| View | Conteúdo | Migração |
|---|---|---|
| `core.v_movimentacoes_base` | um evento do histórico de movimentação do Oracle (relatório 00024) por linha, com diretoria/área oficiais pelo CC do evento, nível pelo vínculo do evento e se a pessoa está ativa hoje | 032 |
| `core.v_movimentacoes_cargo_ativo` | ativos de hoje por cargo, diretoria, área, categoria e nível, com a mediana salarial do cargo | 033 |
| `ops.v_ultima_carga` | "Atualizado em" (tabela `core.oracle_hcm_historico_movimentacao`) | 032 |

Atualização: diária, pelo sync central (`_neon/sync_central.py`, Oracle HCM → bronze → silver → gold → core).

## Regras de negócio

- **Regra V3** (18/09/2026): todo evento cai num tipo. **Movimentações = Promoção + Aumentos Salariais +
  Transferências.** Acordo coletivo fica fora; o ambíguo entre acordo coletivo e mérito fica em "A revisar"
  (fora dos totais, visível no detalhamento). Detalhes em `CONTEXT.md`.
- % de aumento sobre o salário **anterior** (o `percentual` da fonte é sobre o novo).
- Aumento com cargo igual e % acima de 100% sai dos gráficos de % e R$ (provável erro de cadastro) e fica
  marcado no detalhamento.
- Diretoria e área: as do **centro de custo do evento** (numa transferência, o destino), pela regra oficial
  (exceção por pessoa > por posição > CC, `core.mapeamento_diretoria`).
- Taxa de movimentação e % transferidos: pessoas distintas ÷ **ativos de hoje no mesmo filtro**.
- Transferências (página própria): qualquer mudança de centro de custo, mesmo junto de promoção, mérito ou
  acordo coletivo. Por isso o número é maior que o card "Transferências" da Visão geral.
- Tempo até a 1ª promoção: primeira promoção de cada pessoa em **todo o histórico**; entram as que caem no
  período. Admissão = início da cadeia de vínculos (regra D1 da gold).
- Compressão salarial: novo salário do promovido × mediana salarial de quem está ativo hoje no cargo de destino.
- Custo de mobilização: não disponível na fonte.

## O que mudou em relação ao painel anterior (23/10/2026)

| Antes | Agora | Por quê |
|---|---|---|
| Nível e status cruzados **por pessoa** | cruzados pelo **código de atribuição** do evento | quem tinha mais de um vínculo duplicava eventos: 5.513 eventos viravam 7.740 linhas (+40%) e todas as contagens saíam infladas |
| Fonte: histórico do Databricks + base paliativa manual | só `core.oracle_hcm_historico_movimentacao`, publicada pela gold | a gold cobre o período inteiro; o painel não via nada depois de 01/09/2026 |
| Aba Movimentações contava todos os eventos (incluindo acordo coletivo) | conta só os 3 tipos da V3 | ficava diferente do total da primeira aba |
| Taxa dividida pelo headcount da empresa inteira, mesmo com filtro | dividida pelos ativos do mesmo filtro | taxa de uma diretoria saía baixa demais |
| 1ª promoção = primeira dentro do período | primeira de todo o histórico | a 2ª ou 3ª promoção contava como 1ª |
| "Segue ativo" por evento, pelo status do vínculo | por pessoa, se ela tem algum vínculo ativo hoje | transferido por readmissão aparecia como desligado |
| Diretoria por mapeamento em Python (`etl/mapping_diretoria.py`) | na view, mesma regra | uma regra só, a mesma da régua |
| Lia tabelas inteiras e `core_view` (usuário em `grp_app_leitura`) | lê só as 2 views do painel | padrão da Central (sair do `grp_app_leitura`: migração pendente, ver abaixo) |

A classificação V3 em si **não mudou**: aplicada à mesma base, a lógica antiga e o `metricas.py` dão o
mesmo tipo nos 5.379 eventos (conferido em 23/10/2026).

## Conferência

`_neon/validacao/validar_paineis.py`, função `painel_movimentacoes` (relatório diário em
`_neon/validacao/relatorios/`). Em 23/10/2026: 8 comparações ✅ (eventos na view × histórico; eventos,
mérito, enquadramento e convenção coletiva do mês anterior × histórico; ativos e ativos da Comercial ×
régua; eventos sem diretoria = 0).

57 eventos antigos (2014–2024) ficam com diretoria "Não informado": centros de custo extintos, fora do
mapeamento. Não aparecem no período padrão.

## Publicação

No ar desde 23/10/2026: https://movimentacoes-transferencias-pacaembu.streamlit.app/ (card no Hub de
Indicadores). O usuário de banco `app_movimentacoes` lê só as 2 views, `ops.v_ultima_carga` e o login
(migração 034: saiu do `grp_app_leitura`).

Pendente: apagar `etl/`, `scripts/` e `base paliativa/` (fora do git) quando não forem mais necessários.
