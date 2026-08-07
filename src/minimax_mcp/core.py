"""Core ComfyUI operations shared between server and orchestrator."""
from __future__ import annotations

import json
import logging
import os
import random
import shutil
import subprocess
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

from minimax_mcp.comfyui_client import ComfyUIClient, ComfyUIError

load_dotenv()

logger = logging.getLogger(__name__)

# ---------------- config ----------------
PROJECT_ROOT = Path(__file__).resolve().parents[2]
COMFYUI_URL = os.environ.get("COMFYUI_URL", "http://127.0.0.1:8188")
WORKFLOW_PATH = Path(os.environ.get("WORKFLOW_PATH", PROJECT_ROOT / "workflows" / "minimax_h3_t2v_api.json"))
OUTPUT_DIR = Path(os.environ.get("OUTPUT_DIR", PROJECT_ROOT / "output"))
OUTPUT_HOST_DIR = os.environ.get("OUTPUT_HOST_DIR") or str(OUTPUT_DIR)
OUTPUT_PREFIX = os.environ.get("OUTPUT_PREFIX", "video/factory")
H3_NODE_ID = "5"
NOISE_NODE_ID = "6"
SAVE_NODE_CLASS = "SaveVideo"

DIFFUSION_MODEL = os.environ.get("MODEL_DIFFUSION", "minimax_h3_fl2va_pruned_int4_convrot.safetensors")
TEXT_ENCODER = os.environ.get("MODEL_TEXT_ENCODER", "qwen3vl_32b_minimax_h3_int4_convrot.safetensors")
VIDEO_VAE = os.environ.get("MODEL_VIDEO_VAE", "minimax_h3_video_vae_fp16.safetensors")
AUDIO_VAE = os.environ.get("MODEL_AUDIO_VAE", "minimax_h3_audio_vae_fp32.safetensors")


# ---------------- helpers ----------------
def load_workflow() -> dict[str, Any]:
    if not WORKFLOW_PATH.exists():
        raise FileNotFoundError(f"workflow not found: {WORKFLOW_PATH} (run scripts/ui2api.py first)")
    with open(WORKFLOW_PATH) as f:
        return json.load(f)


def duration_to_frames(duration: float, fps: int = 24) -> int:
    frames = max(5, round(duration * fps))
    return frames + (5 - (frames % 17)) % 17


def inject_scene(workflow: dict[str, Any], *, prompt: str, duration: float,
                 width: int, height: int, seed: int, filename_prefix: str) -> dict[str, Any]:
    import copy
    wf = copy.deepcopy(workflow)

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

    for nid, node in wf.items():
        if node.get("class_type") == SAVE_NODE_CLASS:
            node["inputs"]["filename_prefix"] = filename_prefix

    return wf


def output_dir_abs() -> Path:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    return OUTPUT_DIR


def output_host_dir() -> str:
    return OUTPUT_HOST_DIR


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


def submit_scene_core(
    prompt: str,
    duration: float = 5.0,
    # 1024x576, not the 1344x768 H3 canvas maximum: the larger canvas OOMs the
    # sampler on 12 GB of VRAM. Callers with more VRAM can still pass 1344x768.
    width: int = 1024,
    height: int = 576,
    seed: int | None = None,
    filename_prefix: str = "video/factory",
) -> dict[str, Any]:
    if seed is None:
        seed = random.randint(0, 2**31 - 1)
    workflow = load_workflow()
    wf = inject_scene(workflow, prompt=prompt, duration=duration,
                      width=width, height=height, seed=seed,
                      filename_prefix=filename_prefix)
    client = ComfyUIClient(os.environ.get("COMFYUI_URL", "http://127.0.0.1:8188"))
    try:
        prompt_id = client.submit(wf)
    except ComfyUIError as e:
        return {"ok": False, "error": str(e)}
    return {"ok": True, "prompt_id": prompt_id, "seed": seed,
            "duration": duration, "width": width, "height": height}


async def wait_for_video_core(prompt_id: str, timeout: float = 1200.0) -> dict[str, Any]:
    client = ComfyUIClient(COMFYUI_URL)
    try:
        rec = await client.wait_for_execution(prompt_id, timeout=timeout)
    except ComfyUIError as e:
        return {"ok": False, "error": str(e)}
    except Exception as e:
        return {"ok": False, "error": f"unexpected: {e}"}

    # Resolve output path (container view) then translate to the host view for the client.
    path = client.resolve_output(rec, str(OUTPUT_DIR))
    return {"ok": path is not None, "prompt_id": prompt_id,
            "output_path": to_host_path(str(path)) if path else None, "outputs": rec.get("outputs")}


def compose_final_core(scene_paths: list[str], output_path: str = "output/final.mp4") -> dict[str, Any]:
    if len(scene_paths) < 2:
        return {"ok": False, "error": "need at least 2 scenes to compose"}

    # When the MCP runs inside the container, scene_paths arrive in HOST form
    # (OUTPUT_HOST_DIR). Translate them back to this process's view before
    # checking existence, so the same code works on host (no-op) and in-container.
    container_scenes = [to_container_path(p) for p in scene_paths]

    out_host = Path(output_path)
    if not out_host.is_absolute():
        out_host = Path(OUTPUT_HOST_DIR) / out_host
    out_abs = Path(to_container_path(str(out_host)))
    out_abs.parent.mkdir(parents=True, exist_ok=True)

    if not shutil.which("ffmpeg"):
        return {"ok": False, "error": "ffmpeg not found on PATH"}

    concat_file = out_abs.parent / "_concat_list.txt"
    with open(concat_file, "w") as f:
        for sp in container_scenes:
            p = Path(sp)
            if not p.exists():
                return {"ok": False, "error": f"scene file not found: {sp}"}
            f.write(f"file '{p.resolve()}'\n")

    cmd = ["ffmpeg", "-y", "-f", "concat", "-safe", "0",
           "-i", str(concat_file), "-c", "copy", str(out_abs)]
    proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if proc.returncode != 0:
        return {"ok": False, "error": f"ffmpeg failed: {proc.stderr[-800:]}"}
    return {"ok": True, "output_path": to_host_path(str(out_abs)), "scenes": len(scene_paths)}