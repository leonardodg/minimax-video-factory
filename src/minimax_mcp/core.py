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
from minimax_mcp.gpu_lock import acquire as gpu_acquire
from minimax_mcp.gpu_lock import release as gpu_release

load_dotenv()

logger = logging.getLogger(__name__)

# ---------------- config ----------------
PROJECT_ROOT = Path(__file__).resolve().parents[2]
COMFYUI_URL = os.environ.get("COMFYUI_URL", "http://127.0.0.1:8188")
WORKFLOW_PATH = Path(os.environ.get("WORKFLOW_PATH", PROJECT_ROOT / "workflows" / "minimax_h3_t2v_api.json"))
# Same graph with the MiniMax-H3 Turbo LoRA spliced in (node 15) and the stock
# KSamplerSelect swapped for MiniMaxH3TurboSampler. Node ids 1..14 are unchanged,
# so inject_scene patches both workflows with the same code.
TURBO_WORKFLOW_PATH = Path(os.environ.get(
    "TURBO_WORKFLOW_PATH", PROJECT_ROOT / "workflows" / "minimax_h3_t2v_turbo_api.json"))
OUTPUT_DIR = Path(os.environ.get("OUTPUT_DIR", PROJECT_ROOT / "output"))
OUTPUT_HOST_DIR = os.environ.get("OUTPUT_HOST_DIR") or str(OUTPUT_DIR)
OUTPUT_PREFIX = os.environ.get("OUTPUT_PREFIX", "video/factory")
H3_NODE_ID = "5"
NOISE_NODE_ID = "6"
SAVE_NODE_CLASS = "SaveVideo"
# The base workflow ships 14 nodes numbered 1..14. A LoadImage node is added
# only when a first_frame is supplied, under an id well clear of that range so
# it can never collide as the workflow grows. last_frame gets its own id: the
# two anchors can be supplied together, so they cannot share a node.
LOAD_IMAGE_NODE_ID = "90"
LOAD_LAST_IMAGE_NODE_ID = "91"
SCHEDULER_NODE_ID = "9"          # BasicScheduler
TURBO_LORA_NODE_ID = "15"        # MiniMaxH3TurboLoRA, turbo workflow only
DEFAULT_STEPS = 20               # what the workflow ships with, and what every
                                 # render used until steps became tunable
# The turbo LoRA is distilled for 4-8 steps; its author measures 6-8 as
# noticeably better than 4 and no gain above 8. Time is linear in steps here
# (30 steps cost 1.51x of 20, i.e. fixed overhead is ~nil), so 6 steps is
# ~3.3x faster than the 20-step path.
DEFAULT_TURBO_STEPS = 6

DIFFUSION_MODEL = os.environ.get("MODEL_DIFFUSION", "minimax_h3_fl2va_pruned_int8_convrot.safetensors")
TEXT_ENCODER = os.environ.get("MODEL_TEXT_ENCODER", "qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors")
VIDEO_VAE = os.environ.get("MODEL_VIDEO_VAE", "minimax_h3_video_vae_fp16.safetensors")
AUDIO_VAE = os.environ.get("MODEL_AUDIO_VAE", "minimax_h3_audio_vae_fp32.safetensors")


# ---------------- helpers ----------------
def load_workflow(turbo: bool = False) -> dict[str, Any]:
    path = TURBO_WORKFLOW_PATH if turbo else WORKFLOW_PATH
    if not path.exists():
        raise FileNotFoundError(f"workflow not found: {path} (run scripts/ui2api.py first)")
    with open(path) as f:
        return json.load(f)


def duration_to_frames(duration: float, fps: int = 24) -> int:
    frames = max(5, round(duration * fps))
    return frames + (5 - (frames % 17)) % 17


def inject_scene(workflow: dict[str, Any], *, prompt: str, duration: float,
                 width: int, height: int, seed: int, filename_prefix: str,
                 first_frame: str | None = None,
                 last_frame: str | None = None,
                 steps: int | None = None,
                 turbo_lora: str | None = None,
                 turbo_strength: float | None = None,
                 turbo_low_vram: bool | None = None) -> dict[str, Any]:
    """Patch the API workflow for one scene.

    `first_frame` and `last_frame` are names of images already present in
    ComfyUI's input directory (upload one with ComfyUIClient.upload_image).
    Each one given adds a LoadImage node wired into the matching optional input
    of the H3 node, and the model animates from -- and to -- those pictures
    instead of inventing the whole composition from the prompt.

    The model is `minimax_h3_fl2va` -- **First-Last** frame to Video+Audio --
    and the node is MiniMaxH3ImageToVideo, so this is what it was trained for.
    Text only was leaving half of it unused; first_frame alone still left the
    other anchor unused.

    Supplying both is what makes a chapter *land* somewhere chosen: the motion
    decelerates into a known frame instead of being cut wherever it drifted to,
    which is the seam a viewer notices when clips are concatenated.
    """
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

    for anchor, image, node_id in (
        ("first_frame", first_frame, LOAD_IMAGE_NODE_ID),
        ("last_frame", last_frame, LOAD_LAST_IMAGE_NODE_ID),
    ):
        if not image:
            continue
        wf[node_id] = {
            "class_type": "LoadImage",
            "inputs": {"image": image, "upload": "image"},
        }
        inputs[anchor] = [node_id, 0]

    if steps is not None:
        sched = wf.get(SCHEDULER_NODE_ID)
        if sched is None or "steps" not in sched.get("inputs", {}):
            raise KeyError(
                f"scheduler node id '{SCHEDULER_NODE_ID}' has no steps input; "
                "adjust SCHEDULER_NODE_ID"
            )
        sched["inputs"]["steps"] = steps

    # Turbo workflow only: node 15 is the LoRA. Silently ignored on the stock
    # workflow, which has no node 15 -- so callers may always pass these.
    lora_node = wf.get(TURBO_LORA_NODE_ID)
    if lora_node is not None and lora_node.get("class_type") == "MiniMaxH3TurboLoRA":
        if turbo_lora is not None:
            lora_node["inputs"]["lora_name"] = turbo_lora
        if turbo_strength is not None:
            lora_node["inputs"]["strength"] = turbo_strength
        if turbo_low_vram is not None:
            lora_node["inputs"]["low_vram"] = turbo_low_vram

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


def progress_bar(value: float, maximum: float, width: int = 20) -> str:
    """`[#####     ]  50%` -- the part a human actually reads.

    Pure so it can be tested without a render in flight. maximum=0 yields an
    empty bar instead of dividing by zero.
    """
    try:
        ratio = 0.0 if not maximum else max(0.0, min(1.0, float(value) / float(maximum)))
    except (TypeError, ValueError, ZeroDivisionError):
        ratio = 0.0
    filled = round(ratio * width)
    return f"[{'#' * filled}{' ' * (width - filled)}] {round(ratio * 100):>3}%"


def output_relpath(path: Path, output_dir: Path) -> str:
    """Path of `path` relative to `output_dir`, or its bare name if outside it.

    list_outputs used to report only the basename, so three different runs all
    showed up as "scene_0_00001_.mp4" and there was no way to tell them apart.
    The subfolder is the only thing that distinguishes them.
    """
    try:
        return str(path.relative_to(output_dir))
    except ValueError:
        return path.name


# Tracks which prompt_id is holding which GPU-lock token between
# submit_scene_core (acquire) and wait_for_video_core (release) -- the
# actual GPU-busy window is "until ComfyUI reports this prompt done", not
# bounded by any caller's wait_seconds. A render that outlives every
# wait_for_video call this process ever receives for its prompt_id keeps
# the lock held until the next successful poll (or process restart) --
# a known, accepted gap, not a design this module can close on its own
# (see docs/HANDOFF.md, 2026-10-07).
_gpu_tokens_by_prompt: dict[str, str] = {}


def submit_scene_core(
    prompt: str,
    duration: float = 5.0,
    # 1024x576, not the 1344x768 H3 canvas maximum: the larger canvas OOMs the
    # sampler on 12 GB of VRAM. Callers with more VRAM can still pass 1344x768.
    width: int = 1024,
    height: int = 576,
    seed: int | None = None,
    filename_prefix: str = "video/factory",
    first_frame: str | None = None,
    last_frame: str | None = None,
    steps: int | None = None,
    turbo: bool = False,
    turbo_lora: str | None = None,
    turbo_strength: float | None = None,
    turbo_low_vram: bool | None = None,
) -> dict[str, Any]:
    if seed is None:
        seed = random.randint(0, 2**31 - 1)
    client = ComfyUIClient(os.environ.get("COMFYUI_URL", "http://127.0.0.1:8188"))

    # Upload before patching: ComfyUI de-duplicates names, so only it knows
    # what the image ended up being called.
    uploaded: dict[str, str | None] = {"first_frame": None, "last_frame": None}
    for anchor, path in (("first_frame", first_frame), ("last_frame", last_frame)):
        if not path:
            continue
        try:
            uploaded[anchor] = client.upload_image(path)
        except Exception as e:
            return {"ok": False, "stage": "upload", "anchor": anchor, "error": str(e)}

    try:
        workflow = load_workflow(turbo=turbo)
    except FileNotFoundError as e:
        return {"ok": False, "stage": "workflow", "error": str(e)}
    wf = inject_scene(workflow, prompt=prompt, duration=duration,
                      width=width, height=height, seed=seed,
                      filename_prefix=filename_prefix,
                      first_frame=uploaded["first_frame"],
                      last_frame=uploaded["last_frame"],
                      steps=steps, turbo_lora=turbo_lora,
                      turbo_strength=turbo_strength,
                      turbo_low_vram=turbo_low_vram)
    # This machine has one 12 GB GPU, shared with insta_kb's ig-worker
    # (Whisper transcription) -- same lock file, see minimax_mcp/gpu_lock.py.
    # Timeout matches the worst-case render in the production table
    # (CLAUDE.md): ~1300s at 103 Mpixel-frames, rounded up with headroom.
    token = gpu_acquire(f"comfyui render prompt seed={seed}", timeout=1800)
    if token is None:
        return {"ok": False, "stage": "gpu_lock", "error": "GPU busy (ig-worker transcribing), gave up after 1800s"}
    try:
        prompt_id = client.submit(wf)
    except ComfyUIError as e:
        gpu_release(token)
        return {"ok": False, "error": str(e)}
    except Exception:
        # client.submit posts over httpx; a connection error/timeout isn't
        # wrapped as ComfyUIError (only HTTP-status/body errors are), so
        # without this the lock would leak forever on a plain network
        # glitch -- with nothing actually running on the GPU (review
        # finding, 2026-10-07).
        gpu_release(token)
        raise
    _gpu_tokens_by_prompt[prompt_id] = token
    effective_steps = steps or (DEFAULT_TURBO_STEPS if turbo else DEFAULT_STEPS)
    return {"ok": True, "prompt_id": prompt_id, "seed": seed,
            "duration": duration, "width": width, "height": height,
            "first_frame": uploaded["first_frame"],
            "last_frame": uploaded["last_frame"],
            "steps": effective_steps, "turbo": turbo}


async def wait_for_video_core(prompt_id: str, timeout: float = 1200.0) -> dict[str, Any]:
    client = ComfyUIClient(COMFYUI_URL)
    try:
        rec = await client.wait_for_execution(prompt_id, timeout=timeout)
    except ComfyUIError as e:
        # A timeout here means ComfyUI hasn't reported the prompt done yet --
        # the render may still be running, so the GPU lock stays held; the
        # caller (or a later wait_for_video call) is expected to try again.
        # Any OTHER ComfyUIError means the render itself failed/errored out,
        # so the GPU is actually free again -- release it.
        if "Timed out" not in str(e):
            _release_gpu_token(prompt_id)
        return {"ok": False, "error": str(e)}
    except Exception as e:
        _release_gpu_token(prompt_id)
        return {"ok": False, "error": f"unexpected: {e}"}

    _release_gpu_token(prompt_id)
    # Resolve output path (container view) then translate to the host view for the client.
    path = client.resolve_output(rec, str(OUTPUT_DIR))
    return {"ok": path is not None, "prompt_id": prompt_id,
            "output_path": to_host_path(str(path)) if path else None, "outputs": rec.get("outputs")}


def _release_gpu_token(prompt_id: str) -> None:
    token = _gpu_tokens_by_prompt.pop(prompt_id, None)
    if token is not None:
        gpu_release(token)


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