# minimax-video-factory — handoff, atualizado 2026-08-19 22:00

**Este arquivo agora vive no repositório.** Antes ele estava em
`~/bkp/minimax-night/HANDOFF.md`, fora do git — e por isso toda sessão nova
começava sem memória nenhuma. As regras permanentes foram para o
[`CLAUDE.md`](https://github.com/leonardodg/minimax-video-factory/blob/main/CLAUDE.md)
da raiz, que o Claude Code carrega sozinho em toda
sessão; aqui fica o **estado**: o que está rodando, o que já foi medido, o que
está pendente. **Atualizar aqui**, não num arquivo solto no home.

A noite de 07/08 → 08/08 rodou inteira e mediu o que precisava ser medido. As
regras antigas deste arquivo eram do INT4 e **metade caiu**. O que está abaixo
é o estado atual, com os números que substituíram os chutes.

---

## 🔄 EM ANDAMENTO 2026-10-07: atualização completa (deps/ComfyUI/Docker/MCPs/testes)

Plano mestre: `~/.claude/plans/vamos-atualizar-a-lista-groovy-sun.md` — cópias
versionadas em `docs/PLANO_ATUALIZACAO.md` (este repo) e no `insta_kb`.
**Branch: `update/deps-2026-10`** (PR no fim). Execução inline, 10 tasks
(0-9), status da tabela no próprio plano.

| Task | Descrição | Status | Evidência |
|---|---|---|---|
| 0 | Commits pendentes + baseline + cópias do plano | ✅ | baseline `9 passed`; commits `44b6406` (INT8/nvfp4), `4b34bd2` (MCP_TOOLS), `376e6ae` (plano) |
| 1 | Deps insta_kb | ✅ | no repo `insta_kb` (`58e8093`+`d034fd0`); ver HANDOFF de lá |
| 2 | Deps minimax | ✅ | `fastmcp>=4.0.11`+`av==18.1.0`+`requires-python>=3.11`; commits `715216e`+`83c8454` |
| 3 | ComfyUI v0.39.1 + nodes + pesos | ⏳ | |
| 4 | Docker insta_kb (Parte B) | ⏳ | |
| 5 | MCPs do OpenCode | ⏳ | |
| 6 | Matriz de testes | ⏳ | |
| 7 | Fila do insta_kb (329 msgs) | ⏳ | |
| 8 | Documentação | ⏳ | |
| 9 | Diagramas | ⏳ | |

Regra de GPU durante toda a execução: 1 job (render/transcrição/Ollama) por
vez; `av==18.1.0` fixo nos 2 repos; nenhum download de peso sem OK.

### Task 2 ✅ (2026-10-07): deps minimax — fastmcp 4, av 18.1.0

- **Versões no lock:** fastmcp 4.0.11, av 18.1.0 (nunca 19.x), yt-dlp
  2026.8.19, pydantic 2.13.5, ruff 0.16.10, pylint 4.1.2. Validação:
  ruff clean, `9/9` testes, smoke import `fastmcp 4.0.11 | av 18.1.0`.
- **fastmcp 3→4: sem breaking changes no uso atual.** `server.py` só usa
  `FastMCP`, `@mcp.tool()` function-mode e `mcp.run(transport=...)` — nada
  de sampling/roots/shims 3.x (todos removidos na 4.0.0). Review confirmou
  que `FastMCP.run` 4.0.11 aceita os 4 transports, inclusive o
  **`streamable-http`** da produção (`.mcp.json`).
- **Uso de cliente também OK:** `fastmcp.Client` + `StdioTransport`
  (usados em `scripts/generate_mcp_docs.py`, `scripts/demo_aurora.sh`,
  `tests/07_e2e_agent.sh`) importam em 4.0.11 — os 9 testes não os cobrem;
  Task 8 (geração de docs) é a primeira execução real.
- **Desvio 1:** `requires-python >=3.10` → `>=3.11` — `av==18.1.0` exige
  ≥3.11 e o uv não resolvia para 3.10 (EOL desde 2025-10; runtimes reais:
  host 3.14, venv MCP do container 3.11). README/dev-environment
  atualizados (badge 3.11+, FastMCP 4.x).
- **Desvio 2 (corrige o próprio baseline):** o HANDOFF registrava baseline
  `9 passed`, mas no HEAD `5b47daa` o teste `unit_privacy` estava RED — o
  plano versionado (`376e6ae`) continha 34 caminhos `/home/...` e o teste
  anti-vazamento existe só neste repo. O commit `715216e` (plano sem home
  paths, `$HOME/`) é o que deixa o repo verde de verdade; baseline correta:
  `9 passed` **a partir de `715216e`**.
- **Caveat Task 3:** `docker/Dockerfile` só copia `pyproject.toml` (não
  `uv.lock`) e faz `uv sync` sem `--frozen` → a imagem re-resolve dos
  ranges (`av` pin protege, `fastmcp>=4.0.11` flutua). Decidir no rebuild:
  `COPY uv.lock` + `--frozen` (reprodutível) ou registrar float.
- **Nota insta_kb:** sem teste `unit_privacy`; a regra de "nenhum
  `/home/...` em arquivo rastreado" vale só para este repo público.

## ✅ CONCLUÍDO em 2026-10-06: domínio Instagram/KB saiu deste repo

**Objetivo (cumprido):** este projeto nasceu só para gerar vídeo (ComfyUI +
MiniMax H3), mas acumulou um segundo domínio inteiro (base de conhecimento do
Instagram: Postgres+pgvector, RabbitMQ, `ig-worker`, Ollama). Esse segundo
domínio foi **migrado de verdade** (dados reais incluídos) para um projeto
novo e independente, [`insta_kb`](https://github.com/leonardodg/insta_kb) —
ver `insta_kb/docs/HANDOFF.md` e o README de lá, agora documentação completa.

Plano completo (todas as decisões, fases, critérios de verificação):
`~/.claude/plans/task-notification-task-id-a46236a77511d-valiant-cray.md`.

### O que foi feito, nesta ordem, cada um verificado antes do próximo

1. **Código e dados reais migrados para `insta_kb`** — 3403 documentos /
   12755 chunks / 12755 embeddings no Postgres do `insta_kb` (porta 5433),
   filas `ig.saved`/`ig.saved.dead` migradas via backup/restore de
   definições do RabbitMQ. `insta_kb` agora na `main`, 136 testes, pyright
   strict/ruff/bandit/pip-audit limpos, README completo.
2. **Limpeza deste repo, no worktree `worktree-separar-python-comfyui`**
   (commit `1e5efe2`): `server.py` reduzido às 12 tools de vídeo;
   `db.py`/`ig_queue.py`/`ig_sync.py`/`ig_worker.py`/`knowledge.py`/`llm.py`/
   `vault.py` deletados; `pyproject.toml`/`uv.lock` sem as deps do KB;
   `docker/docker-compose.yml` caiu de 5 para 2 serviços (`comfyui`, `mcp`);
   os 4 scripts `ig_*` rastreados migraram para `insta_kb/scripts/` com
   imports corrigidos (verificado por import real, não só sintaxe); 13
   arquivos de teste que só testavam os módulos deletados saíram; o catálogo
   de slash commands (`catalog.py`, `overrides.py`) perdeu as entradas
   `kb-*`/`ig-*`, e os 26 `.md` órfãos de comando saíram de
   `.opencode/command/`/`.claude/commands/`.
3. **Documentação limpa, mesmo worktree** (commit `b52ee21`):
   `docs/KNOWLEDGE_BASE.md` e `docs/OPERACAO_IG.md` (eram tutoriais completos
   de 458+200 linhas) viraram redirecionamentos para `insta_kb`;
   `docs/dev/{modules,extending,contributing,index}.md`, `docs/index.md`,
   `docs/api.md` perderam as seções do domínio migrado;
   `tests/08_knowledge.sh` (chamava tools que não existem mais, rodava de
   verdade via `diagnose.sh`) foi deletado; `README.md` com os números
   certos (12 tools, não os "18"/"24" que já estavam errados antes) e um
   link para `insta_kb` como projeto relacionado.

### O que falta

- **Mergear o worktree para `main`.** Ainda não feito. `git status` na raiz
  do repo (fora do worktree) tem mudanças soltas e não investigadas nesta
  sessão: `pyproject.toml` (+1 linha), `scripts/config.sh`,
  `scripts/ig_reprocessar.py`, `src/minimax_mcp/core.py`,
  `src/minimax_mcp/server.py`, `uv.lock`, `workflows/minimax_h3_t2v_api.json`,
  e não-rastreados `.codex/`, `.pylintrc`, `database.db`,
  `scripts/ig_catchall_check.py`, `scripts/ig_replay_dlq.py`,
  `scripts/ig_sync_bg.py` — provavelmente trabalho anterior do usuário,
  independente deste refactor. Checar com o usuário antes do merge (vai
  precisar resolver conflito em `docs/HANDOFF.md`, que diverge entre a
  branch e este arquivo na `main`).
- **Reconstruir o container `comfyui`/`mcp` com o código novo** — o
  `test_container_deps` (marcador `integration_db`) falha de propósito até
  isso acontecer: o container em execução ainda responde com 26 tools,
  a fonte já declara 12. `docker compose build mcp && docker compose up -d`
  depois do merge resolve.
- Task #8 do plano original (os "4 lugares" por tool MCP) — já feito **aqui**
  neste repo; conferir se vale regenerar um equivalente no `insta_kb` (que
  nunca teve `catalog.py`/`unit_registry` próprio).

---

## ✅ CONCLUÍDO em 2026-08-19: o sync do Instagram e cinco defeitos de conteúdo

**A catch-all está resolvida.** A seção anterior deste arquivo dizia que ela
morria inteira e que faltavam "~495 posts"; os dois fatos mudaram.

### Onde a base está

```
catch-all "All posts"   3375 posts sadios (+1 que não converte, ver abaixo)
processados             3366  =  99,7%
fora                       9
DLQ                       10  (nenhum com conserto de código)
```

O número "~507 perdidos" que este arquivo trazia era **subtração de dados
velhos**, não medição. Medido em 2026-08-19, os posts que só a correção
alcançava eram **219** — o usuário dessalvou posts no intervalo e as coleções
nomeadas passaram a cobrir mais.

### O defeito da catch-all: um post derrubava 3375

Um post salvo volta sem o campo `code`. `Media.code` é obrigatório no modelo do
instagrapi (`types.py:518`), o pydantic levanta dentro da list comprehension de
`mixins/collection.py:131`, e a perda **cascateia por quatro níveis**: o item
derruba a página (~20-50 posts) → a exceção sobe pelo laço de paginação, onde
`total_items` é local, levando **todas as páginas já lidas** → o `except` de
coleção do `saved_posts_by_collection` engole o resto.

Reproduzido ao vivo às 11:13 de 2026-08-19, oito dias depois do primeiro
incidente: paginou 15min22 e jogou os 3375 fora no último trecho. Não era
azar — era determinístico.

**Corrigido** (`daa8515`): `parse_items_tolerant` converte item a item, abaixo
do `collection_medias` — que é o único lugar onde o item ruim ainda existe.
Depois da correção: 0 → **3375 enumerados, 1 descartado**
(`ig_pk=2546806014584256281`, netshoes, sem `code`), com o payload cru em
`output/ig-descartados.jsonl`.

### Os cinco cortes silenciosos de conteúdo

Achados ao investigar por que os resumos inventavam. **O pior não estava no
nosso código:**

| # | corte | medida | commit |
|---|---|---|---|
| 1 | **`num_ctx` do Ollama = 2048** e ele corta **pela frente** | enviados 7206 tokens → leu 2051, HTTP 200, sem aviso | `b0139e7` |
| 2 | Legenda descartada ao reaproveitar mídia do disco | 21 de 24 documentos, correlação 21/21 | `b0139e7` |
| 3 | Só 80 caracteres da legenda entravam na fila | `caption.splitlines()[0][:80]` | `b0139e7` |
| 4 | `body[:4000]` na ingestão de markdown | nota longa entrava pela metade | `b0139e7` |
| 5 | `num_predict` 512 na leitura de tela, 2048 no resumo | 111 tutoriais terminavam sem pontuação | `b0139e7` |

O experimento que decide o item 1, e que vale repetir se alguém duvidar:

```
enviados 7206 tokens, num_ctx padrão -> leu 2051
  pergunta: "qual é o MARCADOR-INICIO e qual é o MARCADOR-FIM?"
  resposta: "O marcador início é JABUTICABA e o fim é JABUTICABA"
             (JABUTICABA era o do FIM)
mesmos 7206 tokens, num_ctx=8192     -> leu 7768, acertou os dois
```

**Ele não falha, responde com confiança usando o que sobrou.** E como o molde do
prompt vem no começo e o material no fim, o que se perdia num documento longo
eram as **instruções**. Subir o teto não bastava — o precipício só muda de
lugar —, então `orcamento_de_material` + `cortar_material` fazem o corte ser
nosso: do material, na fronteira de palavra, preservando o começo, com WARNING
dizendo quanto se perdeu.

### Legenda e descrição visual agora entram sempre (`6a1c657`)

Decidido com o usuário. A legenda era usada **só** quando não havia fala, com o
argumento de que é divulgação — mas em receita e tutorial é nela que estão os
ingredientes e as medidas. O `strip_cta` tira a divulgação; jogar a legenda
fora tirava junto o conteúdo.

E **LER não é DESCREVER**: o caminho de vídeo só lia o texto da tela;
`describe_image` nunca rodava em vídeo. Num vídeo de receita sem narração isso
mandava ao modelo o título e mais nada, com o preparo inteiro nos quadros sem
ninguém olhar. Foi assim que "Faça seu presunto cozido" (80 caracteres) virou
um passo a passo inventado, e o post de um **cachorro** virou conselho de
paternidade.

Ordem do documento, por confiabilidade: **fala → texto na tela → descrição
visual → legenda**.

### As outras três correções da mesma rodada

| commit | o quê |
|---|---|
| `e406714` | `.webp` (Ollama devolvia 400: `Failed to load image or audio file`), vídeo sem faixa de áudio (`IndexError` do PyAV), e o retry passou a cobrir JSON válido de esquema errado |
| `79db6dd` | Carrossel misto: `.mp4` ia para o modelo de imagem, e **uma** descrição falha abortava o carrossel inteiro |

### Reprocessamento: o que foi e o que falta

- **Grupo A** (76 documentos afetados pelo `num_ctx`): **59 refeitos**, 17
  pulados por não terem mais mídia no disco, zero falhas. Backups em
  `output/kb-backup-reprocess/`.
- **Grupo B** (21 documentos sem legenda): **PENDENTE**, bloqueado pelo
  Instagram.

⚠️ **Rodar o grupo B só com o Instagram acessível.** Provado em 2026-08-19: sem
a legenda, reprocessar só troca uma invenção por outra — o doc 3633 saiu de
"como nomear um novo filho" para "guia para apresentar seu recém-nascido", com
tutorial mandando os convidados se ajoelharem. É desperdício de GPU.

### ⛔ O Instagram bloqueou por excesso de requisições

Causa raiz desembrulhada, não suposta:

```
RetryError  ->  ResponseError: too many 429 error responses
```

Não é sessão inválida (a nova está no `.env` e no container, hashes conferidos),
não é rede (o host alcança `i.instagram.com`). É a conta apanhando pelo volume
de 2026-08-19: duas varreduras completas de ~350 requisições, mais as
tempestades de 30 redirecionamentos que o sessionid expirado provocava.

**Só o tempo resolve.** Renovar sessionid não ajuda, e insistir piora — cada
tentativa conta contra o mesmo teto. Testar com **uma** chamada antes de
qualquer lote.

### Os 9 que continuam fora, e por quê

| causa | posts | tem conserto? |
|---|---|---|
| LLM insiste no esquema errado | 4 | talvez — salvar o `resumo` do JSON que ele devolve |
| Indisponível no Instagram | 2 | **não** — o post não existe mais |
| Download vazio | 1 | não |
| Sem texto nenhum | 1 | não |
| Bug `psycopg` (dict cru indo ao Postgres) | 1 | sim, mas é outro assunto |

Sobre os 4 do LLM: eu havia concluído que era comportamento **estável** do
modelo, não sorteio. **Um deles voltou** no segundo reprocessamento, o que
enfraquece a conclusão — é estocástico com probabilidade baixa. Duas tentativas
não bastam para esses posts.

### Ferramentas que nasceram nesta rodada

| script | para quê |
|---|---|
| `scripts/ig_sync_bg.py` | varredura completa em background, com log por coleção |
| `scripts/ig_catchall_check.py` | enumera **só** a catch-all, salva tudo em JSON, não publica nada |
| `scripts/ig_replay_dlq.py` | devolve a DLQ para a fila, deduplicando, com cópia em disco antes |

⚠️ **`ig_replay_dlq.py`: nunca dar `nack(requeue=True)` dentro do laço.** A
mensagem volta na hora e o `basic_get` seguinte a repega — laço infinito,
medido: 2 min e 341 MB de log da mesma dúzia de posts. Segurar tudo sem ack até
a fila esvaziar, e só então decidir o destino.

### Coisas menores, verdadeiras, que vão morder

- **`downloads/ig/<pk>/` é do `root`** (o container escreve lá). Script rodando
  no host não consegue gravar — aparece como `Permission denied: capa.jpg`.
- **O nome do projeto do compose vem da pasta do arquivo**, não do cwd. Com
  `-f docker/docker-compose.yml` a partir da raiz, o projeto vira `docker` e ele
  tenta recriar tudo. Use
  `docker compose -p minimax-video-factory -f docker/docker-compose.yml --env-file .env up -d --no-deps ig-worker`.
- **`docker restart` não relê o `.env`**, e reboot também não: volta o mesmo
  container com a mesma variável. Para trocar o `IG_SESSIONID` é `up -d`.
- **A API de filas do RabbitMQ atrasa alguns segundos.** Logo depois de
  publicar, `ready=0` pode ser mentira — esperar e reconsultar antes de concluir
  que algo se perdeu. Quase virou relatório de perda que não houve.
- **5 documentos ainda passam do orçamento** de 13.293 caracteres com
  `num_ctx=8192`. Agora com WARNING dizendo quanto se perdeu, em vez de silêncio.

### Uma decisão de projeto que ficou em aberto

3277 documentos (96%) não têm seção de legenda — mas **não são 3277 defeitos**:
foram ingeridos quando a legenda só entrava sem fala. A partir de `6a1c657` todo
post novo recebe. Reprocessar os antigos em massa custaria a legenda de cada um
via `media_info`, ou seja, ~3300 requisições ao Instagram. **Não fazer sem
decidir se vale.**

### Histórico: o que mudou no código em 2026-08-10 (`cf5d080`)

| | |
|---|---|
| **Listagem sem teto** | `max_per_collection` 200 → 0. O teto truncava **em silêncio**: a catch-all entregaria 200 de 3618, e Receitas (1124), Inglês (564) e Dev (287) também passavam. Suspeita registrada, não conclusão: "202 posts em vez de 2157" em 2026-08-09 bate com 200 + 2 |
| **Mídia preservada** | `IG_DELETE_AFTER_INGEST` agora é `false` por padrão. Uma pasta por `ig_pk`, e `existing_media()` responde "já está no disco?" **antes** de qualquer requisição — economiza o `media_info`, que é a chamada autenticada, uma por post |
| **`raw_file_path`** | deixou de ser fixo em `None`. A coluna existia e estava vazia nos 12 primeiros |

A razão das três é a mesma assimetria: **requisição ao Instagram é escassa e
punível; reprocessar na GPU é só tempo de máquina local.** Apagar a mídia
amarrava as duas.

**O que nunca dependeu disso:** refazer resumo, categoria, tags ou prompt do
LLM. A transcrição inteira já fica em `documents.transcription_text` (585 a 4035
caracteres nos 12 primeiros), e para imagem é a descrição da visão que cai lá.

### O que o piloto mediu (40 mensagens, 08:30→09:30)

| | |
|---|---|
| ritmo | **90,8 s por mensagem** — a pausa de 90 s governa, como projetado |
| **disco** | **4,0 MB por post** → **12,4 GB** para os 3111. Estimei 19–31 GB; **errei para cima por 2×** |
| falhas | 15%: 10% vídeo mudo, 5% timeout de CDN |
| bloqueio | nenhum. Zero `public_request`, zero parede de login |

**Vídeo mudo era 15 h de desperdício garantido.** Reel de música: o VAD do
Whisper remove 100% do áudio, a transcrição volta vazia, `ingest_text` recusa, e
o post só morria na DLQ **depois de três tentativas** — sendo que transcrever o
mesmo arquivo dá o mesmo vazio, sempre.

Corrigido em `f1f559c` (decisão do usuário: usar a legenda):

- cai para a legenda **completa**, colhida do `media_info` que o download já faz
  (a mensagem da fila só traz a primeira linha, cortada em 80 caracteres);
- `_download_targets` foi partido em `_targets_from_info`, puro, para o
  `media_info` continuar sendo **um** por post;
- sem fala **e** sem legenda → falha **permanente**, direto para a DLQ. Falha de
  rede continua retentável: só o determinístico perde o retry.

**E o link de todo documento estava quebrado.** A URL era `/p/{pk}/`, mas `/p/`
quer o **shortcode** — por isso o fallback de yt-dlp levava HTTP 400 e nunca
poderia ter funcionado. `ig_sync.post_url()` calcula o shortcode a partir do pk
(mesmo número noutra base, codec do instagrapi), **sem rede**. Conferido contra
um post real: o `code` informado pelo Instagram e o calculado dão o mesmo
`DaqrmRXICEP`. O worker recalcula do `ig_pk` em vez de confiar na mensagem,
porque as 3111 já publicadas carregam a URL velha. **Backfill feito: 55 de 56.**

⚠️ **Trocar o daemon é seguro, e a fila prova.** Ao parar: `unacked` voltou para
`ready` (3067 → 3068), nada se perdeu. Esperar `consumers=0` antes de subir o
novo — o RabbitMQ leva alguns segundos para largar a conexão morta, e subir
antes daria dois consumidores na mesma GPU.

### Ler a tela: o áudio não diz o que importa

O usuário apontou, e a medição confirmou com folga: *"pesquise esse projeto
aqui"*, *"olha esse código"* — o nome e o código estão **na tela**, e o áudio
não os pronuncia. O pipeline não deixava a lacuna vazia: **preenchia com
invenção**.

| post | antes | depois |
|---|---|---|
| `3818562307589048738` | `pip install toastnotifications` (pacote inexistente) | `from win10toast import ToastNotifier` |
| `3839009985007901571` | "aula de português" a partir de um áudio de meme | *Kubernetes in 60 seconds* — o assunto real |

**O desenho é do usuário e é o que faz caber:** a leitura roda **no mesmo
worker, em sequência**, dentro da folga que já existia. Não é paralelismo —
paralelo não cabe, e isso foi medido: o pico do worker é **10,8 GB dos 12,3 GB**
da placa, sobrando 1,4 GB, e o modelo de visão pede ~6 GB.

| | processamento | teto |
|---|---|---|
| antes (109 mensagens) | **29,0 s** | 90 s |
| com leitura de tela (7) | **58,1 s** | 90 s |

Como `pace_sleep_seconds` conta do **início** da mensagem, a leitura encolhe a
pausa em vez de esticar a corrida: **custo de cronograma zero**. `keep_alive=0`
na chamada de visão não é performance, é o que evita OOM.

### ⚠️ Pedir ao modelo não segura invenção. Verificar, sim.

A regra "não invente código" no prompt (`5190c3a`) **falhou onde deveria valer**:
no post do Kubernetes, cuja tela não tem comando nenhum, o tutorial saiu com
`kubectl create pod`, `kubectl expose pod` e `kubectl scale deployment`, todos
inventados. Funcionou só onde o código **existia** na tela — ou seja, onde não
era necessária.

`llm.ancorar_codigo` (`ecd720a`) troca o pedido por **verificação**: todo bloco
cercado e todo span que pareça comando precisa aparecer no material
(transcrição + tela); o que não aparece vira `(não mostrado no material)`. Bloco
cai por **maioria**, não unanimidade — o modelo reformata indentação, e derrubar
bloco correto seria trocar um defeito por outro.

### Disco: respondido por série, não por ponto

| | |
|---|---|
| mídia | **4,0 MB/post** |
| fora da mídia (Postgres, log, capa) | **0,7 MB/post** |
| **total** | **4,7 MB/post** → ~13,6 GB para o que falta |
| livre | 47,3 GB |

⚠️ Um relatório mediu "2,1 GB/h fora da mídia" e **isso era ruído da máquina, não
a corrida** — a série de `output/ig-sync-2026-08-10/disco.csv` mostrou 37 MB/h.
O instrumento antigo só media a pasta que ele mesmo enchia; um ponto isolado não
distingue tendência de ruído.

### O worker tem de viver fora da sessão

`nohup` **não** basta: ele protege de SIGHUP, não de SIGTERM, e o worker morreu
duas vezes junto com o comando que o lançou. `setsid` também não bastou. O que
resolveu:

```bash
systemd-run --user --unit=ig-worker --collect \
  --working-directory="$PROJECT_ROOT" \
  /bin/bash -c 'set -a; . ./.env; set +a; exec ./.venv/bin/python -m minimax_mcp.ig_worker >> <log> 2>&1'
```

`systemctl --user restart ig-worker.service` troca o código. Ao parar, o
`unacked` volta para `ready` (visto: 3067 → 3068) — nada se perde. **Esperar
`consumers=0` antes de subir o novo**, senão são dois na mesma GPU.

### Lista de pendências (não fazer agora)

- **Logger em todo o projeto + nível configurável** (`debug=true` ou
  `info/warn/error`). Pedido do usuário em 2026-08-10: "quando tiver uma folga".
  O `llm.py` não tinha `logger` nenhum até `ecd720a` — o defeito é geral.
- **Reprocessar os documentos antigos**: ~148 nasceram sem leitura de tela, sem
  capa e com tutorial possivelmente fabricado. **Não custa Instagram** (mídia no
  disco) e **não precisa da pausa de 90 s** (ela espaça requisições que não
  haverá): ~68 s cada. Falta um caminho de **atualizar** documento — só existem
  `save_document` e `delete_documents`, então é apagar e recriar, com snapshot
  em JSON antes.
- ~~**Os ~495 posts da catch-all**~~ — **RESOLVIDO em 2026-08-19** (`daa8515`).
  O número real era 219, e eles já estão na base. Ver a seção no topo.
- **Visão às vezes lê errado**: um quadro deu `ToastNotification` e outro
  `ToastNotifier`; como nenhuma contém a outra, as duas ficaram no documento.

### Disco é o recurso apertado

`/home` tinha 51 GB livres (já a 90%) quando o piloto começou. A projeção é
~20 GB de mídia para 3111 posts, mas **é estimativa** — a medida real sai do
piloto: `du -sm downloads/ig` dividido pelo número de pastas, vezes 3111.
Coletor pronto em `scratchpad/ig_report.sh`.

### O que já está pronto e NÃO precisa refazer

| | |
|---|---|
| **Sessão do Instagram** | renovada e validada em 2026-08-10 00:05 |
| **Download de carrossel** | consertado e merjado na `main` (`43453e2`) — era o bloqueio real, não a sessão |
| **Limpeza de CTA** | **na `main`**: `strip_cta` (fala) + `clean_title` (legenda) |
| **Export** | `kb_export` / `kb_export_search` testadas com dados reais |
| **Os 12 documentos** | re-ingeridos e backfillados; backup em `output/kb-backup-antes/` e snapshots em `output/kb-backup/` |

**São 12 documentos com `ig_pk`, todos reais** (ids 154–165). O fixture
`Teste de ingestão` (id 150, `ig_pk` 12345) foi apagado em 2026-08-10 00:40 — ele
tinha `ig_pk`, então entrava em toda consulta de Instagram e ia sujar a contagem
do sync. Snapshot restaurável ficou em `output/kb-backup/150-12345.json`.

Isso torna a verificação de amanhã exata: `/ig-sync` deve devolver
`skipped_existing = 12`. Qualquer outro número é sinal de que algo mudou.

### A armadilha que mais custou

**O venv carrega o `minimax_mcp` do `src/` da `main`, não do diretório atual.**
Rodar o daemon de dentro de um worktree NÃO usa o código do worktree. Foi assim
que os 12 posts saíram sem a limpeza de CTA e precisaram de backfill.

---

## Rodada 3 — desenho de 30 s **com falas** (concluída)

Plano aprovado em 2026-08-09 14:10. Três formas de montar 30 s de desenho,
comparadas no mesmo roteiro, mais diálogo em português — que as rodadas 1 e 2
não tinham (os quatro arcos da rodada 2 eram **mudos**).

| Variante | Montagem | Emendas | Custo |
|---|---|---|---|
| **A** | 2 × 15,08 s @704×384 (97,9 M) | **1** | ~40 min/história |
| **B** | 4 × 7,29 s @1024×576 (103,2 M) com `first_frame`+`last_frame` | 3 | ~1 h 45 (inclui pré-viz a 512×320) |
| **C** | o roteiro inteiro num render só | 0 | ~20 min |

Três coisas que esta rodada descobriu e que mudam o projeto:

1. **`last_frame` existe e nunca foi ligado.** O nó `MiniMaxH3ImageToVideo`
   expõe `first_frame` **e** `last_frame` (confirmado em `/object_info`);
   `core.py` só ligava o primeiro. É o input que força um capítulo a *chegar*
   num quadro conhecido em vez de derivar até onde der.
2. **15 s cabem num render só a 704×384** (97,9 M, abaixo dos 101 M que
   passaram). 30 s deixam de ser seis clipes e viram dois.
3. **Diálogo tem sintaxe:** `(personagem, voz (S1)) says: <d>[Portuguese] fala</d>`,
   dentro dos três campos do model card. Suporte estável a 11 idiomas.

⚠️ **Limite duro:** a faixa treinada acaba em **362 frames = 15,08 s**. 30 s num
render só (736 frames) é 2× fora de especificação — cabe na VRAM (84,4 M a
448×256) mas provavelmente degenera. É o probe P5.

### A sondagem — 5/5, concluída 15:37, nenhum OOM

| | config | Mpf | tempo | resultado |
|---|---|---|---|---|
| P1 | 1024×576 · 5,17 s | 73,1 | 871 s | ✅ diálogo PT transcrito **palavra por palavra**, 2 turnos |
| P2 | 1024×576 · 7,29 s | **103,2** | 1313 s | ✅ **passou** — a faixa não medida era boa |
| P3 | 704×384 · 15,08 s | 97,9 | 1242 s | ✅ **limpo**, 4 falas espalhadas pelos 15 s |
| P5 | 448×256 · 30,67 s | 84,4 | 1094 s | ⚠️ renderiza e **degenera** (cor + tempo do áudio) |
| P4 | 512×320 · 5,17 s | 20,3 | 264 s | ✅ `last_frame` obedecido, SSIM 0,877 vs 0,503 |

**Os três números que mudaram o projeto:**

1. **O teto subiu.** 103,2 M passaram. Não é mais "101 M passou, 128 M estourou" —
   é **entre 103,2 M e 128 M**. Um clipe de 7,3 s a 1024×576 cabe.
2. **15 s a 704×384 saem limpos num render só.** 30 s = dois clipes, **uma emenda**.
   É a variante A, e o P3 mostrou que ela não é um consolo: é a melhor imagem da
   sondagem depois do P1.
3. **362 frames é um limite real, não de VRAM.** Ver a seção nova do `CLAUDE.md`:
   fora da faixa treinada a cor apodrece e o áudio se comprime no início.

Log em `~/bkp/minimax-night/rodada3-probes.log`, saídas em `output/rodada3/`.
Produção de H1 nas três variantes disparada às 15:38 (`rodada3.py H1_raposa:ACB`,
log em `rodada3.log`). Os drivers vão para `scripts/` quando a rodada fechar.

---

## Encerrado: validar os 12 documentos de IG

O usuário vai **ler os 12 documentos já ingeridos** e decidir se o pipeline está
bom o bastante para rodar nos 2145 restantes. Nada roda até essa validação.

```sql
-- docs 118 a 129, todos de Instagram
SELECT id, type, title, tags, summary FROM documents
WHERE ig_pk IS NOT NULL ORDER BY id;
```
```bash
cd ~/tools-local/minimax-video-factory
KB_DATABASE_URL="postgresql+psycopg://kb:kb@127.0.0.1:5432/knowledge" \
  ./.venv/bin/python -c "..."   # ou use a tool kb-buscar pelo MCP
```

**O que já foi medido e NÃO adianta reabrir** (custou ~1 h de GPU):

- Ajustar o prompt de categoria: **não muda nada** (variantes A e B idênticas)
- Reduzir o vocabulário de 26 para 10 curadas: **piorou** (3/4 contra 4/4)
- Trocar para `qwen2.5:32b`: funciona (10 categorias contra 4), mas custa
  **3,5 min por documento** — ~5 dias para os 2157. Inviável.
- **Decisão tomada: aceitar categoria grossa.** O usuário reestrutura as
  próprias coleções depois. Detalhes na seção "Classificação de categoria".

**O que sabidamente funciona** e não deve ser mexido sem motivo: `colecao:` e
`categoria:` separadas, timestamps fora dos embeddings, título derivado do
resumo quando não há legenda, dedupe por `ig_pk`.

Se a validação apontar ajuste, ele é de **conteúdo** (prompt de resumo, o que
entra no documento), não de classificação.

---

## Depois da validação: o sync completo

```
posts salvos no Instagram   2157   (medido)
já ingeridos                  12
faltam                     2145
custo medido                50 s por post  ->  ~30 h de GPU
```

**A fila já é o mecanismo de lote.** `ig_sync.sync_saved_posts` lista **uma vez**
e publica todos os novos no RabbitMQ — persistente, status por mensagem, DLQ com
retry. Publique tudo de uma vez e controle o ritmo pelo **consumo**
(`/ig-worker` e `/ig-worker-stop`).

⚠️ **O limite real é o Instagram, não a GPU.** Em 2026-08-09, duas varreduras
completas em uma hora já geraram 429 e derrubaram coleções inteiras da listagem
(a segunda viu 202 posts em vez de 2157). Cada post ainda faz `media_info` +
download. Ritmo sugerido: lotes de 50–100 posts espaçados por horas.

⚠️ **Não use `ig_reingest.py` para isso.** É um script descartável de teste que
relista as 46 coleções a cada execução — exatamente o que dispara o 429. O
caminho de produção é `sync_saved_posts` / a tool `ig-sync`.

Disco: a mídia é apagada depois de processada, **inclusive quando falha**
(`534ae25`). Não acumula.

---

## O que está rodando agora

| Processo | O que faz | Log |
|---|---|---|
| `rodada32.py` | os dois últimos testes da rodada 3, desde 23:16 | `~/bkp/minimax-night/rodada32.log` |

### ⚠️ O usuário tem worktrees ativos — não encostar

```
.worktrees/cta-export    feat/cta-export-markdown    trabalho dele, 2026-08-09
.worktrees/igsync        feat/ig-saved-sync          trabalho dele (regra 3)
.claude/worktrees/last-frame                          meu, JÁ MERJADO, pode remover
```

Há também um arquivo **dele** sem rastreio na `main`:
`docs/superpowers/plans/2026-08-09-cta-cleanup-and-markdown-export.md`.

> **Nunca `git add -A` neste repo.** Sempre caminhos nomeados, senão o trabalho
> não commitado dele entra num commit alheio. Os 14 commits desta rodada foram
> todos assim.

**O `ig_worker` está PARADO.** Foi encerrado em 2026-08-09 15:44 **a pedido
explícito do usuário**, para não disputar a GPU com os renders da rodada 3.
Encerrou limpo (SIGTERM, `ig.saved` com `ready=0` e `consumers=0`, nada
pendurado sem ack); o último trabalho real dele tinha sido às 08:40, documento
129. **A regra 8 continua valendo:** religar é decisão do usuário, não iniciativa
de sessão nova.

**Rodadas anteriores, fechadas:**

- **Noite (18 renders)** — `[00:00] fila da noite concluída`, `[01:14] fase 2 concluída`
- **Rodada 2 (20 renders)** — `[06:55] rodada 2 concluída`

**Não relançar nada** — conferir sempre antes:

```bash
pgrep -af "round2|night_phase2|tmp/overnight|ig_worker"    # vazio = acabou
grep -v RuntimeWarning ~/bkp/minimax-night/round2.log
```

⚠️ **`pgrep` vazio não significa "terminou".** Às 03:07 o `round2.py` morreu com
pgrep vazio e log sem a linha final: uma exceção na composição matou o processo
e 15 renders nunca rodaram. **Distinguir sempre:** log com
`[HH:MM] rodada 2 concluída` = terminou; pgrep vazio sem essa linha = crashou,
ler o traceback. O `round2.py` é retomável (`already_rendered`), então relançar
não re-renderiza nada pronto.

**O `ig-worker` roda no host e usa a mesma GPU** (Whisper + `lfm2:24b` ~6 GB).
O usuário está desenvolvendo em cima dele. Foi subido em 2026-08-09 07:35 **a
pedido dele**, para a Task 6; fora isso, não parar e não reiniciar por conta
própria.

**Se a VRAM parecer ocupada sem ninguém usando:** o ComfyUI mantém os modelos
residentes depois de um render (10,6 GB com 0% de uso, visto após o
`gpu-validation` do CI). Com a fila vazia, `curl -X POST
http://127.0.0.1:8188/free -d '{"unload_models":true,"free_memory":true}'`
devolve tudo (11162 → 890 MiB). Os modelos recarregam no próximo render.

---

## Entregas da rodada 2 — 4 histórias de 30 s

```
output/round2_final/C1_cartoon_30s_audio.mp4   5,9 MB
output/round2_final/C2_liquid_30s_audio.mp4    3,1 MB
output/round2_final/C3_action_30s_audio.mp4    9,3 MB
output/round2_final/C4_scifi_30s_audio.mp4     4,1 MB
```

**Usar os `_audio`** — os `_30s.mp4` sem sufixo são os originais, com o áudio
desigual, guardados só para comparação.

**20 clipes encadeados, todos entre 903 e 907 s.** 4 s de desvio em 5 h.

### O áudio precisou de um passo à parte

O encadeamento resolve a imagem, **não o som**: não existe `first_audio`, o
modelo não aceita condicionamento de áudio, então cada capítulo inventa a
trilha do zero. Medido, por capítulo: C2 variou **31,7 dB** (−43,6 a −11,9) e
C4 **29,7 dB** — os primeiros capítulos praticamente inaudíveis, depois
estourando.

`unify_audio.py` corrige por **ganho estático** (mede LUFS, aplica a diferença
até −21), limitador, e fades de 80 ms nas emendas. Deliberadamente **não** usa
`acrossfade`: ele sobrepõe os trechos, encurta o total e dessincroniza áudio e
vídeo. Vídeo copiado bit a bit — verificado por hash, sai idêntico ao render.

**Parte do degrau foi autorada, não é defeito do modelo:** os prompts do C2
pediam silêncio nos primeiros capítulos (*"single drops, then quiet"*). Em
rodadas futuras, a direção de áudio precisa de nível constante entre capítulos.

---

## Os números medidos — não remedir

### O teto de VRAM é um orçamento único

Não são dois limites (resolução e duração), é **um produto**:
`largura × altura × frames`. Sete pontos, uma conta só:

| pixel-frames | configuração | |
|---|---|---|
| 59 M | 512×320 · 15 s | ✅ 710 s |
| 73 M | 1024×576 · 5 s | ✅ 886 s |
| 91 M | 1152×640 · 5 s | ✅ 1101 s |
| **101 M** | **1216×672 · 5 s** | ✅ 1262 s — **maior que passou** |
| **128 M** | **1344×768 · 5 s** | ❌ OOM |
| 142 M | 1024×576 · 10 s | ❌ OOM |
| 213 M | 1024×576 · 15 s | ❌ OOM (três vezes: E2, G1, G2) |

> **Teto entre 101 M e 128 M.** Resolução e duração pesam igual — gasta-se o
> orçamento em uma **ou** na outra, nunca nas duas.

Máximo por clipe: **~5 s a 1024×576** (7 s bate no teto, nunca testado) e
**~5 s a 1216×672** (já *é* o teto). Passar disso é composição.

### Tempo: 12 s por megapixel-frame

Linear, sem termo quadrático, em 4 resoluções e 2 durações (12,0 / 12,0 / 12,1 /
12,5). **Os "175 s por segundo de vídeo" do handoff antigo só valem a 1024×576.**
O 512×320 de 5 s dá 13,7 — é o carregamento do modelo diluído num render curto.

### Steps são proporcionais e não compensam

F1 a 30 steps: **1341 s** contra 886 s a 20 = **1,514×** para 1,5× de steps.
Custo integral. Com INT4 não houve ganho de qualidade; com INT8 ninguém avaliou
a diferença ainda.

⚠️ **Essa proporcionalidade é a razão de a Turbo LoRA valer tanto.** 1,514× para
1,5× de steps significa que o termo fixo (carregar modelo, encodar texto, decodar
VAE) é ~zero no total: **o tempo é o sampler.** Cortar de 20 para 6 steps corta o
render na mesma proporção. Ver a seção da Turbo LoRA abaixo.

### O teto de resolução subiu 39% com o INT8

Era 1024×576, medido com INT4 (11 GB). O INT8 (21 GB, com `--lowvram` fazendo
streaming da RAM) aguenta **1216×672**.

### Rosto e texto não quebram mais

A regra antiga — *"água e nuvens aguentam; rosto, texto, cidade e multidão
quebram"* — era do INT4. `B1_face_text` (1024×576, 901 s) saiu **"excelente"**
na avaliação do usuário. `B2_crowd` e `B3_glass` também renderizaram.

### 512×320 é 3,3× mais barato

279 s contra 886 s. E foi o **único** que entregou 15 s num render só.

---

## 👉 PRÓXIMO: o teste de 30 s da ROSY (preparado, **nada renderizado**)

Roteiro completo, pronto para executar sem reconstruir contexto, no projeto
ROSY (fora deste repo, que é público):

**`$HOME/Documents/Projects/Rosy/docs/Identity/TESTE_30S.md`**

4 cenas · 576×1024 · 175 frames cada = **29,17 s** · 6 steps turbo · ~27 min de
GPU. Receita `recipe_004`, Smoothie Verde. Os prompts já saem expandidos em
`Rosy/assets/prompts/teste_30s/prontos/`, montados a partir de `_persona.txt`.

103,2 Mpf por clipe: é a configuração do maior render que já passou aqui
(`1024×576 · 7,3 s`, mesmos pixels, girado). Fallback documentado se der OOM.

O que ele põe à prova, e nenhuma dessas coisas foi medida ainda: turbo em
**quatro** clipes seguidos (validado em um só, de 5 s), a persona nova (loadout
base da folha 14, nunca renderizada), consistência entre 4 cenas **sem**
encadeamento de frame, a resolução 512×896, e o degrau de áudio a 4 capítulos.

Antes de submeter: fila zerada, **1587 nós** em `/object_info`, e avisar que o
`ig-worker` disputa a mesma GPU.

---

## 🆕 2026-08-11: Turbo LoRA + os custom nodes — instalado e **validado**

### O resultado

```
turbo6        6 steps   310 s    4,2 s/Mpf   output/validacao_turbo/turbo6_00001_.mp4
baseline20   20 steps   857 s   11,7 s/Mpf   output/validacao_turbo/baseline20_00001_.mp4
                                 ganho 2,76x
```

Mesma cena, mesma seed (20260811), 1024×576 · 124 frames. **Ordem deliberada:
turbo primeiro (frio, pagou o carregamento), baseline depois (quente)** — o
overhead pesou contra o turbo, então 2,76× é piso.

Os 857 s batem com os 886 s históricos (3% de diferença), o que valida a
medição de lado: a máquina não mudou.

### ⚠️ Isto derrubou "o termo fixo é ~zero"

Dois pontos reais dão `tempo ≈ 76 s + 39 s por step`. O experimento antigo (20
contra 30 steps) não conseguia ver o patamar: num intervalo tão curto, 76 s se
diluem e o resultado fica indistinguível de proporcionalidade. **Regra nova:
extrapolação de steps só vale dentro da faixa medida.**

### O áudio sobrevive (Whisper large-v3 + F0 por autocorrelação)

| | ROSY (S1), aguda | BENTO (S2), grave |
|---|---|---|
| turbo 6 | 271 Hz | 131 Hz |
| baseline 20 | 250 Hz | 125 Hz |
| diferença | 1,4 semitons | 0,8 semitons |

As duas falas escritas saíram palavra por palavra nos dois clipes, nos mesmos
tempos (~0–2 s e ~2,7–5 s), sem invasão de registro — quase uma oitava separando
os personagens. O turbo acrescentou um `"É."` de 0,2 s no início, a 250 Hz
(coerente com a ROSY: sílaba extra, não troca de personagem).

Níveis: turbo mean −28,2 / pico −11,3 dB; baseline mean −25,6 / pico −6,8 dB. O
turbo saiu ~3 dB mais baixo. **Um clipe só — não é padrão estabelecido.**

⚠️ **A imagem a 6 steps continua sem avaliação.** Tempo e áudio medidos; o
julgamento visual é do usuário, e é de UM clipe de 5 s.

### O que a instalação entregou

`custom_nodes` foi de 0 para 8 pacotes; o ComfyUI de **825 para 1587 nós**.
Contra o `AcademiaSD_MiniMax-H3_v24`, de 24 tipos faltando sobraram 2:
`Fast Groups Bypasser (rgthree)` (nó virtual JS — funciona na UI, não consta na
API, **não é falta**) e `AcademiaSD_Downloader` (o pack de 2026-08-11 não o
registra mais; apagar do grafo, os pesos já estão no disco).

---

## Detalhamento da instalação

**O que mudou no repo** (branch `worktree-turbo-lora`):

| | |
|---|---|
| `workflows/minimax_h3_t2v_turbo_api.json` | o mesmo grafo, com `MiniMaxH3TurboLoRA` no nó **15** e `MiniMaxH3TurboSampler` no lugar do `KSamplerSelect`. Ids 1–14 idênticos, então `inject_scene` serve aos dois sem `if` |
| `submit_scene` / `generate_video` | ganharam `turbo`, `turbo_lora`, `turbo_strength`, `turbo_low_vram`. `turbo=False` é o default: **nada muda** para quem não pedir |
| `docker/docker-compose.yml` | `custom_nodes` virou bind-mount rw a partir de `CUSTOM_NODES_DIR` |
| `scripts/install_custom_nodes.sh` | clona/atualiza os 8 pacotes e instala as deps no python do ComfyUI |

### ⚠️ A armadilha que mordeu duas vezes no mesmo dia

`custom_nodes` é bind-mount, então o **código** dos nós sobrevive. As
**dependências Python**, não: `pip install` dentro do container grava na camada
gravável, e `docker compose up -d` a descarta.

Sequência real de 2026-08-11:

```
1143 nós   container recém-criado, 3 pacotes em IMPORT FAILED (cv2)
1587 nós   depois de install_custom_nodes.sh --deps-only + restart
1143 nós   depois de um up -d para acrescentar o mount do user dir
           -- os mesmos 3 pacotes, o mesmo cv2
```

O segundo recreate não tinha nada a ver com custom nodes. **Qualquer** mudança
no compose derruba as deps. Por isso elas foram para o `docker/Dockerfile`
(bloco *Python deps of the custom node packs*), que é o único lugar que
sobrevive. `--deps-only` continua existindo como remendo até o rebuild.

**Uma variante de opencv só.** Os pacotes pedem três (`opencv-python`,
`opencv-python-headless`, `opencv-contrib-python`) e todas instalam o mesmo
módulo `cv2` por cima uma da outra. O Dockerfile fixa `opencv-contrib-python`,
que é o superconjunto.

### O ritual completo, na ordem que funcionou

```bash
docker compose -f docker/docker-compose.yml --project-directory . up -d
scripts/install_custom_nodes.sh --deps-only     # deps no python do ComfyUI
docker restart minimax-comfyui                  # imports só acontecem no startup
```

⚠️ **O `restart` não é opcional.** Instalar as deps com o container de pé não
carrega nada: o ComfyUI importa os custom nodes uma vez, no boot. Antes do
restart eram 1143 nós com três pacotes em `IMPORT FAILED`; depois, 1587.

⚠️ **As três falhas tinham uma causa só:** `No module named 'cv2'`. Impact-Pack,
VideoHelperSuite e Easy-Use dependem todos de `opencv-python-headless`. Ao
depurar import de custom node, ler o log **inteiro** antes de tratar cada pacote
como um problema separado —
`docker logs minimax-comfyui | grep -A3 "IMPORT FAILED\|Cannot import"`.

### custom_nodes vivia dentro da imagem

Não era volume. Todo `docker compose build` apagava, **em silêncio**, qualquer nó
instalado — e como o build refaz o download do torch/cu128, ninguém refazia o
build por acidente, então o problema nunca apareceu. Agora é bind-mount.

⚠️ **Semear antes de montar.** O ComfyUI traz `websocket_image_save.py` dentro de
`custom_nodes`; montar um diretório vazio por cima o esconde. O script faz
`docker cp` do conteúdo da imagem na primeira execução.

### Os 8 pacotes, e o que cada um entrega ao all-in-one

O "ALL-IN-ONE WF" da AcademiaSD **não é um custom node** — o `v24` usa 45 tipos de
nó, dos quais **24 faltavam** aqui. Medido comparando o JSON contra `/object_info`:

| pacote | o que o workflow usa dele |
|---|---|
| `ComfyUI-MiniMax-H3-Turbo` (Larryvrh) | `MiniMaxH3TurboLoRA`, `MiniMaxH3TurboSampler` — **o único indispensável** |
| `comfyui_AcademiaSD` | `AcademiaSD_*` (Downloader, MultiLora, ResolutionCalc, Numeric, Noise, PositivePrompt, SaveAndSend, TimeCalculator) e os próprios workflows |
| `rgthree-comfy` | `Fast Groups Bypasser` (×11), `Image Comparer` |
| `ComfyUI-Impact-Pack` | `ImpactSwitch` (×4) — o seletor T2V/I2V/Ref2V |
| `ComfyUI-VideoHelperSuite` | `VHS_VideoCombine`, `VHS_LoadVideo`, `VHS_LoadAudioUpload` |
| `ComfyUI-Frame-Interpolation` | `RIFE VFI` (24 → 48 fps) |
| `ComfyUI-KJNodes` | `ModelPreviewOverrideKJ` (preview por TAE) e os **dois** nós de Sage Attention |
| `ComfyUI-Easy-Use` | `easy cleanGpuUsed`, `clearCacheAll`, `showAnything` |

### O nó do Larryvrh foi escrito para a base que este repo usa

Não é sorte, está no fonte (`__init__.py`, 526 linhas, legível — o `node.zip` do
repo é só cópia empacotada):

- **`use_adaln_curves`**: na base *pruned* o update de adaln vive no espaço
  `silu(t_emb)` de 2688 dim, que o pruned colapsou numa curva de 8. Não dá para
  ser patch de peso nem adaptador de bypass, então o nó **reinjeta em tempo de
  execução** a partir de um grid interpolado (`h3_silu_temb_grid.safetensors`).
- **`TensorWiseINT8Layout`**: no `int8_convrot` o `comfy.ops.linear_input_act`
  chama o kernel int8 fundido **direto no peso**, sem passar pelo `forward` do
  módulo — então o hook de bypass nunca dispara e a LoRA daquele `fc2` sumiria
  em silêncio. O autor mediu: *"nos 50 blocos do DiT os hooks de fc2 disparam 0
  vezes"*. O nó desvia justamente esses para o caminho de merge.

**`low_vram`** é a alavanca: `True` funde a LoRA nos pesos (menor pico de VRAM,
mas num modelo quantizado parte do delta é arredondada fora → mais macio);
`False` aplica em tempo de execução (mais nítido, mais VRAM). O workflow turbo
deste repo sai com **`True`**, escolha conservadora para 12 GB — **não medida**.

### ⚠️ Tudo saiu de `/var/tmp/minimax/` para `$HOME/minimax/` (2026-08-11)

`/var/tmp` é diretório **temporário** por contrato — o `systemd-tmpfiles` tem o
direito de limpá-lo, e 73 GB de pesos não são temporários. Pior: estava fora do
exclude do Timeshift, inchando todo snapshot. `$HOME/minimax/` é gravável sem
sudo e está coberto pelo exclude.

```
$HOME/minimax/
├── models/          73 GB   ← MODELS_DIR
│   ├── text_encoders/    36 GB
│   ├── diffusion_models/ 31 GB
│   ├── vae/             5,5 GB
│   ├── loras/           1,5 GB   ← novo
│   └── vae_approx/      9,4 MB   ← novo
└── custom_nodes/   120 MB   ← CUSTOM_NODES_DIR (8 pacotes + os 2 do ComfyUI)
```

O caminho antigo estava **hardcoded em 12 lugares** (`config.sh`, `server.py`,
`ci.yml`, `setup_whisper.sh`, `demo_aurora.sh`, `07_e2e_agent.sh`, README, AGENTS,
3 docs). Todos passaram a `$HOME/minimax/...`, e o `ci.yml` deixou de fixar
`MODELS_DIR`: agora **pergunta ao container** de onde vem o bind mount de
`/comfy/ComfyUI/models`, do mesmo jeito que já fazia com o output. Isso não
envelhece na próxima mudança de caminho.

⚠️ **`CUSTOM_NODES_DIR` no `.env` não é opcional.** Se faltar, o compose monta o
default `/opt/minimax/custom_nodes` — vazio — por cima de `/comfy/ComfyUI/custom_nodes`,
e **todos** os nós somem de uma vez, sem erro visível.

### Modelos baixados (2026-08-11)

```
models/loras/minimax_h3_turbo_v4_step600_ema.safetensors      780 MB  ✅ o recomendado
models/loras/minimax_h3_turbo_4step_ema_ckpt850.safetensors   780 MB  ✅ alternativa p/ 4 steps
models/vae_approx/taeh3.safetensors                            10 MB  ✅ preview
models/text_encoders/qwen3vl_32b_h3_ultra_uncensored_heretic_int8_convrot.safetensors
                                                             26,4 GB  ⏳ baixando ainda no
                                                                      caminho ANTIGO (o curl
                                                                      já estava aberto); mover
                                                                      ao terminar
```

### Duas coisas que o workflow da AcademiaSD revelou

1. **Ele carrega `minimax_h3_ref2va_pruned_int8_convrot`**, não a `fl2va` daqui.
   `ref2va` é *Reference*-to-Video: consistência de personagem a partir de imagem
   de referência. São **21 GB** e **não foi baixada** — o encadeamento de frame
   deste repo depende de `last_frame`, que é FL2VA. Decisão em aberto, não
   pendência.
2. **`PathchSageAttentionKJ` já vem em BYPASS**, mas
   `MiniMaxH3MemoryEfficientSageAttentionPatch` vem **ativo** — e exige o pacote
   `sageattention`, que não está instalado. Ou instalar, ou desligar esse nó
   (Ctrl+B) antes de rodar o workflow.

---

## O encadeamento de frame — a peça nova

O modelo é **FL2VA** (First-Last frame to Video+Audio). Para durações longas:

1. Extrai o último frame do clipe N:
   `ffmpeg -nostdin -sseof -1 -i clip.mp4 -update 1 -q:v 2 -y frame.png`
   (`-sseof -1` decodifica o último segundo e `-update 1` reescreve o mesmo
   arquivo a cada frame — o que sobra é literalmente o último. Pedir
   `-frames:v 1` junto pegaria o **primeiro** frame do trecho.)
2. Passa como `first_frame` do clipe N+1.
3. `compose_final` junta tudo no fim.

**Duas coisas que não são óbvias:**

- **Prompt novo por capítulo, não o mesmo repetido.** O frame dá continuidade
  visual; o prompt faz a cena avançar. Repetir o prompt original dá o mesmo
  plano seis vezes.
- **Cada prompt tem de recarregar as âncoras de estilo** (traço, luz, paleta,
  lente). O modelo só enxerga **um frame** do passado, não os clipes anteriores
  — sem reancorar, o visual deriva ao longo da cadeia.

Implementado em `round2.py`. Não existe no repo ainda — `compose_final` é só
concat do ffmpeg, não há extração de frame em `src/`. **Vale portar para uma
tool MCP**: é o caminho do projeto para durações longas.

O bloco G da noite existia para testar isto e nem chegou lá: pediu as duas
metades a 15 s × 1024×576 = 213 M, o dobro do teto. **O experimento estava mal
desenhado, não a máquina.**

---

## Estado do repositório

- `~/tools-local/minimax-video-factory`, branch `main` em `2a3187f`.
- **26 tools** MCP (a merge do IG somou 5 às 19 antigas).
- **13 testes unitários** passando.
- `uv run ruff check .` acusa **~25 erros pré-existentes** na `main`, drift da
  merge do IG. Não são dos slash commands nem do fix de VRAM.
- `.env` em INT8. INT4 guardado em `.env.bak-int4` — trocar exige rebuild do
  container e fila vazia.

### Feito nesta sessão

| | |
|---|---|
| **Slash commands do Claude Code** | `8bf4e55` → merge `306e8d0`. 24 comandos em `.claude/commands/` gerados pelo mesmo gerador do OpenCode; `.mcp.json` versionado (docker + remote); `minimax-video-factory-uv` e `minimax-knowledge-base` no escopo local via `claude mcp add-json`. `kb-*` roteado para o servidor **host** — o container não alcança o Postgres. `compress`/`search-sessions` **não** portados: o Claude Code já tem skills globais com esses nomes. |
| **Fix de VRAM no `free()`** | `709887d` → merge `2a3187f`. Ver abaixo. |
| **Arquivos soltos na raiz** | `base_*.png` → `input/base/`; `kb_test_note.md` → `tests/fixtures/`. `overnight.py` e `night_phase2.py` atualizados para o caminho novo. |

### O bug do `free()`, para não reintroduzir

`transcriber.free()` chamava `torch.cuda.empty_cache()` para devolver a VRAM do
Whisper. **Três problemas:** faster-whisper aloca via CTranslate2, não PyTorch,
então `empty_cache()` não libera nada dele (quem libera é o `del` do cache);
`torch` não é importado em nenhum outro lugar do projeto, então `import torch`
criava um contexto CUDA de centenas de MB **na placa que o método existia para
liberar**; e reimportar torch pode **levantar exceção**
(`Only a single TORCH_LIBRARY...`) — dentro de um `finally`, o que descartava
uma transcrição de minutos e renegava a mensagem.

Agora: `gc.collect()` no lugar do torch, e a chamada no `finally` é guardada.
`tests/unit_transcriber.py` fixa os 6 casos. **Verificado que os testes falham
contra a versão anterior: 2 BAD, exit 1, um por bug.**

---

## Regras que valem sempre nesta máquina

1. **Não dar `git push`.** Dispara a CI no runner self-hosted, que renderiza e
   rouba a GPU no meio dos testes. O job `gpu-validation` roda `diagnose.sh
   00–07` com render E2E e tem `if: always()` — **nem falha de lint o impede**.
   *Push feito em 2026-08-09 07:21* (`6153591..6336ea9`, 12 commits), com
   autorização explícita e a GPU livre. **CI 4/4 verde**, incluindo o
   `gpu-validation`. A regra volta a valer: pedir antes de empurrar.
2. **Não publicar estes vídeos.** Várias entradas são fotos pessoais.
3. **Nunca mexer no worktree `.worktrees/igsync`** — trabalho do usuário na
   branch `feat/ig-saved-sync`.
4. **Um render por vez.** Dois concorrentes estouram a VRAM.
5. **Mostrar a fila junto com todo vídeo entregue** e avisar do que houver nela.
6. Worktree é obrigatório para implementação; commit só de documentação, não.
7. Nunca animar rosto de terceiro identificável. Fotos do próprio usuário, sim.
8. **Não mexer no `ig-worker`** — o usuário está desenvolvendo nele.

---

## Regra de produção que saiu da noite

> Orçamento de **~100 M pixel-frames** por render. Gaste em resolução (até
> 1216×672 a 5 s) **ou** em duração (15 s a 512×320) — nunca nas duas.
> Acima disso, é composição com encadeamento de frame.

---

## Pendências

- **Os scripts da rodada 3 ainda estão fora do git**, em `~/bkp/minimax-night/`.
  Quatro deles são ferramenta reutilizável e mereciam `scripts/`:
  `voice_check.py` (F0 por fala, pega troca de voz), `motion.py` (movimento +
  concentração), `smooth_seam.py` (cruza vídeo e áudio pela mesma duração),
  `unify_audio3.py` (nível entre capítulos). **Não foram movidos em 2026-08-09
  porque o usuário avisou que estava trabalhando num worktree** — mover exigiria
  criar outro, e não valia o risco no fim da noite. É o mesmo problema que este
  handoff resolveu para a documentação: conhecimento útil fora do versionamento.
- ~~O enquadramento aberto demais para diálogo~~ **resolvido no mesmo dia**, e por
  um caminho que não era o planejado: a ficha de elenco detalhada faz o modelo
  aproximar o enquadramento sozinho. A correção manual (`medium shot` nas batidas
  com fala) entrou também. Ver `docs/PROMPT_DESENHO_COM_FALA.md`.
- **Portar o encadeamento de frame + a unificação de áudio para tools MCP.**
  O `last_frame` já entrou nas tools (`submit_scene`, `generate_video`); falta a
  **extração de quadro** e a **unificação de áudio**, que seguem em script.
- **Task 6 do plano de IG** (`docs/superpowers/plans/2026-08-09-ig-content-focused-pipeline.md`).
  Steps 1–3 eram no-op: a base não tinha nenhum documento de IG, o `state.json`
  não existia e o worker estava parado. Step 4 (publicar + consumir) foi
  disparado 2026-08-09 07:29. Falta o **Step 5**: verificar que os documentos
  saem focados em conteúdo, não em metadados.
- **Merge de `feat/ig-saved-sync`.** As 5 tools de IG já entraram na `main`
  (`56db1c8`) e as guardas já esperam 24. Se surgir mais uma tool, são **quatro**
  lugares: `catalog.COMMAND_NAMES` (o gerador se recusa a inventar nome), a
  lista canônica de `unit_registry`, a tabela do README, e rodar
  `scripts/generate_commands.py` — que agora escreve **dois** arquivos por tool.
- ~~Os ~25 erros de ruff~~ **zerados** em `6f92da9`. `ruff check .` limpo, e o
  `static-lint` do CI passa. Três dos consertos eram exceções engolidas em
  silêncio, que agora logam.
- **7 s a 1024×576** (≈100 M) nunca foi testado — é o maior clipe que a conta
  diz caber. Valeria um render.
- **`.env.bak-int4` tem um `OPENAI_API_KEY` real.** Nunca foi commitado
  (verificado em todas as refs) e agora `.env.*` está no `.gitignore`, mas a
  chave segue viva em disco num repo público. Vale rotacionar.
- **`~/.cache/uv` ocupa 8,9 GB e não dá para limpar com o comando próprio.**
  `uv cache clean` fica em timeout esperando lock exclusivo: seis processos
  `uv run` de longa duração (os servidores MCP de `minimax-video-factory` e
  `skysql-mcp`, mais um `mkdocs serve`) seguram lock de leitura desde 17/jul e
  não vão soltar. Ou apaga o diretório à mão contornando o lock, ou para os
  seis, limpa e reinicia. **Decidido em 2026-08-09: deixar quieto** — com 61 GB
  livres não compensa derrubar infraestrutura por 1,7% da partição.
- **Categoria: decidido aceitar classificação grossa.** Ver a seção abaixo —
  cinco variantes medidas, nenhuma boa E barata. O usuário vai reestruturar as
  próprias coleções depois, conforme os interesses dele. **Não refazer o
  experimento** sem uma hipótese nova.

---

## Classificação de categoria — medido, decidido, encerrado

Cinco variantes sobre os MESMOS 12 documentos de IG. `SPREAD` = categorias
distintas usadas; `ÂNCORAS` = acertos em casos onde a resposta certa não é
opinião (receita→culinária, podcast de inglês→idiomas...).

| | vocabulário | modelo | spread | âncoras | tempo |
|---|---|---|---|---|---|
| A | 26 coleções cruas | lfm2:24b | 4/26 | 4/4 | 295 s |
| B | 26 + "seja específico" | lfm2:24b | 4/26 | 4/4 | 166 s |
| C | 26 + "seja específico" | qwen2.5:32b | **10/26** | 4/4 | **2548 s** |
| D | 10 curadas | lfm2:24b | 5/10 | **3/4*** | 363 s |
| E | 10 curadas | qwen2.5:32b | — | — | timeout em todo doc |

\* nas mesmas 4 âncoras de A, para ser comparável.

**As quatro conclusões, todas contra a intuição:**

1. **Instrução de prompt não faz nada.** A e B são idênticas, incluindo a
   categoria inventada. Não perca tempo reescrevendo o prompt.
2. **A saída é instável.** Mesmo modelo, mesmo prompt, mesma entrada: um
   documento saiu `Receitas` numa execução e `Inglês` na seguinte. Não há
   resposta a corrigir, há uma distribuição.
3. **Modelo maior resolve, e custa caro demais.** O `qwen2.5:32b` usou 10
   categorias contra 4 e escolheu as específicas (`security`, `Governo`,
   `Energia`) onde o `lfm2` dizia `Tecnologia`. Mas a **3,5 min por documento**:
   sincronizar os 2157 posts levaria ~5 dias só classificando.
4. **Vocabulário "limpo" piorou.** A taxonomia curada de 10 (sem sobreposição,
   granularidade uniforme) fez o `lfm2` errar um caso que ele acertava com as
   26 coleções bagunçadas. Conjectura não testada: nomes concretos e familiares
   (`Receitas`, `Inglês`) ancoram melhor que abstratos (`culinaria`, `idiomas`).

**Decisão de 2026-08-09: aceitar categoria grossa.** Fica o `lfm2:24b` com as
coleções do usuário como vocabulário — que é o que `_category_vocabulary()` já
faz. A `coerce_categoria` (`70cd069`) impede categoria inventada; a
concentração e a instabilidade ficam como custo aceito.

Modelos ainda não testados, se alguém quiser retomar: `gemma4:26b` e
`gpt-oss:20b`, ambos em disco. A pergunta em aberto é se existe um
intermediário com a discriminação do 32B e o custo do 24B.

---

## Scripts guardados aqui

| Arquivo | Para quê |
|---|---|
| `round2.py` | 30 s por encadeamento de frame — **concluído**, e retomável |
| `unify_audio.py` | casa o nível dos capítulos e sela as emendas — **concluído** |
| `ig_reingest.py` | Task 6 step 4: publica o lote de re-ingestão |
| `cat_experiment.py`, `cat_experiment2.py` | as 5 variantes de classificação; os resultados estão na seção acima |
| `backfill_categoria.py` | acrescenta `categoria:` aos docs já ingeridos, sem tocar no Instagram |
| `ig_docs_before_wipe.json` | retrato dos 12 documentos antes do refazer |
| `ig_chain.sh` | espera a publicação e só então sobe o worker (evita OOM) |
| `night_phase2.py` | fase 2 da noite (blocos D/E/F/G) — concluída |
| `overnight.py` | fase 1 da noite (blocos A/B/C) — concluída |
| `*.log` | os resultados. `round2-crash-0307.log` é o crash da composição |
| `frames/` | últimos frames extraídos, um por elo da cadeia |
| `audio_work/` | capítulos normalizados, intermediários da unificação |
| `HANDOFF-int4-2026-08-07.md` | o handoff da era INT4, como linha de base |
| `coverage.py`, `coverage2.py`, `finish_tests.sh` | exercitam as tools pelo MCP |

---

## 2026-10-07 — reconciliação pós-review: fixes presos na branch errada chegaram na `main`

Dois fixes desta sessão (revisão por subagent do split video-factory/insta_kb)
tinham sido comitados, por engano, só no branch `update/deps-2026-10` (a
atualização de dependências que o usuário estava fazendo em paralelo, em
outro terminal, na mesma working directory) — nunca chegaram na `main`:

- `44b6406` build: default INT8 ConvRot + nvfp4 AWQ (compose, .env.example, config.sh)
- `4b34bd2` docs: regenera MCP_TOOLS.md (26 → 12 tools)

`.env` já tinha os valores corretos (int8/nvfp4) explícitos, então produção
nunca foi afetada — só o fallback `:-default` do compose/`.env.example`
ficava errado para quem clonasse sem copiar `.env`. Cherry-pick dos dois para
`main` via worktree temporário (sem tocar o branch `update/deps-2026-10`, que
tem WIP do usuário: bump ComfyUI v0.30.2→v0.39.1, ainda não commitado).
Também adicionei o teste que faltava (`tests/test_scripts.py::test_mcp_docs_not_stale`,
chama `generate_mcp_docs.py --check`) — era a recomendação "Important" do
review que ainda não tinha sido wireada.

**`av==18.1.0`** (escolhido pela atualização de deps paralela, documentado em
`docs/PLANO_ATUALIZACAO.md`) foi verificado de novo, independentemente: ainda
aceita `metadata_errors=` (erro foi `InvalidDataError` de arquivo inválido,
não `TypeError` de parâmetro desconhecido) — confirmado também com uma
transcrição real via faster-whisper. Não reintroduz o bug que `av==15.1.0`
corrigiu.

Push para `main`: `ecca647..86595f1`. CI: 3/4 jobs verdes (Static Lint, Unit
Tests, MCP Handshake); **GPU Validation falhou em `00_prereq.sh`** por RAM
livre no runner ter caído para 9 GB (< 12 GB exigido) — ambiental, não
regressão: o render real (`07_e2e_agent.sh`, `submit_scene`+`compose_final`)
e as 12 tools do container (`09_container_deps.sh`) passaram dentro do mesmo
run. Provável causa: o runner self-hosted é esta própria máquina, e a
atualização de deps paralela e/ou o ig-worker podiam estar consumindo RAM
no momento do job. **Pendência: re-rodar o workflow (`gh workflow run CI
--ref main`) quando a máquina estiver mais livre**, só para confirmar que é
mesmo RAM momentânea e não um limiar que ficou baixo demais.

### Pendências reais no fim desta sessão

- Re-rodar GPU Validation em `main` (ver acima).
- `update/deps-2026-10` (nos dois repos) é trabalho do usuário em andamento
  (plano em `docs/PLANO_ATUALIZACAO.md`/`insta_kb`): bump ComfyUI v0.39.1,
  fastmcp>=4.0.11, av==18.1.0, instagrapi>=3.0.20, fastapi>=0.142.2 — **não
  mexi nisso**, só confirmei que não conflita com os fixes que cherry-pickei.
- `insta_kb`: commitei o teste que faltava (`test_search_db_failure_returns_ok_false_not_raise`)
  direto no branch `update/deps-2026-10` (era o branch já checked-out) — ainda
  não existe um merge desse branch para `dev`/`main`, isso é parte do trabalho
  em andamento do usuário, não meu para decidir.
- `database.db*` (sqlite vazio, sem schema, não referenciado no código) —
  adicionado ao `.gitignore` do insta_kb; arquivos ainda no disco (remoção
  bloqueada pelo classificador de permissões desta sessão).
