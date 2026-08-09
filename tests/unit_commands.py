#!/usr/bin/env python3
"""Unit tests for the slash-command generator (scripts/command_docs).

Pure logic: parses source with `ast`, renders strings. No MCP server, no GPU,
no network.

Run:  uv run --project . python tests/unit_commands.py
Exit 0 = all pass.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.command_docs.parser import parse_tools

FAIL = 0


def ok(label: str) -> None:
    print(f"  [ok]   {label}")


def bad(label: str) -> None:
    global FAIL
    FAIL += 1
    print(f"  [BAD]  {label}")


SERVER_PY = ROOT / "src" / "minimax_mcp" / "server.py"
SPECS = {s.tool_name: s for s in parse_tools(SERVER_PY)}

print("== unit_commands: parser ==")

if len(SPECS) == 24:
    ok("found all 24 @mcp.tool() functions")
else:
    bad(f"found {len(SPECS)} tools, expected 24: {sorted(SPECS)}")

# Only @mcp.tool()-decorated functions, not every function in the module.
if "main" not in SPECS and "to_host_path" not in SPECS:
    ok("undecorated module functions are not mistaken for tools")
else:
    bad(f"non-tool functions leaked into the parse: {sorted(SPECS)}")

dl = SPECS.get("download_video")
if dl and [p.name for p in dl.params] == ["url", "browser"]:
    ok("download_video: parameters in signature order")
else:
    bad(f"download_video params = {[p.name for p in dl.params] if dl else None}")

url_param = next(p for p in dl.params if p.name == "url")
if url_param.required and url_param.default_repr is None:
    ok("download_video.url is required with no default")
else:
    bad(f"download_video.url required={url_param.required} default={url_param.default_repr}")

if "Instagram Reel" in url_param.description:
    ok("description is read out of Field(description=...)")
else:
    bad(f"download_video.url description = {url_param.description!r}")

browser = next(p for p in dl.params if p.name == "browser")
if not browser.required and browser.default_repr == "'chrome'":
    ok("download_video.browser default is captured as a repr")
else:
    bad(f"download_video.browser required={browser.required} default={browser.default_repr}")

# get_status(prompt_id: str) has a bare annotation, no Field(...) at all.
status = SPECS.get("get_status")
pid = next(p for p in status.params if p.name == "prompt_id")
if pid.required and pid.description == "":
    ok("parameter without Field() yields an empty description, not a crash")
else:
    bad(f"get_status.prompt_id description = {pid.description!r}")

# wait_for_video is `async def`.
wait = SPECS.get("wait_for_video")
if wait and wait.is_async:
    ok("async tools are recognised as async")
else:
    bad(f"wait_for_video.is_async = {wait.is_async if wait else None}")

timeout = next(p for p in wait.params if p.name == "timeout")
if timeout.default_repr == "1200.0" and "wait" in timeout.description.lower():
    ok("wait_for_video.timeout default and description parsed")
else:
    bad(f"wait_for_video.timeout default={timeout.default_repr} desc={timeout.description!r}")

# Tools with no parameters at all.
health = SPECS.get("health_check")
if health and health.params == ():
    ok("health_check parses with zero parameters")
else:
    bad(f"health_check params = {health.params if health else None}")

# Union annotations must survive as written.
seed = next(p for p in SPECS["submit_scene"].params if p.name == "seed")
if seed.type_hint == "int | None" and seed.default_repr == "None":
    ok("union type hint preserved verbatim")
else:
    bad(f"submit_scene.seed type={seed.type_hint!r} default={seed.default_repr!r}")

# list[str] annotation.
scenes = next(p for p in SPECS["compose_final"].params if p.name == "scene_paths")
if scenes.type_hint == "list[str]":
    ok("list[str] type hint preserved verbatim")
else:
    bad(f"compose_final.scene_paths type = {scenes.type_hint!r}")

# Docstrings feed the summary line.
if SPECS["knowledge_ask"].docstring.startswith("Responde"):
    ok("docstring captured")
else:
    bad(f"knowledge_ask docstring = {SPECS['knowledge_ask'].docstring[:40]!r}")

print("== unit_commands: catalog ==")

from scripts.command_docs import catalog

missing = sorted(set(SPECS) - set(catalog.COMMAND_NAMES))
if not missing:
    ok("every parsed tool has a command name")
else:
    bad(f"tools with no command name: {missing}")

orphan = sorted(set(catalog.COMMAND_NAMES) - set(SPECS))
if not orphan:
    ok("no command name points at a tool that no longer exists")
else:
    bad(f"command names for unknown tools: {orphan}")

names = list(catalog.COMMAND_NAMES.values())
if len(names) == len(set(names)):
    ok("command names are unique")
else:
    dupes = sorted({n for n in names if names.count(n) > 1})
    bad(f"duplicate command names: {dupes}")

if catalog.command_name("knowledge_ask") == "kb-perguntar":
    ok("command_name maps a knowledge tool to its kb- name")
else:
    bad(f"command_name('knowledge_ask') = {catalog.command_name('knowledge_ask')!r}")

wrong_prefix = [
    (tool, name)
    for tool, name in catalog.COMMAND_NAMES.items()
    if tool.startswith("knowledge_") != name.startswith("kb-")
]
if not wrong_prefix:
    ok("knowledge_* tools get kb-, everything else gets minimax-")
else:
    bad(f"prefix mismatch: {wrong_prefix}")

if (
    catalog.group_of("kb-buscar") == "kb"
    and catalog.group_of("minimax-health") == "video"
    and catalog.group_of("ig-status") == "ig"
):
    ok("group_of splits the three product areas")
else:
    bad("group_of returned the wrong group")

try:
    catalog.command_name("tool_que_nao_existe")
    bad("command_name should raise for an unknown tool")
except KeyError as e:
    if "tool_que_nao_existe" in str(e):
        ok("command_name raises a KeyError naming the missing tool")
    else:
        bad(f"KeyError message unhelpful: {e}")

print("== unit_commands: overrides ==")

from scripts.command_docs.overrides import OVERRIDES

unknown = sorted(set(OVERRIDES) - set(SPECS))
if not unknown:
    ok("every override key names a tool that exists")
else:
    bad(f"overrides for tools that do not exist (renamed? removed?): {unknown}")

bad_params = []
for tool, ov in OVERRIDES.items():
    real = {p.name for p in SPECS[tool].params}
    for pname in ov.param_notas:
        if pname not in real:
            bad_params.append(f"{tool}.{pname}")
if not bad_params:
    ok("every param_notas key names a real parameter")
else:
    bad(f"param_notas for parameters that do not exist: {bad_params}")

collisions = []
for tool, ov in OVERRIDES.items():
    real = {p.name for p in SPECS[tool].params}
    collisions += [f"{tool}.{p}" for p in ov.params_extra if p in real]
if not collisions:
    ok("params_extra never shadows a real parameter")
else:
    bad(f"params_extra colliding with real parameters: {collisions}")

# The three absorbed commands must keep the facts that made them useful.
ABSORBED_FACTS = {
    "download_video": ["database locked", "transcrever"],
    "transcribe_video": ["downloads/", "large-v3"],
    "generate_video": ["OOM", "512x320", "wait_for_video", "EN"],
}
for tool, facts in ABSORBED_FACTS.items():
    ov = OVERRIDES.get(tool)
    if ov is None:
        bad(f"{tool}: no override — the hand-written command was not absorbed")
        continue
    blob = " ".join(
        [
            ov.resumo,
            *ov.param_notas.values(),
            *(e.descricao for e in ov.params_extra.values()),
            *ov.passos,
        ]
    )
    lost = [f for f in facts if f not in blob]
    if lost:
        bad(f"{tool}: facts lost when absorbing the hand-written command: {lost}")
    else:
        ok(f"{tool}: absorbed command kept its operational facts")

if len(OVERRIDES["generate_video"].passos) >= 4:
    ok("generate_video keeps its four ordered post-call steps")
else:
    bad(
        "generate_video.passos has "
        f"{len(OVERRIDES['generate_video'].passos)} steps, expected >= 4 "
        "(translate, await, OOM retry, timeout workaround)"
    )

print("== unit_commands: renderer ==")

from scripts.command_docs import renderer
from scripts.command_docs.overrides import Override as _Ov

dl_md = renderer.render_command(
    SPECS["download_video"], OVERRIDES["download_video"], "minimax-download"
)

if dl_md.startswith("---\ndescription: "):
    ok("command starts with the frontmatter description")
else:
    bad(f"command starts with {dl_md[:40]!r}")

if "$ARGUMENTS" in dl_md:
    ok("command passes $ARGUMENTS through")
else:
    bad("command is missing $ARGUMENTS")

if "minimax-video-factory_download_video" in dl_md:
    ok("command names the fully-qualified MCP tool")
else:
    bad("command does not name the MCP tool")

if "-remote" in dl_md and "-uv" in dl_md:
    ok("command mentions the fallback server variants")
else:
    bad("command is missing the server-variant fallback step")

usage = renderer.render_usage(
    SPECS["download_video"], OVERRIDES["download_video"], "minimax-download"
)
if usage.startswith("/minimax-download <url>"):
    ok("usage line puts required parameters first, in angle brackets")
else:
    bad(f"usage line = {usage!r}")

if "[browser=chrome]" in usage:
    ok("usage line shows optional parameters with their defaults")
else:
    bad(f"usage line missing optional default: {usage!r}")

if "[transcrever]" in usage:
    ok("usage line includes params_extra")
else:
    bad(f"usage line missing params_extra: {usage!r}")

body = dl_md.split("Instruções obrigatórias:")[1]
if body.index("`url`") < body.index("`browser`"):
    ok("extraction list puts required parameters before optional ones")
else:
    bad("extraction list ordering is wrong")

if "database locked" in dl_md:
    ok("param_notas are appended to their parameter's line")
else:
    bad("param_notas did not reach the rendered command")

gen_md = renderer.render_command(
    SPECS["generate_video"], OVERRIDES["generate_video"], "minimax-gerar-video"
)
step_lines = [ln for ln in gen_md.splitlines() if ln[:2].strip().rstrip(".").isdigit()]
if len(step_lines) >= 6:
    ok("override passos become numbered steps, in order")
else:
    bad(f"generate_video rendered only {len(step_lines)} numbered steps")

# Compare positions *inside the steps section only*: "OOM" also appears in the
# width param_nota, which is rendered earlier, so a whole-file index would
# compare the wrong two things.
gen_steps = gen_md.split("Instruções obrigatórias:")[1].split("2. Chame")[1]
if gen_steps.index("traduza") < gen_steps.index("reduza para 512x320"):
    ok("passos keep their declared order")
else:
    bad("passos were reordered")

health_md = renderer.render_command(
    SPECS["health_check"], OVERRIDES["health_check"], "minimax-health"
)
if "$ARGUMENTS" in health_md and "health_check" in health_md:
    ok("a zero-parameter tool renders a valid command")
else:
    bad("zero-parameter tool rendered badly")

bare = renderer.render_command(SPECS["list_outputs"], _Ov(), "minimax-outputs")
if bare.startswith("---\ndescription: ") and "$ARGUMENTS" in bare:
    ok("a tool with an empty override still renders")
else:
    bad("empty override broke the renderer")

print("== unit_commands: catalog page ==")

entries = sorted(
    (catalog.command_name(name), spec, OVERRIDES.get(name, _Ov()))
    for name, spec in SPECS.items()
)
page = renderer.render_catalog_page(entries)

if page.lstrip().startswith("# "):
    ok("catalog page starts with a heading")
else:
    bad(f"catalog page starts with {page[:40]!r}")

if "GERADO AUTOMATICAMENTE" in page:
    ok("catalog page carries the do-not-edit header")
else:
    bad("catalog page is missing the generated-file header")

if all(f"/{cmd}" in page for cmd, _, _ in entries):
    ok("every command appears on the catalog page")
else:
    absent = [c for c, _, _ in entries if f"/{c}" not in page]
    bad(f"commands missing from the catalog page: {absent}")

if "Pipeline de vídeo" in page and "Base de conhecimento" in page:
    ok("catalog page is split by product area")
else:
    bad("catalog page is missing its group headings")

# Compare the two group headings against each other: the overview table at the
# top already lists every command, so comparing a heading against a command
# name would just measure the table.
if page.index("## Pipeline de vídeo") < page.index("## Base de conhecimento"):
    ok("video group precedes the knowledge-base group")
else:
    bad("group order is wrong on the catalog page")

video_start = page.index("## Pipeline de vídeo")
kb_start = page.index("## Base de conhecimento")
if page.index("### `/minimax-health`") > video_start and page.index(
    "### `/kb-buscar`"
) > kb_start:
    ok("each command's section sits under its own group")
else:
    bad("a command section landed in the wrong group")

print("== unit_commands: drift guards ==")

COMMAND_DIR = ROOT / ".opencode" / "command"
on_disk = {p.stem for p in COMMAND_DIR.glob("*.md")}
expected = {catalog.command_name(name) for name in SPECS}

missing_files = sorted(expected - on_disk)
if not missing_files:
    ok("every tool has a command file on disk")
else:
    bad(
        f"tools with no command file: {missing_files}. "
        "Run: uv run python scripts/generate_commands.py"
    )

extra_files = sorted(on_disk - expected - catalog.NON_TOOL_COMMANDS)
if not extra_files:
    ok("no orphan command files (every .md maps to a tool or is allow-listed)")
else:
    bad(f"command files with no matching tool: {extra_files}")

if catalog.NON_TOOL_COMMANDS <= on_disk:
    ok("allow-listed non-tool commands are still present and untouched")
else:
    bad(f"allow-listed commands went missing: {sorted(catalog.NON_TOOL_COMMANDS - on_disk)}")

# Generated content matches what the generator would produce right now.
sys.path.insert(0, str(ROOT / "scripts"))
import generate_commands

stale = sorted(
    str(p.relative_to(ROOT))
    for p, content in generate_commands.build().items()
    if not p.exists() or p.read_text(encoding="utf-8") != content
)
if not stale:
    ok("generated files are up to date with the current tools and overrides")
else:
    bad(
        f"stale generated files: {stale}. "
        "Run: uv run python scripts/generate_commands.py"
    )

# The docs site must actually link the generated page, or it exists but is
# unreachable -- which is the same as not existing for a reader.
mkdocs_yml = (ROOT / "mkdocs.yml").read_text(encoding="utf-8")
if "COMMANDS.md" in mkdocs_yml:
    ok("COMMANDS.md is wired into the MkDocs nav")
else:
    bad("COMMANDS.md exists but is not in the MkDocs nav — nobody can reach it")


# The README carries a hand-written table of every tool. It is the first thing
# anyone reads, and nothing regenerates it -- so a new tool silently leaves it
# a tool short unless something says so.
readme = (ROOT / "README.md").read_text(encoding="utf-8")
undocumented = sorted(t for t in SPECS if f"`{t}`" not in readme)
if not undocumented:
    ok("every tool appears in the README table")
else:
    bad(
        f"tools missing from the README table: {undocumented}. "
        "Add them to the Slash commands section."
    )

print()
if FAIL:
    print(f"FAIL: {FAIL}")
    sys.exit(1)
print("ALL PASS")
