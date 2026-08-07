#!/usr/bin/env python3
"""Pure-logic unit tests for minimax_mcp.server — no GPU, no ComfyUI, no container.

Run:  uv run --project . python tests/unit_pure.py   (or host python3 with deps)
Covers: duration_to_frames, inject_scene (workflow patching), path mapping.
Exit 0 = all pass. Any failure prints [BAD] and exits non-zero.
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from minimax_mcp import server
from minimax_mcp.core import duration_to_frames, inject_scene

FAIL = 0


def ok(label: str) -> None:
    print(f"  [ok]   {label}")


def bad(label: str) -> None:
    global FAIL
    FAIL += 1
    print(f"  [BAD]  {label}")


print("== unit_pure: duration_to_frames ==")
# 5s -> 124 frames, 10s -> 243 (from AGENTS.md / ComfyMathExpression)
CASES = {5.0: 124, 10.0: 243, 1.0: 39, 15.0: 362}
for dur, expect in CASES.items():
    got = duration_to_frames(dur)
    if got == expect:
        ok(f"duration_to_frames({dur}) = {got}")
    else:
        bad(f"duration_to_frames({dur}) = {got}, expected {expect}")

print("== unit_pure: inject_scene (workflow patching) ==")
wf_path = ROOT / "workflows" / "minimax_h3_t2v_api.json"
if not wf_path.exists():
    bad(f"workflow not found: {wf_path}")
else:
    wf = json.loads(wf_path.read_text())
    patched = inject_scene(
        wf,
        prompt="test prompt",
        duration=5.0,
        width=512,
        height=320,
        seed=12345,
        filename_prefix="unit/scene",
    )
    # loader nodes patched to configured model set
    loaders = {
        "1": ("UNETLoader", "unet_name", server.DIFFUSION_MODEL),
        "2": ("CLIPLoader", "clip_name", server.TEXT_ENCODER),
        "3": ("VAELoader", "vae_name", server.VIDEO_VAE),
        "4": ("VAELoader", "vae_name", server.AUDIO_VAE),
    }
    for nid, (cls, key, value) in loaders.items():
        node = patched.get(nid)
        if node is None or node.get("class_type") != cls:
            bad(f"node {nid}: missing class_type {cls}")
        elif node["inputs"].get(key) != value:
            bad(f"node {nid}: {key}={node['inputs'].get(key)!r}, expected {value!r}")
        else:
            ok(f"node {nid} ({cls}) -> {key}={value}")
    h3 = patched.get(server.H3_NODE_ID)
    if h3 is None or h3.get("class_type") != "MiniMaxH3ImageToVideo":
        bad(f"H3 node {server.H3_NODE_ID} missing/renamed")
    else:
        inp = h3["inputs"]
        checks = {
            "prompt": "test prompt",
            "width": 512,
            "height": 320,
            "length": 124,
        }
        for k, v in checks.items():
            if inp.get(k) != v:
                bad(f"H3 {k}={inp.get(k)!r}, expected {v!r}")
            else:
                ok(f"H3 {k}={v}")
    noise = patched.get(server.NOISE_NODE_ID)
    if noise is not None and noise.get("inputs", {}).get("noise_seed") == 12345:
        ok("noise_seed injected")
    else:
        bad("noise_seed not injected")
    save = [n for n in patched.values() if n.get("class_type") == "SaveVideo"]
    if save and save[0]["inputs"].get("filename_prefix") == "unit/scene":
        ok("SaveVideo filename_prefix injected")
    else:
        bad("SaveVideo filename_prefix not injected")
    # original workflow not mutated (deepcopy)
    if wf[server.H3_NODE_ID]["inputs"].get("prompt") != "test prompt":
        ok("original workflow not mutated (deepcopy)")
    else:
        bad("original workflow was mutated!")

print("== unit_pure: path mapping ==")
# with OUTPUT_HOST_DIR == OUTPUT_DIR, mapping is identity
server.OUTPUT_HOST_DIR = str(server.OUTPUT_DIR)
if server.to_host_path("/x/y.mp4") == "/x/y.mp4":
    ok("to_host_path identity when host==container")
else:
    bad("to_host_path identity broken")
# simulate container (OUTPUT_DIR=/comfy/... output, host=.../output)
server.OUTPUT_DIR = Path("/comfy/ComfyUI/output")
server.OUTPUT_HOST_DIR = "/srv/minimax/output"
hp = server.to_host_path("/comfy/ComfyUI/output/scene_0.mp4")
if hp == "/srv/minimax/output/scene_0.mp4":
    ok("to_host_path maps container -> host")
else:
    bad(f"to_host_path: {hp}")
cp = server.to_container_path("/srv/minimax/output/scene_0.mp4")
if cp == "/comfy/ComfyUI/output/scene_0.mp4":
    ok("to_container_path maps host -> container")
else:
    bad(f"to_container_path: {cp}")

print()
if FAIL:
    print(f"FAIL: {FAIL}")
    sys.exit(1)
print("PASS")
