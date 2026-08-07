# ARCHITECTURE.md — MiniMax Video Factory

How the pieces fit together and where the rendering decisions live.

## System diagram

```
[ Video Script (story / scenes) ]
        │
        ▼
[ OpenCode ]  ── MCP (stdio) ──►  [ MCP Server: src/minimax_mcp/server.py ]
                                     │  FastMCP, 6 tools (see below)
                                     │  env: COMFYUI_URL, WORKFLOW_PATH, MODELS_DIR, OUTPUT_DIR
                                     ▼
                              [ ComfyUIClient ]  ── POST /prompt, GET /history, WS /ws, GET /view
                                     │
                                     ▼
                              [ ComfyUI (Docker, v0.30.2, GPU) ]
                                     │  MiniMaxH3ImageToVideo + samplers + VAE-decode + CreateVideo/SaveVideo
                                     ▼
                              [ output/*.mp4  (video + native stereo audio) ]
```

## Components

| Layer | Code | Responsibility |
|---|---|---|
| Orchestrator | OpenCode (config added last) | Splits the script into scenes, writes H3-structured prompts, calls MCP tools |
| Local agent | `src/minimax_mcp/server.py` | MCP server; injects scene values into the API workflow, submits jobs, waits, resolves outputs, composes final |
| HTTP/WS client | `src/minimax_mcp/comfyui_client.py` | `submit()`, `get_history()`, `wait_for_execution()` (WS), `resolve_output()`, `download_file()` |
| Render engine | `docker/` image | ComfyUI pinned v0.30.2, torch 2.8 (DynamicVRAM), loads INT4 H3 set |
| Workflow | `workflows/minimax_h3_t2v_api.json` | Expanded T2V API graph (14 nodes) — see `AGENTS.md` §6 for the node map |

## MCP tools

- `health_check()` — ComfyUI `/system_stats` + the 4 required model files (size-aware).
- `submit_scene(prompt, duration, width, height, seed, filename_prefix)` — patches the
  workflow (H3 node `5`, noise node `6`, SaveVideo prefix), POSTs `/prompt`, returns `prompt_id`.
- `get_status(prompt_id)` — poll `/history`.
- `wait_for_video(prompt_id, timeout)` — websocket-driven; returns the `.mp4` path.
- `list_outputs()` — newest `.mp4` files under `output/`.
- `compose_final(scene_paths, output_path)` — `ffmpeg -f concat -c copy` of scenes.

## Key design decisions

1. **Models are mounted read-only** (`${MODELS_DIR}:/comfy/ComfyUI/models:ro`) so the
   host is the source of truth; `health_check` validates against host paths.
2. **Workflow is expanded API JSON, not the UI template.** The official template packs
   everything behind a *subgraph* node whose `type` is a hash — the backend rejects it.
   The shipped workflow is the frontend-expanded version (14 nodes) and is what the
   server submits.
3. **Duration math**: H3 frame count snaps to a 17k+5 grid at 24 fps
   (`round(seconds*24)` then bump to `≡5 (mod 17)`), matching the template's
   ComfyMathExpression. 5 s → 124 frames, 10 s → 243.
4. **Dynamic VRAM offload** (`--lowvram` + torch ≥ 2.8): the 32 B text encoder
   (~9 GB) and INT4 UNet (~11 GB staged) cannot be co-resident in 12 GB; DynamicVRAM
   swaps them. Without torch ≥ 2.8 the lowvram patches never attach and sampling OOMs.
5. **SaveVideo output is reported under the `images` history key** (with
   `"animated": true`), not `videos`/`gifs` — `resolve_output()` scans all keys.

## Costs / timing (measured, RTX 4080 Laptop)

- 512×320, 5 s, 20 steps, INT4: ~4 min wall (≈ 12.8 s/it + init) for the **first** run
  (includes model load); later runs reuse the staged cache.
- 1024×576 at 20 steps is roughly 4–5× the compute of the smoke resolution — budget
  accordingly per scene. This is the **default** and the largest resolution that
  renders reliably here.
- 1344×768 is the H3 canvas maximum but **OOMs the sampler on 12 GB of VRAM**
  (`torch.OutOfMemoryError`). Only use it on a larger card.
