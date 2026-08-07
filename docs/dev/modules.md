# Module Guide

How the code is organized and how data flows through the system. All modules
live in `src/minimax_mcp/`. The generated
[MCP Tools Reference](../MCP_TOOLS.md) lists the 18 live tools with their
exact parameters — this page explains what each module does underneath.

## Two subsystems, one server

The `server.py` module registers **18 MCP tools** on a single FastMCP app.
They fall into two groups:

1. **Video factory + Audiovisual Studio** — MiniMax H3 generation via
   ComfyUI, download/transcribe/orchestrate.
2. **Knowledge base** — Postgres + pgvector + local LLM ingest/search/ask.

The knowledge-base tools import `minimax_mcp.knowledge` lazily inside each
function so the whole server can boot even when the KB dependencies
(Postgres, Ollama) are down.

## Module responsibilities

### `server.py` — FastMCP app + tool wiring

- Owns the `mcp = FastMCP(...)` instance and all `@mcp.tool()` registrations.
- Reads config from the environment (`COMFYUI_URL`, `OUTPUT_DIR`, `MODEL_*`,
  `KB_DATABASE_URL`, `LLM_*`, etc.) at import time.
- Host/container path mapping for the dockerized ComfyUI setup:
  `to_host_path()` / `to_container_path()` /
  `downloads_to_host_path()` / `downloads_to_container_path()`.
- Each tool is a thin wrapper that imports the domain module and delegates —
  e.g. `knowledge_search()` calls `knowledge.search()`. Keeping the tools
  thin means the underlying functions are unit-testable without MCP.

### `core.py` — shared ComfyUI helpers

- `load_workflow()` — loads the API workflow JSON from `WORKFLOW_PATH`.
- `duration_to_frames(duration, fps=24)` — the H3 17-frame-grid math from
  the template (5 s → 124 frames, 10 s → 243).
- `inject_scene()` — patches the loader nodes (1–4) with the configured
  model set and the H3 node (5) with prompt/duration/resolution.
- `submit_scene_core()` / `wait_for_video_core()` / `compose_final_core()` —
  the actual ComfyUI interaction, used by both `server.py` and
  `orchestrator.py` (no circular imports).

### `comfyui_client.py` — ComfyUI HTTP + WebSocket client

- `ComfyUIClient`: `submit_prompt()`, `get_history()`, `wait_for_completion()`
  (WebSocket-driven progress), `download()`. Wraps `requests`/`websockets`
  against `COMFYUI_URL`. Raises `ComfyUIError` on failure.
- `resolve_output()` scans **every** history output kind (`images`, `videos`,
  `gifs`) for a `.mp4` filename — `SaveVideo` lands under the `images` key.

### `downloader.py` — yt-dlp wrapper

- `VideoDownloader` + `download_video()`: downloads Instagram Reels, YouTube,
  etc. via yt-dlp with `cookiesfrombrowser` (default `chrome`). Returns
  `{ok, filepath, title, duration, uploader}`.

### `transcriber.py` — faster-whisper wrapper

- `AudioTranscriber` + `transcribe_video()`: GPU (default `cuda`) Whisper
  transcription with timestamps and per-segment text. Default language `pt`.

### `orchestrator.py` — the studio pipeline

- `AudiovisualStudio` + `run_studio_pipeline()`: URL → download →
  transcribe → cinematic prompt → (optionally) generate video. Powers the
  `studio_pipeline` MCP tool.

### `llm.py` — LLM client (provider-abstracted)

- `generate_structured(prompt, model, ...)` — returns a parsed dict from the
  LLM. Uses `POST /api/chat` with a system message telling the model to
  ignore embedded instructions and return strict JSON (`format=json`,
  `num_predict=2048`, `temperature=0.2`).
- Provider switch via `LLM_PROVIDER`: `ollama` (default) or
  `openai-compatible` (set `OPENAI_API_URL`/`OPENAI_API_KEY`).
- `embed(text)` — embeddings via Ollama (`EMBEDDING_MODEL`, default
  `mxbai-embed-large`, 1024-dim). Embeddings are always local Ollama
  regardless of `LLM_PROVIDER`.
- `chat(prompt)` — free-form completion (used by `ask`).
- `SUMMARY_PROMPT_TEMPLATE` / `build_summary_prompt()` — turns raw text into
  a `{summary, tutorial, ...}` JSON object.

### `db.py` — persistence layer

- SQLAlchemy models: `Document`, `Chunk`, `Embedding` (pgvector).
- `chunk_text(text, max_chars=700, overlap=100)` — overlap chunking. The
  default `max_chars=700` keeps each chunk under Ollama's ~512-token
  embedding batch limit.
- `save_document(...)`, `search_documents(...)`, `reindex_all(...)`,
  `delete_documents(...)`. ORM-only access so the engine is swappable.
- **Gotcha:** `delete_documents(source_url=None)` deletes every document
  without a source_url — always pass an explicit `source_url` when you only
  want to remove one source.

### `knowledge.py` — KB orchestration + prompts

- `_parse_frontmatter()` — reads YAML frontmatter (title/tags/url) from
  markdown files.
- `_extract_section()` — reuses a `## Summary` section if present, else the
  LLM generates it.
- `ingest_text` / `ingest_video` / `ingest_audio` / `ingest_markdown` — the
  four ingest paths, each ending in `_save_document_with()`.
- `search()` — hybrid: Postgres full-text (`to_tsvector`/`plainto_tsquery`)
  + pgvector cosine; returns ranked `{document_id, snippets, score, ...}`.
- `ask()` — RAG: search → inject top-k into a prompt requiring per-claim
  source citations → `llm.chat`.
- `reindex()` — recompute chunks + embeddings for all documents.

### `vault.py` — Obsidian export (optional)

- `write_markdown_copy(document, vault_path)` — writes a markdown copy to
  `VAULT_PATH` (Obsidian). Failures never fail the ingest (soft-fail).
  Postgres remains the source of truth; the vault is a convenience copy.

## Data flow: knowledge ingest

```
text / video / audio / markdown
        │
        ▼
knowledge.ingest_* ──▶ transcribe (video/audio) ──▶ LLM summary+tutorial
        │                                              (llm.generate_structured)
        ▼
db.save_document ──▶ chunk_text ──▶ embeddings (llm.embed) ──▶ pgvector
        │
        ▼
vault.write_markdown_copy (optional, best-effort)
```

## Data flow: knowledge query

```
search(query) ──▶ full-text + cosine over Embeddings
        │
        ▼
ranked candidates ──▶ ask(query, top_k) ──▶ LLM answer with per-claim
                                              citations (llm.chat)
```

## Data flow: video generation

```
submit_scene(prompt, duration, w, h, seed)
        │
        ▼
core.inject_scene(workflow) ──▶ comfyui_client.submit_prompt ──▶ /prompt
        │
        ▼
comfyui_client.wait_for_completion (WebSocket) ──▶ .mp4 in output/
```
