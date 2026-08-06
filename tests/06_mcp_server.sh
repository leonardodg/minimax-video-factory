#!/usr/bin/env bash
# tests/06_mcp_server.sh — MCP server starts, initialize handshake OK.
# Preferred path: in-container (docker exec, no host uv). Falls back to host uv.
set -u
FAIL=0
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
if [ -f "$ROOT/scripts/config.sh" ]; then
    # shellcheck disable=SC1091
    source "$ROOT/scripts/config.sh"
fi

echo "== MCP Server =="

INIT='{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"diag","version":"0"}}}'

RESP=""
if docker ps --format '{{.Names}}' 2>/dev/null | grep -q "^${COMFY_CONTAINER:-minimax-comfyui}\$"; then
    echo "  [info] using in-container MCP (${COMFY_CONTAINER:-minimax-comfyui})"
    RESP=$(printf '%s\n' "$INIT" | timeout 30 docker exec -i "${COMFY_CONTAINER:-minimax-comfyui}" bash /workspace/scripts/mcp_runner.sh 2>/dev/null | head -1) || RESP=""
else
    echo "  [info] container down; falling back to host uv"
    if [ ! -d "$ROOT/.venv" ] && command -v uv >/dev/null 2>&1; then
        (cd "$ROOT" && uv sync >/dev/null 2>&1) || true
    fi
    RESP=$(printf '%s\n' "$INIT" | (cd "$ROOT" && timeout 30 uv run --quiet python src/minimax_mcp/server.py 2>/dev/null) | head -1) || RESP=""
fi

if echo "$RESP" | grep -q 'protocolVersion'; then
    echo "  [ok]   MCP initialize handshake OK"
else
    echo "  [MISS] MCP handshake failed (server error?) — check container/venv + server.py"
    FAIL=$((FAIL+1))
fi

exit "$FAIL"
