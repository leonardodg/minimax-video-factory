# Knowledge Base — Tutorial & Reference

Personal knowledge base powered by **Postgres + pgvector** (storage and
semantic search) and a **local LLM (Ollama)** that turns transcriptions/text
into a summary, step-by-step tutorial, objectives, and tags. Everything runs
locally (no cloud).

In this document:
- [1. What it is / when to use](#1-what-it-is-when-to-use)
- [2. Prerequisites & setup](#2-prerequisites-setup)
- [3. The 7 tools (full reference + best options)](#3-the-7-tools)
- [4. Recommended flows step by step](#4-recommended-flows)
- [5. Using it from the OpenCode chat (prompt examples)](#5-using-it-from-the-opencode-chat)
- [6. Database structure](#6-database-structure)
- [7. Configuration (.env)](#7-configuration-env)
- [8. Troubleshooting](#8-troubleshooting)

---

## 1. What it is / when to use

The video MCP exposes **18 tools in total** (11 original MiniMax H3/Studio + 7
knowledge base). The 7 new ones:

| Tool | What it does | Needs GPU? |
|---|---|---|
| `knowledge_ingest_text` | Saves a ready text/transcription to the base (summary+tutorial via LLM) | No |
| `knowledge_ingest_video` | Downloads + transcribes + documents a video (Reel/YouTube) | Yes (Whisper GPU) |
| `knowledge_ingest_audio` | Transcribes + documents an audio/podcast | Yes (Whisper GPU) |
| `knowledge_ingest_markdown` | Imports `.md` files (Obsidian/tutorials): frontmatter + `## Summary` or LLM | No |
| `knowledge_search` | Keyword + semantic search in the base | No |
| `knowledge_ask` | Answers questions with RAG (search + LLM) about what was saved | No |
| `knowledge_reindex` | Recomputes chunks + embeddings for all documents | No |

**Typical lifecycle:** `ingest_*` → `search`/`ask` → (switched embedding
model?) → `reindex`.

---

## 2. Prerequisites & setup

```bash
cd $PROJECT_ROOT
source scripts/config.sh

# 1. Postgres + pgvector (dedicated minimax-kb-postgres container)
docker compose $COMPOSE_ARGS up -d postgres

# 2. Tables (alembic) — once
uv run alembic upgrade head

# 3. Ollama running with the models
ollama list          # should show lfm2:24b and mxbai-embed-large
# if missing:
# ollama pull lfm2:24b
# ollama pull mxbai-embed-large
```

> **Where the server runs:** the knowledge base uses **host-uv** (`uv run python
> src/minimax_mcp/server.py`), not the ComfyUI container — it needs direct
> access to `localhost:11434` (Ollama) and `127.0.0.1:5432` (Postgres) from
> the host.

---

## 3. The 7 tools

### `knowledge_ingest_markdown`

Imports **markdown** files (obsidian, docs, tutorials). Reuses the YAML
frontmatter (`title`, `url`, `tags`, `aliases`) and a `## Summary` section
when present; otherwise the LLM generates `summary` + `tutorial` + `objectives`
+ `tags`. Accepts a single file or a directory (skips dot-prefixed subfolders,
e.g. `.trash`/`.obsidian`).

| Parameter | Required | Default | Best option |
|---|---|---|---|
| `path` | ✅ | — | path to the `.md` or the folder |
| `recursive` | ❌ | `false` | `true` to include subfolders |
| `doc_type` | ❌ | `document` | `document`, `tutorial`, `manual` |
| `platform` | ❌ | `obsidian` | source of the files |
| `language` | ❌ | `pt` | content language |
| `reindex_if_exists` | ❌ | `false` | regenerate embeddings if the file already exists in the base |

> **Tip:** to migrate an entire Obsidian collection, point `path` at the
> folder and use `recursive=true`. Uploading ~27 tutorials takes ~1–2 min
> with `lfm2:24b`.

### `knowledge_ingest_text`

Stores a **ready** text/transcription (pasted, from a file, transcribed
elsewhere) and generates `summary` + `tutorial` + `objectives` + `tags` via
LLM.

| Parameter | Required | Default | Best option |
|---|---|---|---|
| `text` | ✅ | — | The full transcription; more context = better tutorial |
| `source_url` | ❌ | `null` | source URL (Reel, YT, article) to link in the result |
| `title` | ❌ | summary[0:80] | short, descriptive title |
| `platform` | ❌ | `manual` | `manual`, `instagram`, `youtube`, `podcast` |

**Returns:** `{ok, document_id, title, summary, tutorial, tags, vault}`

### `knowledge_ingest_video`

Downloads (yt-dlp + cookies), transcribes (Whisper GPU) and documents a video
in one step.

| Parameter | Required | Default | Best option |
|---|---|---|---|
| `url` | ✅ | — | Reel/YouTube URL |
| `browser` | ❌ | `chrome` | `chrome`, `firefox`, `edge`, `brave` — use the logged-in browser |
| `whisper_model` | ❌ | `small` | `small` (good balance), `medium` (more accurate), `large-v3` (max, slow) |

> **GPU note:** uses Whisper on `cuda`; each ingest consumes VRAM for a few
> minutes.

### `knowledge_ingest_audio`

Same as video, but for **audio/podcast**. Accepts a local path **or** a URL
(downloads first).

| Parameter | Required | Default | Best option |
|---|---|---|---|
| `path_or_url` | ✅ | — | `/path/audio.mp3` or podcast URL |
| `browser` | ❌ | `chrome` | only relevant when passing a URL |
| `whisper_model` | ❌ | `small` | same as above |

### `knowledge_search`

Hybrid search: **full-text in Portuguese** (Postgres `to_tsvector`) +
**semantic cosine** (pgvector `mxbai-embed-large`). Returns ranked snippets.

| Parameter | Required | Default | Best option |
|---|---|---|---|
| `query` | ✅ | — | term or short phrase |
| `top_k` | ❌ | `5` | `5–10` to explore, `3` for question context |

### `knowledge_ask`

RAG: searches the `top_k` relevant documents, builds context and the LLM
answers **only from that** (doesn't make things up — says so if it doesn't
know). Also returns `sources`.

| Parameter | Required | Default | Best option |
|---|---|---|---|
| `query` | ✅ | — | natural-language question |
| `top_k` | ❌ | `3` | `3` typical; increase for broad questions |

### `knowledge_reindex`

Recomputes chunks + embeddings for **all** documents. Use when switching the
embedding model (the `model` is recorded per chunk).

| Parameter | Required | Default | Best option |
|---|---|---|---|
| `embedding_model` | ❌ | `EMBEDDING_MODEL` from `.env` | only set it to force another one |

---

## 4. Recommended flows

**Flow A — document a YouTube/Instagram Reel and save it:**
```
knowledge_ingest_video(url="https://www.youtube.com/watch?v=...", whisper_model="small")
```

**Flow B — transcribe audio already on disk:**
```
knowledge_ingest_audio(path_or_url="/path/my_podcast.mp3")
```

**Flow C — save pasted text (notes, article, old transcription):**
```
knowledge_ingest_text(text="<paste the transcription>", title="My summary", platform="manual")
```

**Flow D — ask your base (RAG):**
```
knowledge_ask(query="How did I install Docker on Ubuntu?")
```

**Flow E — maintenance (embedding switch):**
```
# 1. change EMBEDDING_MODEL in .env  2. then:
knowledge_reindex()
```

---

## 5. Using it from the OpenCode chat

The `minimax-knowledge-base` MCP server is already configured
(`~/.config/opencode/opencode.json`, `enabled: true`). **Restart opencode** to
load it; then just chat:

> **"Document this text in my knowledge base: [paste text]"**
> → OpenCode calls `knowledge_ingest_text` and shows `document_id`, summary, tutorial and tags.

> **"Download, transcribe and save this Reel to the base: https://www.instagram.com/p/DbHIZl5Pk_0/"**
> → `knowledge_ingest_video(url=..., whisper_model="small")` (needs GPU/Whisper).

> **"Transcribe and document this podcast: /path/my_podcast.mp3"**
> → `knowledge_ingest_audio(path_or_url=...)`.

> **"Search my base for 'Docker Ubuntu'"**
> → `knowledge_search(query="Docker Ubuntu")`.

> **"What have I saved about Docker? Answer based on my base."**
> → `knowledge_ask(query="What have I saved about Docker?")`.

> **"I just switched the embedding model; reindex everything."**
> → `knowledge_reindex()`.

**Chat tips:**
1. If opencode doesn't find the tool, make sure you're in a **new session**
   (MCP is loaded at startup) and that Postgres + Ollama are up.
2. Prefer `knowledge_ask` for **questions** and `knowledge_search` for
   **listing/exploring**.
3. `ingest_video`/`ingest_audio` use GPU (Whisper). If VRAM is busy with an
   H3 render, use `whisper_model="base"` (lighter) or wait for it to finish.

---

## 6. Database structure

Created by `alembic upgrade head` (`alembic/versions/0001_initial.py`).
Relationship: **1 document → N chunks → 1 embedding per chunk.**

### `documents` — one record per ingested item

| Column | Type | Description |
|---|---|---|
| `id` | integer PK | |
| `type` | varchar(20) | `text`, `video`, `audio` |
| `source_url` | text nullable | source URL |
| `platform` | varchar(50) nullable | `manual`, `instagram`, `youtube`, `podcast` |
| `title` | text nullable | |
| `language` | varchar(10) nullable | e.g. `pt` |
| `transcription_text` | text nullable | original text/transcription |
| `summary` | text nullable | LLM-generated summary |
| `tutorial` | text nullable | step-by-step tutorial (markdown) |
| `objectives` | text nullable | objectives, one per line |
| `tags` | json nullable | list of tags |
| `raw_file_path` | text nullable | path of the original downloaded file |
| `llm_provider` | varchar(50) nullable | `ollama` |
| `llm_model` | varchar(100) nullable | e.g. `lfm2:24b` |
| `created_at` | datetime | default `now()` |

### `chunks` — overlapping text snippets for embedding

| Column | Type | Description |
|---|---|---|
| `id` | integer PK | |
| `document_id` | int FK → `documents.id` (ON DELETE CASCADE) | |
| `chunk_text` | text | snippet (up to ~700 chars, overlap 100) || `chunk_index` | integer | order within the document |

### `embeddings` — semantic vector per chunk

| Column | Type | Description |
|---|---|---|
| `id` | integer PK | |
| `chunk_id` | int FK → `chunks.id` (ON DELETE CASCADE, UNIQUE) | 1:1 |
| `model` | varchar(100) | model that generated the vector (e.g. `mxbai-embed-large`) |
| `vector` | `vector(1024)` (pgvector) | embedding |

### Indexes

- GIN full-text on `documents.transcription_text` (language `portuguese`) for
  `to_tsvector`/`plainto_tsquery`.
- pgvector index on `embeddings.vector` for cosine.

### How to inspect

```bash
docker exec minimax-kb-postgres psql -U kb -d knowledge -c "\dt"
docker exec minimax-kb-postgres psql -U kb -d knowledge \
  -c "SELECT id, type, title, llm_model, tags FROM documents ORDER BY id;"
```

---

## 7. Configuration (.env)

| Var | Default | Description |
|---|---|---|
| `KB_DATABASE_URL` | `postgresql+psycopg://kb:kb@127.0.0.1:5432/knowledge` | SQLAlchemy connection |
| `KB_POSTGRES_USER/PASSWORD/DB/PORT` | `kb`/`kb`/`knowledge`/`5432` | used by compose |
| `LLM_PROVIDER` | `ollama` | or `openai-compatible` |
| `LLM_MODEL` | `lfm2:24b` | **best balance for ~30 GB RAM**. Alternatives: `qwen2.5-coder:14b` (faster, ~1 min/ingest) or `qwen2.5:32b-instruct-q4_K_M` (better quality, but 15+ min — swap). `gpt-oss:20b` **doesn't work** (ignores `format=json`). |
| `LLM_TIMEOUT` | `900` | timeout per call (s); increase for 32B models |
| `OLLAMA_URL` | `http://localhost:11434` | |
| `EMBEDDING_MODEL` | `mxbai-embed-large` | embeddings are **always local**, even with `LLM_PROVIDER=openai-compatible` |
| `EMBEDDING_DIM` | `1024` | vector dimension (must match the model) |
| `VAULT_PATH` | empty (off) | markdown copy to Obsidian, if set |
| `WHISPER_MODEL` / `WHISPER_DEVICE` | `small` / `cuda` | transcription |
| `STUDIO_DOWNLOADS_DIR` | `<project>/downloads` | where downloaded files are saved |

---

## 8. Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `knowledge_*` returns a connection error to `127.0.0.1:5432` | Postgres is down | `docker compose $COMPOSE_ARGS up -d postgres` |
| Error `42P01 relation "documents" does not exist` | migration not applied | `uv run alembic upgrade head` |
| `LLM generation failed: timed out` | `LLM_TIMEOUT` too short for the model | use `lfm2:24b` or increase `LLM_TIMEOUT` |
| `LLM generation failed: Expecting value... char 0` | model returns non-JSON text | switch `LLM_MODEL` (`gpt-oss:20b` is incompatible) |
| Ollama not responding | daemon stopped | `ollama serve` (or systemd) |
| OpenCode doesn't see the tools | old session / entry not loaded | restart opencode; check `enabled: true` |
| Embeddings don't match after switching model | chunks with the old `model` | `knowledge_reindex()` |
