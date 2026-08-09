"""The one hand-written list: what each tool is called as a slash command.

Names are deliberately not derived from the tool name. `/kb-perguntar` reads
better than `/kb-knowledge-ask`, and the Portuguese verbs match the three
commands that already existed. Naming is a judgement call, so a new tool fails
the build until a human names it.
"""
from __future__ import annotations

COMMAND_NAMES: dict[str, str] = {
    # Video pipeline
    "health_check": "minimax-health",
    "submit_scene": "minimax-submit-scene",
    "get_status": "minimax-status",
    "queue_status": "minimax-fila",
    "wait_for_video": "minimax-wait",
    "list_outputs": "minimax-outputs",
    "compose_final": "minimax-compose",
    "download_video": "minimax-download",
    "transcribe_video": "minimax-transcrever",
    "create_cinematic_prompt": "minimax-prompt-cinematico",
    "generate_video": "minimax-gerar-video",
    "studio_pipeline": "minimax-studio",
    # Knowledge base
    "knowledge_ingest_text": "kb-ingest-texto",
    "knowledge_ingest_markdown": "kb-ingest-markdown",
    "knowledge_ingest_video": "kb-ingest-video",
    "knowledge_ingest_audio": "kb-ingest-audio",
    "knowledge_search": "kb-buscar",
    "knowledge_ask": "kb-perguntar",
    "knowledge_reindex": "kb-reindex",
    # Instagram sync
    "ig_sync_saved": "ig-sync",
    "ig_queue_status": "ig-status",
    "ig_worker_start": "ig-worker",
    "ig_worker_stop": "ig-worker-stop",
    "ig_get_progress": "ig-progress",
}

GROUP_TITLES: dict[str, str] = {
    "video": "Pipeline de vídeo",
    "kb": "Base de conhecimento",
    "ig": "Instagram sync",
}

# Commands in .opencode/command/ that are not backed by an MCP tool. The
# coverage test must not demand a tool for these. They are deliberately NOT
# ported to .claude/commands/: Claude Code already ships `compress` and
# `search-sessions` as global skills, and a project command of the same name
# would shadow them.
NON_TOOL_COMMANDS: frozenset[str] = frozenset({"compress", "search-sessions"})

# Which server actually answers each group, for clients that can route.
#
# The knowledge_* tools talk straight to Postgres (127.0.0.1:5432) and Ollama
# (localhost:11434), neither of which the container can reach, so they only
# work on the host server. Video and IG tools want the container, where the
# models and the ComfyUI bind-mounts live. OpenCode names one server for all
# 24 and leans on the fallback step; Claude Code gets told the truth up front.
SERVER_BY_GROUP: dict[str, str] = {
    "video": "minimax-video-factory",
    "ig": "minimax-video-factory",
    "kb": "minimax-knowledge-base",
}

# Variants to try when the primary server is not connected, in order. The kb
# group has none on purpose: the container variants cannot reach Postgres, so
# retrying there turns a clear "not connected" into a confusing timeout.
FALLBACKS_BY_GROUP: dict[str, tuple[str, ...]] = {
    "video": ("minimax-video-factory-remote", "minimax-video-factory-uv"),
    "ig": ("minimax-video-factory-remote", "minimax-video-factory-uv"),
    "kb": (),
}


def command_name(tool: str) -> str:
    """Slash-command name for `tool`. Raises if the tool has never been named."""
    try:
        return COMMAND_NAMES[tool]
    except KeyError:
        raise KeyError(
            f"tool {tool!r} has no command name. Add it to COMMAND_NAMES in "
            f"scripts/command_docs/catalog.py — naming is a human decision, so "
            f"the generator will not guess one."
        ) from None


def group_of(command: str) -> str:
    """Which product area a command belongs to: 'kb', 'ig' or 'video'."""
    if command.startswith("kb-"):
        return "kb"
    if command.startswith("ig-"):
        return "ig"
    return "video"


def server_of(command: str) -> str:
    """The MCP server that actually answers `command`."""
    return SERVER_BY_GROUP[group_of(command)]


def fallbacks_of(command: str) -> tuple[str, ...]:
    """Server variants to try for `command` when the primary is not connected."""
    return FALLBACKS_BY_GROUP[group_of(command)]
