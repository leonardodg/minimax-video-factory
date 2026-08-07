#!/usr/bin/env python3
"""Generate one OpenCode slash command per MCP tool, plus docs/COMMANDS.md.

Run after adding or changing a tool:

    uv run python scripts/generate_commands.py

`--check` writes nothing and exits non-zero if anything is stale; that is the
form to run in CI.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from scripts.command_docs import catalog, renderer
from scripts.command_docs.overrides import OVERRIDES, Override
from scripts.command_docs.parser import parse_tools

SERVER_PY = ROOT / "src" / "minimax_mcp" / "server.py"
COMMAND_DIR = ROOT / ".opencode" / "command"
CATALOG_PAGE = ROOT / "docs" / "COMMANDS.md"


def build() -> dict[Path, str]:
    """Map every output path to the content it should have."""
    specs = parse_tools(SERVER_PY)
    outputs: dict[Path, str] = {}
    for spec in specs:
        command = catalog.command_name(spec.tool_name)
        override = OVERRIDES.get(spec.tool_name, Override())
        outputs[COMMAND_DIR / f"{command}.md"] = renderer.render_command(
            spec, override, command
        )

    entries = sorted(
        (
            catalog.command_name(spec.tool_name),
            spec,
            OVERRIDES.get(spec.tool_name, Override()),
        )
        for spec in specs
    )
    outputs[CATALOG_PAGE] = renderer.render_catalog_page(entries)
    return outputs


def _undocumented_params() -> list[str]:
    """Parameters with no description in the code and none in an override."""
    return [
        f"{spec.tool_name}.{p.name}"
        for spec in parse_tools(SERVER_PY)
        for p in spec.params
        if not p.description
        and not OVERRIDES.get(spec.tool_name, Override()).param_notas.get(p.name)
    ]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="do not write; exit non-zero if any output is stale",
    )
    args = parser.parse_args()

    outputs = build()
    stale = [
        p
        for p, content in outputs.items()
        if not p.exists() or p.read_text(encoding="utf-8") != content
    ]

    if args.check:
        if stale:
            print("stale, run scripts/generate_commands.py:")
            for p in sorted(stale):
                print(f"  {p.relative_to(ROOT)}")
            return 1
        print(f"up to date ({len(outputs) - 1} commands + docs/COMMANDS.md)")
        return 0

    COMMAND_DIR.mkdir(parents=True, exist_ok=True)
    CATALOG_PAGE.parent.mkdir(parents=True, exist_ok=True)
    for path, content in outputs.items():
        path.write_text(content, encoding="utf-8")

    print(f"wrote {len(outputs) - 1} commands + docs/COMMANDS.md")
    undocumented = _undocumented_params()
    if undocumented:
        print("parameters with no description anywhere (consider an override):")
        for name in undocumented:
            print(f"  {name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
