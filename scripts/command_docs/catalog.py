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
}

GROUP_TITLES: dict[str, str] = {
    "video": "Pipeline de vídeo",
    "kb": "Base de conhecimento",
}

# Commands in .opencode/command/ that are not backed by an MCP tool. The
# coverage test must not demand a tool for these.
NON_TOOL_COMMANDS: frozenset[str] = frozenset({"compress", "search-sessions"})


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
    """Which product area a command belongs to: 'kb' or 'video'."""
    return "kb" if command.startswith("kb-") else "video"
