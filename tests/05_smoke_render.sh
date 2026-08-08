#!/usr/bin/env bash
# tests/05_smoke_render.sh — POST /prompt a short clip through the real pipeline,
# wait for completion, then verify the .mp4 has a video stream AND stereo audio.
# Uses the MCP server's inject_scene() + ComfyUIClient so it tests the real code path.
set -u
FAIL=0
if [ -f "$(dirname "${BASH_SOURCE[0]}")/../scripts/config.sh" ]; then
    # shellcheck disable=SC1091
    source "$(dirname "${BASH_SOURCE[0]}")/../scripts/config.sh"
fi
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PROJ="$ROOT"
OUTPUT_DIR="${OUTPUT_DIR:-$ROOT/output}"

echo "== Smoke render (short clip, real pipeline) =="

# --- do not jump somebody's render queue ------------------------------------
# shellcheck disable=SC1091
source "$(dirname "${BASH_SOURCE[0]}")/lib_queue.sh"
skip() { echo "  [SKIP] $1"; exit 78; }
wait_for_idle_queue || skip "render queue still busy after ${CI_QUEUE_WAIT_SECONDS:-600}s — the GPU is in use, not broken"


if [ ! -f "$WORKFLOW" ]; then
    echo "  [MISS] workflow not found: $WORKFLOW"
    exit 1
fi
if ! command -v ffprobe >/dev/null 2>&1; then
    echo "  [MISS] ffprobe not installed (needed to verify audio/video streams)"
    exit 1
fi

SMOKE_DIR="$OUTPUT_DIR/smoke"
mkdir -p "$SMOKE_DIR"

PYTHON="python3"
if command -v uv >/dev/null 2>&1 && [ -f "$ROOT/pyproject.toml" ]; then
    PYTHON="uv run --project $ROOT python"
fi

$PYTHON - "$WORKFLOW" "$SMOKE_DIR" <<'PY' || FAIL=1
import json, os, sys, time
from pathlib import Path

workflow_path, smoke_dir = sys.argv[1], sys.argv[2]
root = os.path.dirname(os.path.dirname(os.path.abspath(workflow_path)))
sys.path.insert(0, os.path.join(root, "src"))

# These live in core, not server: importing from server also pulls the whole
# FastMCP tool registry, which this smoke test does not need.
from minimax_mcp.core import inject_scene, load_workflow  # noqa: E402
from minimax_mcp.comfyui_client import ComfyUIClient  # noqa: E402

# Low-res short smoke clip: 512x320 (multiple of 32), 5s -> 124 frames on the 17k+5 grid.
prefix = os.path.join("smoke", f"smoke_{int(time.time())}")
wf = inject_scene(
    load_workflow(),
    prompt="a hungry black cat staring at an empty food bowl, close-up, soft kitchen daylight, faint meow",
    duration=5.0, width=512, height=320, seed=42, filename_prefix=prefix,
)

client = ComfyUIClient(os.environ.get("COMFYUI_URL", "http://127.0.0.1:8188"), timeout=60)

try:
    prompt_id = client.submit(wf)
except Exception as e:
    print(f"  [BAD] submit failed: {e}")
    sys.exit(1)
print(f"  [ok]   submitted prompt_id={prompt_id}")

import asyncio
try:
    hist = asyncio.run(client.wait_for_execution(prompt_id, timeout=1800))
except Exception as e:
    print(f"  [BAD] render failed: {e}")
    sys.exit(1)

out = client.resolve_output(hist, os.environ.get("OUTPUT_DIR", os.path.join(os.path.dirname(workflow_path), "..", "output")))
if not out:
    print("  [BAD] no .mp4 in history outputs")
    sys.exit(1)
print(f"  [ok]   rendered -> {out}")

import subprocess
res = subprocess.run(["ffprobe", "-v", "error", "-show_streams", "-of", "json", out],
                     capture_output=True, text=True)
if res.returncode != 0:
    print("  [BAD] ffprobe failed:", res.stderr[:400])
    sys.exit(1)
streams = json.loads(res.stdout)["streams"]
kinds = {s["codec_type"] for s in streams}
if "video" not in kinds:
    print("  [BAD] no video stream"); sys.exit(1)
audio = [s for s in streams if s["codec_type"] == "audio"]
if not audio:
    print("  [BAD] no audio stream (H3 should produce native stereo audio)")
    sys.exit(1)
ch = audio[0].get("channels")
print(f"  [ok]   video stream present; audio: {ch} ch ({audio[0].get('codec_name')})")
if ch != 2:
    print("  [WARN] expected stereo (2ch), got", ch)
else:
    print("  [ok]   stereo audio confirmed (2ch)")
PY

exit "$FAIL"
