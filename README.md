# MiniMax H3 · INT4 ConvRot — Local Video Factory

> Orchestrate **MiniMax H3** (text → video **+ native stereo audio**, single diffusion pass) on a local GPU, driven by **OpenCode** through an **MCP server** that talks to a **ComfyUI** backend via its HTTP/WebSocket API.

## Architecture

```
[Your Video Script]  (story / scene descriptions)
        │
        ▼
[ OpenCode (Orchestrator) ]  ──MCP (stdio)──►  [ Local Agent (MCP Server) ]
        │                                            │   POST /prompt
        │       ┌────────────────────────────────────┘
        ▼       ▼
[ ComfyUI Backend (Docker + GPU) ]  ◄── shares models + output with MCP
        │   WebSocket + GET /view
        ▼
[ Final .mp4  (video + stereo audio) ]
```

The MCP server and ComfyUI run in the **same container** (no host uv/Python). For
remote VPS use, the MCP can also be exposed over HTTPS — see
[docs/MCP_REMOTE.md](docs/MCP_REMOTE.md).

## Components

| Layer | Role | Technology |
|---|---|---|
| **OpenCode** | Interprets the script, splits into scenes (5–15 s), writes H3-structured prompts, calls the MCP tools | opencode |
| **Local Agent** | MCP server; injects prompt into the API workflow JSON, submits jobs, monitors, retrieves files | Python + FastMCP (`src/minimax_mcp/server.py`, in-image venv `/opt/mcp-venv`) |
| **Render Engine** | Loads MiniMax H3 into VRAM, runs the diffusion pass, saves `.mp4` | ComfyUI ≥ 0.30.0 (Docker) |
| **Model** | MiniMax H3 Base FL2VA, pruned **INT4** ConvRot (tuned for 12 GB VRAM) | `Merserk/MiniMax-H3-INT4-ConvRot` |

## Configuration (`.env`)

Everything is centralized in a `.env` file at the repo root (see `.env.example`):

```bash
PROJECT_ROOT=/path/to/minimax-video-factory   # absolute (used for /workspace mount)
MODELS_DIR=/var/tmp/minimax/models            # where the ~32 GB of weights live
OUTPUT_DIR=.../output                         # generated .mp4 (mounted into container)
OUTPUT_PREFIX=video/factory                   # default filename prefix
# Model set (bigger variants supported): MODEL_DIFFUSION, MODEL_TEXT_ENCODER, *_BYTES
COMFYUI_TAG=v0.30.2  COMFYUI_PORT=8188  COMFYUI_EXTRA_ARGS=--lowvram --fast-disk ...
MCP_TRANSPORT=streamable-http  MCP_HOST=0.0.0.0  MCP_PORT=8848   # remote/VPS MCP
DOCKER_HUB_USER=leonardodg  DOCKER_HUB_REPO=minimax-video-factory
```

## Quick start

```bash
cd minimax-video-factory

# 0. Configure
cp .env.example .env     # edit PROJECT_ROOT, MODELS_DIR, OUTPUT_DIR

# 1. Environment checks
./scripts/diagnose.sh 00

# 2. Download models (~32 GB, public HF repos; resumes on re-run)
./scripts/download_models.sh          # reads MODEL_* + MODELS_DIR from .env

# 3. Start ComfyUI (Docker + GPU). Build includes the in-image MCP venv.
./scripts/start_comfyui.sh            # uses $COMPOSE_ARGS (loads project-root .env)

# 4. Full validation suite (models, workflow, real smoke render, MCP, E2E)
./scripts/diagnose.sh                 # runs 00..07; needs a few minutes for the renders
```

## Validation suite (`./scripts/diagnose.sh [NN ...]`)

| # | Checks | Status |
|---|---|---|
| 00 | Host prereqs (GPU/VRAM ≥ 12 GB, Docker, curl, ffmpeg) | PASS |
| 01 | Docker image + container + GPU passthrough | PASS |
| 02 | ComfyUI API up (≥ 0.30.0) + H3 node classes present | PASS |
| 03 | 4 model files present with exact sizes (env-configured set) | PASS |
| 04 | Workflow: all 14 node class_types resolve | PASS |
| 05 | Smoke render: real 5 s clip → .mp4 with video + stereo audio | PASS |
| 06 | MCP server stdio initialize handshake (in-container) | PASS |
| 07 | E2E agent flow: health → 2×submit_scene → wait → list → compose_final | PASS |

## Requirements (hardware floor)

| Resource | Minimum | Notes |
|---|---|---|
| GPU | 12 GB VRAM (RTX 3060/4070/4080 class) | INT4 pruned + ComfyUI dynamic VRAM offload |
| System RAM | 16 GB free (32 GB recommended) | **`--fast-disk` is required** on 16–32 GB machines |
| Disk | ~45 GB free on the models partition | Models ≈ 32 GB + Docker image ≈ 12 GB |
| Software | Docker + NVIDIA Container Toolkit, `curl`, `ffmpeg` | `uv` only needed for host-side dev/MCP-client tests |

## Verified stack & key gotchas

- ComfyUI pinned at **`v0.30.2`**; base `pytorch/pytorch:2.5.1-cuda12.4-cudnn9-runtime`
  with **torch upgraded to `2.8.0+cu128`** in-image. torch ≥ 2.8 enables ComfyUI's
  DynamicVRAM — without it `--lowvram` attaches 0 patches and 12 GB VRAM OOMs.
  `torchvision==0.23.0` / `torchaudio==2.8.0` are pinned to the same release train.
- ComfyUI runs with `--lowvram --fast-disk --disable-pinned-memory`, listening on
  `0.0.0.0` *inside* the container (127.0.0.1 breaks docker-proxy port publishing);
  the compose file maps it to `127.0.0.1:8188` on the host.
- The two official VAEs live in the **`vae/` subfolder** of `Comfy-Org/MiniMax-H3`
  (download URL must include `vae/`). The INT4 files are at the repo root.
- The official UI template's single "hash" node is a **subgraph** expanded by the
  frontend into 14 real nodes; `workflows/minimax_h3_t2v_api.json` ships the expanded
  API format. See `AGENTS.md` §6 for the node map and duration math.

See [docs/INSTALLATION.md](docs/INSTALLATION.md), [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md),
[docs/MCP_REMOTE.md](docs/MCP_REMOTE.md) (VPS/HTTPS MCP) and
**[AGENTS.md](AGENTS.md)** (operating manual for AI agents).

## OpenCode MCP config (3 ways)

```jsonc
// A) stdio via docker exec (no host uv) — RECOMMENDED local
"minimax-video-factory": {
  "type": "local",
  "command": ["docker", "exec", "-i", "minimax-comfyui", "bash", "/workspace/scripts/mcp_runner.sh"]
},

// B) stdio via host uv
"minimax-video-factory": {
  "type": "local",
  "command": ["uv", "run", "--directory", "/path/to/minimax-video-factory", "python", "src/minimax_mcp/server.py"],
  "environment": { "MODELS_DIR": "/opt/minimax/models", "COMFYUI_URL": "http://127.0.0.1:8188" }
},

// C) remote HTTPS (VPS) — "MCP por link https"
"minimax-video-factory": {
  "type": "remote",
  "url": "https://mcp.example.com/mcp"
}
```

All three are present (disabled where applicable) in `~/.config/opencode/opencode.json`.

## License

Project code: MIT (see `LICENSE`).  
Model weights: **MiniMax H3 Community License** (see [MiniMaxAI/MiniMax-H3](https://huggingface.co/MiniMaxAI/MiniMax-H3)).
