"""MiniMax Video Factory — MCP Server ("Local Production Agent").

Exposes ComfyUI + MiniMax H3 as MCP tools for OpenCode:

  * health_check()                    -> backend + models status
  * submit_scene(prompt, ...)         -> inject prompt into API workflow, POST /prompt, return prompt_id
  * get_status(prompt_id)             -> poll ComfyUI history
  * wait_for_video(prompt_id, ...)    -> block until render finishes, return path to .mp4
  * list_outputs()                    -> list generated videos in the output dir
  * compose_final(scene_paths, ...)   -> ffmpeg concat of scenes into a final video

  # New: Audiovisual Studio tools
  * download_video(url, ...)          -> download video from Instagram/YT using yt-dlp + browser cookies
  * transcribe_video(path, ...)       -> transcribe audio using faster-whisper (local, GPU)
  * create_cinematic_prompt(text, ...) -> convert transcription into MiniMax H3 prompt
  * generate_video(prompt, ...)       -> submit prompt to MiniMax H3 via ComfyUI
  * studio_pipeline(url, ...)         -> full pipeline: URL → download → transcribe → prompt → video

Run (stdio, for OpenCode MCP):
  uv run --directory <project> python src/minimax_mcp/server.py

Configuration (env vars / .env):
  COMFYUI_URL           http://127.0.0.1:8188
  WORKFLOW_PATH         path to API-format workflow JSON (default workflows/minimax_h3_t2v_api.json)
  MODELS_DIR            host models dir (for health checks)
  OUTPUT_DIR            host output dir where ComfyUI writes .mp4 (default <project>/output)
  STUDIO_DOWNLOADS_DIR  directory for downloaded videos (default <project>/downloads)
  WHISPER_MODEL         whisper model size: tiny, base, small, medium, large-v3 (default: small)
  WHISPER_DEVICE        cuda or cpu (default: cuda)
  WHISPER_COMPUTE_TYPE  float16 (GPU), int8 (CPU), float32 (default: float16)
  STUDIO_BROWSER        browser for cookies: chrome, firefox, edge, brave (default: chrome)
"""
from __future__ import annotations

import logging
import os
import sys
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from fastmcp import FastMCP
from pydantic import Field

from minimax_mcp import ig_queue
from minimax_mcp.comfyui_client import ComfyUIClient
from minimax_mcp.core import (
    compose_final_core,
    output_relpath,
    progress_bar,
    submit_scene_core,
    wait_for_video_core,
)
from minimax_mcp.downloader import VideoDownloader
from minimax_mcp.orchestrator import AudiovisualStudio
from minimax_mcp.transcriber import AudioTranscriber

# ---------------- logging ----------------
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
logger = logging.getLogger("minimax_mcp")

load_dotenv()

# ---------------- config ----------------
PROJECT_ROOT = Path(__file__).resolve().parents[2]
COMFYUI_URL = os.environ.get("COMFYUI_URL", "http://127.0.0.1:8188")
WORKFLOW_PATH = Path(os.environ.get("WORKFLOW_PATH", PROJECT_ROOT / "workflows" / "minimax_h3_t2v_api.json"))
MODELS_DIR = Path(os.environ.get("MODELS_DIR") or
                  ("/opt/minimax/models" if os.path.isdir("/opt/minimax/models") else "/var/tmp/minimax/models"))
OUTPUT_DIR = Path(os.environ.get("OUTPUT_DIR", PROJECT_ROOT / "output"))
OUTPUT_HOST_DIR = os.environ.get("OUTPUT_HOST_DIR") or str(OUTPUT_DIR)
OUTPUT_PREFIX = os.environ.get("OUTPUT_PREFIX", "video/factory")

# Studio config
STUDIO_DOWNLOADS_DIR = Path(os.environ.get("STUDIO_DOWNLOADS_DIR", PROJECT_ROOT / "downloads"))
STUDIO_DOWNLOADS_HOST_DIR = os.environ.get("STUDIO_DOWNLOADS_HOST_DIR") or str(STUDIO_DOWNLOADS_DIR)
WHISPER_MODEL = os.environ.get("WHISPER_MODEL", "small")
WHISPER_DEVICE = os.environ.get("WHISPER_DEVICE", "cuda")
WHISPER_COMPUTE_TYPE = os.environ.get("WHISPER_COMPUTE_TYPE", "float16")
STUDIO_BROWSER = os.environ.get("STUDIO_BROWSER", "chrome")

H3_NODE_ID = "5"
NOISE_NODE_ID = "6"
SAVE_NODE_CLASS = "SaveVideo"

DIFFUSION_MODEL = os.environ.get("MODEL_DIFFUSION", "minimax_h3_fl2va_pruned_int4_convrot.safetensors")
TEXT_ENCODER = os.environ.get("MODEL_TEXT_ENCODER", "qwen3vl_32b_minimax_h3_int4_convrot.safetensors")
VIDEO_VAE = os.environ.get("MODEL_VIDEO_VAE", "minimax_h3_video_vae_fp16.safetensors")
AUDIO_VAE = os.environ.get("MODEL_AUDIO_VAE", "minimax_h3_audio_vae_fp32.safetensors")

REQUIRED_MODELS = {
    "diffusion_models": [DIFFUSION_MODEL],
    "text_encoders": [TEXT_ENCODER],
    "vae": [VIDEO_VAE, AUDIO_VAE],
}

mcp = FastMCP("minimax-video-factory")


# ---------------- helpers ----------------
def output_dir_abs() -> Path:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    return OUTPUT_DIR


def to_host_path(p: str | os.PathLike[str]) -> str:
    s = str(p)
    if OUTPUT_HOST_DIR != str(OUTPUT_DIR):
        try:
            rel = Path(s).relative_to(OUTPUT_DIR)
            return str(Path(OUTPUT_HOST_DIR) / rel)
        except ValueError:
            pass
    return s


def to_container_path(p: str | os.PathLike[str]) -> str:
    s = str(p)
    if OUTPUT_HOST_DIR != str(OUTPUT_DIR):
        try:
            rel = Path(s).relative_to(Path(OUTPUT_HOST_DIR))
            return str(OUTPUT_DIR / rel)
        except ValueError:
            pass
    return s


def downloads_to_host_path(p: str | os.PathLike[str]) -> str:
    s = str(p)
    if STUDIO_DOWNLOADS_HOST_DIR != str(STUDIO_DOWNLOADS_DIR):
        try:
            rel = Path(s).relative_to(STUDIO_DOWNLOADS_DIR)
            return str(Path(STUDIO_DOWNLOADS_HOST_DIR) / rel)
        except ValueError:
            pass
    return s


def downloads_to_container_path(p: str | os.PathLike[str]) -> str:
    s = str(p)
    if STUDIO_DOWNLOADS_HOST_DIR != str(STUDIO_DOWNLOADS_DIR):
        try:
            rel = Path(s).relative_to(Path(STUDIO_DOWNLOADS_HOST_DIR))
            return str(STUDIO_DOWNLOADS_DIR / rel)
        except ValueError:
            pass
    return s


# ---------------- tools ----------------
@mcp.tool()
def health_check() -> dict[str, Any]:
    """Check ComfyUI backend health and required MiniMax H3 models presence."""
    client = ComfyUIClient(COMFYUI_URL)
    backend = client.health()
    if not backend.get("ok"):
        return {"ok": False, "comfyui": backend, "models": "unknown"}

    models: dict[str, Any] = {}
    all_ok = True
    for sub, files in REQUIRED_MODELS.items():
        present = []
        for fname in files:
            p = MODELS_DIR / sub / fname
            present.append({"name": fname, "present": p.exists(),
                            "size_gb": round(p.stat().st_size / 1e9, 2) if p.exists() else None})
            if not p.exists():
                all_ok = False
        models[sub] = present

    return {"ok": backend["ok"] and all_ok, "comfyui": backend, "models": models}


@mcp.tool()
def submit_scene(
    prompt: str = Field(description="MiniMax H3 structured prompt (shots + camera + audio)"),
    duration: float = Field(default=5.0, description="Clip duration in seconds (4-15; snaps to 17-frame grid)"),
    width: int = Field(default=1024, description="Output width (multiple of 32). Default 1024: 1344x768 OOMs the sampler on 12 GB VRAM"),
    height: int = Field(default=576, description="Output height (multiple of 32). Default 576: raising it past 1024x576 risks OOM on 12 GB VRAM"),
    seed: int | None = Field(default=None, description="Random seed (defaults to random)"),
    filename_prefix: str = Field(default=OUTPUT_PREFIX, description="Output filename prefix (default from OUTPUT_PREFIX env)"),
    first_frame: str | None = Field(default=None, description="Caminho de uma imagem de referência; o vídeo é animado a partir dela (o modelo é FL2VA, treinado para isso)"),
    steps: int | None = Field(default=None, description="Passos do sampler (default 20). Mais passos = mais detalhe e mais tempo, proporcionalmente"),
) -> dict[str, Any]:
    """Inject a scene prompt into the API workflow and submit it to ComfyUI.

    Returns {"prompt_id": ...}. Use wait_for_video() to await completion.
    """
    return submit_scene_core(
        prompt=prompt, duration=duration, width=width, height=height,
        seed=seed, filename_prefix=filename_prefix, first_frame=first_frame,
        steps=steps,
    )


@mcp.tool()
async def queue_status(
    watch_seconds: float = Field(
        default=20.0,
        description="Segundos ouvindo o progresso do sampler. 0 pula e retorna só a fila",
    ),
) -> dict[str, Any]:
    """Mostra a fila de renderização do ComfyUI: o que está rodando, o que espera,
    e a barra de progresso do sampler quando disponível."""
    client = ComfyUIClient(COMFYUI_URL)
    snap = client.queue_snapshot()

    progress = None
    if watch_seconds > 0 and snap["running"]:
        progress = await client.watch_progress(watch_seconds)

    lines = []
    for job in snap["running"]:
        label = job["filename_prefix"] or job["prompt_id"][:8]
        if progress and progress.get("prompt_id") in (None, job["prompt_id"]):
            value, maximum = progress.get("value", 0), progress.get("max", 0)
            lines.append(
                f"RODANDO   {label}  {progress_bar(value, maximum)}  "
                f"({value}/{maximum} steps)"
            )
        else:
            lines.append(f"RODANDO   {label}  (progresso não capturado)")
    for i, job in enumerate(snap["pending"], start=1):
        label = job["filename_prefix"] or job["prompt_id"][:8]
        lines.append(f"  {i}º na fila  {label}")
    if not lines:
        lines.append("fila vazia")

    return {
        "ok": True,
        "running": snap["running"],
        "pending": snap["pending"],
        "total": snap["total"],
        "progress": progress,
        # A percentage counts sampler steps only. VAE decode and video encoding
        # come after and are not represented, so 100% of the sampler is not
        # 100% of the clip -- the step count is shown so nobody is misled.
        "progress_note": (
            "A porcentagem conta apenas os steps do sampler; o decode do VAE e a "
            "codificação do vídeo vêm depois e não aparecem aqui."
        ),
        "summary": "\n".join(lines),
    }


@mcp.tool()
def get_status(prompt_id: str) -> dict[str, Any]:
    """Get the current status of a submitted ComfyUI prompt."""
    client = ComfyUIClient(COMFYUI_URL)
    try:
        hist = client.get_history(prompt_id)
    except Exception as e:
        return {"ok": False, "error": str(e)}
    rec = hist.get(prompt_id)
    if rec is None:
        # ComfyUI only writes to /history once a prompt FINISHES, so absence
        # means "queued" OR "rendering right now". Reporting both as queued hid
        # a jammed backlog for a full day: the stuck job and the ten waiting
        # behind it looked identical. Ask the queue which one this is.
        state = client.queue_state(prompt_id) or "queued"
        return {"ok": True, "prompt_id": prompt_id, "state": state, "outputs": None}
    status = rec.get("status", {})
    completed = bool(status.get("completed")) or bool(rec.get("outputs"))
    if completed:
        path = client.resolve_output(rec, str(output_dir_abs()))
        return {"ok": True, "prompt_id": prompt_id, "state": "completed",
                "output_path": to_host_path(path) if path else None, "outputs": rec.get("outputs")}
    if status.get("status_str") == "error":
        return {"ok": True, "prompt_id": prompt_id, "state": "error",
                "error": status}
    return {"ok": True, "prompt_id": prompt_id, "state": "running"}


@mcp.tool()
async def wait_for_video(
    prompt_id: str,
    timeout: float = Field(default=1200.0, description="Max seconds to wait"),
) -> dict[str, Any]:
    """Block until the prompt finishes rendering; returns path to the generated .mp4."""
    return await wait_for_video_core(prompt_id, timeout=timeout)


@mcp.tool()
def list_outputs() -> list[dict[str, Any]]:
    """List generated .mp4 files in the output directory."""
    d = output_dir_abs()
    files = sorted(d.rglob("*.mp4"), key=lambda p: p.stat().st_mtime, reverse=True)
    # relpath, not just filename: every run writes scene_0_00001_.mp4, and only
    # the subfolder says which run it belongs to.
    return [{"filename": p.name, "relpath": output_relpath(p, d),
             "path": to_host_path(p),
             "size_mb": round(p.stat().st_size / 1e6, 2),
             "modified": p.stat().st_mtime} for p in files]


@mcp.tool()
def compose_final(
    scene_paths: list[str] = Field(description="Ordered list of .mp4 scene files"),
    output_path: str = Field(default="output/final.mp4", description="Where to write the composed video"),
) -> dict[str, Any]:
    """Concatenate scene .mp4 files with ffmpeg into a final video (re-encode, crossfade-free)."""
    return compose_final_core(scene_paths, output_path)


# =============================================================================
# NEW: Audiovisual Studio Tools
# =============================================================================

@mcp.tool()
def download_video(
    url: str = Field(description="Video URL (Instagram Reel, YouTube, etc.)"),
    browser: str = Field(default="chrome", description="Browser for cookies: chrome, firefox, edge, brave"),
) -> dict[str, Any]:
    """Download a video from Instagram Reels, YouTube, or other platforms using yt-dlp with browser cookies."""
    downloader = VideoDownloader(output_dir=STUDIO_DOWNLOADS_DIR, browser=browser)
    result = downloader.download(url)
    if result.get("ok"):
        result["filepath"] = downloads_to_host_path(result["filepath"])
    return result


@mcp.tool()
def transcribe_video(
    video_path: str = Field(description="Path to video file to transcribe"),
    model_size: str = Field(default="small", description="Whisper model: tiny, base, small, medium, large-v3"),
    device: str = Field(default="cuda", description="cuda or cpu"),
    language: str = Field(default="pt", description="Language code (pt for Portuguese)"),
) -> dict[str, Any]:
    """Transcribe audio from a video file using faster-whisper (local, GPU-accelerated)."""
    video_path = downloads_to_container_path(video_path)
    if model_size != "small" or device != "cuda":
        transcriber = AudioTranscriber(model_size=model_size, device=device)
        return transcriber.transcribe(video_path)
    # Use default studio transcriber
    studio = AudiovisualStudio(downloads_dir=STUDIO_DOWNLOADS_DIR)
    return studio.transcriber.transcribe(video_path)


@mcp.tool()
def create_cinematic_prompt(
    transcription: str = Field(description="Full transcription text from video"),
    style: str = Field(default="cinematic", description="Prompt style: cinematic, educational, social"),
) -> dict[str, Any]:
    """Convert a transcription into a cinematic MiniMax H3 structured prompt."""
    from minimax_mcp.orchestrator import AudiovisualStudio
    studio = AudiovisualStudio(downloads_dir=STUDIO_DOWNLOADS_DIR)
    prompt = studio.create_cinematic_prompt(transcription, style=style)
    return {"ok": True, "prompt": prompt, "style": style, "length": len(prompt)}


@mcp.tool()
def generate_video(
    prompt: str = Field(description="MiniMax H3 structured prompt (shots + camera + audio)"),
    duration: float = Field(default=10.0, description="Clip duration in seconds (4-15; snaps to 17-frame grid)"),
    width: int = Field(default=1024, description="Output width (multiple of 32). Default 1024: 1344x768 OOMs the sampler on 12 GB VRAM"),
    height: int = Field(default=576, description="Output height (multiple of 32). Default 576: raising it past 1024x576 risks OOM on 12 GB VRAM"),
    seed: int | None = Field(default=None, description="Random seed"),
    filename_prefix: str = Field(default="studio/", description="Output filename prefix"),
    first_frame: str | None = Field(default=None, description="Caminho de uma imagem de referência; o vídeo é animado a partir dela (o modelo é FL2VA, treinado para isso)"),
    steps: int | None = Field(default=None, description="Passos do sampler (default 20). Medido: 30 e 40 não melhoram e custam 8x o tempo"),
    wait_seconds: float = Field(default=900.0, description="Quanto esperar antes de devolver só o prompt_id. Medido: 512x320 leva ~4.5min, 1024x576 ~3min com modelo quente"),
) -> dict[str, Any]:
    """Generate a video using the MiniMax H3 model via ComfyUI.

    Espera até wait_seconds; se o render não terminar, devolve state=rendering
    com o prompt_id em vez de segurar a conexão."""
    from minimax_mcp.orchestrator import AudiovisualStudio
    studio = AudiovisualStudio(downloads_dir=STUDIO_DOWNLOADS_DIR)
    return studio.generate_video(
        prompt=prompt, duration=duration, width=width, height=height, seed=seed,
        first_frame=first_frame, filename_prefix=filename_prefix,
        steps=steps, wait_seconds=wait_seconds,
    )


@mcp.tool()
def studio_pipeline(
    url: str = Field(description="Video URL (Instagram Reel, YouTube, etc.)"),
    style: str = Field(default="cinematic", description="Prompt style: cinematic, educational, social"),
    duration: float = Field(default=10.0, description="Generated clip duration in seconds"),
    width: int = Field(default=1024, description="Output width. Default 1024: 1344x768 OOMs the sampler on 12 GB VRAM"),
    height: int = Field(default=576, description="Output height. Default 576: raising it past 1024x576 risks OOM on 12 GB VRAM"),
) -> dict[str, Any]:
    """
    Run the complete audiovisual studio pipeline:
    URL → download → transcribe → create prompt → generate video.
    """
    from minimax_mcp.orchestrator import AudiovisualStudio
    studio = AudiovisualStudio(downloads_dir=STUDIO_DOWNLOADS_DIR)
    result = studio.run_full_pipeline(
        url=url, style=style, duration=duration, width=width, height=height,
    )
    if result.get("ok"):
        for key in ("downloaded_file", "transcription_file", "prompt_file"):
            if result.get(key):
                result[key] = downloads_to_host_path(result[key])
    return result


# =============================================================================
# NEW: Knowledge Base Tools
# =============================================================================

@mcp.tool()
def knowledge_ingest_text(
    text: str = Field(description="Texto/transcrição já pronta para processar"),
    source_url: str | None = Field(default=None, description="URL de origem, se houver"),
    title: str | None = Field(default=None, description="Título do documento"),
    platform: str = Field(default="manual", description="Origem: manual, instagram, youtube, podcast"),
) -> dict[str, Any]:
    """Gera resumo+tutorial via LLM local e salva um texto/transcrição já pronto na base de conhecimento."""
    from minimax_mcp import knowledge
    return knowledge.ingest_text(text, source_url=source_url, title=title, platform=platform)


@mcp.tool()
def knowledge_ingest_markdown(
    path: str = Field(
        description="Arquivo .md ou diretório (ex.: caminho do Obsidian) a importar"
    ),
    recursive: bool = Field(
        default=False, description="Se path for diretório, incluir subdiretórios"
    ),
    doc_type: str = Field(
        default="document", description="Tipo do documento na base (ex.: document, tutorial)"
    ),
) -> dict[str, Any]:
    """Importa um ou mais arquivos markdown (ex.: tutoriais do Obsidian) para a base de conhecimento.
    Aproveita YAML frontmatter (title/tags/url) e reutiliza `## Summary` se houver; senão gera via LLM."""
    from minimax_mcp import knowledge
    return knowledge.ingest_markdown(path, recursive=recursive, doc_type=doc_type)


@mcp.tool()
def knowledge_ingest_video(
    url: str = Field(description="URL do vídeo (Instagram Reel, YouTube, etc.)"),
    browser: str = Field(default=STUDIO_BROWSER, description="Navegador para cookies"),
    whisper_model: str = Field(default=WHISPER_MODEL, description="Tamanho do modelo Whisper"),
) -> dict[str, Any]:
    """Baixa, transcreve e documenta um vídeo na base de conhecimento (resumo + tutorial via LLM)."""
    from minimax_mcp import knowledge
    return knowledge.ingest_video(
        url, browser=browser, downloads_dir=STUDIO_DOWNLOADS_DIR,
        whisper_model=whisper_model, whisper_device=WHISPER_DEVICE,
    )


@mcp.tool()
def knowledge_ingest_audio(
    path_or_url: str = Field(description="Caminho local de um áudio/podcast, ou URL para baixar"),
    browser: str = Field(default=STUDIO_BROWSER, description="Navegador para cookies (se for URL)"),
    whisper_model: str = Field(default=WHISPER_MODEL, description="Tamanho do modelo Whisper"),
) -> dict[str, Any]:
    """Transcreve e documenta um áudio/podcast na base de conhecimento (resumo + tutorial via LLM)."""
    from minimax_mcp import knowledge
    return knowledge.ingest_audio(
        path_or_url, browser=browser, downloads_dir=STUDIO_DOWNLOADS_DIR,
        whisper_model=whisper_model, whisper_device=WHISPER_DEVICE,
    )


@mcp.tool()
def knowledge_search(
    query: str = Field(description="Termo ou pergunta para buscar na base de conhecimento"),
    top_k: int = Field(default=5, description="Número máximo de resultados"),
) -> dict[str, Any]:
    """Busca na base de conhecimento (palavra-chave + semântica) e retorna os documentos mais relevantes."""
    from minimax_mcp import knowledge
    return knowledge.search(query, top_k=top_k)


@mcp.tool()
def knowledge_ask(
    query: str = Field(description="Pergunta em linguagem natural sobre o que já foi salvo"),
    top_k: int = Field(default=3, description="Quantos documentos usar como contexto"),
) -> dict[str, Any]:
    """Responde a uma pergunta usando RAG sobre a base de conhecimento (busca + LLM)."""
    from minimax_mcp import knowledge
    return knowledge.ask(query, top_k=top_k)


@mcp.tool()
def knowledge_reindex(
    embedding_model: str | None = Field(
        default=None, description="Modelo de embedding a usar (default: EMBEDDING_MODEL do .env)"
    ),
) -> dict[str, Any]:
    """Recalcula chunks e embeddings de todos os documentos (use após trocar de modelo de embedding)."""
    from minimax_mcp import knowledge
    return knowledge.reindex(embedding_model=embedding_model)


# =============================================================================
# NEW: Instagram Saved Posts -> Knowledge Base (RabbitMQ queue + ig-worker)
# =============================================================================

@mcp.tool()
def ig_sync_saved() -> dict[str, Any]:
    """Enfileira todos os posts salvos do Instagram (via IG_SESSIONID) na fila ig.saved.
    Nao processa nada — o daemon ig-worker consome a fila em background.
    Retorna {ok, published, skipped_existing, total}."""
    from minimax_mcp import db, ig_sync

    if not ig_sync.IG_SESSIONID:
        return {"ok": False, "error": ig_sync.SESSIONID_MISSING}
    conn = ig_queue.connect()
    try:
        channel = conn.channel()
        ig_queue.declare(channel)
        session = db.get_session()
        try:
            existing = db.list_ig_pks(session)
        finally:
            session.close()
        client = ig_sync.make_client()
        return ig_sync.sync_saved_posts(
            client, existing_pks=existing,
            publish_fn=lambda msg: ig_queue.publish(channel, msg),
        )
    except Exception as e:
        return {"ok": False, "error": f"ig_sync_saved failed: {e}"}
    finally:
        ig_queue.close(conn)


@mcp.tool()
def ig_queue_status() -> dict[str, Any]:
    """Mostra o tamanho da fila ig.saved (ready/dead) e quantos consumidores ativos."""
    from minimax_mcp import ig_queue as _q

    conn = _q.connect()
    try:
        return _q.queue_status(conn.channel())
    except Exception as e:
        return {"ok": False, "error": f"ig_queue_status failed: {e}"}
    finally:
        _q.close(conn)


@mcp.tool()
def ig_worker_start() -> dict[str, Any]:
    """Envia o comando 'start' ao daemon ig-worker (retoma o consumo da fila)."""
    from minimax_mcp import ig_queue as _q

    conn = _q.connect()
    try:
        channel = conn.channel()
        _q.declare(channel)
        import json as _json

        channel.basic_publish(
            exchange="", routing_key=_q.CONTROL_QUEUE,
            body=_json.dumps({"command": "start"}), properties=None,
        )
        return {"ok": True, "command": "start"}
    except Exception as e:
        return {"ok": False, "error": f"ig_worker_start failed: {e}"}
    finally:
        _q.close(conn)


@mcp.tool()
def ig_worker_stop() -> dict[str, Any]:
    """Envia o comando 'stop' ao daemon ig-worker (pausa o consumo da fila)."""
    from minimax_mcp import ig_queue as _q

    conn = _q.connect()
    try:
        channel = conn.channel()
        _q.declare(channel)
        import json as _json

        channel.basic_publish(
            exchange="", routing_key=_q.CONTROL_QUEUE,
            body=_json.dumps({"command": "stop"}), properties=None,
        )
        return {"ok": True, "command": "stop"}
    except Exception as e:
        return {"ok": False, "error": f"ig_worker_stop failed: {e}"}
    finally:
        _q.close(conn)


@mcp.tool()
def ig_get_progress(
    last_n: int = Field(default=10, description="Quantos últimos resultados processados mostrar"),
) -> dict[str, Any]:
    """Mostra os últimos N posts do Instagram processados pelo ig-worker (state em downloads/ig)."""
    from minimax_mcp import db

    state_file = os.environ.get("IG_STATE_FILE", "downloads/ig/state.json")
    entries: list[dict] = []
    try:
        from pathlib import Path as _P

        if _P(state_file).exists():
            import json as _json

            entries = _json.loads(_P(state_file).read_text(encoding="utf-8"))
    except Exception:
        entries = []
    try:
        session = db.get_session()
        try:
            total_ig = len(db.list_ig_pks(session))
        finally:
            session.close()
    except Exception as e:
        return {"ok": False, "error": f"ig_get_progress failed: {e}"}
    return {"ok": True, "last": entries[-last_n:], "documents_with_ig_pk": total_ig}


# ---------------- entrypoint ----------------
def main() -> None:
    transport = os.environ.get("MCP_TRANSPORT", "stdio")
    if transport in ("stdio", "http", "streamable-http", "sse"):
        logger.info("Starting MiniMax Video Factory MCP server (transport=%s comfy=%s workflow=%s)",
                    transport, COMFYUI_URL, WORKFLOW_PATH)
        if transport == "stdio":
            mcp.run(transport="stdio")
        else:
            host = os.environ.get("MCP_HOST", "0.0.0.0")
            port = int(os.environ.get("MCP_PORT", "8848"))
            kwargs: dict[str, Any] = {"host": host, "port": port}
            if transport == "streamable-http":
                kwargs["path"] = "/mcp"
            mcp.run(transport=transport, **kwargs)
    else:
        sys.exit(f"Unknown MCP_TRANSPORT={transport!r} (use stdio, http, streamable-http or sse)")


if __name__ == "__main__":
    main()