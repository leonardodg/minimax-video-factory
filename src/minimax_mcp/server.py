"""MiniMax Video Factory — MCP Server ("Local Production Agent").

Exposes ComfyUI + MiniMax H3 as MCP tools for OpenCode:

  * health_check()                    -> backend + models status
  * submit_scene(prompt, ...)         -> inject prompt into API workflow, POST /prompt, return prompt_id
  * get_status(prompt_id)             -> poll ComfyUI history
  * wait_for_video(prompt_id, ...)    -> block until render finishes, return path to .mp4
  * list_outputs()                    -> list generated videos in the output dir
  * compose_final(scene_paths, ...)   -> ffmpeg concat of scenes into a final video

Run (stdio, for OpenCode MCP):
  uv run --directory <project> python src/minimax_mcp/server.py

Configuration (env vars / .env):
  COMFYUI_URL     http://127.0.0.1:8188
  WORKFLOW_PATH   path to API-format workflow JSON (default workflows/minimax_h3_t2v_api.json)
  MODELS_DIR      host models dir (for health checks)
  OUTPUT_DIR      host output dir where ComfyUI writes .mp4 (default <project>/output)
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
# When the MCP server runs INSIDE a container (docker exec) but reports paths to
# the host orchestrator, OUTPUT_HOST_DIR is the host-side view of OUTPUT_DIR.
OUTPUT_HOST_DIR = os.environ.get("OUTPUT_HOST_DIR") or str(OUTPUT_DIR)
OUTPUT_PREFIX = os.environ.get("OUTPUT_PREFIX", "video/factory")
H3_NODE_ID = "5"            # MiniMaxH3ImageToVideo (T2V) node in the expanded API workflow
NOISE_NODE_ID = "6"         # RandomNoise node (carries the seed)
SAVE_NODE_CLASS = "SaveVideo"

# Model set — overridable via .env (MODEL_DIFFUSION etc.) so bigger variants work.
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
def load_workflow() -> dict[str, Any]:
    if not WORKFLOW_PATH.exists():
        raise FileNotFoundError(f"workflow not found: {WORKFLOW_PATH} (run scripts/ui2api.py first)")
    with open(WORKFLOW_PATH) as f:
        return json.load(f)


def duration_to_frames(duration: float, fps: int = 24) -> int:
    """Snap seconds to the model's 17k+5 frame grid at 24fps (same as ComfyMathExpression)."""
    frames = max(5, round(duration * fps))
    return frames + (5 - (frames % 17)) % 17


def inject_scene(workflow: dict[str, Any], *, prompt: str, duration: float,
                 width: int, height: int, seed: int, filename_prefix: str) -> dict[str, Any]:
    """Patch the expanded T2V workflow with per-scene values.

    Sets the model loader nodes (UNET/CLIP/VAE) to the configured model set, then
    overrides the H3 node inputs (prompt/width/height/length), the RandomNoise
    seed, and the SaveVideo output prefix.
    """
    import copy
    wf = copy.deepcopy(workflow)

    # loader nodes: 1=UNET, 2=CLIP, 3=video VAE, 4=audio VAE (expanded workflow)
    loaders = {
        "1": ("UNETLoader", "unet_name", DIFFUSION_MODEL),
        "2": ("CLIPLoader", "clip_name", TEXT_ENCODER),
        "3": ("VAELoader", "vae_name", VIDEO_VAE),
        "4": ("VAELoader", "vae_name", AUDIO_VAE),
    }
    for nid, (cls, key, value) in loaders.items():
        node = wf.get(nid)
        if node is not None and node.get("class_type") == cls and key in node.get("inputs", {}):
            node["inputs"][key] = value

    h3 = wf.get(H3_NODE_ID)
    if h3 is None:
        raise KeyError(f"H3 node id '{H3_NODE_ID}' not found in workflow; adjust H3_NODE_ID")
    inputs = h3["inputs"]
    inputs["prompt"] = prompt
    inputs["width"] = width
    inputs["height"] = height
    inputs["length"] = duration_to_frames(duration)

    noise = wf.get(NOISE_NODE_ID)
    if noise is not None and "noise_seed" in noise.get("inputs", {}):
        noise["inputs"]["noise_seed"] = seed

    # SaveVideo node: set filename_prefix
    for nid, node in wf.items():
        if node.get("class_type") == SAVE_NODE_CLASS:
            node["inputs"]["filename_prefix"] = filename_prefix

    return wf


def output_dir_abs() -> Path:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    return OUTPUT_DIR


def to_host_path(p: str | os.PathLike[str]) -> str:
    """Map a container-side path under OUTPUT_DIR to the host-side view."""
    s = str(p)
    if OUTPUT_HOST_DIR != str(OUTPUT_DIR):
        try:
            rel = Path(s).relative_to(OUTPUT_DIR)
            return str(Path(OUTPUT_HOST_DIR) / rel)
        except ValueError:
            pass
    return s


def to_container_path(p: str | os.PathLike[str]) -> str:
    """Map a host-side path under OUTPUT_HOST_DIR back into the container view."""
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
    if seed is None:
        seed = random.randint(0, 2**31 - 1)
    workflow = load_workflow()
    wf = inject_scene(workflow, prompt=prompt, duration=duration,
                      width=width, height=height, seed=seed,
                      filename_prefix=filename_prefix)
    client = ComfyUIClient(COMFYUI_URL)
    try:
        prompt_id = client.submit(wf)
    except ComfyUIError as e:
        return {"ok": False, "error": str(e)}
    return {"ok": True, "prompt_id": prompt_id, "seed": seed,
            "duration": duration, "width": width, "height": height}


@mcp.tool()
def get_status(prompt_id: str) -> dict[str, Any]:
    """Get the current status of a submitted ComfyUI prompt."""
    client = ComfyUIClient(COMFYUI_URL)
    try:
        hist = client.get_history(prompt_id)
    except Exception as e:  # noqa: BLE001
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
    client = ComfyUIClient(COMFYUI_URL)
    try:
        rec = await client.wait_for_execution(prompt_id, timeout=timeout)
    except ComfyUIError as e:
        return {"ok": False, "error": str(e)}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": f"unexpected: {e}"}
    path = client.resolve_output(rec, str(output_dir_abs()))
    return {"ok": path is not None, "prompt_id": prompt_id,
            "output_path": to_host_path(path) if path else None, "outputs": rec.get("outputs")}


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
    if len(scene_paths) < 2:
        return {"ok": False, "error": "need at least 2 scenes to compose"}

    out_abs = Path(to_container_path(output_path))
    if not out_abs.is_absolute():
        out_abs = OUTPUT_DIR / output_path
    out_abs.parent.mkdir(parents=True, exist_ok=True)

    if not shutil.which("ffmpeg"):
        return {"ok": False, "error": "ffmpeg not found on PATH"}

    concat_file = output_dir_abs() / "_concat_list.txt"
    concat_file.parent.mkdir(parents=True, exist_ok=True)
    with open(concat_file, "w") as f:
        for sp in scene_paths:
            p = Path(to_container_path(sp))
            if not p.exists():
                return {"ok": False, "error": f"scene file not found: {sp}"}
            f.write(f"file '{p.resolve()}'\n")

    cmd = ["ffmpeg", "-y", "-f", "concat", "-safe", "0",
           "-i", str(concat_file), "-c", "copy", str(out_abs)]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        return {"ok": False, "error": f"ffmpeg failed: {proc.stderr[-800:]}"}
    return {"ok": True, "output_path": to_host_path(out_abs),
            "scenes": len(scene_paths)}


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
