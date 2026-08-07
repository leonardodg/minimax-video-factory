# INSTALLATION.md — MiniMax Video Factory + Audiovisual Studio

Verified install procedure on a 12 GB VRAM Linux machine (tested: RTX 4080 Laptop,
30 GB RAM). Follow the phases **in order**. The OpenCode/agent integration is LAST.

> For an AI agent configuring this on a fresh machine, read `AGENTS.md` first — it
> encodes every pitfall hit during the original build (subgraph hash, torch 2.8,
> `--listen`, VAE subfolder URLs, etc.).

---

## 0. Hardware & OS floor

| Resource | Requirement |
|---|---|
| GPU | NVIDIA, ≥ 12 GB VRAM (INT4 pruned fits 12 GB) |
| System RAM | 16 GB free (30 GB used here; `--fast-disk` mandatory on ≤ 32 GB) |
| Disk | ~45 GB free (models ≈ 32 GB + image ≈ 12 GB) |
| OS | Linux with working `docker` + `nvidia-container-toolkit` |

---

## 1. Host prerequisites

```bash
sudo apt-get install -y docker.io docker-compose-v2 curl jq ffmpeg
sudo nvidia-ctk runtime configure --runtime=docker && sudo systemctl restart docker
docker compose version && ffmpeg -version | head -1
./scripts/diagnose.sh 00        # confirms all of the above + VRAM ≥ 12 GB
```

`uv` is **no longer required on the host** — the MCP server (with its own venv
`/opt/mcp-venv`) is baked into the Docker image. Install `uv` only if you want to
run the MCP server or the fastmcp client on the host (dev mode).

---

## 2. Configure `.env` (central config)

```bash
cp .env.example .env
# edit at least:
#   PROJECT_ROOT=/path/to/minimax-video-factory   (absolute — used for the /workspace mount)
#   MODELS_DIR=/var/tmp/minimax/models            (where weights live)
#   OUTPUT_DIR=/path/to/minimax-video-factory/output
#   STUDIO_DOWNLOADS_DIR=/path/to/minimax-video-factory/downloads  # new: downloaded videos
#   WHISPER_MODEL=small      # tiny/base/small/medium/large-v3
#   WHISPER_DEVICE=cuda      # cuda/cpu
#   WHISPER_COMPUTE_TYPE=float16
#   STUDIO_BROWSER=chrome    # chrome/firefox/edge/brave
```

Everything (paths, model set, ports, MCP transport, studio config) is read from this
one file by `scripts/config.sh`, `download_models.sh`, the Docker compose file and
the MCP server.

---

## 3. Models directory

Preferred: `/opt/minimax/models`. If you cannot use `sudo` (e.g. non-interactive
shell), everything falls back to `/var/tmp/minimax/models` automatically — or just
set `MODELS_DIR` in `.env`.

```bash
sudo mkdir -p /opt/minimax/models && sudo chown -R "$USER" /opt/minimax
# or, no-sudo fallback:
#   mkdir -p /var/tmp/minimax/models
```

---

## 4. Download models (~32 GB)

```bash
./scripts/download_models.sh        # reads MODELS_DIR + MODEL_* from .env
```

Downloads with resume (`curl -C -`) and size-verified skip. Sources:

| File (local path under `MODELS_DIR/`) | Repo | Bytes |
|---|---|---|
| `diffusion_models/minimax_h3_fl2va_pruned_int4_convrot.safetensors` | `Merserk/MiniMax-H3-INT4-ConvRot` | 11,337,536,776 |
| `text_encoders/qwen3vl_32b_minimax_h3_int4_convrot.safetensors` | same | 14,952,506,624 |
| `vae/minimax_h3_video_vae_fp16.safetensors` | `Comfy-Org/MiniMax-H3` (**`vae/` subfolder!**) | 5,207,808,496 |
| `vae/minimax_h3_audio_vae_fp32.safetensors` | same (**`vae/` subfolder!**) | 605,254,808 |

Verify: `./scripts/diagnose.sh 03` (checks exact sizes ±2%).

---

## 5. Build image + start ComfyUI

```bash
./scripts/start_comfyui.sh        # builds (if needed) + up; uses $COMPOSE_ARGS -> loads project-root .env
sleep 15
./scripts/diagnose.sh 01 && ./scripts/diagnose.sh 02
```

What the image does (see `docker/Dockerfile`):
- Base `pytorch/pytorch:2.5.1-cuda12.4-cudnn9-runtime`, ComfyUI `v0.30.2`.
- **Upgrades torch to `2.8.0+cu128`** (with `torchvision==0.23.0`, `torchaudio==2.8.0`)
  so ComfyUI uses DynamicVRAM — required for `--lowvram` to actually offload on 12 GB.
- Installs `uv` + creates `/opt/mcp-venv` (project deps) so the MCP server runs inside
  the container; `/workspace` is a read-only bind-mount of the repo.
- Runs `main.py --listen 0.0.0.0 --port 8188` + `COMFYUI_EXTRA_ARGS` from `.env`.
  `0.0.0.0` *inside* the container is required (127.0.0.1 breaks docker-proxy);
  compose maps it to `127.0.0.1:8188` on the host.

> **Compose env gotcha:** always start/stop via `./scripts/start_comfyui.sh` /
> `./scripts/stop_comfyui.sh` (they pass `--project-directory` + `--env-file`). A bare
> `docker compose -f docker/docker-compose.yml` reads `.env` from `docker/` (absent)
> and resolves relative mounts one level too high.

---

## 6. Validate workflow + smoke render

```bash
./scripts/diagnose.sh 04 && ./scripts/diagnose.sh 05
```

`04` checks all 14 node classes exist. `05` submits a real 512×320/5 s clip and
verifies the `.mp4` has a video stream **and stereo audio** (MiniMax H3 native audio).
First render takes ~4–5 min (model load + 20 steps).

---

## 7. MCP server + E2E

```bash
./scripts/diagnose.sh 06   # stdio handshake via `docker exec` (in-container MCP)
./scripts/diagnose.sh 07   # full agent flow: health → submit 2 scenes → wait → compose
```

---

## 8. Audiovisual Studio (NEW) — Install Whisper + Test Pipeline

```bash
# 1. Install Whisper model (small=244MB, good PT-BR)
./scripts/setup_whisper.sh small   # or base/medium/large-v3

# 2. Install extra deps (yt-dlp, faster-whisper, requests) — already in pyproject.toml
./scripts/install_deps.sh

# 3. Test the studio pipeline with a local file (save_only mode, no GPU render)
cd minimax-video-factory
uv run python -c "
from minimax_mcp.orchestrator import AudiovisualStudio
studio = AudiovisualStudio(downloads_dir='downloads')
result = studio.run_full_pipeline(
    url='local_test',
    style='cinematic',
    duration=5.0,
    width=512,
    height=320,
    save_only=True,
    output_dir='output/transcriptions'
)
print('OK:', result.get('ok'))
print('Transcription:', result.get('transcription_file'))
print('Prompt:', result.get('prompt_file'))
"
```

Expected output: transcription + prompt saved to `output/transcriptions/`.

---

## 5. OpenCode integration (LAST)

Add the MCP entry to your `opencode.json`. Three options:

```jsonc
// A) docker exec (recommended, no host uv)
"minimax-video-factory": {
  "type": "local",
  "command": ["docker", "exec", "-i", "minimax-comfyui", "bash", "/workspace/scripts/mcp_runner.sh"]
}

// B) host uv
"minimax-video-factory": {
  "type": "local",
  "command": ["uv", "run", "--directory", "/path/to/minimax-video-factory", "python", "src/minimax_mcp/server.py"],
  "environment": { "MODELS_DIR": "/opt/minimax/models", "COMFYUI_URL": "http://127.0.0.1:8188" }
}

// C) remote HTTPS (VPS) — see docs/MCP_REMOTE.md
"minimax-video-factory": {
  "type": "remote",
  "url": "https://mcp.example.com/mcp"
}
```

---

## 9. Remote MCP over HTTPS (VPS)

Optional. To expose the MCP as `https://…` from a VPS (run container there, add a
Caddy/nginx TLS reverse proxy in front of `127.0.0.1:${MCP_PORT:-8848}`), follow
`docs/MCP_REMOTE.md`. Configure OpenCode with `"type": "remote", "url": "https://…/mcp"`.

---

## Troubleshooting cheat-sheet

| Symptom | Cause / fix |
|---|---|
| `Connection reset by peer` from host | Container must listen on `0.0.0.0` (docker-proxy connects to container IP). Rebuild with the shipped CMD. |
| `/prompt` → 400 `value_not_in_list` | Missing model file → re-run `download_models.sh`. |
| `/prompt` → 400 `bad_link`/`missing_node_type` | Workflow wiring or subgraph hash — use the expanded `workflows/minimax_h3_t2v_api.json`. |
| `torch.OutOfMemoryError` at 512×320 | torch < 2.8 (no DynamicVRAM) or `--lowvram` missing. Rebuild image. |
| Container crash `undefined symbol: torch_library_impl` | `torchaudio` version mismatch — must be `2.8.0` with torch `2.8.0`. |
| VAE download 404 | URL must include `vae/` subfolder prefix. |
| Model file looks complete but test fails | Sizes changed upstream — refresh from `?blobs=true` API. |
| MCP stdio handshake hangs / boots uvicorn | `MCP_TRANSPORT` left at `streamable-http` — `mcp_runner.sh` forces `stdio`; don't override it. |
| Container mounts look wrong (`OUTPUT_HOST_DIR=../output`) | Started compose with a bare `-f` (no `--project-directory`/`--env-file`). Use `./scripts/start_comfyui.sh`. |
| Remote MCP `GET /mcp` → 406 | Expected — needs `Accept: application/json, text/event-stream` (a POST client works). |

---

## 9. Audiovisual Studio Quick Reference

| Tool | MCP Call Example |
|---|---|
| `download_video` | `{"url": "https://instagram.com/p/...", "browser": "chrome"}` |
| `transcribe_video` | `{"video_path": "downloads/video.mp4", "model_size": "small"}` |
| `create_cinematic_prompt` | `{"transcription": "...", "style": "cinematic"}` |
| `generate_video` | `{"prompt": "...", "duration": 10, "width": 1024, "height": 576}` |
| `studio_pipeline` | `{"url": "https://instagram.com/p/...", "save_only": true}` |

**Full pipeline example (save_only):**
```json
{
  "tool": "studio_pipeline",
  "arguments": {
    "url": "https://www.instagram.com/p/DbHIZl5Pk_0/",
    "style": "cinematic",
    "duration": 10,
    "width": 1024,
    "height": 576,
    "save_only": true,
    "output_dir": "output/transcriptions"
  }
}
```