<div align="center">

# MiniMax Video Factory

### Text → video **with native stereo audio**, on your own GPU. No API keys, no cloud, no per-clip cost.

[![License: MIT](https://img.shields.io/badge/License-MIT-1de9d6.svg)](LICENSE)
[![CI](https://github.com/leonardodg/minimax-video-factory/actions/workflows/ci.yml/badge.svg)](https://github.com/leonardodg/minimax-video-factory/actions/workflows/ci.yml)
[![Docs](https://github.com/leonardodg/minimax-video-factory/actions/workflows/docs.yml/badge.svg)](https://leonardodg.github.io/minimax-video-factory/)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-3776ab.svg)](https://www.python.org/)
[![MCP](https://img.shields.io/badge/MCP-FastMCP%203.x-8a2be2.svg)](https://gofastmcp.com)
[![VRAM](https://img.shields.io/badge/VRAM-12%20GB-76b900.svg)](#-render-cost-measured)

**[Documentation](https://leonardodg.github.io/minimax-video-factory/)** ·
**[Slash commands](https://leonardodg.github.io/minimax-video-factory/COMMANDS/)** ·
**[MCP tools](https://leonardodg.github.io/minimax-video-factory/MCP_TOOLS/)** ·
**[Installation](https://leonardodg.github.io/minimax-video-factory/INSTALLATION/)**

<img width="720" alt="Title card animated by MiniMax H3" src="docs/assets/hero-factory-intro.gif">

<sub>Title card drawn with ffmpeg, animated by H3 from a <code>first_frame</code> — 1024×576, 16 min on an RTX 4080 Laptop. The glow, the scan-lines and the audio are generated.</sub>

</div>

Describe a scene in plain language. Get back an `.mp4` with picture **and sound**, generated in a single diffusion pass by **MiniMax H3** — running on a 12 GB consumer card, driven from your AI coding agent through an **MCP server**. Nothing leaves the machine.

---

## 💸 What a clip costs

Most agentic video tools orchestrate paid APIs and bill you per second of output. This one loads the weights onto your own card.

| | This project | Typical cloud pipeline |
|---|---|---|
| **Cost per clip** | **$0.00** | $0.10 – $2.00 |
| **Cost of 100 clips** | **$0.00** | $10 – $200 |
| **Time per 5 s clip** | ~4 min (512×320) · ~15 min (1024×576) | seconds to minutes |
| **Data leaving your machine** | **none** | prompt, and often the output |
| **Works offline** | **yes**, after the one-time model download | no |
| **Up-front cost** | ~35 GB disk, a 12 GB GPU | none |

You trade wall-clock time for money and privacy. Whether that is a good trade depends on whether you already own the GPU.

---

## 📋 Features

- 🎬 **Text → video + audio in one pass** — H3 generates native stereo sound with the picture, not a soundtrack pasted on afterwards
- 🔌 **18 MCP tools** — drive the whole pipeline from an AI agent, no CLI to memorise
- ⌨️ **18 slash commands** — generated from the code, so they can never drift from what the tools actually accept
- 📥 **Ingest what you already watch** — download Instagram Reels and YouTube with browser cookies, transcribe locally with Whisper
- 🧠 **Personal knowledge base** — Postgres + pgvector, hybrid search and RAG, all with a local LLM
- 🔒 **Fully local** — models, inference, database and transcription run on your machine
- 🖥️ **12 GB VRAM is enough** — INT4 ConvRot weights tuned for consumer cards
- ✅ **Validated end to end** — 9 unit suites plus an 8-step GPU pipeline check in CI

---

## Technologies and Tools

### Core
| Technology | Role |
|---|---|
| **MiniMax H3** (`Merserk/MiniMax-H3-INT4-ConvRot`) | Text → video + native stereo audio, pruned INT4 for 12 GB VRAM |
| **ComfyUI** ≥ 0.30.0 | Render engine; loads H3 into VRAM and runs the diffusion pass |
| **FastMCP 3.x** | MCP server exposing the pipeline as tools over stdio / streamable-http |
| **Python** ≥ 3.10 + **uv** | Application and dependency management |

### Studio
| Technology | Role |
|---|---|
| **yt-dlp** | Downloads Reels, YouTube and friends using your browser's cookies |
| **faster-whisper** | Local, GPU-accelerated transcription with timestamps |
| **ffmpeg** | Scene concatenation and output inspection |

### Knowledge base
| Technology | Role |
|---|---|
| **Postgres 16 + pgvector** | Source of truth; documents, chunks and embeddings |
| **SQLAlchemy 2 + Alembic** | ORM access and schema migrations |
| **Ollama** (`lfm2:24b`, `mxbai-embed-large`) | Local summarisation and embeddings |

### Infrastructure
| Technology | Role |
|---|---|
| **Docker + Compose** | ComfyUI with GPU passthrough; the MCP venv ships inside the image |
| **GitHub Actions** | Cloud jobs for lint and tests, a self-hosted job for the real GPU suite |
| **MkDocs + Material** | Documentation site, published to GitHub Pages |

---

## 🏗 Architecture

```
[Your scene description]  (plain language, any language)
        │
        ▼
[ AI agent (OpenCode / Claude Code) ]  ──MCP (stdio)──►  [ MCP Server ]
        │                                                      │  POST /prompt
        │       ┌──────────────────────────────────────────────┘
        ▼       ▼
[ ComfyUI + MiniMax H3 (Docker + GPU) ]  ◄── shares models + output with the MCP
        │   WebSocket progress + GET /view
        ▼
[ final .mp4 — video + stereo audio ]
```

The MCP server runs **inside the ComfyUI container**, so it shares the loaded models, the GPU and the output directory. No second copy of 32 GB of weights, no host-to-container path guessing.

---

## 🚀 Quick Start

### Prerequisites

| Resource | Minimum | Notes |
|---|---|---|
| GPU | NVIDIA, **12 GB VRAM** | Verified on an RTX 4080 Laptop |
| RAM | ~12 GB free | ComfyUI needs headroom during model load |
| Disk | ~35 GB | ~32 GB of weights plus outputs |
| Software | Docker + Compose, [uv](https://docs.astral.sh/uv/), ffmpeg | `nvidia-container-toolkit` for GPU passthrough |

### Installation

```bash
git clone https://github.com/leonardodg/minimax-video-factory.git
cd minimax-video-factory

# 0. Configure
cp .env.example .env          # edit PROJECT_ROOT, MODELS_DIR, OUTPUT_DIR

# 1. Check the host
./scripts/diagnose.sh 00

# 2. Download the models (~32 GB, public HF repos; resumes on re-run)
./scripts/download_models.sh

# 3. Start ComfyUI (Docker + GPU); the image already contains the MCP venv
./scripts/start_comfyui.sh

# 4. Validate everything (models, workflow, a real render, MCP, end to end)
./scripts/diagnose.sh

# 5. Optional: Whisper model for the studio pipeline
./scripts/setup_whisper.sh small
```

---

## 🎬 Examples

### Generate a scene

```
/minimax-gerar-video "a hungry black cat staring at an empty food bowl,
                      close-up, soft kitchen daylight, faint meow"
```

<img width="360" alt="Generated cat clip" src="docs/assets/demo-cat.gif">

*512×320, 5 s, ~4 min. Rendered with native audio — the meow is generated, not added.*

### Reel → transcription → new video

```
/minimax-studio https://www.instagram.com/p/XXXXXXXX/
```

Downloads the Reel, transcribes it locally with Whisper, turns the transcript into a
cinematic H3 prompt, and renders a new clip from it.

### Animate a picture you already have

The model is `minimax_h3_**fl2va**` — First-Last frame to Video+Audio. Give it a
starting image and it animates *that* instead of inventing a composition:

```
/minimax-gerar-video "soft cyan light pulses behind the text, dust drifts upward"
                      first_frame=assets/title-card.png
```

This is the single biggest quality lever in the project. Text-only generation asks
the model to invent framing, lighting, subject and motion at once; a first frame
hands it everything but the motion.

### Save what you learn, then ask about it later

```
/kb-ingest-video https://www.instagram.com/p/XXXXXXXX/
/kb-perguntar "what did I save about docker volumes?"
```

The answer comes only from your own knowledge base, with the sources cited.

---

## ✍️ What actually improves a clip

Measured, not guessed — and the first conclusion turned out to be too broad.

### Subject tolerance is the real lever

<img width="400" alt="Sea at dawn, 512x320, text only" src="docs/assets/demo-sea.gif">

*512×320, 5 s, text prompt only, no reference image, ~4 min. Better than clips
rendered at twice the resolution.*

That clip is the smallest, cheapest thing this repo produced, and it beats the
aerial city rendered at 1024×576 with a photograph to work from. The model did
not get better. **The subject got easier to represent.**

| Forgiving — works even at 512×320 | Unforgiving — struggles at any resolution here |
|---|---|
| Water, waves, surf | Faces in close-up |
| Clouds, mist, smoke | Legible text of any size |
| Light, glow, reflections | Detailed architecture |
| Wide landscape, horizon | Crowds of people |
| Slow organic motion | Hundreds of small objects (a city from above) |

Everything on the left is a continuous texture with no small object that must
come out *right*. Everything on the right asks diffusion for precision it does
not have — and no prompt, resolution or step count fixes that.

### Resolution matters, but only for the right subject

| | Resolution | Prompt style | Time | Result |
|---|---|---|---|---|
| A | 512×320, 15 s | loose prose | 14 min | city dissolves into noise |
| B | 1024×576, 5 s | loose prose | **3 min** | buildings and bridge legible |
| C | 1024×576, 5 s | model-card format | 16 min | no visible gain over B |
| D | 1024×576, 5 s | ComfyUI template format | 20 min | no visible gain over B |

A → B is a real jump, but only because the subject was a *city*: thousands of
buildings that cannot fit in 512 pixels. For the sea, the extra pixels would
have bought nothing.

### Prompt format is not a lever

Three mutually contradictory formats — loose prose, the model card's
`integrated_multimodal_description:` fields, and the ComfyUI template's
`<Picture 1>` / `SHOT 1:` convention — produced the same clip. Write clearly and
stop optimising.

### Steps are not a lever either

| Steps | Time | Result |
|---|---|---|
| 20 | **3 min** | baseline |
| 30 | 24 min | no visible gain |
| 40 | 32 min | no visible gain, some vertical artefacts |

Eight times the wall-clock for nothing. 20 is where this model saturates here.

### So, in order

1. **Pick a forgiving subject.** This decides more than every other setting
   combined.
2. **Start from an image** (`first_frame`) when the composition matters — the
   model keeps it and animates it, instead of inventing one badly.
3. **Render at 1024×576** if the subject has fine detail. If it does not,
   512×320 in 4 minutes is the better trade.
4. **Describe plainly** — subject, what moves, the light, and an audio cue. H3
   generates sound, and a prompt with no audio wastes half the model.
5. **Need something longer?** Render several clips and join them with
   `compose_final`. One long low-res take is the worst of both.

### Text does not survive

Video models do not write. Draw text into the base image and let H3 light it —
the title card at the top of this README is exactly that, `drawtext` handed to
H3 as a `first_frame`.

Even then, **small text degrades**. In that render the 17 px caption came back
reading `local CPU · 22 GB VRAM` instead of `local GPU · 12 GB VRAM` — the model
rewrote two characters. Large type survived untouched. Keep anything that must
be correct out of the frame.

---

## ⌨️ Slash commands

Every MCP tool has a matching command. `/minimax-*` drives the video pipeline, `/kb-*` the knowledge base.

### Render pipeline

| Tool | Command | What it does |
|---|---|---|
| `health_check` | `/minimax-health` | ComfyUI reachable and all four model files present |
| `submit_scene` | `/minimax-submit-scene` | Queue a render, return the `prompt_id` immediately |
| `wait_for_video` | `/minimax-wait` | Block until a render finishes, return the `.mp4` |
| `get_status` | `/minimax-status` | Queued, rendering, finished or failed — for one render |
| `queue_status` | `/minimax-fila` | The whole queue, with a sampler progress bar |
| `list_outputs` | `/minimax-outputs` | Every clip rendered so far, newest first |
| `compose_final` | `/minimax-compose` | Concatenate scenes into one file with ffmpeg |
| `generate_video` | `/minimax-gerar-video` | Prompt → rendered clip, submit and wait in one call |

### Studio

| Tool | Command | What it does |
|---|---|---|
| `download_video` | `/minimax-download` | Fetch a Reel or YouTube video using browser cookies |
| `transcribe_video` | `/minimax-transcrever` | Local Whisper transcription with timestamps |
| `create_cinematic_prompt` | `/minimax-prompt-cinematico` | Turn a transcript into a structured H3 prompt |
| `studio_pipeline` | `/minimax-studio` | The whole chain: URL → download → transcribe → prompt → render |

### Knowledge base

| Tool | Command | What it does |
|---|---|---|
| `knowledge_ingest_text` | `/kb-ingest-texto` | Summarise and store a text you already have |
| `knowledge_ingest_video` | `/kb-ingest-video` | Download, transcribe and document a video |
| `knowledge_ingest_audio` | `/kb-ingest-audio` | Transcribe and document a podcast |
| `knowledge_ingest_markdown` | `/kb-ingest-markdown` | Import `.md` files; reuses `## Summary` and skips the LLM |
| `knowledge_search` | `/kb-buscar` | Hybrid search — keyword and semantic, fused with RRF |
| `knowledge_ask` | `/kb-perguntar` | Answer from your own base only, citing the sources |
| `knowledge_reindex` | `/kb-reindex` | Recompute chunks and embeddings for everything |

The command files are **generated from the tool signatures** — `uv run python scripts/generate_commands.py`. A test fails if a tool ever lacks one. Full reference: **[docs/COMMANDS.md](https://leonardodg.github.io/minimax-video-factory/COMMANDS/)**.

---

## ⏱ Render cost (measured, RTX 4080 Laptop, INT4, 20 steps)

| Resolution | 5 s clip | Notes |
|---|---|---|
| 512×320 | **~4 min** | Smoke resolution; what CI renders |
| **1024×576** | **~15 min** | **Default.** Largest that renders reliably here |
| 1344×768 | — | H3's canvas maximum, but **OOMs the sampler on 12 GB** |

The first render of a session is slower: it includes loading ~32 GB of weights.

---

## ✅ Validation suite (`./scripts/diagnose.sh [NN ...]`)

| # | Checks |
|---|---|
| 00 | Host prereqs — GPU/VRAM ≥ 12 GB, Docker, curl, ffmpeg |
| 01 | Docker image built, container running, GPU visible inside |
| 02 | ComfyUI API up (≥ 0.30.0) and the H3 node classes present |
| 03 | All 4 model files present, with exact sizes |
| 04 | Workflow: all 14 node `class_type`s resolve |
| 05 | Smoke render — a real 5 s clip with video **and** stereo audio |
| 06 | MCP stdio initialize handshake, in-container |
| 07 | End to end — health → submit → wait → list → compose |
| 08 | Knowledge base over MCP (skips cleanly when Postgres is absent) |

Plus `uv run pytest -m unit` for the pure-logic suites, which need no GPU, no container and no network.

---

## ⚙️ Configuration (`.env`)

```bash
PROJECT_ROOT=/path/to/minimax-video-factory   # absolute; used for the /workspace mount
MODELS_DIR=/var/tmp/minimax/models            # where the ~32 GB of weights live
OUTPUT_DIR=.../output                         # generated .mp4 (mounted into the container)

COMFYUI_TAG=v0.30.2  COMFYUI_PORT=8188
MCP_TRANSPORT=streamable-http  MCP_HOST=0.0.0.0  MCP_PORT=8848

# Studio
STUDIO_DOWNLOADS_DIR=.../downloads
WHISPER_MODEL=small           # tiny/base/small/medium/large-v3
WHISPER_DEVICE=cuda           # cuda/cpu

# Knowledge base
KB_DATABASE_URL=postgresql+psycopg://kb:kb@127.0.0.1:5432/knowledge
LLM_MODEL=lfm2:24b            # measured: qwen2.5:32b took 15+ min per ingest here
EMBEDDING_MODEL=mxbai-embed-large
```

See **[Installation](https://leonardodg.github.io/minimax-video-factory/INSTALLATION/)** for every variable.

---

## 🛠 Project structure

```
minimax-video-factory/
├── .github/workflows/
│   ├── ci.yml                    # cloud lint/tests + self-hosted GPU suite
│   └── docs.yml                  # builds and publishes the docs site
├── .opencode/command/            # 18 generated slash commands
├── docker/
│   ├── Dockerfile                # ComfyUI + in-image MCP venv
│   └── docker-compose.yml        # GPU passthrough, Postgres for the KB
├── scripts/
│   ├── diagnose.sh               # the validation suite runner
│   ├── start_comfyui.sh
│   ├── download_models.sh
│   ├── generate_commands.py      # slash commands, generated from the code
│   ├── generate_mcp_docs.py      # tool reference, generated from the registry
│   └── command_docs/             # parser · catalog · overrides · renderer
├── src/minimax_mcp/
│   ├── server.py                 # the 18 @mcp.tool() definitions
│   ├── core.py                   # workflow injection, submission, output resolution
│   ├── comfyui_client.py         # HTTP + WebSocket client
│   ├── orchestrator.py           # the studio pipeline
│   ├── downloader.py             # yt-dlp
│   ├── transcriber.py            # faster-whisper
│   ├── knowledge.py              # knowledge base use cases
│   ├── db.py                     # Postgres + pgvector via SQLAlchemy
│   ├── llm.py                    # Ollama / OpenAI-compatible client
│   └── vault.py                  # optional Obsidian markdown export
├── tests/                        # 00–08 shell suites + unit_*.py
├── docs/                         # MkDocs site sources
└── workflows/                    # the H3 API workflow JSON
```

---

## 📦 Useful commands

```bash
# Validation
./scripts/diagnose.sh                 # everything
./scripts/diagnose.sh 05 07           # only these
uv run pytest -m unit                 # pure logic, fast, no services

# Docs
uv sync --only-group docs && uv run mkdocs serve    # http://127.0.0.1:8000

# Regenerate what is generated
uv run python scripts/generate_commands.py          # slash commands + COMMANDS.md
uv run python scripts/generate_mcp_docs.py          # MCP_TOOLS.md

# Stack
./scripts/start_comfyui.sh
./scripts/stop_comfyui.sh
docker compose -f docker/docker-compose.yml logs -f comfyui
```

---

## 🔌 OpenCode MCP config

```json
{
  "mcp": {
    "minimax-video-factory": {
      "type": "local",
      "command": ["docker", "exec", "-i", "minimax-comfyui",
                  "bash", "/workspace/scripts/mcp_runner.sh"],
      "enabled": true
    }
  }
}
```

Three variants (in-container, host `uv`, remote over HTTP) are documented in
**[Remote MCP](https://leonardodg.github.io/minimax-video-factory/MCP_REMOTE/)**.

---

## ⚠️ Honest limitations

Things this cannot do, stated plainly so you can decide before downloading 32 GB.

- **5 seconds at a time.** H3 renders 4–15 s clips. Longer pieces are several
  renders concatenated with `compose_final`, not one continuous take.
- **1024×576 is the ceiling on 12 GB.** 1344×768 is the model's canvas maximum
  but it OOMs the sampler. A larger card lifts this; this repo does not.
- **No legible text.** See the prompt section above — bake text into a
  `first_frame` instead.
- **Minutes, not seconds.** ~15 min for a 5 s clip at 1024×576. If you need
  volume and have a budget, a paid API will be faster.
- **INT4 weights.** Quantised for consumer VRAM; full-precision H3 will look
  better and does not fit.
- **One GPU, one render.** No queue parallelism, no distributed rendering.
- **Not a video editor.** Concatenation is ffmpeg `concat`, nothing more —
  no transitions, no titles, no colour grading.

## 🔐 A note on the self-hosted runner

This repo is public and its GPU test job runs on a personal machine. That job
**refuses to run code from forks** — see the guard in `.github/workflows/ci.yml`.
If you fork this and wire up your own runner, keep that guard. A self-hosted
runner executing a stranger's pull request has your SSH keys and your docker
socket.

---

## 🤝 Contributing

<img src="https://avatars.githubusercontent.com/u/1678290?s=400&u=2f875356b82f055057b6e9679c0b66001b9b29f9&v=4" width="120" title="LeoDG">

Issues and pull requests are welcome. Fork PRs run the lint and test jobs on GitHub's runners; the GPU suite runs only on the maintainer's machine.

**Adding an MCP tool?** It touches nine places — catalog, overrides, two generators, three tests and the table above. Six are enforced by the suite. The checklist is in [docs/dev/extending.md](https://leonardodg.github.io/minimax-video-factory/dev/extending/#add-a-new-mcp-tool).

## 📄 License

MIT — see [LICENSE](LICENSE).

## 📮 Contact

LeoDG — [@leodg](https://leodg.dev)

- **Repository:** https://github.com/leonardodg/minimax-video-factory
- **Documentation:** https://leonardodg.github.io/minimax-video-factory/
