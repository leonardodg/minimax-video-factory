#!/usr/bin/env bash
# tests/07_e2e_agent.sh — full agent flow over MCP stdio:
#   health_check -> submit_scene (2 scenes) -> wait_for_video -> list_outputs -> compose_final
set -u
FAIL=0
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
if [ -f "$ROOT/scripts/config.sh" ]; then
    # shellcheck disable=SC1091
    source "$ROOT/scripts/config.sh"
fi

# --- do not jump somebody's render queue ------------------------------------
# shellcheck disable=SC1091
source "$(dirname "${BASH_SOURCE[0]}")/lib_queue.sh"
skip() { echo "  [SKIP] $1"; exit 78; }
wait_for_idle_queue || skip "render queue still busy after ${CI_QUEUE_WAIT_SECONDS:-600}s — the GPU is in use, not broken"

echo "== E2E agent flow (MCP stdio) =="
# Client (fastmcp) runs on the host with uv; SERVER runs inside the container
# (docker exec) so the full dockerized stack is exercised. Falls back to host-uv
# server when the container is unavailable.
if [ ! -d "$ROOT/.venv" ] && command -v uv >/dev/null 2>&1; then
    (cd "$ROOT" && uv sync >/dev/null 2>&1)
fi

SERVER_MODE=container
if ! docker ps --format '{{.Names}}' 2>/dev/null | grep -q "^${COMFY_CONTAINER:-minimax-comfyui}\$"; then
    echo "  [info] container down; using host-uv server for E2E"
    SERVER_MODE=uv
fi
export SERVER_MODE

uv run --project "$ROOT" python - "$ROOT" <<'PY' || FAIL=1
import asyncio, json, os, sys, time

root = sys.argv[1]
sys.path.insert(0, os.path.join(root, "src"))
server_mode = os.environ.get("SERVER_MODE", "container")

from fastmcp import Client  # noqa: E402
from fastmcp.client.transports import StdioTransport  # noqa: E402

PREFIX = f"e2e_{int(time.time())}"

async def main() -> int:
    env = dict(os.environ)
    env["MODELS_DIR"] = env.get("MODELS_DIR", "/var/tmp/minimax/models")
    if server_mode == "container":
        transport = StdioTransport(
            command="docker",
            args=["exec", "-i", os.environ.get("COMFY_CONTAINER", "minimax-comfyui"),
                  "bash", "/workspace/scripts/mcp_runner.sh"],
            env=env,
        )
    else:
        transport = StdioTransport(
            command="uv",
            args=["run", "--project", root, "python", "src/minimax_mcp/server.py"],
            cwd=root,
            env=env,
        )
    async with Client(transport) as client:
        print("  [ok]   connected to MCP server over stdio")

        # 1. health
        h = await client.call_tool("health_check", {})
        hd = json.loads(h.content[0].text)
        if not hd.get("ok"):
            print(f"  [BAD] health_check not ok: {json.dumps(hd)[:300]}")
            return 1
        print("  [ok]   health_check: comfyui up, models present")
        print("         models:", {k: len(v) for k, v in hd["models"].items()})

        # 2. submit ONE short low-res scene.
        # One render, not two: this test proves the pipeline works end to end,
        # and a second clip costs another few minutes of GPU to prove nothing
        # the first one did not. compose_final still gets two inputs below.
        scene_ids, seeds = [], []
        for i, scene in enumerate(["a hungry black cat staring at an empty food bowl, close-up, soft light, faint meow"]):
            r = await client.call_tool("submit_scene", {
                "prompt": scene, "duration": 5.0, "width": 512, "height": 320,
                "seed": 100 + i, "filename_prefix": f"{PREFIX}/scene_{i}",
            })
            rd = json.loads(r.content[0].text)
            if not rd.get("ok"):
                print(f"  [BAD] submit_scene[{i}] failed: {json.dumps(rd)[:300]}")
                return 1
            scene_ids.append(rd["prompt_id"]); seeds.append(rd["seed"])
            print(f"  [ok]   submitted scene_{i} prompt_id={rd['prompt_id']} seed={rd['seed']}")

        # 3. wait for each
        paths = []
        for i, pid in enumerate(scene_ids):
            r = await client.call_tool("wait_for_video", {"prompt_id": pid, "timeout": 1800})
            rd = json.loads(r.content[0].text)
            if not rd.get("ok") or not rd.get("output_path"):
                print(f"  [BAD] wait_for_video[{i}] failed: {json.dumps(rd)[:400]}")
                return 1
            paths.append(rd["output_path"])
            print(f"  [ok]   scene_{i} rendered -> {rd['output_path']}")

        # 4. list_outputs
        r = await client.call_tool("list_outputs", {})
        rd = json.loads(r.content[0].text)
        if not isinstance(rd, list) or not rd:
            print("  [BAD] list_outputs empty")
            return 1
        print(f"  [ok]   list_outputs: {len(rd)} mp4 files")

        # 5. compose_final
        # Use a RELATIVE output path so the server resolves it under its own
        # OUTPUT_DIR/OUTPUT_HOST_DIR (host<->container mapping is handled server-side).
        final_rel = f"output/{PREFIX}_final.mp4"
        # compose_final refuses fewer than 2 scenes, and concatenation does not
        # care that both inputs are the same file -- so the single rendered
        # clip exercises the ffmpeg path without paying for a second render.
        compose_inputs = paths * 2 if len(paths) == 1 else paths
        r = await client.call_tool("compose_final", {"scene_paths": compose_inputs, "output_path": final_rel})
        rd = json.loads(r.content[0].text)
        if not rd.get("ok") or not rd.get("output_path") or not os.path.exists(rd["output_path"]):
            print(f"  [BAD] compose_final failed: {json.dumps(rd)[:400]}")
            return 1
        final = rd["output_path"]
        print(f"  [ok]   compose_final -> {final} ({os.path.getsize(final)//1024} KB, {rd.get('scenes')} scenes)")
        print(f"  [PASS] full E2E agent flow OK")
        return 0

try:
    sys.exit(asyncio.run(main()))
except Exception as e:  # noqa: BLE001
    print(f"  [BAD] e2e exception: {e}")
    sys.exit(1)
PY

exit "$FAIL"
