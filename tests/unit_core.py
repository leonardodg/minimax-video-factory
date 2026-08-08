#!/usr/bin/env python3
"""Pure-logic unit tests for minimax_mcp.core — no ComfyUI, no GPU, no network.

Run: uv run --directory . python tests/unit_core.py
Exit 0 = all pass. Any failure prints [BAD] and exits non-zero.
"""
import sys
import tempfile
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

FAIL = 0


def ok(label: str) -> None:
    print(f"  [ok]   {label}")


def bad(label: str) -> None:
    global FAIL
    FAIL += 1
    print(f"  [BAD]  {label}")


print("== unit_core: duration_to_frames ==")
from minimax_mcp import core

CASES = {5.0: 124, 10.0: 243, 1.0: 39, 15.0: 362, 0.5: 22}
for dur, expect in CASES.items():
    got = core.duration_to_frames(dur)
    if got == expect:
        ok(f"duration_to_frames({dur}) = {got}")
    else:
        bad(f"duration_to_frames({dur}) = {got}, expected {expect}")

print("== unit_core: inject_scene ==")
wf_path = ROOT / "workflows" / "minimax_h3_t2v_api.json"
if not wf_path.exists():
    bad(f"workflow not found: {wf_path}")
else:
    import json
    wf = json.loads(wf_path.read_text())
    patched = core.inject_scene(
        wf, prompt="p", duration=5.0, width=512, height=320,
        seed=99, filename_prefix="unit/core",
    )
    h3 = patched.get(core.H3_NODE_ID, {}).get("inputs", {})
    if h3.get("prompt") == "p" and h3.get("length") == 124:
        ok("inject_scene patches prompt + length (duration_to_frames)")
    else:
        bad(f"inject_scene H3 inputs = {h3!r}")
    noise = patched.get(core.NOISE_NODE_ID, {}).get("inputs", {})
    if noise.get("noise_seed") == 99:
        ok("inject_scene patches noise_seed")
    else:
        bad(f"inject_scene noise = {noise!r}")
    if wf[core.H3_NODE_ID]["inputs"].get("prompt") != "p":
        ok("inject_scene does not mutate the original workflow (deepcopy)")
    else:
        bad("inject_scene mutated the original workflow")

print("== unit_core: submit_scene_core ==")
with mock.patch.object(core, "ComfyUIClient") as m:
    client = m.return_value
    client.submit.return_value = "pid-1"
    result = core.submit_scene_core("prompt x", duration=5.0, width=512, height=320, seed=7, filename_prefix="u/")
    if result.get("ok") and result.get("prompt_id") == "pid-1" and result.get("seed") == 7:
        ok("submit_scene_core returns ok + prompt_id + seed")
    else:
        bad(f"submit_scene_core result = {result!r}")
    if client.submit.call_count == 1:
        ok("client.submit called once with the injected workflow")
    else:
        bad(f"client.submit call_count = {client.submit.call_count}")

    client.submit.side_effect = core.ComfyUIError("boom")
    result = core.submit_scene_core("p", seed=1)
    if not result.get("ok") and "boom" in result.get("error", ""):
        ok("submit_scene_core converts ComfyUIError to {ok:False, error}")
    else:
        bad(f"submit_scene_core error result = {result!r}")

print("== unit_core: wait_for_video_core ==")
async def run_wait():
    with mock.patch.object(core, "ComfyUIClient") as m:
        client = m.return_value
        client.wait_for_execution = mock.AsyncMock(
            return_value={"outputs": {"images": [{"filename": "a_00001_.mp4"}]}}
        )
        client.resolve_output.return_value = "/comfy/ComfyUI/output/a_00001_.mp4"
        return await core.wait_for_video_core("pid-2", timeout=10)

import asyncio

res = asyncio.run(run_wait())
if res.get("ok") and res.get("output_path") and res.get("prompt_id") == "pid-2":
    ok("wait_for_video_core returns ok + output_path + prompt_id")
else:
    bad(f"wait_for_video_core result = {res!r}")

print("== unit_core: compose_final_core ==")
with tempfile.TemporaryDirectory() as td:
    tmp = Path(td)
    a, b = tmp / "a.mp4", tmp / "b.mp4"
    a.write_bytes(b"x")
    b.write_bytes(b"y")
    out = tmp / "out" / "final.mp4"

    with mock.patch.object(core, "subprocess") as sp:
        sp.run.return_value = mock.MagicMock(returncode=0, stderr="")
        result = core.compose_final_core([str(a), str(b)], output_path=str(out))
        if result.get("ok") and result.get("scenes") == 2 and result.get("output_path"):
            ok("compose_final_core returns ok + scenes count + output_path")
        else:
            bad(f"compose_final_core result = {result!r}")

    result = core.compose_final_core([str(a)], output_path=str(out))
    if not result.get("ok") and "at least 2" in result.get("error", ""):
        ok("compose_final_core rejects < 2 scenes")
    else:
        bad(f"compose_final_core 1-scene result = {result!r}")

    missing = tmp / "nope.mp4"
    with mock.patch.object(core, "subprocess") as sp:
        sp.run.return_value = mock.MagicMock(returncode=0, stderr="")
        result = core.compose_final_core([str(a), str(missing)], output_path=str(out))
        if not result.get("ok") and "not found" in result.get("error", ""):
            ok("compose_final_core fails soft on a missing scene file")
        else:
            bad(f"compose_final_core missing-file result = {result!r}")

print()
if FAIL:
    print(f"FAIL: {FAIL}")
    sys.exit(1)
print("PASS")

print("== unit_core: queue state (get_status must not call a running render 'queued') ==")
from minimax_mcp.comfyui_client import queue_state_from

# Shape of ComfyUI's /queue: [queue_index, prompt_id, workflow, extra, outputs]
QUEUE = {
    "queue_running": [[0, "aaa-running", {}, {}, []]],
    "queue_pending": [[1, "bbb-pending", {}, {}, []], [2, "ccc-pending", {}, {}, []]],
}

if queue_state_from(QUEUE, "aaa-running") == "running":
    ok("a prompt in queue_running reports 'running'")
else:
    bad(f"running prompt reported {queue_state_from(QUEUE, 'aaa-running')!r}")

if queue_state_from(QUEUE, "bbb-pending") == "pending":
    ok("a prompt in queue_pending reports 'pending'")
else:
    bad(f"pending prompt reported {queue_state_from(QUEUE, 'bbb-pending')!r}")

if queue_state_from(QUEUE, "zzz-unknown") is None:
    ok("a prompt in neither list reports None")
else:
    bad(f"unknown prompt reported {queue_state_from(QUEUE, 'zzz-unknown')!r}")

if queue_state_from({}, "anything") is None:
    ok("an empty queue payload does not raise")
else:
    bad("empty queue payload should yield None")

# Malformed entries must not take the tool down: this runs while the user is
# staring at something that looks stuck, which is the worst time to crash.
if queue_state_from({"queue_running": [[0], "garbage", None]}, "x") is None:
    ok("malformed queue entries are tolerated")
else:
    bad("malformed queue entries should yield None")

print("== unit_core: list_outputs relpath ==")
from minimax_mcp.core import output_relpath

if output_relpath(Path("/out/e2e_123/scene_0.mp4"), Path("/out")) == "e2e_123/scene_0.mp4":
    ok("relpath keeps the subfolder that tells two scene_0 files apart")
else:
    bad(f"relpath = {output_relpath(Path('/out/e2e_123/scene_0.mp4'), Path('/out'))!r}")

if output_relpath(Path("/out/top.mp4"), Path("/out")) == "top.mp4":
    ok("a file at the root of the output dir keeps its bare name")
else:
    bad("relpath wrong for a top-level file")

# A path outside the output dir must degrade, not raise.
if output_relpath(Path("/elsewhere/x.mp4"), Path("/out")) == "x.mp4":
    ok("a path outside the output dir falls back to the bare name")
else:
    bad(f"relpath outside root = {output_relpath(Path('/elsewhere/x.mp4'), Path('/out'))!r}")

print("== unit_core: first_frame (image-conditioned generation) ==")
import json as _json

from minimax_mcp.core import LOAD_IMAGE_NODE_ID
from minimax_mcp.core import inject_scene as _inject

_WF = _json.loads(Path(ROOT / "workflows" / "minimax_h3_t2v_api.json").read_text())

# Without an image the workflow must be exactly what it always was: the H3 node
# is an ImageToVideo node whose first_frame is optional, and text-only
# generation is still the common case.
_no_img = _inject(_WF, prompt="p", duration=5.0, width=512, height=320,
                  seed=1, filename_prefix="x")
if "first_frame" not in _no_img["5"]["inputs"]:
    ok("no first_frame: the H3 node keeps no image input")
else:
    bad("first_frame leaked into a text-only workflow")
if LOAD_IMAGE_NODE_ID not in _no_img:
    ok("no first_frame: no LoadImage node is added")
else:
    bad("a LoadImage node was added without an image")

_img = _inject(_WF, prompt="p", duration=5.0, width=512, height=320,
               seed=1, filename_prefix="x", first_frame="ref_shot.png")
loader = _img.get(LOAD_IMAGE_NODE_ID)
if loader and loader["class_type"] == "LoadImage":
    ok("with first_frame: a LoadImage node is added")
else:
    bad(f"LoadImage node missing: {loader!r}")

if loader and loader["inputs"]["image"] == "ref_shot.png":
    ok("LoadImage points at the uploaded filename")
else:
    bad(f"LoadImage.image = {loader['inputs']['image'] if loader else None!r}")

if _img["5"]["inputs"].get("first_frame") == [LOAD_IMAGE_NODE_ID, 0]:
    ok("H3 first_frame is wired to the LoadImage output")
else:
    bad(f"first_frame wiring = {_img['5']['inputs'].get('first_frame')!r}")

# inject_scene deep-copies, so the original on disk must be untouched.
if "first_frame" not in _WF["5"]["inputs"] and LOAD_IMAGE_NODE_ID not in _WF:
    ok("the source workflow dict is not mutated")
else:
    bad("inject_scene mutated the workflow it was given")

# The chosen node id must not collide with the 14 nodes already there.
if LOAD_IMAGE_NODE_ID not in _WF:
    ok(f"node id {LOAD_IMAGE_NODE_ID!r} does not collide with the base workflow")
else:
    bad(f"node id {LOAD_IMAGE_NODE_ID!r} already exists in the workflow")

print()
if FAIL:
    print(f"FAIL: {FAIL}")
    sys.exit(1)
print("ALL PASS")
