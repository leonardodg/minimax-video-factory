#!/usr/bin/env python3
"""Guard the render-resolution defaults against the 12 GB VRAM ceiling.

1344x768 is the H3 canvas maximum, but it OOMs the sampler on this machine
(`torch.OutOfMemoryError`). 1024x576 is the largest resolution that renders
reliably. The hand-written /minimax-gerar-video command has said so since day
one, while the tool signatures still defaulted to the value that crashes — so
anyone calling the tool without arguments hit the failure.

These tests read the defaults straight out of the source with `ast`, so they
need no GPU, no ComfyUI and no imports of torch.

Run:  uv run --project . python tests/unit_defaults.py
Exit 0 = all pass.
"""
import ast
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# The largest resolution that renders without OOM on 12 GB of VRAM.
SAFE_WIDTH = 1024
SAFE_HEIGHT = 576

# Tools that accept width/height and therefore must default to the safe pair.
SIZED_TOOLS = ("submit_scene", "generate_video", "studio_pipeline")

FAIL = 0


def ok(label: str) -> None:
    print(f"  [ok]   {label}")


def bad(label: str) -> None:
    global FAIL
    FAIL += 1
    print(f"  [BAD]  {label}")


def _literal(node: ast.AST):
    """Return the literal value of a default node, unwrapping Field(default=...)."""
    if isinstance(node, ast.Call) and getattr(node.func, "id", "") == "Field":
        for kw in node.keywords:
            if kw.arg == "default":
                return _literal(kw.value)
        return None
    try:
        return ast.literal_eval(node)
    except (ValueError, SyntaxError):
        return None


def defaults_of(source: Path, func_name: str) -> dict:
    """Map parameter name -> default literal for one function in `source`."""
    tree = ast.parse(source.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == func_name:
            args = node.args.args
            # defaults align to the tail of the positional args
            padded = [None] * (len(args) - len(node.args.defaults)) + list(node.args.defaults)
            found = {}
            for arg, default in zip(args, padded):
                found[arg.arg] = _literal(default) if default is not None else None
            for arg, default in zip(node.args.kwonlyargs, node.args.kw_defaults):
                found[arg.arg] = _literal(default) if default is not None else None
            return found
    raise AssertionError(f"function {func_name} not found in {source}")


print("== unit_defaults: MCP tool signatures ==")

server_py = ROOT / "src" / "minimax_mcp" / "server.py"
for tool in SIZED_TOOLS:
    params = defaults_of(server_py, tool)
    if params.get("width") == SAFE_WIDTH:
        ok(f"{tool}: width defaults to {SAFE_WIDTH}")
    else:
        bad(f"{tool}: width defaults to {params.get('width')}, expected {SAFE_WIDTH} (OOM above it)")
    if params.get("height") == SAFE_HEIGHT:
        ok(f"{tool}: height defaults to {SAFE_HEIGHT}")
    else:
        bad(f"{tool}: height defaults to {params.get('height')}, expected {SAFE_HEIGHT} (OOM above it)")

print("== unit_defaults: core and orchestrator ==")

# Every layer that carries its own width/height default, not just the MCP
# surface: the first pass of this fix missed orchestrator.py entirely, so the
# tool defaulted safely while the layer under it still defaulted to the OOM.
INTERNAL_DEFAULTS = {
    ("core.py", "submit_scene_core"),
    ("orchestrator.py", "generate_video"),
    ("orchestrator.py", "run_full_pipeline"),
    ("orchestrator.py", "run_studio_pipeline"),
}

for filename, func in sorted(INTERNAL_DEFAULTS):
    params = defaults_of(ROOT / "src" / "minimax_mcp" / filename, func)
    got = (params.get("width"), params.get("height"))
    if got == (SAFE_WIDTH, SAFE_HEIGHT):
        ok(f"{filename}:{func} defaults to {SAFE_WIDTH}x{SAFE_HEIGHT}")
    else:
        bad(
            f"{filename}:{func} defaults to {got[0]}x{got[1]}, "
            f"expected {SAFE_WIDTH}x{SAFE_HEIGHT}"
        )


def _sized_functions(path: Path) -> set[str]:
    """Functions in `path` that carry a *default* width or height.

    Required parameters are excluded: `inject_scene(*, width, height)` can't
    smuggle in a bad default because it has none — the caller always decides.
    Only defaults can be silently wrong.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"))
    found = set()
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        positional = node.args.args
        with_defaults = {
            arg.arg for arg in positional[len(positional) - len(node.args.defaults):]
        }
        with_defaults |= {
            arg.arg
            for arg, default in zip(node.args.kwonlyargs, node.args.kw_defaults)
            if default is not None
        }
        if with_defaults & {"width", "height"}:
            found.add(node.name)
    return found


# Catch a *new* sized function added without being listed above.
for filename in ("core.py", "orchestrator.py"):
    declared = {fn for mod, fn in INTERNAL_DEFAULTS if mod == filename}
    actual = _sized_functions(ROOT / "src" / "minimax_mcp" / filename)
    unlisted = actual - declared
    if unlisted:
        bad(f"{filename}: functions with width/height not covered by this test: {sorted(unlisted)}")
    else:
        ok(f"{filename}: every width/height function is covered")

print("== unit_defaults: base workflow ==")

workflow = json.loads((ROOT / "workflows" / "minimax_h3_t2v_api.json").read_text(encoding="utf-8"))
sizes = [
    (node_id, inputs.get("width"), inputs.get("height"))
    for node_id, node in workflow.items()
    if isinstance(node, dict)
    for inputs in [node.get("inputs") or {}]
    if "width" in inputs and "height" in inputs
]
if not sizes:
    bad("no node with width/height found in the base workflow")
for node_id, w, h in sizes:
    # inject_scene() overwrites these at submit time, but the file is also
    # loaded directly in the ComfyUI UI — where nothing overwrites it.
    if (w, h) == (SAFE_WIDTH, SAFE_HEIGHT):
        ok(f"workflow node {node_id}: {w}x{h}")
    else:
        bad(f"workflow node {node_id}: {w}x{h}, expected {SAFE_WIDTH}x{SAFE_HEIGHT}")

print("== unit_defaults: descriptions warn about the ceiling ==")

server_src = server_py.read_text(encoding="utf-8")
tree = ast.parse(server_src)
missing_warning = []
for node in ast.walk(tree):
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in SIZED_TOOLS:
        for arg, default in zip(
            node.args.args[len(node.args.args) - len(node.args.defaults):], node.args.defaults
        ):
            if arg.arg not in ("width", "height"):
                continue
            desc = ""
            if isinstance(default, ast.Call):
                for kw in default.keywords:
                    if kw.arg == "description" and isinstance(kw.value, ast.Constant):
                        desc = kw.value.value
            if "VRAM" not in desc and "OOM" not in desc:
                missing_warning.append(f"{node.name}.{arg.arg}")

if missing_warning:
    bad(f"width/height descriptions without a VRAM/OOM warning: {missing_warning}")
else:
    ok("every width/height description mentions the VRAM ceiling")

print()
if FAIL:
    print(f"FAIL: {FAIL}")
    sys.exit(1)
print("ALL PASS")
