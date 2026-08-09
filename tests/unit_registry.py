#!/usr/bin/env python3
"""Registry test for the MCP server: the 24 @mcp.tool functions are registered,
required params have Field(description=...), and the set matches docs/MCP_TOOLS.md.

Run: uv run --directory . python tests/unit_registry.py
Exit 0 = all pass. Any failure prints [BAD] and exits non-zero.
"""
import asyncio
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

FAIL = 0


def ok(label: str) -> None:
    print(f"  [ok]   {label}")


def bad(label: str) -> None:
    global FAIL
    FAIL += 1
    print(f"  [BAD]  {label}")


EXPECTED_TOOLS = {
    # original video factory
    "health_check",
    "submit_scene",
    "get_status",
    "queue_status",
    "wait_for_video",
    "list_outputs",
    "compose_final",
    # audiovisual studio
    "download_video",
    "transcribe_video",
    "create_cinematic_prompt",
    "generate_video",
    "studio_pipeline",
    # knowledge base
    "knowledge_ingest_text",
    "knowledge_ingest_markdown",
    "knowledge_ingest_video",
    "knowledge_ingest_audio",
    "knowledge_search",
    "knowledge_ask",
    "knowledge_reindex",
    # instagram saved-posts sync
    "ig_sync_saved",
    "ig_queue_status",
    "ig_worker_start",
    "ig_worker_stop",
    "ig_get_progress",
}

# required params that MUST carry a Field(description=...)
REQUIRED_DESCRIBED = {
    "submit_scene": ["prompt"],
    "download_video": ["url"],
    "transcribe_video": ["video_path"],
    "create_cinematic_prompt": ["transcription"],
    "generate_video": ["prompt"],
    "studio_pipeline": ["url"],
    "compose_final": ["scene_paths"],
    "knowledge_ingest_text": ["text"],
    "knowledge_ingest_markdown": ["path"],
    "knowledge_ingest_video": ["url"],
    "knowledge_ingest_audio": ["path_or_url"],
    "knowledge_search": ["query"],
    "knowledge_ask": ["query"],
}


async def main() -> None:
    from minimax_mcp import server

    tools = await server.mcp.list_tools()
    names = {t.name for t in tools}

    print("== unit_registry: tool set ==")
    if names == EXPECTED_TOOLS:
        ok(f"exactly {len(EXPECTED_TOOLS)} tools registered, set matches expectation")
    else:
        missing = EXPECTED_TOOLS - names
        extra = names - EXPECTED_TOOLS
        if missing:
            bad(f"missing tools: {sorted(missing)}")
        if extra:
            bad(f"unexpected tools: {sorted(extra)}")

    by_name = {t.name: t for t in tools}

    print("== unit_registry: required params carry Field(description=...) ==")
    for tool_name, params in REQUIRED_DESCRIBED.items():
        t = by_name.get(tool_name)
        if t is None:
            bad(f"tool {tool_name} not registered")
            continue
        schema = t.parameters.get("properties", {})
        for p in params:
            meta = schema.get(p, {})
            if not meta.get("description"):
                bad(f"{tool_name}.{p}: required param missing Field(description=...)")
            else:
                ok(f"{tool_name}.{p} described")

    print("== unit_registry: no tool is left without a docstring ==")
    for name, t in by_name.items():
        if not (t.description or "").strip():
            bad(f"{name}: no docstring/description")
    ok("all registered tools carry a description")

    print("== unit_registry: tool set matches docs/MCP_TOOLS.md ==")
    md = ROOT / "docs" / "MCP_TOOLS.md"
    if not md.exists():
        bad(f"docs/MCP_TOOLS.md not found at {md}")
    else:
        content = md.read_text(encoding="utf-8")
        doc_tool_names = set(re.findall(r"^## .*?`([a-z_]+)`|^### .*?`([a-z_]+)`", content, re.MULTILINE))
        doc_flat = {n for tup in doc_tool_names for n in tup if n}
        doc_flat = {n for n in doc_flat if n in EXPECTED_TOOLS}
        if doc_flat == EXPECTED_TOOLS:
            ok("all 24 tools documented in docs/MCP_TOOLS.md")
        else:
            bad(f"MCP_TOOLS.md mentions {sorted(doc_flat)} but expected {sorted(EXPECTED_TOOLS)}")

    print("== unit_registry: tools fail soft (never raise) ==")
    from unittest.mock import patch

    from minimax_mcp import db as _db

    with patch.object(_db, "get_session", side_effect=RuntimeError("db down")):
        res = server.ig_get_progress()
    if res.get("ok") is False and "ig_get_progress failed" in res.get("error", ""):
        ok("ig_get_progress returns {ok: False} instead of raising when the DB is down")
    else:
        bad(f"ig_get_progress did not fail soft: {res!r}")


if __name__ == "__main__":
    asyncio.run(main())
    print()
    if FAIL:
        print(f"FAIL: {FAIL}")
        sys.exit(1)
    print("PASS")
