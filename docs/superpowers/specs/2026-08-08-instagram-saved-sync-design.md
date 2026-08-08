# Sync automático de posts salvos do Instagram → Base de Conhecimento

Status: aprovado pelo usuário, pronto para plano de implementação.

## Contexto

O usuário tem muitos vídeos (e fotos) salvos no Instagram que ficam perdidos.
O projeto já possui o pipeline de conhecimento (KB): `download_video` →
`transcribe_video` (Whisper) → `ingest_text` (LLM local gera resumo/tutorial/tags
+ embedding pgvector + cópia markdown opcional no vault Obsidian).

Objetivo: enumerar **todos** os posts salvos do Instagram (via instagrapi,
autenticado com a sessão do usuário), colocá-los numa **fila RabbitMQ** (docker
local como default; RabbitMQ da VPS opcional via `RABBITMQ_URL`) e um **daemon
worker** que consome 1 a 1, baixa, transcreve (vídeos) ou descreve (fotos via
vision LLM) e documenta na base de conhecimento — sem inserção manual um a um.

## Arquitetura

```
Instagram (conta logada, IG_SESSIONID)
        │
        ▼
[ig_sync_saved: tool MCP]  instagrapi.saved_posts() → filtra tudo → publica na fila
        │
        ▼
    ┌─────────────────────┐
    │   RabbitMQ          │  ← docker compose local (default) OU VPS via RABBITMQ_URL
    │   queue: ig.saved   │     DLQ: ig.saved.dead
    └─────────────────────┘
        │
        ▼
[ig-worker: daemon container]  mesmo compose/imagem do H3, mesma rede
        │   consome 1 a 1 (prefetch=1):
        ├── download (yt-dlp, cookies Chrome)
        ├── vídeo → Whisper transcribe (GPU)
        ├── foto   → vision LLM (Ollama qwen2.5vl:7b via host-gateway) descreve
        ├── ingest no KB (LLM resumo/tutorial/tags + embedding) — reusa knowledge.py
        └── ack; duplicados pulados (ig_pk)
        │
        ▼
    Postgres KB (pgvector) + cópia markdown no Obsidian (VAULT_PATH, opcional)
```

Peças novas: `minimax_mcp/ig_sync.py` (enumeração+publicação),
`minimax_mcp/ig_worker.py` (daemon consumer), `minimax_mcp/ig_queue.py`
(abstração RabbitMQ), serviços `rabbitmq` + `ig-worker` no docker-compose,
4 tools MCP novas, slash commands.

## Decisões técnicas-chave

- **Enumeração**: `instagrapi` (lib Python), autenticado via `IG_SESSIONID`
  (sessionid dos cookies do Chrome — sem senha no `.env`). `client.saved_posts()`
  lista todos os salvos com metadados. `delay_range` para não disparar
  rate-limit/checkpoint.
- **Fila**: RabbitMQ. Docker compose local é o default (portável, como o Postgres
  do KB); VPS opcional trocando `RABBITMQ_URL`. Mensagens durable (persistem).
- **Dedup**: chave `ig_pk` (estável, única por post). Novo campo `ig_pk` na tabela
  `documents`; antes de processar, worker consulta o KB por `ig_pk` ou
  `source_url` → se existe, `ack` sem processar (não gasta GPU/LLM).
- **Escopo**: processa **tudo** (vídeos + fotos + carousels). Carousel → primeiro
  clipe/imagem.
- **Fotos**: descritas com vision LLM local via Ollama (`OLLAMA_VISION_MODEL`,
  default `qwen2.5vl:7b`), o texto vira o conteúdo documentado (`doc_type="image"`).
- **Coleções**: se o instagrapi expuser a coleção/pasta do post, vira tag
  (ex.: `coleção/tutoriais`); senão, tags vêm da IA (comportamento atual).
- **Worker**: daemon contínuo no container `ig-worker` (mesma imagem do H3,
  mesmo compose, mesma rede → alcança `postgres:5432` e `rabbitmq`; Ollama do host
  via `extra_hosts: host.docker.internal:host-gateway`). Concorrência configurável
  (`IG_WORKER_CONCURRENCY`, default 1) pois Whisper/Ollama dividem a VRAM com o H3.
- **Interface**: tools MCP fail-soft (`ig_sync_saved`, `ig_queue_status`,
  `ig_worker_start/stop`, `ig_get_progress`) + slash commands. Enfileirar ≠
  processar: `ig_sync_saved` só publica; o daemon processa em background.
- **RabbitMQ indisponível**: tools retornam `{ok: false, error}`; worker reconecta
  com backoff.

## Contrato da mensagem

```json
{
  "ig_pk": "3123456789012345678",
  "media_type": "video" | "image" | "carousel",
  "url": "https://www.instagram.com/reel/...",
  "title": "Título/caption (truncado)",
  "owner_username": "autor",
  "collection_name": "Tutoriais" | null,
  "status": "queued"
}
```

- Queue `ig.saved` (durable). Header `attempts` (inicia 0).
- `attempts >= 3` → move para `ig.saved.dead` (DLQ) + log. Caso contrário `nack`
  requeue (com backoff).
- Mensagem corrompida → DLQ direta (sem loop de requeue).

## Config (.env)

```
IG_SESSIONID=...                         # obrigatório (sessionid dos cookies do Chrome)
RABBITMQ_URL=amqp://guest:guest@localhost:5672/   # default local; VPS = trocar
RABBITMQ_QUEUE=ig.saved
IG_WORKER_CONCURRENCY=1
IG_DOWNLOADS_DIR=downloads/ig
OLLAMA_VISION_MODEL=qwen2.5vl:7b
WHISPER_MODEL=small                       # já existe
```

## Tools MCP novas

| Tool | Função | GPU |
|---|---|---|
| `ig_sync_saved()` | instagrapi → lista todos salvos → filtra → publica. Retorna `{ok, published, skipped_existing, total}` | Não |
| `ig_queue_status()` | tamanho da fila `ig.saved`, `ready`/`unacked`/`dead`, workers | Não |
| `ig_worker_start()` / `ig_worker_stop()` | inicia/pausa o daemon consumer | Sim |
| `ig_get_progress()` | últimos N resultados processados (estado em `downloads/ig/state.json` + consulta KB) | Não |

Slash commands (`scripts/generate_commands.py`, padrão existente):
`/ig-sync`, `/ig-status`, `/ig-worker`.

## Docker Compose

- Novo serviço `rabbitmq`: imagem `rabbitmq:3-management`, porta 5672 + 15672
  publicadas só em `127.0.0.1`.
- Novo serviço `ig-worker`: mesma imagem do H3, `--gpus all`, rede do compose,
  `extra_hosts: host.docker.internal:host-gateway`, `depends_on: comfyui, rabbitmq`.
  Comando: `python -m minimax_mcp.ig_worker`.
- Dependências novas no `pyproject.toml`: `instagrapi`, `pika`.

## Segurança

- `IG_SESSIONID` e credenciais RabbitMQ só no `.env` (gitignored). Nunca logar
  nem commitar.
- RabbitMQ local publicado só em `127.0.0.1`; VPS via `RABBITMQ_URL` com credenciais.
- instagrapi com `delay_range` (evita checkpoint/rate-limit).

## Erros

- Corrompida → DLQ direta.
- LLM/transcribe falha → tentativa++, requeue com backoff.
- RabbitMQ fora → tools fail-soft `{ok:false}`; worker reconecta com backoff.
- Download bloqueado (privado/expirado) → DLQ após tentativas.

## Testes

- **unit**: parse de mensagem, dedup key, lógica de tentativas/DLQ, tag de coleção.
- **integration_db**: dedup real contra Postgres (doc fake com `ig_pk`; re-sync
  não duplica).
- **integration_llm**: vision descreve imagem fake; `ingest_text` end-to-end.
- **e2e manual** (precisa conta IG): `ig_sync_saved` real → worker processa 1-2 →
  confere no KB.
