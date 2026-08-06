#!/usr/bin/env bash
# scripts/demo_aurora.sh — render the "Aurora" example script through the MCP server
# (same flow an OpenCode agent runs: health_check -> submit_scene x2 -> wait -> compose_final).
# Usage: MODELS_DIR=/var/tmp/minimax/models ./scripts/demo_aurora.sh   (log to demo_aurora.log)
set -u
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
if [ -f "$ROOT/scripts/config.sh" ]; then
    # shellcheck disable=SC1091
    source "$ROOT/scripts/config.sh"
fi

echo "== Demo: Aurora script via MCP =="
if [ ! -d "$ROOT/.venv" ] && command -v uv >/dev/null 2>&1; then
    (cd "$ROOT" && uv sync >/dev/null 2>&1)
fi

uv run --project "$ROOT" python - "$ROOT" <<'PY' || exit 1
import asyncio, json, os, sys, time
root = sys.argv[1]

from fastmcp import Client
from fastmcp.client.transports import StdioTransport

SCENES = [
    {
        "prompt": ("Extreme macro shot of the ocean surface at sunrise. Slow-motion saltwater "
                   "droplets lift and freeze mid-air as golden first light pierces the mist. "
                   "Shallow depth of field, sun glint bokeh, 24fps film look. Ambient audio: calm "
                   "ocean waves, soft lapping, a distant celesta note rising."),
        "duration": 6.0, "width": 960, "height": 544, "seed": 2101,
        "filename_prefix": "aurora/scene1_ocean",
    },
    {
        "prompt": ("Wide landscape of a snow-covered mountain range under a slowly rippling green "
                   "aurora borealis. Stars visible above, light wind spiraling fresh snow across "
                   "the ridge. Audio swells: strong wind, deep bass, soft rising harmonics."),
        "duration": 6.0, "width": 960, "height": 544, "seed": 2102,
        "filename_prefix": "aurora/scene2_aurora",
    },
]

async def main() -> int:
    env = dict(os.environ)
    env.setdefault("MODELS_DIR", "/var/tmp/minimax/models")
    t = StdioTransport(command="uv",
                       args=["run", "--project", root, "python", "src/minimax_mcp/server.py"],
                       cwd=root, env=env)
    async with Client(t) as client:
        h = await client.call_tool("health_check", {})
        hd = json.loads(h.content[0].text)
        print(f"[health] ok={hd.get('ok')}", flush=True)
        if not hd.get("ok"):
            return 1

        prompt_ids = []
        for i, sc in enumerate(SCENES):
            r = await client.call_tool("submit_scene", sc)
            rd = json.loads(r.content[0].text)
            if not rd.get("ok"):
                print(f"[scene{i}] submit FAILED: {json.dumps(rd)[:300]}", flush=True)
                return 1
            prompt_ids.append(rd["prompt_id"])
            print(f"[scene{i}] submitted {rd['prompt_id']} seed={rd['seed']} len~{sc['duration']}s", flush=True)

        paths = []
        for i, pid in enumerate(prompt_ids):
            print(f"[scene{i}] rendering... (up to 30 min)", flush=True)
            r = await client.call_tool("wait_for_video", {"prompt_id": pid, "timeout": 2400})
            rd = json.loads(r.content[0].text)
            if not rd.get("ok") or not rd.get("output_path"):
                print(f"[scene{i}] render FAILED: {json.dumps(rd)[:400]}", flush=True)
                return 1
            paths.append(rd["output_path"])
            print(f"[scene{i}] done -> {rd['output_path']}", flush=True)

        final = os.path.join(root, "output", f"aurora_final_{int(time.time())}.mp4")
        r = await client.call_tool("compose_final", {"scene_paths": paths, "output_path": final})
        rd = json.loads(r.content[0].text)
        if not rd.get("ok"):
            print(f"[final] compose FAILED: {json.dumps(rd)[:400]}", flush=True)
            return 1
        print(f"[final] -> {final} ({os.path.getsize(final)//1024} KB, {rd.get('scenes')} scenes)", flush=True)
        print("[PASS] Aurora demo complete", flush=True)
        return 0

sys.exit(asyncio.run(main()))
PY
