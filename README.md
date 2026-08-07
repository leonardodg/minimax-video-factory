# MiniMax H3 · INT4 ConvRot — Local Video Factory + Audiovisual Studio

> Orchestrate **MiniMax H3** (text → video **+ native stereo audio**, single diffusion pass) on a local GPU, driven by **OpenCode** through an **MCP server** that talks to a **ComfyUI** backend via its HTTP/WebSocket API.
>
> **New:** Full audiovisual studio pipeline — download videos (Instagram Reels, YouTube), transcribe locally with Whisper, generate cinematic prompts, and render with MiniMax H3 — all via MCP tools.

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

**New: Audiovisual Studio Pipeline**
```
[Instagram Reel / YouTube URL]
        │
        ▼
[Download] ──► [Transcribe (Whisper)] ──► [Prompt Engineering] ──► [MiniMax H3 Render]
        │              │                      │                        │
        ▼              ▼                      ▼                        ▼
    .mp4 file    .txt transcription      .txt prompt             .mp4 output
```

## Components

| Layer | Role | Technology |
|---|---|---|
| **OpenCode** | Interprets the script, splits into scenes (5–15 s), writes H3-structured prompts, calls the MCP tools | opencode |
| **Local Agent** | MCP server; injects prompt into the API workflow JSON, submits jobs, monitors, retrieves files | Python + FastMCP (`src/minimax_mcp/server.py`, in-image venv `/opt/mcp-venv`) |
| **Render Engine** | Loads MiniMax H3 into VRAM, runs the diffusion pass, saves `.mp4` | ComfyUI ≥ 0.30.0 (Docker) |
| **Model** | MiniMax H3 Base FL2VA, pruned **INT4** ConvRot (tuned for 12 GB VRAM) | `Merserk/MiniMax-H3-INT4-ConvRot` |
| **Downloader** | Instagram Reels, YouTube, etc. with browser cookies | yt-dlp |
| **Transcriber** | Local GPU-accelerated Whisper (PT-BR + timestamps) | faster-whisper |
| **Prompt Engineer** | Template-based cinematic/educational/social prompt generation | Python (pluggable LLM later) |

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

# Studio config
STUDIO_DOWNLOADS_DIR=.../downloads            # downloaded videos
WHISPER_MODEL=small                           # tiny/base/small/medium/large-v3
WHISPER_DEVICE=cuda                           # cuda/cpu
WHISPER_COMPUTE_TYPE=float16                  # float16/int8/float32
STUDIO_BROWSER=chrome                         # chrome/firefox/edge/brave
```

## Quick Start

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

# 5. Optional: Install Whisper model for studio pipeline
./scripts/setup_whisper.sh small      # or base/medium/large-v3
```

## Validation Suite (`./scripts/diagnose.sh [NN ...]`)

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

## New: Audiovisual Studio MCP Tools

| Tool | Description |
|---|---|
| `download_video(url, browser?)` | Download Instagram Reels, YouTube, etc. using yt-dlp + browser cookies |
| `transcribe_video(path, model_size?, device?, language?)` | Local Whisper transcription with timestamps (GPU) |
| `create_cinematic_prompt(transcription, style?)` | Convert transcription → cinematic/educational/social prompt |
| `generate_video(prompt, duration, width, height, seed?)` | Submit to MiniMax H3 via ComfyUI |
| `studio_pipeline(url, style?, duration?, width?, height?, save_only?)` | **Full pipeline**: URL → download → transcribe → prompt → video (or save_only) |

### Example: Full Pipeline from Instagram Reel

```python
# In OpenCode chat:
"Baixe o Reel https://www.instagram.com/p/DbHIZl5Pk_0/, 
 transcreva, crie um prompt cinematográfico e salve 
 transcrição + prompt em output/transcriptions/ (save_only=True)"
```

Or via MCP directly:
```json
{
  "tool": "studio_pipeline",
  "arguments": {
    "url": "https://www.instagram.com/p/DbHIZl5Pk_0/",
    "style": "cinematic",
    "duration": 10,
    "width": 1344,
    "height": 768,
    "save_only": true
  }
}
```

## New: Knowledge Base MCP Tools

Personal knowledge base backed by Postgres + pgvector, with a local LLM (Ollama by
default) turning transcriptions into structured summaries/tutorials.

| Tool | Description |
|---|---|
| `knowledge_ingest_text(text, source_url?, title?, platform?)` | Summarize+document a ready-made text/transcription |
| `knowledge_ingest_video(url, browser?, whisper_model?)` | Download + transcribe + document a video |
| `knowledge_ingest_audio(path_or_url, browser?, whisper_model?)` | Transcribe + document a local/downloaded audio (podcasts) |
| `knowledge_search(query, top_k?)` | Full-text + semantic (pgvector) search |
| `knowledge_ask(query, top_k?)` | RAG: answer a question using the knowledge base as context |
| `knowledge_reindex(embedding_model?)` | Recompute chunks/embeddings for every document |

Setup: `docker compose $COMPOSE_ARGS up -d postgres` then `uv run alembic upgrade head`
(see `AGENTS.md` §10). Requires Ollama running locally with `LLM_MODEL` and
`EMBEDDING_MODEL` pulled.

Full parameter-level reference for every tool (this table and the original
Audiovisual Studio one) is auto-generated — see
[`docs/MCP_TOOLS.md`](docs/MCP_TOOLS.md), regenerated via
`uv run python scripts/generate_mcp_docs.py`. Don't hand-edit that file.

For a step-by-step tutorial, chat-prompt examples, and the database schema see
[`docs/KNOWLEDGE_BASE.md`](docs/KNOWLEDGE_BASE.md).

## Requirements (hardware floor)

| Resource | Minimum | Notes |
|---|---|---|
| GPU | 12 GB VRAM (RTX 3060/4070/4080 class) | INT4 pruned + ComfyUI dynamic VRAM offload |
| System RAM | 16 GB free (32 GB recommended) | **`--fast-disk` is required** on 16–32 GB machines |
| Disk | ~45 GB free on the models partition | Models ≈ 32 GB + Docker image ≈ 12 GB |
| Software | Docker + NVIDIA Container Toolkit, `curl`, `ffmpeg` | `uv` only needed for host-side dev/MCP-client tests |

## Verified Stack & Key Gotchas

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

## OpenCode MCP Config (3 ways)

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

### Knowledge base MCP entry

The `knowledge_*` tools need host access to Postgres and Ollama, so they get a
dedicated entry (same server binary, different env):

```jsonc
"minimax-knowledge-base": {
  "type": "local",
  "command": ["uv", "run", "--directory", "/path/to/minimax-video-factory", "python", "src/minimax_mcp/server.py"],
  "environment": {
    "MCP_TRANSPORT": "stdio",
    "KB_DATABASE_URL": "postgresql+psycopg://kb:kb@127.0.0.1:5432/knowledge",
    "LLM_PROVIDER": "ollama",
    "OLLAMA_URL": "http://localhost:11434",
    "LLM_MODEL": "lfm2:24b",
    "EMBEDDING_MODEL": "mxbai-embed-large"
  }
}
```

## License

Project code: MIT (see `LICENSE`).  
Model weights: **MiniMax H3 Community License** (see [MiniMaxAI/MiniMax-H3](https://huggingface.co/MiniMaxAI/MiniMax-H3)).