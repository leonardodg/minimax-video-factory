# Developer Documentation

Everything you need to develop, test, and extend this project. The docs in
this section describe the system **as it is today** — always verify against
the actual source in `src/minimax_mcp/` and the generated tool reference in
`docs/MCP_TOOLS.md`.

## What's here

- [Development Environment](dev-environment.md) — get a working dev setup
  from scratch: `uv`, `.env`, Postgres, Ollama, ComfyUI, MCP servers.
- [Module Guide](modules.md) — what each module does and how data flows
  through the system.
- [Extending the System](extending.md) — add an MCP tool, a new ingest type,
  an LLM provider, or a new download platform.
- [Contributing & Testing](contributing.md) — contribution flow, test
  markers, linting, and the diagnostic suite.

## Source layout at a glance

```
src/minimax_mcp/
├── server.py            # FastMCP app + all tool registrations (18 tools)
├── comfyui_client.py    # ComfyUIClient: submit/history/websocket/download
├── core.py              # shared ComfyUI helpers (workflow, paths, durations)
├── downloader.py        # yt-dlp wrapper with browser cookies
├── transcriber.py       # faster-whisper wrapper (GPU, PT-BR + timestamps)
├── orchestrator.py      # URL → download → transcribe → prompt → video
├── llm.py               # Ollama / OpenAI-compatible client + embeddings
├── db.py                # SQLAlchemy models, chunking, CRUD, search, reindex
├── knowledge.py         # ingest/search/ask/reindex orchestration + prompts
└── vault.py             # Obsidian markdown export (optional, VAULT_PATH)
```

The generated [MCP Tools Reference](../MCP_TOOLS.md) is the source of truth
for the live tool registry; this section explains how the pieces fit together.
