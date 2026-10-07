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

import os

# submit_scene_core acquires the shared GPU lock for real (ComfyUIClient is
# mocked below, but gpu_lock isn't) -- isolated dir so this never contends
# with a real render or insta_kb's ig-worker for ~/.gpu-lock.
os.environ.setdefault("GPU_LOCK_DIR", tempfile.mkdtemp())

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

    # The model is FL2VA: First-LAST frame to Video+Audio. Both anchors are
    # optional and independent, and supplying both is the whole point -- a
    # chapter that must LAND on a chosen frame decelerates into the cut instead
    # of being chopped wherever it drifted to. They need separate LoadImage
    # nodes: one shared node would make the second anchor overwrite the first.
    if "first_frame" not in h3 and "last_frame" not in h3:
        ok("inject_scene wires neither anchor when neither is given")
    else:
        bad(f"inject_scene invented an anchor: {h3!r}")

    both = core.inject_scene(
        wf, prompt="p", duration=5.0, width=512, height=320,
        seed=99, filename_prefix="unit/core",
        first_frame="a.png", last_frame="b.png",
    )
    bh3 = both.get(core.H3_NODE_ID, {}).get("inputs", {})
    if bh3.get("first_frame") == [core.LOAD_IMAGE_NODE_ID, 0] and \
       bh3.get("last_frame") == [core.LOAD_LAST_IMAGE_NODE_ID, 0]:
        ok("inject_scene wires both anchors to their own LoadImage nodes")
    else:
        bad(f"inject_scene anchors = {bh3.get('first_frame')!r} / {bh3.get('last_frame')!r}")
    if core.LOAD_IMAGE_NODE_ID != core.LOAD_LAST_IMAGE_NODE_ID:
        ok("the two anchors use distinct node ids")
    else:
        bad("first_frame and last_frame share a node id -- one would clobber the other")
    imgs = (both.get(core.LOAD_IMAGE_NODE_ID, {}).get("inputs", {}).get("image"),
            both.get(core.LOAD_LAST_IMAGE_NODE_ID, {}).get("inputs", {}).get("image"))
    if imgs == ("a.png", "b.png"):
        ok("each LoadImage node carries its own image name")
    else:
        bad(f"LoadImage images = {imgs!r}")

    only_last = core.inject_scene(
        wf, prompt="p", duration=5.0, width=512, height=320,
        seed=99, filename_prefix="unit/core", last_frame="b.png",
    )
    lh3 = only_last.get(core.H3_NODE_ID, {}).get("inputs", {})
    if lh3.get("last_frame") == [core.LOAD_LAST_IMAGE_NODE_ID, 0] and "first_frame" not in lh3:
        ok("last_frame alone works without a first_frame (L2VA)")
    else:
        bad(f"last_frame alone = {lh3.get('last_frame')!r}, first_frame = {lh3.get('first_frame')!r}")

print("== unit_core: submit_scene_core ==")
# submit_scene_core/wait_for_video_core are tested here for their OWN logic
# (workflow patching, error shapes, output resolution) -- the GPU-lock
# acquire/release pairing has its own dedicated coverage in
# unit_gpu_lock.py. Mocked (not just isolated via GPU_LOCK_DIR) because
# several submit_scene_core calls below never reach a matching
# wait_for_video_core call in this script -- with the real lock, the
# second successful submit would deadlock waiting for the first's token,
# which nothing here ever releases.
mock.patch.object(core, "gpu_acquire", lambda holder, timeout=300: "unit-test-token").start()
mock.patch.object(core, "gpu_release", lambda token: None).start()

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

with mock.patch.object(core, "ComfyUIClient") as m:
    # Upload happens before the workflow is patched, because ComfyUI
    # de-duplicates names: only it knows what the file ended up being called.
    # Both anchors go through it, and the NAMES IT RETURNS are what gets wired.
    client = m.return_value
    client.submit.return_value = "pid-2"
    client.upload_image.side_effect = lambda p: "uploaded_" + p
    result = core.submit_scene_core("p", seed=2, first_frame="a.png", last_frame="b.png")
    if result.get("first_frame") == "uploaded_a.png" and result.get("last_frame") == "uploaded_b.png":
        ok("submit_scene_core uploads both anchors and reports the stored names")
    else:
        bad(f"submit_scene_core anchors = {result.get('first_frame')!r} / {result.get('last_frame')!r}")
    wired = client.submit.call_args[0][0][core.H3_NODE_ID]["inputs"]
    if wired.get("first_frame") and wired.get("last_frame"):
        ok("both anchors reach the submitted workflow, not just the first")
    else:
        bad(f"submitted workflow anchors = {wired.get('first_frame')!r} / {wired.get('last_frame')!r}")

    # An upload that fails has to say WHICH anchor failed: with two of them,
    # "upload failed" alone leaves the caller guessing which path is wrong.
    client.upload_image.side_effect = RuntimeError("no such file")
    result = core.submit_scene_core("p", seed=3, last_frame="missing.png")
    if not result.get("ok") and result.get("anchor") == "last_frame" and result.get("stage") == "upload":
        ok("a failed upload names the anchor that failed")
    else:
        bad(f"upload failure result = {result!r}")

with mock.patch.object(core, "ComfyUIClient") as m, \
     mock.patch.object(core, "gpu_release") as release_spy:
    # client.submit posts over httpx -- a connection error/timeout isn't
    # wrapped as ComfyUIError (only HTTP-status/body errors are), so this
    # exercises the plain `except Exception` path, not the ComfyUIError one
    # above. Without it the GPU lock leaked forever on a network glitch,
    # with nothing actually running on the GPU (review finding, 2026-10-07).
    client = m.return_value
    client.submit.side_effect = ConnectionError("network blip")
    try:
        core.submit_scene_core("p", seed=4)
        bad("submit_scene_core swallowed a non-ComfyUIError exception")
    except ConnectionError:
        if release_spy.call_count == 1:
            ok("a non-ComfyUIError submit failure still releases the GPU lock")
        else:
            bad(f"gpu_release call_count = {release_spy.call_count}, expected 1")

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

print("== unit_core: queue snapshot + progress bar ==")
from minimax_mcp.comfyui_client import queue_snapshot_from
from minimax_mcp.core import progress_bar

_Q = {
    "queue_running": [[0, "aaa", {"5": {"inputs": {"width": 512, "height": 320}},
                                  "14": {"inputs": {"filename_prefix": "showcase/01_plane"}}}]],
    "queue_pending": [[1, "bbb", {"14": {"inputs": {"filename_prefix": "e2e_123/scene_0"}}}],
                      [2, "ccc", {}]],
}
snap = queue_snapshot_from(_Q)
if [j["prompt_id"] for j in snap["running"]] == ["aaa"]:
    ok("snapshot separates the running job")
else:
    bad(f"running = {snap['running']}")
if [j["prompt_id"] for j in snap["pending"]] == ["bbb", "ccc"]:
    ok("snapshot keeps pending jobs in queue order")
else:
    bad(f"pending = {snap['pending']}")
if snap["running"][0]["filename_prefix"] == "showcase/01_plane":
    ok("snapshot pulls the output prefix, so a job is identifiable")
else:
    bad(f"prefix = {snap['running'][0].get('filename_prefix')}")
if snap["pending"][1]["filename_prefix"] is None:
    ok("a job with no recognisable prefix yields None, not a crash")
else:
    bad("missing prefix should be None")
if snap["total"] == 3:
    ok("snapshot totals running + pending")
else:
    bad(f"total = {snap['total']}")
if queue_snapshot_from({})["total"] == 0:
    ok("an empty queue payload is handled")
else:
    bad("empty payload should total 0")

# The bar is what a human reads; keep it pure so it is testable.
if progress_bar(0, 20, width=10) == "[          ]   0%":
    ok("progress_bar at zero")
else:
    bad(f"bar(0,20) = {progress_bar(0, 20, width=10)!r}")
if progress_bar(20, 20, width=10) == "[##########] 100%":
    ok("progress_bar at full")
else:
    bad(f"bar(20,20) = {progress_bar(20, 20, width=10)!r}")
if progress_bar(10, 20, width=10) == "[#####     ]  50%":
    ok("progress_bar at half")
else:
    bad(f"bar(10,20) = {progress_bar(10, 20, width=10)!r}")
# Division by zero is the obvious way this crashes in the wild.
if progress_bar(0, 0, width=10) == "[          ]   0%":
    ok("progress_bar tolerates max=0")
else:
    bad(f"bar(0,0) = {progress_bar(0, 0, width=10)!r}")

print("== unit_core: sampler steps are tunable ==")
from minimax_mcp.core import SCHEDULER_NODE_ID

_wf_default = _inject(_WF, prompt="p", duration=5.0, width=512, height=320,
                      seed=1, filename_prefix="x")
if _wf_default[SCHEDULER_NODE_ID]["inputs"]["steps"] == 20:
    ok("default stays at 20 steps")
else:
    bad(f"default steps = {_wf_default[SCHEDULER_NODE_ID]['inputs']['steps']}")

_wf_40 = _inject(_WF, prompt="p", duration=5.0, width=512, height=320,
                 seed=1, filename_prefix="x", steps=40)
if _wf_40[SCHEDULER_NODE_ID]["inputs"]["steps"] == 40:
    ok("steps=40 reaches the scheduler node")
else:
    bad(f"steps=40 produced {_wf_40[SCHEDULER_NODE_ID]['inputs']['steps']}")

# The workflow on disk had steps hardcoded and nothing could change it; make
# sure tuning one render does not mutate the shared workflow.
if _WF[SCHEDULER_NODE_ID]["inputs"]["steps"] == 20:
    ok("tuning steps does not mutate the source workflow")
else:
    bad("inject_scene mutated the workflow's step count")

print("== unit_core: execution errors explain themselves ==")
from minimax_mcp.comfyui_client import describe_execution_error

_OOM = {"status_str": "error", "messages": [
    ["execution_start", {"prompt_id": "x"}],
    ["execution_error", {"node_id": "10", "node_type": "SamplerCustomAdvanced",
                         "exception_type": "torch.OutOfMemoryError",
                         "exception_message": "Allocation on device \n\nThis error means..."}],
]}
_msg = describe_execution_error(_OOM)
# The three resolution tests all died of this and were reported two different
# ways, which cost an investigation into a bug that did not exist.
if "out of GPU memory" in _msg and "SamplerCustomAdvanced" in _msg:
    ok("an OOM says it is an OOM, and where")
else:
    bad(f"OOM described as: {_msg!r}")
if "resolution" in _msg or "shorten" in _msg:
    ok("the OOM message says what to do about it")
else:
    bad("OOM message offers no remedy")

# The same failure arrives in two shapes depending on which branch catches it.
_direct = {"node_id": "10", "node_type": "VAEDecode",
           "exception_type": "RuntimeError", "exception_message": "boom\nsecond line"}
if describe_execution_error(_direct) == "RuntimeError in VAEDecode: boom":
    ok("a bare execution_error payload is described the same way")
else:
    bad(f"direct payload: {describe_execution_error(_direct)!r}")

if describe_execution_error({"status_str": "error"}):
    ok("an unrecognised payload still returns something rather than crashing")
else:
    bad("empty description for an unknown payload")

print()
if FAIL:
    print(f"FAIL: {FAIL}")
    sys.exit(1)
print("ALL PASS")
