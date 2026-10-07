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
}

GROUP_TITLES: dict[str, str] = {
    "video": "Pipeline de vídeo",
}

# Commands in .opencode/command/ that are not backed by an MCP tool. The
# coverage test must not demand a tool for these. They are deliberately NOT
# ported to .claude/commands/: Claude Code already ships `compress` and
# `search-sessions` as global skills, and a project command of the same name
# would shadow them.
NON_TOOL_COMMANDS: frozenset[str] = frozenset({"compress", "search-sessions"})

# Which server actually answers each group, for clients that can route. The
# knowledge_*/ig_* tools (and their minimax-knowledge-base server) moved to
# the insta_kb project in 2026-10-06 -- this repo only has the video group
# left, so there is nothing left to route between.
SERVER_BY_GROUP: dict[str, str] = {
    "video": "minimax-video-factory",
}

# Variants to try when the primary server is not connected, in order.
FALLBACKS_BY_GROUP: dict[str, tuple[str, ...]] = {
    "video": ("minimax-video-factory-remote", "minimax-video-factory-uv"),
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
    """Which product area a command belongs to. Only 'video' exists in this
    repo now -- kb-*/ig-* moved to insta_kb."""
    return "video"


def server_of(command: str) -> str:
    """The MCP server that actually answers `command`."""
    return SERVER_BY_GROUP[group_of(command)]


def fallbacks_of(command: str) -> tuple[str, ...]:
    """Server variants to try for `command` when the primary is not connected."""
    return FALLBACKS_BY_GROUP[group_of(command)]
