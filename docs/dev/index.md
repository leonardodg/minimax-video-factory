# Developer Documentation

Everything you need to develop, test, and extend this project. The docs in
this section describe the system **as it is today** — always verify against
the actual source in `src/minimax_mcp/` and the generated tool reference in
`docs/MCP_TOOLS.md`.

> **Looking for the knowledge base or Instagram sync?** That domain moved
> whole — code and production data — to
> [`insta_kb`](https://github.com/leonardodg/insta_kb) in 2026-10-06. This
> repo is video-generation only now.

## What's here

- [Development Environment](dev-environment.md) — get a working dev setup
  from scratch: `uv`, `.env`, ComfyUI, MCP servers.
- [Module Guide](modules.md) — what each module does and how data flows
  through the system.
- [Extending the System](extending.md) — add an MCP tool or a new download
  platform.
- [Contributing & Testing](contributing.md) — contribution flow, test
  markers, linting, and the diagnostic suite.

## Source layout at a glance

```
src/minimax_mcp/
├── server.py            # FastMCP app + all tool registrations (12 tools)
├── comfyui_client.py    # ComfyUIClient: submit/history/websocket/download
├── core.py              # shared ComfyUI helpers (workflow, paths, durations)
├── downloader.py        # yt-dlp wrapper with browser cookies
├── transcriber.py       # faster-whisper wrapper (GPU, PT-BR + timestamps)
└── orchestrator.py      # URL → download → transcribe → prompt → video
```

The generated [MCP Tools Reference](../MCP_TOOLS.md) is the source of truth
for the live tool registry; this section explains how the pieces fit together.
