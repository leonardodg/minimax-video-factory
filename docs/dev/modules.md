# Module Guide

How the code is organized and how data flows through the system. All modules
live in `src/minimax_mcp/`. The generated
[MCP Tools Reference](../MCP_TOOLS.md) lists the 12 live tools with their
exact parameters — this page explains what each module does underneath.

> **Looking for the knowledge base or Instagram sync?** That domain
> (`knowledge.py`, `db.py`, `llm.py`, `vault.py`, `ig_sync.py`, `ig_queue.py`,
> `ig_worker.py`) moved whole — code and production data — to the
> [`insta_kb`](https://github.com/leonardodg/insta_kb) project in 2026-10-06.
> This repo is video-generation only now.

## One subsystem, one server

The `server.py` module registers **12 MCP tools** on a single FastMCP app,
all of them the video factory + Audiovisual Studio:

1. **Video factory** — MiniMax H3 generation via ComfyUI: submit, poll,
   wait, list, compose.
2. **Audiovisual Studio** — download a reference video, transcribe it,
   turn the transcript into a cinematic prompt, generate.

## Module responsibilities

### `server.py` — FastMCP app + tool wiring

- Owns the `mcp = FastMCP(...)` instance and all `@mcp.tool()` registrations.
- Reads config from the environment (`COMFYUI_URL`, `OUTPUT_DIR`, `MODEL_*`,
  etc.) at import time.
- Host/container path mapping for the dockerized ComfyUI setup:
  `to_host_path()` / `to_container_path()` /
  `downloads_to_host_path()` / `downloads_to_container_path()`.
- Each tool is a thin wrapper that delegates to `core.py`/`orchestrator.py` —
  keeping the tools thin means the underlying functions are unit-testable
  without MCP.

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
  `{ok, filepath, title, duration, uploader}`. Used by the Audiovisual Studio
  to fetch a reference video to transcribe, not by any knowledge-base path
  (that pipeline lives in `insta_kb` now).

### `transcriber.py` — faster-whisper wrapper

- `AudioTranscriber` + `transcribe_video()`: GPU (default `cuda`) Whisper
  transcription with timestamps and per-segment text. Default language `pt`.

### `orchestrator.py` — the studio pipeline

- `AudiovisualStudio` + `run_studio_pipeline()`: URL → download →
  transcribe → cinematic prompt → (optionally) generate video. Powers the
  `studio_pipeline` MCP tool.

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

## Data flow: the studio pipeline

```
studio_pipeline(url)
        │
        ▼
downloader.download_video ──▶ transcriber.transcribe_video ──▶ cinematic prompt
        │
        ▼
submit_scene_core ──▶ wait_for_video_core ──▶ .mp4 in output/
```
