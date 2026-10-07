# Auditoria SOLID — minimax-video-factory

Data: 2026-10-07 · Método: radon cc/mi + vulture + grafo AST + revisão manual checklist · Baseline: 9 passed + privacy + ruff + pyright (não re-executado) · Escopo: só avaliar (nenhum código alterado)

> Repo público: nenhum path absoluto de home directory aparece neste documento (usa-se `src/...`, `tests/...`, `docs/...`, `~/.gpu-lock`).

---

## 1. Métricas

### 1.1 Inventário medido

| Módulo | LOC | cc≥6 | pior cc | MI (rank) | fan-out | fan-in |
|---|---:|---:|---:|---:|---:|---:|
| `src/minimax_mcp/server.py` | 468 | 3 | 10 (`queue_status`:238) | 44.0 (A) | **9** | 0 |
| `src/minimax_mcp/comfyui_client.py` | 343 | 6 | 15 (`wait_for_execution`:237) | **41.2** (A) | 0 | 3 |
| `src/minimax_mcp/core.py` | 367 | 3 | **20** (`inject_scene`:74) | 47.0 (A) | 3 | 2 |
| `src/minimax_mcp/orchestrator.py` | 341 | 2 | 7 (`generate_video`:84) | 59.3 (A) | 4 | **4** |
| `src/minimax_mcp/transcriber.py` | 218 | 2 | 8 (`transcribe`:95) | 69.5 (A) | 0 | 2 |
| `src/minimax_mcp/downloader.py` | 133 | 1 | 11 (`download`:60) | 67.1 (A) | 0 | 2 |
| `src/minimax_mcp/gpu_lock.py` | 137 | 0 | — | 69.5 (A) | 0 | 2 |
| `src/minimax_mcp/__init__.py` | 3 | 0 | — | 100 (A) | 0 | 1 |
| **total** | **2.010** | **18** | 20 | — | — | — |

- **vulture (conf 80): vazio = 0 dead code** detectado automaticamente (a revisão manual achou API pública sem chamador — ver §5, item 9; vulture a 80% não marca defs "públicas").
- **Grafo AST:** 8 módulos, 12 arestas, **0 ciclos de import**. Arestas: `server→{core, orchestrator, comfyui_client, downloader, transcriber, minimax_mcp}`, `orchestrator→{core, comfyui_client, downloader, transcriber}`, `core→{comfyui_client, gpu_lock}`.
- Observação sobre o fan-in de `orchestrator`=4: são 4 *statements* de import todos em `server.py` (1 top-level em `server.py:57` + 3 lazy em `server.py:386`, `:413`, `:437`) — o número infla por re-import redundante, não por reuso real (item 9 do backlog).

### 1.2 As 18 funções cc≥6

| cc | local | função |
|---:|---|---|
| **20** | `core.py:74` | `inject_scene` |
| 15 | `comfyui_client.py:237` | `wait_for_execution` |
| 12 | `comfyui_client.py:82` | `describe_execution_error` |
| 11 | `downloader.py:60` | `download` |
| 11 | `core.py:234` | `submit_scene_core` |
| 10 | `server.py:238` | `queue_status` |
| 9 | `comfyui_client.py:311` | `resolve_output` |
| 8 | `transcriber.py:95`, `server.py:288`, `core.py:337`, `comfyui_client.py:202`, `comfyui_client.py:166` | `transcribe`, `get_status`, `compose_final_core`, `watch_progress`, `upload_image` |
| 7 | `server.py:187`, `orchestrator.py:84`, `comfyui_client.py:52` | `health_check`, `generate_video`, `queue_snapshot_from` |
| 6 | `transcriber.py:65`, `orchestrator.py:215`, `comfyui_client.py:27` | `_get_model`, `run_full_pipeline`, `queue_state_from` |

Leitura: nenhuma função abaixo de cc=6 é suspeita; os picos estão todos em "funções que fazem mais do que seu nome diz" — exatamente o que SRP/OCP capturam.

---

## 2. Single Responsibility / Open-Closed

### 2.1 S — Single Responsibility

**`server.py` — polyglot, 5 papéis no mesmo arquivo (SRP).** Evidência por faixa:

| papel | faixa |
|---|---|
| config/env + constantes de workflow | `server.py:66-98` |
| rotas HTTP de diagnóstico GPU (Flask/Starlette, fora do MCP) | `server.py:110-132` |
| mapeamento de path host↔container (output e downloads) | `server.py:135-182` |
| 12 tools MCP (`@mcp.tool` ×12: `health_check` … `studio_pipeline`) | `server.py:186-446` |
| bootstrap de transporte (stdio/http/sse) | `server.py:450-466` |

Sendo 12 tools (não ~20) + 3 rotas custom. Como *composition root* alguma mistura é esperada; o problema concreto é que os papéis 1 e 3 **duplicam `core.py`** (§4.1) e o papel 4 mistura delegação pura (`submit_scene`:229) com lógica de negócio própria (`queue_status`:249-284, `get_status`:295-312, `health_check`:194-206).

**`core.py` — 5-6 responsabilidades (SRP).** O docstring diz "Core ComfyUI operations shared between server and orchestrator" (`core.py:1`), mas o arquivo também é:

1. leitor de config/env + nomes de modelo (`core.py:23-57`);
2. loader + mutador de workflow JSON (`load_workflow`:61-66, `inject_scene`:74-162);
3. tradutor de paths host↔container (`core.py:165-193`);
4. formatter de UI (`progress_bar`:196-207, `output_relpath`:210-220);
5. **dono de estado de processo** — mapa `prompt_id→token` do lock de GPU (`_gpu_tokens_by_prompt`, `core.py:231`) + ciclo de vida acquire/release (`submit_scene_core`:282-298, `_release_gpu_token`:331-334);
6. orquestrador de subprocess ffmpeg (`compose_final_core`:337-368).

Cada uma delas muda por motivo diferente (workflow ComfyUI vs. deploy container vs. concorrência de GPU vs. mídia).

**`comfyui_client.py` — docstring desmentido pela classe (SRP).** O cabeçalho declara 4 responsabilidades (`comfyui_client.py:1-8`: submit, ws, history, view), a classe expõe **13 métodos** (`comfyui_client.py:114-343`): system info (`health`:121, `object_info`:129), fila (`get_history`:137, `get_queue`:142, `queue_state`:148, `queue_snapshot`:195), envio (`submit`:156, `upload_image`:166), monitoramento ws (`watch_progress`:202, `wait_for_execution`:237, `interrupt`:233), resolução/download de saída (`resolve_output`:311, `download_file`:331). Dois padrões de polling diferentes (`watch_progress` e `wait_for_execution`) convivem na mesma classe.

**Pontos positivos (mesma métrica):** `gpu_lock.py` é coeso e pequeno (MI 69.5, cc<6 em tudo); `downloader.py` e `transcriber.py` têm exatamente uma responsabilidade cada; as funções puras extraídas para teste (`queue_state_from`:27, `queue_snapshot_from`:52, `describe_execution_error`:82, `progress_bar`:196) mostram disciplina de extração já praticada no repo.

### 2.2 O — Open-Closed

Não há hierarquias de workflow nem registro/strategy em lugar nenhum; extensão = editar função existente. Cadeias quantificadas:

1. **`describe_execution_error` (cc=12), `comfyui_client.py:82-111`** — varredura de `messages` (90-96) + **3 ramos por tipo de erro**: OOM especial (103-108), genérico com `exception_type` (109-110), fallback `json.dumps` (111). Um novo tipo de falha do ComfyUI (erro de CUDA não-OOM, validação de nó, NSFW-filter) exige editar a função. Padrão `se predicate → template` fecharia o ramo.
2. **`inject_scene` (cc=20), `core.py:74-162`** — a boa notícia: `loaders` é tabela-driven (`core.py:102-107`) e os dois âncoras passam por loop (`core.py:122-132`). O problema é a **quantidade de concerns numa função só**: modelos (102-111), prompt/tamanho (113-120), âncoras first/last (122-132), steps+scheduler (134-141), Turbo LoRA com 3 sub-ifs (145-152), seed do ruído (154-156), `filename_prefix` do SaveVideo (158-160). **7 pontos de extensão**: um novo tunable (cfg, sampler select, preset de resolução), um terceiro tipo de âncora, ou um workflow com outro node id ⇒ editar esta função **e** `submit_scene_core` (`core.py:234-250`) **e** as assinaturas das tools `submit_scene` (`server.py:210-224`) e `generate_video` (`server.py:393-408`).
3. **`wait_for_execution` (cc=15), `comfyui_client.py:237-308`** — dispatch `if/elif` sobre `evt_type` (291-303) com sub-ramos de `executing` (292-300) + fallback de poll a cada ramo (267-269, 278-282, 305-306). Um novo evento ws (`execution_success`, `progress_eta`) = editar o loop. Além disso `"Timed out" in str(e)` torna a *classificação* do timeout dependente do texto da mensagem (`core.py:317`).
4. **`get_status` (cc=8), `server.py:288-312`** — mini state-machine em if-encadeado: sem histórico → pergunta à fila (296-302); `completed` (304-308); `status_str == "error"` (309-311); senão "running" (312). Um estado novo do ComfyUI (paused/interrupted) = editar o if-chain.

Contra-exemplo positivo: os templates de prompt são um dict extensível (`orchestrator.py:54-79`) e o mapeamento de fila é tabela (`comfyui_client.py:42`) — OCP está sendo aplicado onde o autor já sentiu a dor.

---

## 3. Liskov / Interface Segregation / Dependency Inversion

### 3.1 L — Liskov

**N/A para hierarquias de tipos** — o repo não tem hierarquias substituíveis: `ComfyUIError(RuntimeError)` (`comfyui_client.py:23`) e `GpuLockTimeout(Exception)` (`gpu_lock.py:96`) têm uma implementação cada; nenhuma classe é estendida em teste ou produção.

Existe, porém, um **violação de contrato semântico** (espírito de LSP, sem herança): a assinatura informal `dict {"ok": ...}` é interpretada de forma divergente entre camadas, e num ponto concreto **o contrato documentado não é o que o código entrega** — ver achado **CRÍTICO-1** (§5): `orchestrator.py:144-166` trata `wait_for_video_core` como se ela *lançasse* `ComfyUIError`, mas `core.py:307-328` *retorna* `{"ok": False, ...}`. O teste que deveria garantir o contrato (`tests/unit_orchestrator.py:178-185`) mocka justamente a versão antiga (que lança), mascarando a divergência.

Também coerente/consistente: `{"ok": True, "state": "rendering"}` sem `output_path` (`orchestrator.py:151-164`, intenção) e `{"ok": True, "sem_audio": True}` (`transcriber.py:135-143`) são variações deliberadas de `ok`, mas nenhum doc/tipagem formaliza as variantes — o consumidor precisa conhecer todos os formatos.

### 3.2 I — Interface Segregation

**`ComfyUIClient` é um client grosso: 13 métodos / 5 grupos de responsabilidade, 3 consumidores.**

| consumidor | métodos que realmente usa |
|---|---|
| `core.py` | `upload_image`:262, `submit`:286, `wait_for_execution`:310, `resolve_output`:326 |
| `server.py` | `health`:190, `queue_snapshot`:247, `watch_progress`:251, `get_history`:292, `queue_state`:301, `resolve_output`:306 |
| `orchestrator.py` | apenas a exceção `ComfyUIError`:9 |

Nenhum consumidor usa a interface inteira; todos recebem a classe inteira. Custo prático baixo em Python (tests fazem `mock.patch.object(core, "ComfyUIClient")`, `tests/unit_core.py:193`), mas a segregação ausente é o que permite `wait_for_execution` virar cc=15 num único método. E 3 métodos **não têm nenhum chamador in-repo**: `object_info`:129, `interrupt`:233, `download_file`:331.

**Tools MCP com params fat, repetidos em 3 camadas.**

- `submit_scene`: **13 params** (`server.py:210-224`);
- `generate_video`: **14 params** (`server.py:393-408`) — redeclara os mesmos ~11 params de render de `submit_scene`;
- `submit_scene_core`: **12 params** (`core.py:234-250`).

O mesmo tuple de 12 argumentos é repassado linha-a-linha em `server.py:229-234`, `server.py:415-421` e `orchestrator.py:118-132`. Um RenderOptions/SceneSpec dataclass eliminaria 3 assinaturas + 2 blocos de forwarding e faria "adicionar um tunable" (ver OCP) virar 1 mudança em vez de 5.

`gpu_lock` é o contra-exemplo positivo de ISP: 4 funções pequenas e coesas (`acquire`/`release`/`held`/`status`), cada uma com um chamador distinto.

### 3.3 D — Dependency Inversion

**Não há abstração entre camadas: `core.py` importa e instancia o `ComfyUIClient` concreto.**

- import concreto: `core.py:15`; instanciação direta: `core.py:253` (`submit_scene_core`) e `core.py:308` (`wait_for_video_core`);
- `server.py` também instancia direto em 3 tools: `server.py:189`, `server.py:246`, `server.py:290`;
- único "seam" de teste = monkeypatch de atributo de módulo (`tests/unit_core.py:193`), não injeção;
- `AudiovisualStudio` instancia `VideoDownloader`/`AudioTranscriber` concretos no `__init__` (`orchestrator.py:34-37`); os testes contornam com `object.__new__` + `MagicMock` (`tests/unit_orchestrator.py:53-57`, `:148`) — o custo da ausência de injeção já aparece como workaround repetido nos testes.

**`gpu_lock` como ponto de injeção:** `core.py:16-17` importa `acquire`/`release` como funções puras de módulo — na prática um singleton de filesystem, o que é **correto** para o requisito (lock entre processos/repo, decidido em `docs/HANDOFF.md`, 2026-10-07). O desvio é o estado derivado `_gpu_tokens_by_prompt` (`core.py:231`), que transforma `core.py` em dono de estado global de processo (documentado com a limitação aceita em `core.py:223-230`).

**Direção das dependências:** em camadas e sem ciclos (grafo: 0 ciclos) — `orchestrator → core → comfyui_client`, `server → {core, orchestrator, …}`. Duas ressalvas:

1. `server.py:48` importa `comfyui_client` **direto**, ao lado de `core` — a camada de apresentação alcança o adapter (contribui para o fan-out 9 do server);
2. o fan-out 9 é inflado pelos 3 re-imports lazy de `orchestrator` (`server.py:386`, `:413`, `:437`) já presentes no import top-level (`server.py:57`).

---

## 4. Acoplamento e coesão

### 4.1 Duplicação entre `server.py` e `core.py` (acoplamento por cópia)

| conceito | `server.py` | `core.py` |
|---|---|---|
| `COMFYUI_URL`, `WORKFLOW_PATH`, `OUTPUT_DIR`, `OUTPUT_PREFIX` | 68-75 | 25-34 |
| `H3_NODE_ID`, `NOISE_NODE_ID`, `SAVE_NODE_CLASS` | 85-87 (**sem uso no arquivo**) | 35-37 (usados) |
| nomes dos 4 modelos + mapa | 89-98 | 54-57 |
| `output_dir_abs` / `to_host_path` / `to_container_path` | 136-160 | 165-193 |

As duas cópias de path-mapping são lógica idêntica (`relative_to` + fallback). Hoje concordam porque leem as mesmas env vars; são 2 pontos de divergência silenciosa (a famosa "mudou num lugar, o outro fica stale"). As variantes `downloads_to_host_path`/`downloads_to_container_path` (`server.py:163-182`) são o mesmo molde 3ª vez.

### 4.2 Coesão medida pelo MI

MI todos em rank A (repo pequeno e bem particionado), mas a **ordem relativa é exatamente a ordem dos problemas de SRP**:

```
comfyui_client 41.2  <  server 44.0  <  core 47.0  |  orchestrator 59.3  <  downloader 67.1  <  transcriber/gpu_lock 69.5
     (5 grupos)          (5 papéis)     (5-6 resp.)       (1 pipeline)         (1 tarefa)          (1 tarefa)
```

Os 3 piores MI são os 3 arquivos com múltiplas responsabilidades; os melhores são os de tarefa única. Coesão e acoplamento apontam para os mesmos alvos — bom sinal de que o backlog abaixo não é ruído.

### 4.3 Outros nós de acoplamento

- **Classificação de erro por string-match**: `"Timed out" not in str(e)` em `core.py:317` **e** `orchestrator.py:147` — acopla 2 camadas ao texto exato de `comfyui_client.py:308`. Já é rassalva registrada do review (`docs/HANDOFF.md:1367`: "string-match frágil a refactor futuro … sem teste que pegaria isso").
- **Estado global de módulo**: `_gpu_tokens_by_prompt` (`core.py:231`), `_held_fds` (`gpu_lock.py:43`), `_model_cache` (`transcriber.py:41`) — os 3 documentados e justificados; apenas o primeiro é acoplamento entre duas chamadas MCP separadas (limitação aceita, `core.py:226-230`).
- **Documentação e código divergentes** no contrato `state=rendering` (ver CRÍTICO-1): `docs/COMMANDS.md:114`, `docs/MCP_TOOLS.md:37`, `server.py:411` prometem o que `orchestrator.py:151-166` nunca entrega em produção.
- **Duplicação cross-repo** (`gpu_lock.py`, `transcriber.py`, `downloader.py` gemelos do insta_kb): **fora de escopo** (decisão registrada no plano de não compartilhar); citado só como fato.

---

## 5. Backlog priorizado (crítico → cosmético, severidade × esforço)

Esforço: **S** ≤ 1h · **M** ≈ meio dia · **L** ≈ 1-2 dias. Ação sugerida = avaliação; nada foi alterado.

| # | Sev. | Esf. | Achado | Evidência | Ação sugerida |
|---|---|---|---|---|---|
| 1 | **crítico** | M | Contrato `state=rendering` morto: `wait_for_video_core` **retorna** `{"ok": False}` no timeout, mas `generate_video` trata como se **lançasse** `ComfyUIError` — o branch `timed_out`/`state=rendering` é inalcançável em produção; `studio_pipeline` no timeout **perde o prompt_id** (o bug que o commit `5095e21` queria corrigir), e o teste passa porque mocka a assinatura antiga (que lança). Docs prometem o comportamento oposto. | `orchestrator.py:139-166` vs `core.py:307-328`; teste `tests/unit_orchestrator.py:178-185`; docs `docs/COMMANDS.md:114`, `docs/MCP_TOOLS.md:37`, `server.py:411`; perda do prompt_id em `orchestrator.py:297-298` | Decidir o contrato (recomendação: `wait_for_video_core` devolver/tipar `timed_out` — ou re-levantar — e o orchestrador consumir o dict), corrigir o teste para mockar o contrato real, conferir docs. **É bugfix, não refatoração.** |
| 2 | importante | S | Classificação de timeout por string-match em 2 arquivos, já apontada como frágil no review. | `core.py:317`, `orchestrator.py:147`; `docs/HANDOFF.md:1367` | Subclass `ComfyUITimeout(ComfyUIError)` levantada em `comfyui_client.py:308`; consumidores checam tipo. Resolve junto com #1. |
| 3 | importante | M | `server.py` polyglot (config + rotas GPU + path mapping + 12 tools + bootstrap) **e** duplicação literal de config/paths com `core.py` (2 fontes de verdade). | `server.py:66-98`≡`core.py:23-57`; `server.py:136-160`≡`core.py:165-193` | Extrair `config.py` + `paths.py`; `server.py` fica só com tools/rotas/bootstrap. |
| 4 | importante | M | `core.py` com 5-6 responsabilidades (config, workflow, paths, formatação, estado de lock GPU, ffmpeg). | `core.py:23-57`, `61-162`, `165-220`, `223-231`, `331-368` | Separar `workflow.py` (load+inject) e `gpu_session.py` (mapa de tokens); manter em `core` só o que é realmente partilhado server↔orchestrator. |
| 5 | importante | M | DIP ausente: `ComfyUIClient` concreto instanciado em 5 pontos; seam de teste é monkeypatch. | `core.py:15`, `core.py:253`, `core.py:308`, `server.py:189`, `server.py:246`, `server.py:290` | Aceitar client/factory como parâmetro (default `ComfyUIClient(COMFYUI_URL)`); testes deixam de patchar atributo de módulo. |
| 6 | importante | M | `inject_scene` cc=20 — 7 concerns e 7 pontos de extensão numa função; estender âncora/tunable toca 5 locais. | `core.py:74-162` (+ `core.py:234-250`, `server.py:210-224`, `server.py:393-408`) | Decompor em `_patch_models/_prompt_size/_anchors/_steps/_turbo/_seed_save` (funções puras testáveis, mesmo molde já usado em `queue_state_from`). |
| 7 | importante | S | OCP em `describe_execution_error` (3 ramos if por tipo de erro) e em `wait_for_execution` (dispatch de eventos ws embutido no poll). | `comfyui_client.py:103-111`, `comfyui_client.py:291-303` | Tabela `predicate → template` de erros; handlers de evento em dict `type → fn`. |
| 8 | menor | M | ISP: params fat de tool repetidos em 3 camadas; `ComfyUIClient` 13 métodos/5 grupos (3 sem chamador). | `server.py:210-224` / `393-408` / `core.py:234-250`; `comfyui_client.py:114-343` | `RenderOptions` dataclass; no client, separar monitor (ws) de output (resolve/download) ou ao menos agrupar seções documentadas. |
| 9 | menor | S | Superfície morta/vestigial: constantes sem uso, API pública sem chamador, re-imports redundantes. | `server.py:85-87`; `comfyui_client.py:129`, `:233`, `:331`; `core.py:170`; `orchestrator.py:314`; `downloader.py:127`; `transcriber.py:211`; re-imports `server.py:386,413,437` | Remover constantes/`output_host_dir`; marcar conveniências como API pública intencional (docstring) ou remover; apagar os 3 re-imports. |
| 10 | menor | S | `get_status` state-machine if-encadeada (novo estado = editar). | `server.py:295-312` | Tabela de estado ou delegar o parsing ao client (já tem `queue_state`). |

### Matriz severidade × esforço

|  | S | M | L |
|---|---|---|---|
| **crítico** | — | #1 | — |
| **importante** | #2, #7 | #3, #4, #5, #6 | — |
| **menor** | #9, #10 | #8 | — |
| **cosmético** | Apêndice A | — | — |

---

## 6. Veredito go/no-go

**→ `ciclo futura`.**

Justificativa: o repo está estruturalmente saudável para o seu porte — 0 ciclos de import, 0 dead code (vulture), MI em rank A, módulos de tarefa única coesos (`gpu_lock`, `downloader`, `transcriber`), testes verdes e comentários de decisão acima da média — e nenhum achado SOLID justifica parar o desenvolvimento para refatorar agora; os itens #3-#8 são dívidas de estrutura que só começam a custar no próximo ciclo de crescimento (novo tunable de render, novo estado ComfyUI, novo tool). **Ressalva obrigatória:** o achado **#1 é bug, não refatoração** — o contrato `state=rendering` documentado (`docs/COMMANDS.md:114`, `server.py:411`) é inalcançável em produção e um `studio_pipeline` no timeout descarta o `prompt_id`; essa correção deve entrar no próximo ciclo imediatamente (com o teste deixando de mockar a assinatura antiga), mas não muda o veredito de refatoração.

---

## Apêndice A: achados cosméticos

Nenhum destes afeta comportamento; listados para completeness, fora do backlog.

1. `import copy` dentro de `inject_scene` (`core.py:99`) — módulo já é importável no topo; mesmo molde: `import os as _os` em `upload_image` (`comfyui_client.py:176`).
2. `generate_video` redeclara `logging`/`logger` dentro da função (`orchestrator.py:112-113`), sombreando o `logger` de módulo (`orchestrator.py:17`); `run_full_pipeline` repete `logging.getLogger` na linha 176/239.
3. Imports lazy redundantes de `AudiovisualStudio` em `server.py:386`, `:413`, `:437` — já importado no topo (`server.py:57`); único efeito colateral é inflar o fan-in do orchestrator no grafo (§1.1).
4. `progress_bar` (`core.py:196`) vive em `core` mas só é consumido por `queue_status` (`server.py:259`) — candidato natural a um módulo de formatação se #3/#4 forem feitos.
5. `downloads_to_host_path`/`downloads_to_container_path` (`server.py:163-182`) são cópias do molde `to_host_path`/`to_container_path` com outro par de dirs — 4 funções onde cabem 1 parametrizada.
6. Docstring do cabeçalho de `comfyui_client.py:1-8` descreve 4 responsabilidades; a classe tem 13 métodos em 5 grupos (§3.2) — atualizar o docstring já ajudaria.
7. `describe_execution_error` faz `json.dumps(payload)[:300]` como último fallback (`comfyui_client.py:111`) — ok, mas o comentário de origem ("três OOMs idênticos pareciam dois bugs") mereceria um teste de regressão do formato da string.
8. `downloader.download` (cc=11, `downloader.py:60-115`) mistura retry de cookies, fallback de extensão de arquivo e shape do retorno — funciona e está comentado; se crescer, extrair `_resolve_downloaded_path` (`downloader.py:85-96`).
9. Duplicação cross-repo com insta_kb (`gpu_lock.py`, `transcriber.py`, `downloader.py`): **fora de escopo** — decisão registrada de não compartilhar; citada apenas como observação.

### O que não foi avaliado

- **Suíte completa, ruff, pyright**: não re-executados (baseline assumida como verde conforme escopo).
- **Comportamento em runtime real**: sem backend ComfyUI vivo, o timeout do `wait_for_execution` e a recuperação de `prompt_id` foram avaliados por leitura de código + testes, não por execução.
- **Segurança/segredos e corretude das rotas GPU**: fora do checklist SOLID; as rotas `server.py:110-132` foram vistas só do ângulo de SRP.
- **Multi-processamento**: estabilidade dos globais de módulo (`_gpu_tokens_by_prompt`, `_held_fds`) sob múltiplos workers/uvicorn não foi avaliada (deploy atual é um processo por instância MCP, conforme `gpu_lock.py:39-42`).
- **Duplicação cross-repo** com insta_kb: deliberadamente não auditada (decisão de não compartilhar registrada no plano).
