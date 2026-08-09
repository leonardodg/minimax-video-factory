"""Turn a ToolSpec plus its Override into an OpenCode command file.

Pure string building: no file I/O, so every shape can be unit-tested. The
layout mirrors the three commands that were hand-written and used in anger --
frontmatter with a usage line, $ARGUMENTS, then numbered instructions.
"""
from __future__ import annotations

from scripts.command_docs import catalog
from scripts.command_docs.overrides import Override
from scripts.command_docs.parser import ParamSpec, ToolSpec

MCP_SERVER = "minimax-video-factory"

# Every command carries this: the user runs several server variants and the
# default one is not always the live one.
FALLBACK_STEP = (
    "Chame `{tool}` com esses parâmetros. Se a variante default do servidor MCP "
    "estiver indisponível, use a variante conectada (`{server}-remote` ou `{server}-uv`)."
)

GENERATED_HEADER = (
    "<!-- GERADO AUTOMATICAMENTE por scripts/generate_commands.py -->\n"
    "<!-- Não edite à mão: rode `uv run python scripts/generate_commands.py`. -->\n"
)

GROUP_ORDER = ("video", "kb", "ig")


def _sorted_params(spec: ToolSpec) -> tuple[list[ParamSpec], list[ParamSpec]]:
    required = [p for p in spec.params if p.required]
    optional = [p for p in spec.params if not p.required]
    return required, optional


def _escape_pipes(text: str) -> str:
    """Escape `|` so a description cannot break out of a markdown table cell."""
    return text.replace("|", "\\|")


def _unquote(default_repr: str) -> str:
    """`"'chrome'"` -> `chrome`, so usage lines read naturally."""
    if len(default_repr) >= 2 and default_repr[0] == default_repr[-1] == "'":
        return default_repr[1:-1]
    return default_repr


def render_usage(spec: ToolSpec, override: Override, command: str) -> str:
    """The `/command <required> [optional=default]` line."""
    required, optional = _sorted_params(spec)
    parts = [f"/{command}"]
    parts += [f"<{p.name}>" for p in required]
    parts += [
        f"[{p.name}={_unquote(p.default_repr)}]"
        if p.default_repr not in (None, "None")
        else f"[{p.name}]"
        for p in optional
    ]
    parts += [
        f"[{name}={extra.default}]" if extra.default else f"[{name}]"
        for name, extra in override.params_extra.items()
    ]
    return " ".join(parts)


def _summary(spec: ToolSpec, override: Override) -> str:
    if override.resumo:
        return override.resumo.rstrip(".")
    first_line = spec.docstring.splitlines()[0].strip() if spec.docstring else ""
    if not first_line:
        raise ValueError(
            f"tool {spec.tool_name!r} has neither a docstring nor an override "
            f"resumo. Add one of the two: a command without a description is "
            f"worse than no command."
        )
    return first_line.rstrip(".")


def _describe(param: ParamSpec, override: Override) -> str:
    """The description to show for a parameter.

    A `param_notas` entry *replaces* the `Field(description=...)` rather than
    appending to it. The Field descriptions are written in English for the tool
    API; the commands are written in Portuguese for a human. Appending produced
    bilingual, half-duplicated lines like "Whisper model: tiny, base, small
    (default `small`). tiny/base/small/medium/large-v3."
    """
    return override.param_notas.get(param.name) or param.description or ""


def _param_line(param: ParamSpec, override: Override) -> str:
    desc = _describe(param, override)
    if param.required:
        line = f"   - `{param.name}` (obrigatória)"
        line += f" — {desc}" if desc else ""
    else:
        line = f"   - `{param.name}`: {desc}" if desc else f"   - `{param.name}`"
        if param.default_repr is not None:
            line += f" (default `{_unquote(param.default_repr)}`)"
    return line.rstrip(".") + "."


def _numbered_steps(spec: ToolSpec, override: Override, call_step: str) -> list[str]:
    """The numbered instruction list, shared by every client dialect.

    Only `call_step` differs between clients: how a tool is named and which
    servers to fall back to are client-specific, everything else is not.
    """
    required, optional = _sorted_params(spec)
    lines: list[str] = []

    step = 1
    if required or optional or override.params_extra:
        lines.append(f"{step}. Extraia:")
        for param in required + optional:
            lines.append(_param_line(param, override))
        for name, extra in override.params_extra.items():
            line = f"   - `{name}`: {extra.descricao}"
            if extra.default:
                line += f" (default `{extra.default}`)"
            lines.append(line.rstrip(".") + ".")
        step += 1

    lines.append(f"{step}. {call_step}")
    step += 1

    for passo in override.passos:
        lines.append(f"{step}. {passo}")
        step += 1

    if not override.passos:
        lines.append(f"{step}. Reporte o resultado da tool ao usuário.")

    return lines


def render_command(spec: ToolSpec, override: Override, command: str) -> str:
    """The complete .md body for one OpenCode slash command."""
    summary = _summary(spec, override)
    usage = render_usage(spec, override, command)

    lines = [
        "---",
        f"description: {summary}. Uso: {usage}",
        "---",
        "",
        (f"Execute a ferramenta MCP **`{MCP_SERVER}_{spec.tool_name}`** "
        f"(server `{MCP_SERVER}`)."),
        "",
        "Entrada do usuário (tudo depois do comando):",
        "$ARGUMENTS",
        "",
        "Instruções obrigatórias:",
    ]
    lines += _numbered_steps(
        spec, override, FALLBACK_STEP.format(tool=spec.tool_name, server=MCP_SERVER)
    )
    return "\n".join(lines) + "\n"


def claude_tool_ref(server: str, tool: str) -> str:
    """How Claude Code names an MCP tool: `mcp__<server>__<tool>`.

    Not the same shape as OpenCode's `<server>_<tool>`. Writing the OpenCode
    form into a Claude Code command produces a command that lists fine and
    fails on every run, because no tool by that name is ever exposed.
    """
    return f"mcp__{server}__{tool}"


def _claude_call_step(spec: ToolSpec, command: str) -> str:
    """The 'call the tool' step, with the fallbacks that apply to its group."""
    server = catalog.server_of(command)
    fallbacks = catalog.fallbacks_of(command)
    step = (
        f"Chame `{claude_tool_ref(server, spec.tool_name)}` com esses parâmetros."
    )
    if fallbacks:
        alts = " ou ".join(
            f"`{claude_tool_ref(alt, spec.tool_name)}`" for alt in fallbacks
        )
        step += f" Se o servidor `{server}` não estiver conectado, use {alts}."
    else:
        step += (
            f" Esta tool só existe no servidor `{server}`, que roda no host com "
            f"acesso direto a Postgres e Ollama. Se ele não estiver conectado, "
            f"diga isso ao usuário — não tente as variantes do container, que "
            f"não alcançam o Postgres e só devolvem timeout."
        )
    return step


def render_claude_command(spec: ToolSpec, override: Override, command: str) -> str:
    """The complete .md body for one Claude Code slash command.

    Same instructions as the OpenCode form, three differences that matter:
    the tool reference is `mcp__server__tool`, the usage line moves out of
    `description` into the dedicated `argument-hint` field, and the server
    fallbacks are the ones that can actually serve this command's group.
    """
    summary = _summary(spec, override)
    usage = render_usage(spec, override, command)
    # argument-hint shows only the arguments; the leading "/command" that
    # render_usage emits is already on screen when the hint appears.
    hint = usage[len(f"/{command}") :].strip()

    lines = ["---", f"description: {summary}"]
    if hint:
        lines.append(f"argument-hint: {hint}")
    lines += [
        "---",
        "",
        GENERATED_HEADER.rstrip("\n"),
        "",
        (
            "Execute a ferramenta MCP "
            f"**`{claude_tool_ref(catalog.server_of(command), spec.tool_name)}`**."
        ),
        "",
        "Entrada do usuário (tudo depois do comando):",
        "$ARGUMENTS",
        "",
        "Instruções obrigatórias:",
    ]
    lines += _numbered_steps(spec, override, _claude_call_step(spec, command))
    return "\n".join(lines) + "\n"


def render_catalog_page(entries) -> str:
    """The docs/COMMANDS.md page: overview table plus a section per command.

    `entries` is an iterable of (command, ToolSpec, Override).
    """
    from scripts.command_docs.catalog import GROUP_TITLES, group_of

    entries = list(entries)
    lines = [
        "# Slash commands",
        "",
        GENERATED_HEADER,
        ("Um comando para cada ferramenta MCP, gerado para os dois clientes: "
        "OpenCode (`.opencode/command/`) e Claude Code (`.claude/commands/`). "
        "Esta página descreve o uso humano; a referência de programação das "
        "tools está em [MCP Tools Reference](MCP_TOOLS.md)."),
        "",
        ("Os comandos `kb-*` só funcionam contra o servidor **host** "
        "(`minimax-knowledge-base`): as tools `knowledge_*` falam direto com "
        "Postgres e Ollama, que o container não alcança. Os demais rodam no "
        "container."),
        "",
        "| Comando | Tool | O que faz |",
        "|---|---|---|",
    ]
    for command, spec, override in entries:
        summary = _summary(spec, override)
        lines.append(f"| `/{command}` | `{spec.tool_name}` | {summary} |")
    lines.append("")

    for group in GROUP_ORDER:
        in_group = [e for e in entries if group_of(e[0]) == group]
        if not in_group:
            continue
        lines += [f"## {GROUP_TITLES[group]}", ""]
        for command, spec, override in in_group:
            lines += [
                f"### `/{command}`",
                "",
                _summary(spec, override) + ".",
                "",
                "```",
                render_usage(spec, override, command),
                "```",
                "",
            ]
            required, optional = _sorted_params(spec)
            if required or optional or override.params_extra:
                lines += [
                    "| Parâmetro | Obrigatório | Default | Descrição |",
                    "|---|---|---|---|",
                ]
                for p in required + optional:
                    default = "—" if p.default_repr is None else f"`{_unquote(p.default_repr)}`"
                    # Escaped outside the f-string: a backslash inside an
                    # f-string expression is a SyntaxError before Python 3.12,
                    # and this project declares requires-python >= 3.10.
                    desc = _escape_pipes(_describe(p, override))
                    obrigatorio = "sim" if p.required else "não"
                    lines.append(
                        f"| `{p.name}` | {obrigatorio} | {default} | {desc} |"
                    )
                for name, extra in override.params_extra.items():
                    default = f"`{extra.default}`" if extra.default else "—"
                    lines.append(
                        f"| `{name}` | não | {default} | "
                        f"{_escape_pipes(extra.descricao)} |"
                    )
                lines.append("")
            if override.passos:
                lines += ["**Notas operacionais:**", ""]
                lines += [f"- {passo}" for passo in override.passos]
                lines.append("")

    return "\n".join(lines) + "\n"
