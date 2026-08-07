# AGENTS.md — MiniMax Video Factory + Audiovisual Studio

Operating manual for AI agents configuring and operating this project on a new machine.
It encodes **everything learned while building the original factory**: the architecture,
the exact setup order, the pitfalls we hit, and the validation commands. Read it fully
before touching anything; follow the phases in order.

---

## 1. What this project is

A local "video factory": an orchestrator (OpenCode) talks over MCP to a local agent
(FastMCP server) that drives a ComfyUI backend (Docker + NVIDIA GPU) running the
MiniMax H3 open-weights model — a text-to-video model with **native stereo audio**
(voice, SFX, music in one forward pass). Output: final `.mp4`.

**New: Audiovisual Studio** — Full pipeline: download videos (Instagram Reels, YouTube),
transcribe locally with Whisper, generate cinematic prompts, and render with MiniMax H3.

**Stack & versions (verified):**

| Component | Version / choice | Why |
|---|---|---|
| ComfyUI | tag `v0.30.2` | First stable release with MiniMax H3 (day-0 support) |
| Base image | `pytorch/pytorch:2.5.1-cuda12.4-cudnn9-runtime`, **torch upgraded in-image to 2.8.0+cu128** (DynamicVRAM) | torch ≥ 2.8 required for lowvram to work |
| Diffusion model | `Merserk/MiniMax-H3-INT4-ConvRot` → `minimax_h3_fl2va_pruned_int4_convrot.safetensors` (11.3 GB) | INT4 pruned fits 12 GB VRAM |
| Text encoder | same repo → `qwen3vl_32b_minimax_h3_int4_convrot.safetensors` (15.0 GB) | Qwen3-VL-32B, INT4 |
| Video VAE | `Comfy-Org/MiniMax-H3` → `vae/minimax_h3_video_vae_fp16.safetensors` (4.85 GB) | official, **stored in `vae/` subfolder** |
| Audio VAE | same → `vae/minimax_h3_audio_vae_fp32.safetensors` (0.58 GB) | official, **stored in `vae/` subfolder** |
| MCP | FastMCP 3.x (Python 3.14, `uv`) | stdio transport |
| Downloader | yt-dlp + browser cookies | Instagram Reels, YouTube, etc. |
| Transcriber | faster-whisper (GPU) | local, free, PT-BR + timestamps |
| Docker | Compose v2, `--gpus all`, nvidia-container-toolkit | GPU passthrough tested |

**Hardware floor:** 12 GB VRAM (RTX 4080 Laptop worked), ~12 GB free RAM for ComfyUI,
~45 GB free disk for models.

**Critical ComfyUI flags** (30 GB RAM machine, not the container): `--fast-disk`
(mandatory, else 45–51 GB RSS → OOM) + `--disable-pinned-memory` (0.30.x regression
workaround) + **`--lowvram`** (mandatory on 12 GB VRAM — Qwen3VL-32B INT4 text encoder
(~9 GB loaded) plus the INT4 diffusion model together exceed 12 GB; a NORMAL_VRAM run
dies with `torch.OutOfMemoryError` in node 5 `MiniMaxH3ImageToVideo`). See §5.

---

## 2. Repository layout

```
minimax-video-factory/
├── AGENTS.md                 <- this file
├── README.md                 <- public EN docs
├── .env / .env.example       <- CENTRAL config (paths, model set, ports, MCP)
├── docs/INSTALLATION.md      <- verified step-by-step install
├── docs/ARCHITECTURE.md      <- component + decision notes
├── docs/MCP_REMOTE.md        <- VPS / HTTPS MCP deployment (Caddy/nginx)
├── pyproject.toml            <- uv project (fastmcp, httpx, websockets, pydantic, yt-dlp, faster-whisper, requests)
├── docker/
│   ├── Dockerfile            <- pinned v0.30.2, base pytorch 2.5.1, torch 2.8, IN-IMAGE uv venv (/opt/mcp-venv)
│   └── docker-compose.yml    <- .env-driven mounts (MODELS_DIR/OUTPUT_DIR/PROJECT_ROOT), gpus all, MCP port
├── scripts/
│   ├── config.sh             <- loads .env + exports derived vars + COMPOSE_ARGS
│   ├── diagnose.sh           <- test runner: ./scripts/diagnose.sh [NN ...]
│   ├── download_models.sh    <- 4-file downloader (reads MODEL_* from .env), resume + size-verified skip
│   ├── start_comfyui.sh / stop_comfyui.sh  <- use $COMPOSE_ARGS (project-root .env)
│   ├── mcp_runner.sh         <- MCP stdio INSIDE container (docker exec entrypoint)
│   ├── mcp_http_runner.sh    <- MCP streamable-http INSIDE container (for VPS/HTTPS)
│   ├── publish_image.sh      <- build + tag + push to Docker Hub (DOCKER_HUB_USER/REPO)
│   ├── setup_whisper.sh      <- NEW: download Whisper models (tiny/base/small/medium/large-v3)
│   ├── install_deps.sh       <- NEW: pip install yt-dlp, faster-whisper, requests
│   └── ui2api.py             <- litegraph UI JSON -> API JSON converter
├── workflows/
│   └── minimax_h3_t2v_api.json   <- EXPANDED T2V workflow (14 nodes), see §6
├── src/minimax_mcp/
│   ├── server.py             <- FastMCP app, 11 tools; model set + prefix from env; path mapping host<->container
│   ├── comfyui_client.py     <- ComfyUIClient (submit/history/websocket/download)
│   ├── downloader.py         <- NEW: yt-dlp wrapper with browser cookies
│   ├── transcriber.py        <- NEW: faster-whisper wrapper (GPU, PT-BR)
│   ├── transcriber.py        <- NEW: faster-whisper wrapper (GPU, PT-BR)
│   ├── orchestrator.py       <- NEW: pipeline URL → download → transcribe → prompt → video
│   ├── orchestrator.py       <- NEW: pipeline URL → download → transcribe → prompt → video
│   ├── core.py               <- NEW: shared ComfyUI functions (no circular imports)
│   └── server.py             <- FastMCP app, 11 tools (original + studio tools)
├── tests/                    <- 00..07 bash tests, each echoes [ok]/[MISS]/[BAD]
├── output/                   <- generated .mp4 (host side of the mount)
├── downloads/                <- downloaded videos (gitignored)
└── output/transcriptions/    <- saved transcriptions + prompts (gitignored)
```

---

## 3. Models directory

- **Preferred:** `/opt/minimax/models` (documented). Needs `sudo mkdir -p` + `sudo chown`.
- **Fallback (no interactive sudo):** `/var/tmp/minimax/models` — writable, on `/`,
  survives reboots. `config.sh` and `server.py` auto-detect this.

Models go under `{MODELS_DIR}/{diffusion_models,text_encoders,vae}` with the four
filenames from §1. Verify with `./scripts/diagnose.sh 03` (checks exact byte sizes,
±2% tolerance). Expected sizes (bytes): diffusion `11337536776`, text encoder
`14952506624`, video VAE `5207808496`, audio VAE `605254808`. **Gotcha:** on the HF
repo the two VAEs live in a `vae/` subfolder, so their resolve URLs must be
`.../vae/<file>?download=true`, NOT at the repo root (404 otherwise). The INT4 files
from `Merserk/MiniMax-H3-INT4-ConvRot` are at the repo root.

**Model set is configurable via .env** (`MODEL_DIFFUSION`, `MODEL_TEXT_ENCODER`,
`*_BYTES`). Bigger variants (FP8_SCALED ~24 GB, BF16 ~48 GB) are documented in
`.env.example`; `download_models.sh` and `tests/03_models.sh` read them from .env.

---

## 4. Setup phases (do them IN ORDER — the OpenCode/agent integration is LAST)

1. **Infra:** Docker, compose plugin, nvidia-container-toolkit, curl, ffmpeg, jq.
   Host uv is NO LONGER required (MCP runs in the image); keep it only for dev.
   Verify: `./scripts/diagnose.sh 00`.
2. **Image + container:** build from `docker/Dockerfile` (includes in-image uv venv
   at `/opt/mcp-venv`), start via `./scripts/start_comfyui.sh` (uses `$COMPOSE_ARGS`
   so the project-root `.env` is loaded). Verify: `./scripts/diagnose.sh 01` (GPU in
   container) and `./scripts/diagnose.sh 02` (API reachable, version ≥ 0.30.0, H3
   nodes present).
3. **Models:** `./scripts/download_models.sh` (~32 GB, resumes; reads MODEL_* from .env).
   Verify: `./scripts/diagnose.sh 03`.
4. **Workflow:** API JSON already ships in `workflows/`. Verify:
   `./scripts/diagnose.sh 04` (all class_types resolve via `/object_info`).
5. **Smoke render:** `./scripts/diagnose.sh 05` (short clip through the real pipeline).
6. **MCP server (stdio, in container):** `./scripts/diagnose.sh 06` — must run via
   `docker exec` (the runner now lives in the image). For remote/VPS HTTPS see
   `docs/MCP_REMOTE.md` + `scripts/mcp_http_runner.sh`.
7. **End-to-end agent flow** (`tests/07_e2e_agent.sh` — real `submit_scene` → `wait_for_video`
   → `compose_final` over stdio, renders two low-res scenes). Verify: `./scripts/diagnose.sh 07`.
8. **Docs** (README EN) and **only then** the OpenCode `opencode.json` integration
   (docker-exec entry; uv + remote-https variants kept as disabled examples).

**New: Audiovisual Studio (run after step 7)**
9. **Install Whisper model:** `./scripts/setup_whisper.sh small` (or base/medium/large-v3)
10. **Install deps:** `./scripts/install_deps.sh` (yt-dlp, faster-whisper, requests)
11. **Test studio pipeline:** `uv run python -c "from minimax_mcp.orchestrator import AudiovisualStudio; studio = AudiovisualStudio(downloads_dir='downloads'); result = studio.run_full_pipeline(url='local_test', save_only=True, output_dir='output/transcriptions'); print(result)"`
12. **Only then** OpenCode `opencode.json` integration.

---

## 5. Docker / ComfyUI gotchas (all learned the hard way)

- **`--listen 127.0.0.1` INSIDE the container BREAKS port publishing.** docker-proxy
  connects to the container's interface IP, not its loopback → host `curl` gets
  `Connection reset by peer` while it works inside the container. The image MUST run
  ComfyUI with `--listen 0.0.0.0`; the compose file maps the port to
  `127.0.0.1:8188:8188` on the host. (First build shipped
  `--listen 127.0.0.1` and we debugged exactly this.)
- **Version comparison bug:** `0.30.2` → `MAJOR=0`, `MINOR=30`. Test must treat
  `major==0 && minor>=30` as OK, not `major>=1`.
- **VRAM threshold:** a "12 GB" card reports ~12282 MiB. Test threshold is `>= 12000`,
  not `>= 12288` (false negative).
- **`nohup … &` is NOT enough in non-interactive shells** — when the launching command
  times out, the process group gets killed. Use `setsid nohup bash … </dev/null &`
  for long downloads.
- **`download_models.sh` must not skip on `-s` (non-empty)** — a 2.2 GB partial file
  would be treated as complete. It now stores expected byte sizes and only skips when
  `have >= expect`; otherwise it resumes with `curl -C -`.
- **VAE URLs need the `vae/` subfolder prefix** — the two VAEs are NOT at the repo root
  of `Comfy-Org/MiniMax-H3`; fetching `.../resolve/main/<file>` returns 404. Use
  `.../resolve/main/vae/<file>?download=true`. Always confirm exact remote paths via
  `https://huggingface.co/api/models/<repo>?blobs=true` before hardcoding them.
- ComfyUI validates `/prompt` server-side: with models absent you get HTTP 400 with
  `value_not_in_list` errors — that is EXPECTED and confirms the workflow structure is
  fine. Structural errors would be `bad_link` / `required_input_missing` / `not_a_valid_type`.
- Container has **no `curl`** — test from inside with `python urllib`.
- **`--lowvram` is required on 12 GB VRAM.** The base image `pytorch/pytorch:2.5.1`
  predates DynamicVRAM support (needs torch ≥ 2.8); with torch 2.5.1 ComfyUI warns
  "VRAM estimates may be unreliable" and `--lowvram` attaches **0 patches** — the
  32B text encoder (~9 GB) and the INT4 UNet end up co-resident and
  `MiniMaxH3ImageToVideo`/`SamplerCustomAdvanced` OOM even at 512×320.
- **torch must be upgraded to ≥ 2.8 inside the image** so ComfyUI uses DynamicVRAM
  (this is what actually makes lowvram work; "Model MiniMaxH3 prepared for dynamic
  VRAM loading" in logs is the good sign). There is **no cu124 wheel for torch ≥ 2.8**
  — install from the **cu128** index (`--index-url https://download.pytorch.org/whl/cu128`);
  those wheels bundle their own CUDA libs via pip `nvidia-*` deps and the host driver
  supports CUDA 12.8. **Pin `torchvision==0.23.0` and `torchaudio==2.8.0` to the same
  2.8.0 release train** — an unpinned `pip install torchaudio` grabs 2.13 which needs
  torch ≥ 2.13 and the container crashes at boot with
  `OSError: _torchaudio.abi3.so: undefined symbol: torch_library_impl`.
- **`SaveVideo` output lands under the `images` history key**, not `videos`/`gifs`.
  `resolve_output()` must scan *every* kind for a `.mp4` filename or it returns None
  even though the file was rendered (the .mp4 is saved to `output/<prefix>_NNNNN_.mp4`).

### 5.x Dockerized MCP gotchas (new stack)

- **All scripts use `$COMPOSE_ARGS`** (`config.sh` builds
  `--project-directory $PROJECT_ROOT --env-file $PROJECT_ROOT/.env -f $COMPOSE_FILE`).
  NEVER call `docker compose -f docker/docker-compose.yml` bare: compose otherwise
  reads `.env` from `docker/` (absent) and relative mounts resolve one level too high.
- **Bind mounts in the compose file MUST use absolute host paths** (from `.env`:
  `MODELS_DIR`, `OUTPUT_DIR`, `INPUT_DIR`, `PROJECT_ROOT`). With `--project-directory`
  a relative `../output` becomes `$PROJECT_ROOT/../output` (wrong). This bit us: the
  container started with `OUTPUT_HOST_DIR=../output` and an empty models mount.
- **The in-image MCP venv lives at `/opt/mcp-venv`** (created by the Dockerfile with
  `UV_PROJECT_ENVIRONMENT`). `/workspace` is a read-only bind-mount, so the venv
  cannot be inside it. `mcp_runner.sh` runs `/opt/mcp-venv/bin/python` directly with
  `PYTHONPATH=/workspace/src` — there is **no `/opt/mcp-venv/bin/uv`**.
- **`mcp_runner.sh` forces `MCP_TRANSPORT=stdio`** even though the container env now
  defaults to `streamable-http` (for VPS). Without the override the stdio handshake
  hangs (server boots uvicorn instead). `mcp_http_runner.sh` forces `streamable-http`.
- **Remote MCP (streamable-http)**: server binds `MCP_HOST/MCP_PORT` (default
  `0.0.0.0:8848`, endpoint `/mcp`). The compose file publishes it on `127.0.0.1` only.
  A bare `GET /mcp` returns HTTP 406 (expected — needs `Accept: text/event-stream`).
  Real clients POST with `Accept: application/json, text/event-stream`. Front with
  Caddy/nginx TLS for HTTPS (`docs/MCP_REMOTE.md`). **No auth** — keep it off public
  `0.0.0.0` or add Basic Auth/mTLS.
- **Health check vs models dir**: when the MCP runs in the container, `MODELS_DIR`
  inside the container is `/comfy/ComfyUI/models` (compose env), NOT the host path.
  `OUTPUT_HOST_DIR` is the host-side view of output so reported paths work in OpenCode.
- **The Dockerfile's `COPY`/`uv sync` build context is the project ROOT** (`context: ..`
  in compose). Keep scripts/workflows under the repo so they land in the image and in
  the `/workspace` mount.

---

## 6. The H3 workflow (critical knowledge)

### 6.1 The template hash is a SUBGRAPH, not a node class

The official template `video_minimax_h3_t2v.json` has a single functional node whose
`type` is `4c314f31-ecda-4b08-ae98-faaba1bf613f`. That string is **NOT a security token,
NOT a per-user env var, and NOT a registered class**. It is the `id` of a **subgraph**
(stored in `definitions.subgraphs[0]`) named "Image to Video (MiniMax H3)". The ComfyUI
frontend expands that subgraph into 14 real nodes at load time. The backend rejects the
hash as a `class_type` (`missing_node_type`). When converting a template, you must
**expand subgraphs**, not copy node types verbatim.

### 6.2 The expanded T2V workflow (`workflows/minimax_h3_t2v_api.json`)

14 nodes, API format (top-level map: node id → `{class_type, inputs}`):

| ID | class_type | Notes |
|---|---|---|
| 1 | `UNETLoader` | `unet_name` = INT4 diffusion |
| 2 | `CLIPLoader` | `clip_name` = INT4 text encoder, `type=minimax` |
| 3 | `VAELoader` | video VAE |
| 4 | `VAELoader` | audio VAE |
| 5 | `MiniMaxH3ImageToVideo` | **H3 T2V core**: `clip`,`vae`,`prompt`,`width`,`height`,`length` |
| 6 | `RandomNoise` | `noise_seed` (the seed) |
| 7 | `BasicGuider` | model=1, conditioning=5[0] |
| 8 | `KSamplerSelect` | `sampler_name=res_multistep` |
| 9 | `BasicScheduler` | `scheduler=simple`, `steps=20`, `denoise=1` |
| 10 | `SamplerCustomAdvanced` | noise=6, guider=7, sampler=8, sigmas=9, latent=5[1] |
| 11 | `VAEDecode` | video latent→images (vae=3) |
| 12 | `VAEDecodeAudio` | audio latent→audio (vae=4) |
| 13 | `CreateVideo` | images=11, audio=12, `fps=24`, `bit_depth=8` |
| 14 | `SaveVideo` | `filename_prefix`, `format=auto`, `codec=auto` |

**Duration→frames math** (the template's ComfyMathExpression): `snap(sec*24)` up to the
17k+5 grid → `frames = max(5, round(d*24)) + (5 - (max(5, round(d*24)) % 17)) % 17`.
`5s → 124 frames`, `10s → 243`. Reimplemented in `server.py::duration_to_frames`.

**`server.py` node IDs:** `H3_NODE_ID="5"`, `NOISE_NODE_ID="6"`, SaveVideo found by
`class_type=="SaveVideo"`. The loader nodes (1–4) are patched per submission with the
configured model set (`MODEL_DIFFUSION`/`MODEL_TEXT_ENCODER`/`MODEL_VIDEO_VAE`/
`MODEL_AUDIO_VAE` from .env), so bigger variants work without editing the workflow.

---

## 7. MCP tools (FastMCP; stdio locally, streamable-http for VPS)

### Original Video Factory Tools
- `health_check()` — ComfyUI `/system_stats` + required model files presence/sizes.
- `submit_scene(prompt, duration, width, height, seed, filename_prefix)` — injects into
  the workflow, POST `/prompt`, returns `{prompt_id, seed}`. `filename_prefix` defaults
  to `OUTPUT_PREFIX` from .env.
- `get_status(prompt_id)` — history poll: queued / running / completed / error.
- `wait_for_video(prompt_id, timeout)` — websocket-driven block until render done,
  returns path to `.mp4` (host view via `OUTPUT_HOST_DIR` when running in-container).
- `list_outputs()` — list generated videos in the output dir.
- `compose_final(scene_paths, output_path)` — ffmpeg concat of scenes into a final video
  (re-encode, crossfade-free).

### New: Audiovisual Studio Tools
- `download_video(url, browser?)` — Download Instagram Reels, YouTube, etc. using yt-dlp
  with browser cookies. Returns `{ok, filepath, title, duration, uploader}`.
- `transcribe_video(path, model_size?, device?, language?)` — Transcribe audio from video
  using faster-whisper (local, GPU). Returns `{ok, text, segments, language}` with timestamps.
- `create_cinematic_prompt(transcription, style?)` — Convert transcription into a
  cinematic/educational/social MiniMax H3 structured prompt. Returns `{ok, prompt, style, length}`.
- `generate_video(prompt, duration, width, height, seed?, filename_prefix?)` — Submit
  prompt to MiniMax H3 via ComfyUI. Returns `{ok, output_path, prompt_id, seed}`.
- `studio_pipeline(url, style?, duration?, width?, height?, save_only?, output_dir?)`
  — **Full pipeline**: URL → download → transcribe → prompt → video (or save_only).
  Returns all intermediate results + final video path or saved files.

**Running (3 modes):**

| Mode | Command | Where |
|---|---|---|
| Local stdio (dockerized) | `docker exec -i minimax-comfyui bash /workspace/scripts/mcp_runner.sh` | container |
| Local stdio (host uv) | `uv run --directory <project> python src/minimax_mcp/server.py` | host |
| Remote HTTPS (VPS) | `MCP_TRANSPORT=streamable-http python src/minimax_mcp/server.py` behind Caddy/nginx | container/`mcp_http_runner.sh` |

Transport selection: env `MCP_TRANSPORT` (`stdio` default; `http`, `streamable-http`,
`sse` also supported) + `MCP_HOST`/`MCP_PORT` (default `0.0.0.0:8848`, path `/mcp`).

Config env vars: `COMFYUI_URL`, `WORKFLOW_PATH`, `MODELS_DIR`, `OUTPUT_DIR`,
`OUTPUT_PREFIX`, `OUTPUT_HOST_DIR`, `MODEL_*`, `STUDIO_DOWNLOADS_DIR`,
`WHISPER_MODEL`, `WHISPER_DEVICE`, `WHISPER_COMPUTE_TYPE`, `STUDIO_BROWSER`.

**Client-side note:** when connecting with `fastmcp.Client` + `StdioTransport`, pass
`env=dict(os.environ)` (and ensure `MODELS_DIR`) to the transport — the child process
does NOT inherit the parent env otherwise, and `health_check` will report all models
missing. `StdioTransport(command, args, env, cwd)` — the old `["cmd", ...]` list
signature no longer exists in fastmcp 3.x.

### Adding or changing a tool

Every tool has a matching OpenCode slash command, generated from this file's
signatures. When you add or change an `@mcp.tool()`:

1. Give it a command name in `scripts/command_docs/catalog.py`. The generator
   will not invent one — naming is a human call.
2. If there is operational knowledge the signature cannot express (hardware
   limits, known error messages, chaining into another tool), record it in
   `scripts/command_docs/overrides.py`.
3. Run `uv run python scripts/generate_commands.py`.
4. Commit the generated `.md` files together with the tool.

`tests/unit_commands.py` fails if you skip any of these — that is deliberate.
The seven knowledge-base tools went undocumented for days precisely because
nothing forced the step.

---

## 8. Validation & troubleshooting cheat-sheet

```bash
cd <project>
./scripts/diagnose.sh            # full run (aggregates PASS/FAIL)
./scripts/diagnose.sh 02 03      # single blocks
docker logs minimax-comfyui      # ComfyUI logs
curl -s http://127.0.0.1:8188/system_stats
curl -s http://127.0.0.1:8188/object_info | jq 'keys[]' | grep -i minimax
# MCP stdio handshake (in-container):
printf '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"probe","version":"1"}}}\n' | docker exec -i minimax-comfyui bash /workspace/scripts/mcp_runner.sh
# MCP HTTP (streamable-http) — expect 406 on bare GET; POST with the right headers works:
curl -s -X POST http://127.0.0.1:8848/mcp -H 'Content-Type: application/json' -H 'Accept: application/json, text/event-stream' -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"curl","version":"1"}}}'
```

If `/prompt` returns 400: read `node_errors` — `value_not_in_list` = missing model file;
anything else (bad_link/required_input_missing) = workflow wiring bug (§6.2).

---

## 9. Tutorial: Como pedir ao OpenCode via MCP para baixar/transcrever/gerar vídeo

### Configuração no `opencode.json`

```jsonc
{
  "mcp": {
    "minimax-video-factory": {
      "type": "local",
      "command": ["docker", "exec", "-i", "minimax-comfyui", "bash", "/workspace/scripts/mcp_runner.sh"],
      "description": "MiniMax H3 video factory + Audiovisual Studio"
    }
  }
}
```

### Exemplos de uso no chat do OpenCode

#### 1. Baixar apenas (Instagram Reel)
> "Baixe este Reel do Instagram: https://www.instagram.com/p/DbHIZl5Pk_0/"

O OpenCode chamará `download_video` com o URL. O arquivo será salvo em `downloads/`.

#### 2. Transcrever um vídeo local
> "Transcreva o vídeo `downloads/Video by anajcodes.mp4` usando Whisper small em GPU"

Chama `transcribe_video` com `model_size="small"`, `device="cuda"`, `language="pt"`.

#### 3. Criar prompt cinematográfico a partir de transcrição
> "Crie um prompt cinematográfico para MiniMax H3 baseado nesta transcrição: [cole a transcrição aqui]"

Usa `create_cinematic_prompt` com `style="cinematic"` (ou "educational", "social").

#### 4. Pipeline completo (download → transcrever → prompt → salvar)
> "Baixe este Reel https://www.instagram.com/p/DbHIZl5Pk_0/, transcreva com Whisper, crie prompt cinematográfico e salve transcrição + prompt em output/transcriptions/ (não gere vídeo)"

Chama `studio_pipeline` com `save_only=true`, `output_dir="output/transcriptions"`.

#### 4b. Pipeline completo com geração de vídeo (requer GPU livre)
> "Baixe este Reel, transcreva, crie prompt e gere o vídeo de 10s 1344x768"

Chama `studio_pipeline` com `save_only=false` (padrão). **Atenção:** consome GPU por ~5 min/clip.

#### 5. Gerar vídeo a partir de prompt pronto
> "Gere um vídeo de 5s: 'A beautiful sunset over the ocean, gentle waves, cinematic lighting'"

Usa `generate_video` direto (pula download/transcrição).

### Dicas importantes

1. **Container deve estar rodando** para ferramentas que usam GPU (generate_video, transcribe_video com GPU). Verifique: `docker ps | grep minimax-comfyui`

2. **Cookies do navegador** — `download_video` usa `cookiesfrombrowser=('chrome',)`. Feche o Chrome antes se der erro de "database locked".

3. **GPU memory** — Com `--lowvram` em 12 GB, cada clip de 5s leva ~4-5 min. Reiniciar o container (`./scripts/stop_comfyui.sh && ./scripts/start_comfyui.sh`) limpa fragmentação VRAM entre clips pesados.

4. **save_only=True** — pula a geração de vídeo (não precisa de GPU). Útil para só baixar/transcrever/criar prompt.

5. **Output paths** — O MCP retorna paths relativos ao host via `OUTPUT_HOST_DIR`. Arquivos salvos em `output/transcriptions/` e vídeos em `output/`.

6. **Resolução máxima na prática = 1024x576 em 12 GB VRAM.** A documentação diz que o canvas H3 vai até 768x1344, mas `generate_video`/`submit_scene` com **1344x768 OOM no sampler** (`torch.OutOfMemoryError`) mesmo com `--lowvram`. O maior tamanho testado sem OOM é **1024x576** (~15-20 min/clip de 5s); 512x320 é o mais rápido (~5 min). Sempre informe a resolução no prompt da demo.

7. **Timeout MCP do opencode:** o client opencode tem timeout curto por padrão (~60s) para chamadas MCP — `wait_for_video`/`generate_video` (5-30 min) estouram com `MCP error -32001: Request timed out` mesmo passando `timeout=` ao tool. Fix: `"experimental": { "mcp_timeout": 3600000 }` no config global do opencode (`~/.config/opencode/opencode.json`). Aplica-se a processos novos (`opencode run`); sessões abertas precisam restart.

8. **`opencode run` NÃO tem flag `--mcp`.** Servers MCP configurados no config global (`mcp.*` com `enabled: true`) são carregados automaticamente em toda sessão. `opencode run --auto "<prompt>"` é suficiente (evita o `Unknown argument: mcp`).

### Exemplo completo no chat

> **Você:** "Quero transformar este Reel em um vídeo educativo: https://www.instagram.com/p/DbHIZl5Pk_0/
> 1. Baixe o vídeo
> 2. Transcreva com Whisper small
> 3. Crie um prompt estilo 'educational' (explicativo, 15s)
> 4. Salve a transcrição e o prompt em output/transcriptions/
> 5. NÃO gere o vídeo ainda (save_only=true)"

> **OpenCode:** [executa studio_pipeline com save_only=true...]
> ✅ Transcrição salva em: output/transcriptions/transcription_20260806_XXXXX.txt
> ✅ Prompt salvo em: output/transcriptions/prompt_20260806_XXXXX.txt

> **Você (depois):** "Ok, agora gere o vídeo com esse prompt salvo, 15s, 1344x768"

> **OpenCode:** [executa generate_video com o prompt...]
> ✅ Vídeo gerado em: output/studio/...

### Comandos opencode (slash)

Definidos em `.opencode/command/` (carregados no start do opencode — precisa restart para novos comandos):

| Comando | Uso |
|---|---|
| `/minimax-gerar-video` | Gera vídeo no MiniMax H3 via MCP. `$ARGUMENTS` aceita descrição em linguagem natural + `duration=`, `width=`, `height=`, `seed=`, `filename_prefix=`. Template impõe **1024x576** (OOM acima). Se `generate_video` travar, fallback: `submit_scene` + `wait_for_video`. |
| `/minimax-download` | Baixa vídeo (Reel/YT) via yt-dlp + cookies. `$ARGUMENTS`: `<URL> [browser=chrome] [transcrever] [model_size=small] [language=pt]`. Se `transcrever`, chama `transcribe_video` em GPU. |
| `/minimax-transcrever` | Transcreve um vídeo **local** com Whisper (GPU). `$ARGUMENTS`: `<caminho-do-video> [model_size=small] [device=cuda] [language=pt]`. Usa a tool `transcribe_video`. |

### Resumo dos comandos MCP disponíveis

| Ferramenta | Quando usar | Precisa GPU? |
|---|---|---|
| `download_video` | Baixar Reel/YT | Não |
| `transcribe_video` | Transcrever arquivo local | Sim (GPU) |
| `create_cinematic_prompt` | Criar prompt a partir de texto | Não |
| `generate_video` | Renderizar vídeo no MiniMax H3 | Sim (GPU) |
| `studio_pipeline` | Pipeline completo (tudo junto) | Só se `save_only=false` |
| `health_check` | Verificar ComfyUI + modelos | Não |
| `compose_final` | Concatenar cenas | Não (ffmpeg CPU) |
## 10. Knowledge Base (Postgres + pgvector + local LLM)

**Setup:**
1. `docker compose $COMPOSE_ARGS up -d postgres` — brings up Postgres with pgvector.
2. `uv run alembic upgrade head` — creates `documents`/`chunks`/`embeddings` tables.
3. Ensure Ollama is running (`ollama list` should show `LLM_MODEL` and
   `EMBEDDING_MODEL` from `.env`, default `lfm2:24b` and `mxbai-embed-large`).
   `LLM_TIMEOUT` (default 900 s) bounds each generation call; the slow 32B-class
   models can exceed even 900 s on a swapping 30 GB box — prefer `lfm2:24b`.
4. The MCP server runs in **host mode** for these tools (`uv run --directory
   <project> python src/minimax_mcp/server.py`), not inside the `comfyui`
   container — it needs direct access to `localhost:11434` (Ollama) and
   `127.0.0.1:${KB_POSTGRES_PORT}` (Postgres).

**Data model:** one `documents` row per ingested item (`type`: video/audio/text),
each split into `chunks`, each chunk with one `embeddings` row (pgvector,
`mxbai-embed-large`, 1024 dims). `knowledge_search` combines Postgres full-text
search (`to_tsvector`/`plainto_tsquery`, GIN index) with pgvector cosine
similarity.

**LLM provider:** `LLM_PROVIDER=ollama` (default) or `openai-compatible`
(set `OPENAI_API_URL`/`OPENAI_API_KEY`, e.g. OpenRouter/Groq free tier).
Embeddings are always local via Ollama regardless of `LLM_PROVIDER`.

**Obsidian export:** optional, controlled by `VAULT_PATH` in `.env`. Leave
empty to skip — the existing vault at `~/Documents/Obsidian Vault` was flagged
as possibly unhealthy, so Postgres (not Obsidian) is the source of truth.
Failures writing the markdown copy never fail the ingest call.

**Validation:** `./tests/08_knowledge.sh` (requires Postgres + Ollama running).
`uv run pytest -m unit` / `-m integration_db` / `-m integration_llm` for
selective marker-based runs. `tests/integration_knowledge_db.py` is idempotent
(cleans up its own `example.com/test` documents via `db.delete_documents`), so
repeated runs don't accumulate stale docs that break top-result assertions.

**Full tutorial & reference:** `docs/KNOWLEDGE_BASE.md` — the 6 `knowledge_*`
tools with all parameters and best options, recommended flows, chat-prompt
examples for OpenCode, the Postgres schema (`documents`/`chunks`/`embeddings`),
`.env` knobs and troubleshooting. The complete 18-tool auto-generated reference
lives in `docs/MCP_TOOLS.md`.

### 10.1 Tutorial: pedir via chat (OpenCode)

MCP entry: `minimax-knowledge-base` (host-uv, `enabled: true`). **Restart the
opencode session** after config changes. Requer Postgres + Ollama de pé.

| Prompt no chat | Tool chamada |
|---|---|
| "Documente este texto na minha base: [texto]" | `knowledge_ingest_text` |
| "Baixe, transcreva e salve este Reel na base: <URL>" | `knowledge_ingest_video` |
| "Transcreva e documente este podcast: /path/x.mp3" | `knowledge_ingest_audio` |
| "Importe os tutoriais de /path/pasta (markdown/Obsidian) para a base" | `knowledge_ingest_markdown` |
| "Pesquise na minha base por 'Docker Ubuntu'" | `knowledge_search` |
| "O que eu já salvei sobre Docker? Responda com base na base." | `knowledge_ask` |
| "Troquei o modelo de embedding; reindexe tudo." | `knowledge_reindex` |

**Melhores escolhas de parâmetros:**
- `whisper_model`: `small` (padrão, bom equilíbrio) → `medium`/`large-v3` p/ fidelidade (mais lento, mais VRAM).
- `top_k` em `knowledge_search`: `5–10` para explorar; `knowledge_ask` usa `3` por padrão.
- `LLM_MODEL`: `lfm2:24b` recomendado em 30 GB RAM; `qwen2.5-coder:14b` mais rápido; 32B só se não se importar com 15+ min/ingest.
