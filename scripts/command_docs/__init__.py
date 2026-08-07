"""Offline generator for OpenCode slash commands, driven by the MCP registry.

Nothing here imports `minimax_mcp`: the tools are read out of the source with
`ast`, so the generator runs with no GPU, no ComfyUI and no database.
"""
from scripts.command_docs.parser import ParamSpec, ToolSpec, parse_tools

__all__ = ["ParamSpec", "ToolSpec", "parse_tools"]
