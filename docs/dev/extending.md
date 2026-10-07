# Extending the System

Practical guides for the most common extension points. All new MCP tools
should follow the existing thin-wrapper pattern in `server.py`.

> This repo is video-generation only since 2026-10-06 — the knowledge-base
> and Instagram-sync domain moved to [`insta_kb`](https://github.com/leonardodg/insta_kb).
> "Add a new ingest type" and "Add a new LLM provider" below live there now.

## Add a new MCP tool

Adding a tool touches nine places. Six of them are enforced by a test, so
skipping one turns the suite red rather than shipping a half-registered tool —
which is what happened once when a stale container image left the server
exposing none of the registered tools.

| # | Step | Enforced by |
|---|---|---|
| 1 | Implement the domain function in its module (`knowledge.py`, `core.py`, …), free of MCP concerns so it stays unit-testable | — |
| 2 | Register it in `server.py` with `@mcp.tool()` and a `Field(description=…)` per parameter | — |
| 3 | Name its slash command in `scripts/command_docs/catalog.py` | `unit_commands` |
| 4 | Record operational knowledge the signature cannot express in `scripts/command_docs/overrides.py` | — (optional) |
| 5 | `uv run python scripts/generate_commands.py` and commit the generated `.md` | `unit_commands` (staleness) |
| 6 | `uv run python scripts/generate_mcp_docs.py` for `docs/MCP_TOOLS.md` | — |
| 7 | Add the tool name to `tests/unit_registry.py` | `unit_registry` |
| 8 | Bump the expected tool count in `tests/unit_commands.py` | `unit_commands` |
| 9 | Add a row to the **README** tool table | `unit_commands` |

Two more, when they apply:

- **New dependency?** Rebuild the container image (`./scripts/start_comfyui.sh`).
  The image ships its own venv, and a stale one makes `server.py` fail to import
  — leaving the MCP handshake succeeding while the server exposes *zero* tools.
  `tests/09_container_deps.sh` catches this.
- **Write a test** for the domain function (`tests/unit_*.py`, marker `unit`),
  plus a script-level entry in `tests/test_scripts.py`. See
  [Contributing & Testing](contributing.md).

The generated files — `.opencode/command/*.md`, `docs/MCP_TOOLS.md`,
`docs/COMMANDS.md` — are never hand-edited. Change `overrides.py` and
regenerate.

### The shape of a tool

```python
@mcp.tool()
def my_new_tool(
    param: str = Field(description="What this param does"),
) -> dict[str, Any]:
    """One-line description of what the tool does."""
    from minimax_mcp import orchestrator
    return orchestrator.my_function(param)
```

- `Field(description=...)` on every parameter — clients read these, and the
  slash command generator turns them into the command's own documentation.
- Import the domain module lazily inside the function if it has a heavy or
  optional dependency, so the server still boots without it.
- Return a plain `dict` carrying `ok: bool`. Never let an exception cross the
  MCP boundary.

## Add a new download platform

`downloader.py` uses yt-dlp, so any platform yt-dlp supports works out of the
box (Instagram, YouTube, TikTok, etc.). No code change needed for a new
platform; test it with the `download_video` tool. If the platform needs
browser cookies, pass `browser=` (default `chrome`).

## Add a new model (Bigger MiniMax variants)

The ComfyUI loader nodes (1–4) in the workflow are patched per submission
with the configured model set from `.env` (`MODEL_DIFFUSION`,
`MODEL_TEXT_ENCODER`, `MODEL_VIDEO_VAE`, `MODEL_AUDIO_VAE`). To switch
models:

1. Add the new filenames/byte sizes to `.env` (see `.env.example` for the
   FP8_SCALED/BF16 variants).
2. Ensure the files exist in `{MODELS_DIR}/{diffusion_models,text_encoders,vae}`
   (download via `scripts/download_models.sh`, which reads the `MODEL_*` vars).
3. No workflow edit needed — `core.inject_scene()` reads the model names
   from the env at submit time.

## Code style & checks

- **Formatting/lint:** `ruff check src tests` (and `ruff format` if you want
  auto-formatting).
- **Tests:** `uv run pytest -m unit` for fast pure-logic tests; the
  `integration_db` marker needs the `comfyui` container up (see
  [Contributing & Testing](contributing.md)).
- **Docs:** after any registry or behavior change, rebuild the site:
  `uv run mkdocs build --strict`.
