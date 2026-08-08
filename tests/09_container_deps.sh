#!/usr/bin/env bash
# tests/09_container_deps.sh — the in-container MCP venv can actually run every tool.
#
# Why this exists: the knowledge-base tools failed with "No module named
# 'pgvector'" when called through the container MCP, while passing every
# existing test. 08_knowledge.sh drives the server with `uv run` against the
# HOST venv, and 06_mcp_server.sh only checks the stdio handshake -- so nobody
# ever imported a tool's dependencies inside the image. The image had been
# built before those dependencies entered pyproject.toml and was never rebuilt.
#
# The gap is structural, not a one-off: any dependency added to pyproject.toml
# is missing from a stale image until someone rebuilds, and the container path
# is the one the README tells users to configure.
set -u
FAIL=0
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
if [ -f "$ROOT/scripts/config.sh" ]; then
    # shellcheck disable=SC1091
    source "$ROOT/scripts/config.sh"
fi
COMFY_CONTAINER="${COMFY_CONTAINER:-minimax-comfyui}"
MCP_PY="${MCP_PY:-/opt/mcp-venv/bin/python}"

echo "== In-container MCP venv (dependencies for every tool) =="

skip() { echo "  [SKIP] $1"; exit 78; }

command -v docker >/dev/null 2>&1 || skip "docker not installed"
docker ps --format '{{.Names}}' 2>/dev/null | grep -q "^${COMFY_CONTAINER}$" \
    || skip "container '${COMFY_CONTAINER}' is not running (./scripts/start_comfyui.sh)"

# --- 1. every declared runtime dependency is installed in the image ----------
# Compared by distribution name rather than import name: "psycopg[binary]"
# imports as psycopg, "PyYAML" as yaml, "python-dotenv" as dotenv. Guessing
# that mapping is how such a check quietly stops covering things.
DECLARED=$(python3 - "$ROOT/pyproject.toml" <<'PY'
import re, sys, tomllib
with open(sys.argv[1], "rb") as fh:
    data = tomllib.load(fh)
for spec in data["project"]["dependencies"]:
    name = re.split(r"[<>=!~\[; ]", spec.strip(), maxsplit=1)[0]
    print(name.strip().lower().replace("_", "-"))
PY
)

INSTALLED=$(docker exec "$COMFY_CONTAINER" "$MCP_PY" -c "
from importlib.metadata import distributions
for d in distributions():
    name = (d.metadata['Name'] or '').strip().lower().replace('_','-')
    if name: print(name)
" 2>/dev/null)

if [ -z "$INSTALLED" ]; then
    echo "  [BAD] could not list packages in ${MCP_PY} inside ${COMFY_CONTAINER}"
    FAIL=$((FAIL+1))
else
    MISSING=""
    while IFS= read -r dep; do
        [ -n "$dep" ] || continue
        echo "$INSTALLED" | grep -qx "$dep" || MISSING="$MISSING $dep"
    done <<< "$DECLARED"
    if [ -n "$MISSING" ]; then
        echo "  [BAD] declared in pyproject.toml but absent from the image:$MISSING"
        echo "        the image predates these dependencies — rebuild: ./scripts/start_comfyui.sh"
        FAIL=$((FAIL+1))
    else
        echo "  [ok]   every runtime dependency in pyproject.toml is installed"
    fi
fi

# --- 2. the tool modules themselves import -----------------------------------
# The check that would have caught the real failure: a dependency can be
# present and the module still fail to import.
MODULES="minimax_mcp.server minimax_mcp.core minimax_mcp.comfyui_client \
minimax_mcp.db minimax_mcp.llm minimax_mcp.knowledge minimax_mcp.vault \
minimax_mcp.downloader minimax_mcp.transcriber minimax_mcp.orchestrator \
minimax_mcp.ig_queue minimax_mcp.ig_sync minimax_mcp.ig_worker"

for m in $MODULES; do
    if docker exec -e PYTHONPATH=/workspace/src "$COMFY_CONTAINER" \
        "$MCP_PY" -c "import $m" >/dev/null 2>&1; then
        echo "  [ok]   import $m"
    else
        err=$(docker exec -e PYTHONPATH=/workspace/src "$COMFY_CONTAINER" \
            "$MCP_PY" -c "import $m" 2>&1 | tail -1)
        echo "  [BAD] import $m -> ${err}"
        FAIL=$((FAIL+1))
    fi
done

# --- 3. the registry the container exposes matches the source ----------------
# A tool whose module fails to import can still leave the server running with
# that tool silently absent; count them where the user actually calls them.
EXPECTED=$(grep -c '^@mcp.tool()' "$ROOT/src/minimax_mcp/server.py")
# list_tools(), not get_tools(): the latter does not exist on this FastMCP's
# server object, and asking for it made the check report "none" against a
# perfectly healthy container -- a false alarm that outlived the real bug.
ACTUAL=$(docker exec -e PYTHONPATH=/workspace/src "$COMFY_CONTAINER" "$MCP_PY" -c "
import asyncio, sys
sys.path.insert(0, '/workspace/src')
from minimax_mcp.server import mcp
print(len(asyncio.run(mcp.list_tools())))
" 2>/dev/null | tail -1)

if [ "$ACTUAL" = "$EXPECTED" ]; then
    echo "  [ok]   container exposes all $EXPECTED tools"
else
    echo "  [BAD] container exposes '${ACTUAL:-none}' tools, source declares $EXPECTED"
    FAIL=$((FAIL+1))
fi

echo ""
if [ "$FAIL" -gt 0 ]; then
    echo "FAIL: $FAIL"
    exit 1
fi
echo "ALL PASS"
