# Extending the System

Practical guides for the most common extension points. All new MCP tools
should follow the existing thin-wrapper pattern in `server.py`.

## Add a new MCP tool

1. **Implement the domain function** in the right module. E.g. for a
   knowledge-base feature, add the function to `knowledge.py` (or `db.py`,
   `llm.py`, etc.). Keep it free of MCP concerns so it stays unit-testable.

2. **Register it in `server.py`** with `@mcp.tool()`, following the existing
   pattern:

   ```python
   @mcp.tool()
   def my_new_tool(
       param: str = Field(description="What this param does"),
   ) -> dict[str, Any]:
       """One-line description of what the tool does."""
       from minimax_mcp import knowledge
       return knowledge.my_function(param)
   ```

   Notes:
   - Use `Field(description=...)` for every parameter — clients (OpenCode)
     read these descriptions.
   - Import the domain module lazily inside the function so the server still
     boots if the KB stack is down.
   - Return a plain `dict` with `ok: bool` for failures.

3. **Regenerate the tool reference** so `docs/MCP_TOOLS.md` matches the live
   registry (it's generated from the registry, not hand-edited):

   ```bash
   source scripts/config.sh
   MCP_TRANSPORT=stdio uv run python scripts/generate_mcp_docs.py
   ```

4. **Add a test.** Prefer a unit test for the domain function
   (`tests/unit_knowledge.py`-style, marker `unit`) plus a script-level test
   in `tests/test_scripts.py` if the tool is also exercised by the diagnostic
   suite. See [Contributing & Testing](contributing.md).

5. **Update docs** if the tool changes user-facing behavior: the
   `docs/KNOWLEDGE_BASE.md` tutorial tables, `README.md`, and `AGENTS.md` all
   reference the tool list.

## Add a new ingest type (video/audio/text/markdown)

1. Add the ingest function in `knowledge.py` following the existing four.
   The common tail is `_save_document_with(...)` which handles chunking,
   embeddings, and the optional vault write — reuse it.
2. If the ingest needs to extract content first (download, transcribe), reuse
   `downloader.py` / `transcriber.py`.
3. Register the MCP tool (see above) and regenerate the docs.

## Add a new LLM provider

`llm.py` dispatches on `LLM_PROVIDER`:

- `ollama` → `_ollama_generate()`
- `openai-compatible` → `_openai_compatible_generate()` (uses
  `OPENAI_API_URL` / `OPENAI_API_KEY`; works with OpenRouter/Groq free tier)

To add a provider:

1. Add a branch in `generate_structured()` / `chat()` and a
   `_<provider>_generate()` helper.
2. Make sure it honors the same contract: `force_json` must produce
   parseable JSON that `parse_llm_json()` can read.
3. Update `.env.example` docs and the Knowledge Base guide.

**Embeddings are always local Ollama** regardless of `LLM_PROVIDER`.

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
  integration markers need Postgres + Ollama up (see
  [Contributing & Testing](contributing.md)).
- **Docs:** after any registry or behavior change, rebuild the site:
  `uv run mkdocs build --strict`.
