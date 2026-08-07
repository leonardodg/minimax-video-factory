#!/usr/bin/env bash
# tests/08_knowledge.sh — knowledge base MCP tools over stdio.
# Prerequisites: Postgres up + migrated (Task 1/2), Ollama running with
# LLM_MODEL and EMBEDDING_MODEL pulled (Task 6/7). Server runs in host-uv mode.
set -u
FAIL=0
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
if [ -f "$ROOT/scripts/config.sh" ]; then
    # shellcheck disable=SC1091
    source "$ROOT/scripts/config.sh"
fi

echo "== Knowledge base (MCP stdio, host uv) =="

# --- skip when the backing services are absent ------------------------------
# diagnose.sh reads exit 78 (EX_CONFIG) as SKIP. A knowledge-base test with no
# database is not a defect in this repo, it is a test that cannot run -- and
# reporting it as PASS would be worse than either, because it would hide a real
# regression behind a green tick. This mirrors what tests/conftest.py already
# does for the pytest integration markers.
skip() { echo "  [SKIP] $1"; exit 78; }

[ -n "${KB_DATABASE_URL:-}" ] || \
    skip "KB_DATABASE_URL not set (cp .env.example .env, or export it)"

# postgresql+psycopg://user:pass@host:port/db -> host, port
KB_HOSTPORT="${KB_DATABASE_URL##*@}"
KB_HOSTPORT="${KB_HOSTPORT%%/*}"
KB_HOST="${KB_HOSTPORT%%:*}"
KB_PORT="${KB_HOSTPORT##*:}"
[ "$KB_PORT" = "$KB_HOST" ] && KB_PORT=5432

if ! timeout 2 bash -c "exec 3<>/dev/tcp/${KB_HOST}/${KB_PORT}" 2>/dev/null; then
    skip "Postgres unreachable at ${KB_HOST}:${KB_PORT} (docker compose -f docker/docker-compose.yml up -d postgres)"
fi

OLLAMA_BASE="${OLLAMA_URL:-http://localhost:11434}"
if ! curl -fsS --max-time 3 "${OLLAMA_BASE}/api/tags" >/dev/null 2>&1; then
    skip "Ollama unreachable at ${OLLAMA_BASE}"
fi

SAMPLE_TEXT="Hoje vou mostrar como instalar o Docker no Ubuntu. Primeiro, atualize os pacotes com apt update. Depois, instale com apt install docker.io. Por fim, adicione seu usuario ao grupo docker para nao precisar de sudo."

uv run --directory "$ROOT" python - "$ROOT" "$SAMPLE_TEXT" <<'PY' || FAIL=1
import asyncio, json, os, sys

root, sample_text = sys.argv[1], sys.argv[2]
sys.path.insert(0, os.path.join(root, "src"))

from fastmcp import Client
from fastmcp.client.transports import StdioTransport


async def main() -> int:
    env = dict(os.environ)
    env["MCP_TRANSPORT"] = "stdio"
    transport = StdioTransport(
        command="uv", args=["run", "--directory", root, "python", "src/minimax_mcp/server.py"],
        cwd=root, env=env,
    )
    async with Client(transport) as client:
        print("  [ok]   connected to MCP server over stdio (host uv)")

        r = await client.call_tool("knowledge_ingest_text", {
            "text": sample_text, "title": "Instalar Docker no Ubuntu", "platform": "manual",
        })
        rd = json.loads(r.content[0].text)
        if not rd.get("ok"):
            print(f"  [BAD] knowledge_ingest_text failed: {json.dumps(rd)[:400]}")
            return 1
        print(f"  [ok]   knowledge_ingest_text -> document_id={rd['document_id']}")
        print(f"         tags={rd.get('tags')}")

        r = await client.call_tool("knowledge_search", {"query": "Docker Ubuntu", "top_k": 5})
        rd = json.loads(r.content[0].text)
        if not rd.get("ok") or not rd.get("results"):
            print(f"  [BAD] knowledge_search failed or empty: {json.dumps(rd)[:400]}")
            return 1
        print(f"  [ok]   knowledge_search -> {len(rd['results'])} result(s)")

        r = await client.call_tool("knowledge_ask", {"query": "Como instalar o Docker no Ubuntu?"})
        rd = json.loads(r.content[0].text)
        if not rd.get("ok") or not rd.get("answer"):
            print(f"  [BAD] knowledge_ask failed or empty answer: {json.dumps(rd)[:400]}")
            return 1
        print(f"  [ok]   knowledge_ask -> {rd['answer'][:100]!r}...")

        r = await client.call_tool("knowledge_reindex", {})
        rd = json.loads(r.content[0].text)
        if not rd.get("ok") or rd.get("documents_reindexed", 0) < 1:
            print(f"  [BAD] knowledge_reindex failed: {json.dumps(rd)[:400]}")
            return 1
        print(f"  [ok]   knowledge_reindex -> {rd['documents_reindexed']} document(s)")

        print("  [PASS] full knowledge base flow OK")
        return 0

try:
    sys.exit(asyncio.run(main()))
except Exception as e:  # noqa: BLE001
    print(f"  [BAD] exception: {e}")
    sys.exit(1)
PY

exit "$FAIL"
