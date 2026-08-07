"""Extract tool signatures from the MCP server source, without importing it.

Importing `server.py` would pull in torch, faster-whisper and a Postgres
connection; the generator would then need a GPU, downloaded models and a live
database just to produce text. Reading the AST keeps it to milliseconds on any
machine.
"""
from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path

TOOL_DECORATOR = "mcp.tool"


@dataclass(frozen=True)
class ParamSpec:
    name: str
    type_hint: str
    default_repr: str | None
    description: str
    required: bool


@dataclass(frozen=True)
class ToolSpec:
    tool_name: str
    docstring: str
    params: tuple[ParamSpec, ...]
    is_async: bool


def _is_tool(node: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    """True when the function carries an @mcp.tool() decorator."""
    for dec in node.decorator_list:
        target = dec.func if isinstance(dec, ast.Call) else dec
        if (
            isinstance(target, ast.Attribute)
            and isinstance(target.value, ast.Name)
            and f"{target.value.id}.{target.attr}" == TOOL_DECORATOR
        ):
            return True
    return False


def _callee_name(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return ""


def _field_parts(default: ast.AST | None) -> tuple[str | None, str]:
    """Split a default node into (default_repr, description).

    Handles three shapes: no default, a plain literal, and `Field(default=...,
    description=...)`. A `Field(...)` with no `default=` means the parameter is
    required even though it syntactically has a default value.
    """
    if default is None:
        return None, ""
    if isinstance(default, ast.Call) and _callee_name(default.func) == "Field":
        default_repr = None
        description = ""
        for kw in default.keywords:
            if kw.arg == "default":
                default_repr = ast.unparse(kw.value)
            elif kw.arg == "description" and isinstance(kw.value, ast.Constant):
                description = str(kw.value.value)
        return default_repr, description
    return ast.unparse(default), ""


def _params_of(node: ast.FunctionDef | ast.AsyncFunctionDef) -> tuple[ParamSpec, ...]:
    positional = node.args.args
    # Defaults align to the tail of the positional args.
    padded: list[ast.AST | None] = [None] * (
        len(positional) - len(node.args.defaults)
    ) + list(node.args.defaults)

    pairs: list[tuple[ast.arg, ast.AST | None]] = list(zip(positional, padded))
    pairs += list(zip(node.args.kwonlyargs, node.args.kw_defaults))

    specs = []
    for arg, default in pairs:
        if arg.arg in ("self", "cls"):
            continue
        default_repr, description = _field_parts(default)
        specs.append(
            ParamSpec(
                name=arg.arg,
                type_hint=ast.unparse(arg.annotation) if arg.annotation else "",
                default_repr=default_repr,
                description=description,
                required=default_repr is None,
            )
        )
    return tuple(specs)


def parse_tools(source: Path) -> list[ToolSpec]:
    """Return every @mcp.tool() function in `source`, sorted by tool name."""
    tree = ast.parse(source.read_text(encoding="utf-8"))
    tools = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if not _is_tool(node):
            continue
        tools.append(
            ToolSpec(
                tool_name=node.name,
                docstring=(ast.get_docstring(node) or "").strip(),
                params=_params_of(node),
                is_async=isinstance(node, ast.AsyncFunctionDef),
            )
        )
    tools.sort(key=lambda t: t.tool_name)
    return tools
