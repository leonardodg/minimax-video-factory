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

import json
import logging
import os
import random
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Optional

from dotenv import load_dotenv
from fastmcp import FastMCP
from pydantic import Field

from minimax_mcp.comfyui_client import ComfyUIClient, ComfyUIError
from minimax_mcp.downloader import VideoDownloader
from minimax_mcp.transcriber import AudioTranscriber
from minimax_mcp.orchestrator import AudiovisualStudio
from minimax_mcp.core import (
    load_workflow,
    duration_to_frames,
    inject_scene,
    submit_scene_core,
    wait_for_video_core,
    compose_final_core,
    output_dir_abs,
    to_host_path,
    to_container_path,
)

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


# ---------------- tools ----------------
@mcp.tool()
def health_check() -> dict[str, Any]:
    """Check ComfyUI backend health and required MiniMax H3 models presence."""
    from minimax_mcp.comfyui_client import ComfyUIClient
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
    width: int = Field(default=1344, description="Output width (multiple of 32; H3 canvas is 768 short edge capped 768x1344)"),
    height: int = Field(default=768, description="Output height (multiple of 32; H3 canvas is 768 short edge capped 768x1344)"),
    seed: Optional[int] = Field(default=None, description="Random seed (defaults to random)"),
    filename_prefix: str = Field(default=OUTPUT_PREFIX, description="Output filename prefix (default from OUTPUT_PREFIX env)"),
) -> dict[str, Any]:
    """Inject a scene prompt into the API workflow and submit it to ComfyUI.

    Returns {"prompt_id": ...}. Use wait_for_video() to await completion.
    """
    from minimax_mcp.core import submit_scene_core
    return submit_scene_core(
        prompt=prompt, duration=duration, width=width, height=height,
        seed=seed, filename_prefix=filename_prefix,
    )


@mcp.tool()
def get_status(prompt_id: str) -> dict[str, Any]:
    """Get the current status of a submitted ComfyUI prompt."""
    from minimax_mcp.comfyui_client import ComfyUIClient
    client = ComfyUIClient(COMFYUI_URL)
    try:
        hist = client.get_history(prompt_id)
    except Exception as e:
        return {"ok": False, "error": str(e)}
    rec = hist.get(prompt_id)
    if rec is None:
        return {"ok": True, "prompt_id": prompt_id, "state": "queued", "outputs": None}
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
    from minimax_mcp.core import wait_for_video_core
    return await wait_for_video_core(prompt_id, timeout=timeout)


@mcp.tool()
def list_outputs() -> list[dict[str, Any]]:
    """List generated .mp4 files in the output directory."""
    d = output_dir_abs()
    files = sorted(d.rglob("*.mp4"), key=lambda p: p.stat().st_mtime, reverse=True)
    return [{"filename": p.name, "path": to_host_path(p),
             "size_mb": round(p.stat().st_size / 1e6, 2),
             "modified": p.stat().st_mtime} for p in files]


@mcp.tool()
def compose_final(
    scene_paths: list[str] = Field(description="Ordered list of .mp4 scene files"),
    output_path: str = Field(default="output/final.mp4", description="Where to write the composed video"),
) -> dict[str, Any]:
    """Concatenate scene .mp4 files with ffmpeg into a final video (re-encode, crossfade-free)."""
    from minimax_mcp.core import compose_final_core
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
    from minimax_mcp.orchestrator import AudiovisualStudio
    from minimax_mcp.downloader import VideoDownloader
    downloader = VideoDownloader(output_dir=STUDIO_DOWNLOADS_DIR, browser=browser)
    return downloader.download(url)


@mcp.tool()
def transcribe_video(
    video_path: str = Field(description="Path to video file to transcribe"),
    model_size: str = Field(default="small", description="Whisper model: tiny, base, small, medium, large-v3"),
    device: str = Field(default="cuda", description="cuda or cpu"),
    language: str = Field(default="pt", description="Language code (pt for Portuguese)"),
) -> dict[str, Any]:
    """Transcribe audio from a video file using faster-whisper (local, GPU-accelerated)."""
    from minimax_mcp.transcriber import AudioTranscriber
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
    width: int = Field(default=1344, description="Output width (multiple of 32)"),
    height: int = Field(default=768, description="Output height (multiple of 32)"),
    seed: Optional[int] = Field(default=None, description="Random seed"),
    filename_prefix: str = Field(default="studio/", description="Output filename prefix"),
) -> dict[str, Any]:
    """Generate a video using the MiniMax H3 model via ComfyUI."""
    from minimax_mcp.core import submit_scene_core
    from minimax_mcp.orchestrator import AudiovisualStudio
    studio = AudiovisualStudio(downloads_dir=STUDIO_DOWNLOADS_DIR)
    return studio.generate_video(
        prompt=prompt, duration=duration, width=width, height=height, seed=seed,
    )


@mcp.tool()
def studio_pipeline(
    url: str = Field(description="Video URL (Instagram Reel, YouTube, etc.)"),
    style: str = Field(default="cinematic", description="Prompt style: cinematic, educational, social"),
    duration: float = Field(default=10.0, description="Generated clip duration in seconds"),
    width: int = Field(default=1344, description="Output width"),
    height: int = Field(default=768, description="Output height"),
) -> dict[str, Any]:
    """
    Run the complete audiovisual studio pipeline:
    URL → download → transcribe → create prompt → generate video.
    """
    from minimax_mcp.orchestrator import AudiovisualStudio
    studio = AudiovisualStudio(downloads_dir=STUDIO_DOWNLOADS_DIR)
    return studio.run_full_pipeline(
        url=url, style=style, duration=duration, width=width, height=height,
    )


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