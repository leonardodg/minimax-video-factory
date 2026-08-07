# Gerador de slash commands + documentação — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Gerar um slash command do OpenCode para cada uma das 18 tools MCP a partir do código, mais uma página de documentação, com um teste que quebra quando uma tool nova aparece sem comando.

**Architecture:** Um pipeline de quatro etapas puras, em `scripts/command_docs/`. `parser.py` lê `server.py` com `ast` e produz `ToolSpec`; `catalog.py` diz como cada tool se chama como comando; `overrides.py` carrega o conhecimento operacional que não está no código; `renderer.py` combina os três em markdown. `scripts/generate_commands.py` é só a CLI que orquestra e escreve. Nenhuma etapa importa `minimax_mcp` — o gerador roda sem GPU, sem ComfyUI, sem Postgres.

**Tech Stack:** Python ≥3.10 (stdlib `ast`, `dataclasses`, `pathlib`), pytest com marcador `unit`, ruff.

## Global Constraints

- **Não alterar `src/minimax_mcp/server.py`** nem qualquer tool. O gerador só lê.
- **Não tocar** em `.opencode/command/compress.md` e `.opencode/command/search-sessions.md` — não mapeiam para tools MCP e vivem numa allowlist explícita.
- O gerador roda **offline**: nada de importar `minimax_mcp`, nada de rede, nada de serviço de pé.
- **Idempotente**: rodar duas vezes produz bytes idênticos.
- Testes seguem a convenção do repositório: script `tests/unit_*.py` com `ok()`/`bad()` e `sys.exit(1)`, registrado em `tests/test_scripts.py` com `@pytest.mark.unit`. **Não** introduzir testes pytest-nativos — o repositório não usa esse estilo.
- Todo arquivo gerado começa com o cabeçalho de "não edite à mão", como `docs/MCP_TOOLS.md`.
- `uv run ruff check .` limpo ao fim de cada task. O projeto usa defaults do ruff com `ignore = ["BLE001", "B008"]`.
- Scripts de teste com shebang precisam de bit de execução (`chmod +x`), senão ruff acusa `EXE001`.
- Textos dos comandos em **português**; código, docstrings e mensagens de commit em inglês, como no resto do repositório.
- Trabalhar no worktree `.worktrees/slash-commands` (branch `feat/slash-commands`).

## Inventário congelado (18 tools)

Fonte da verdade para `catalog.py`. Se `server.py` mudar, o teste de cobertura acusa.

| Tool | Comando | Params (obrigatórios primeiro) |
|---|---|---|
| `health_check` | `minimax-health` | — |
| `submit_scene` | `minimax-submit-scene` | `prompt`; `duration=5.0`, `width=1024`, `height=576`, `seed=None`, `filename_prefix` |
| `get_status` | `minimax-status` | `prompt_id` |
| `wait_for_video` | `minimax-wait` | `prompt_id`; `timeout=1200.0` |
| `list_outputs` | `minimax-outputs` | — |
| `compose_final` | `minimax-compose` | `scene_paths`; `output_path="output/final.mp4"` |
| `download_video` | `minimax-download` | `url`; `browser="chrome"` |
| `transcribe_video` | `minimax-transcrever` | `video_path`; `model_size="small"`, `device="cuda"`, `language="pt"` |
| `create_cinematic_prompt` | `minimax-prompt-cinematico` | `transcription`; `style="cinematic"` |
| `generate_video` | `minimax-gerar-video` | `prompt`; `duration=10.0`, `width=1024`, `height=576`, `seed=None`, `filename_prefix="studio/"` |
| `studio_pipeline` | `minimax-studio` | `url`; `style="cinematic"`, `duration=10.0`, `width=1024`, `height=576` |
| `knowledge_ingest_text` | `kb-ingest-texto` | `text`; `source_url=None`, `title=None`, `platform="manual"` |
| `knowledge_ingest_markdown` | `kb-ingest-markdown` | `path`; `recursive=False`, `doc_type="document"` |
| `knowledge_ingest_video` | `kb-ingest-video` | `url`; `browser`, `whisper_model` |
| `knowledge_ingest_audio` | `kb-ingest-audio` | `path_or_url`; `browser`, `whisper_model` |
| `knowledge_search` | `kb-buscar` | `query`; `top_k=5` |
| `knowledge_ask` | `kb-perguntar` | `query`; `top_k=3` |
| `knowledge_reindex` | `kb-reindex` | `embedding_model=None` |

`wait_for_video` é `async def` e `get_status`/`wait_for_video` têm parâmetros
sem `Field(...)` (`prompt_id: str` cru) — os dois casos precisam ser tratados
pelo parser.

## Contratos entre as camadas

Definidos na Task 1 e consumidos por todas as seguintes:

```python
@dataclass(frozen=True)
class ParamSpec:
    name: str
    type_hint: str          # "str", "int | None", "list[str]"
    default_repr: str | None  # "'chrome'", "5.0", "None"; None se obrigatório
    description: str        # do Field(description=...), "" se ausente
    required: bool

@dataclass(frozen=True)
class ToolSpec:
    tool_name: str
    docstring: str
    params: tuple[ParamSpec, ...]   # ordem da assinatura
    is_async: bool
```

```python
@dataclass(frozen=True)
class Override:
    resumo: str = ""                        # frontmatter description
    param_notas: Mapping[str, str] = ...    # anexado à linha do parâmetro
    params_extra: Mapping[str, str] = ...   # params que não existem na tool
    passos: tuple[str, ...] = ()            # passos numerados extras, ordenados
```

`params_extra` existe porque `/minimax-download` aceita `transcrever`,
`model_size` e `language` — que pertencem a `transcribe_video`, não a
`download_video`. O comando encadeia duas tools, e sem esse campo a absorção
perderia metade da interface dele.

## File Structure

| Arquivo | Responsabilidade |
|---|---|
| `scripts/command_docs/__init__.py` | Reexporta `ToolSpec`, `ParamSpec`, `Override` |
| `scripts/command_docs/parser.py` | `ast` → `list[ToolSpec]`. Não conhece markdown |
| `scripts/command_docs/catalog.py` | `tool_name` → nome do comando + grupo. A única lista escrita à mão |
| `scripts/command_docs/overrides.py` | Conhecimento operacional por tool. Dados, sem lógica |
| `scripts/command_docs/renderer.py` | `ToolSpec` + `Override` + nome → markdown. Puro, sem I/O |
| `scripts/generate_commands.py` | CLI: lê, renderiza, escreve, relata. O único com I/O |
| `tests/unit_commands.py` | Parser, catálogo, renderer, cobertura, idempotência |
| `.opencode/command/*.md` | 18 arquivos gerados |
| `docs/COMMANDS.md` | Página gerada |

---

### Task 1: Parser AST → ToolSpec

**Files:**
- Create: `scripts/command_docs/__init__.py`
- Create: `scripts/command_docs/parser.py`
- Create: `tests/unit_commands.py`
- Modify: `tests/test_scripts.py`

**Interfaces:**
- Consumes: nada.
- Produces: `ParamSpec`, `ToolSpec` (campos acima) e `parse_tools(source: Path) -> list[ToolSpec]`, que retorna as tools na ordem em que aparecem no arquivo.

- [ ] **Step 1: Criar o pacote**

```bash
cd $PROJECT_ROOT/.worktrees/slash-commands
mkdir -p scripts/command_docs
```

Criar `scripts/command_docs/__init__.py`:

```python
"""Offline generator for OpenCode slash commands, driven by the MCP registry.

Nothing here imports `minimax_mcp`: the tools are read out of the source with
`ast`, so the generator runs with no GPU, no ComfyUI and no database.
"""
from scripts.command_docs.parser import ParamSpec, ToolSpec, parse_tools

__all__ = ["ParamSpec", "ToolSpec", "parse_tools"]
```

- [ ] **Step 2: Escrever o teste falhando**

Criar `tests/unit_commands.py`:

```python
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

from scripts.command_docs.parser import parse_tools  # noqa: E402

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

if len(SPECS) == 18:
    ok("found all 18 @mcp.tool() functions")
else:
    bad(f"found {len(SPECS)} tools, expected 18: {sorted(SPECS)}")

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

print()
if FAIL:
    print(f"FAIL: {FAIL}")
    sys.exit(1)
print("ALL PASS")
```

- [ ] **Step 3: Rodar o teste e confirmar que falha**

```bash
chmod +x tests/unit_commands.py
python3 tests/unit_commands.py
```
Expected: FAIL com `ModuleNotFoundError: No module named 'scripts.command_docs.parser'`

- [ ] **Step 4: Escrever `scripts/command_docs/parser.py`**

```python
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
        if isinstance(target, ast.Attribute) and isinstance(target.value, ast.Name):
            if f"{target.value.id}.{target.attr}" == TOOL_DECORATOR:
                return True
    return False


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


def _callee_name(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return ""


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
    """Return every @mcp.tool() function in `source`, in file order."""
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
```

- [ ] **Step 5: Rodar o teste e confirmar que passa**

Run: `python3 tests/unit_commands.py`
Expected: `ALL PASS` com 13 `[ok]`.

Se `found N tools, expected 18` falhar, `server.py` mudou desde este plano —
atualize o inventário congelado antes de seguir, não o número no teste.

- [ ] **Step 6: Registrar em `tests/test_scripts.py`**

Adicionar depois de `test_unit_defaults`:

```python
@pytest.mark.unit
def test_unit_commands():
    result = _run_script("unit_commands.py")
    assert result.returncode == 0, result.stdout + result.stderr
```

- [ ] **Step 7: Rodar a suíte e o lint**

```bash
uv run pytest -m unit -q
uv run ruff check .
```
Expected: 8 passed; ruff limpo.

- [ ] **Step 8: Commit**

```bash
git add scripts/command_docs tests/unit_commands.py tests/test_scripts.py
git commit -m "feat(commands): AST parser that extracts MCP tool signatures"
```

---

### Task 2: Catálogo de nomes

**Files:**
- Create: `scripts/command_docs/catalog.py`
- Modify: `tests/unit_commands.py`

**Interfaces:**
- Consumes: `ToolSpec` da Task 1.
- Produces: `COMMAND_NAMES: dict[str, str]`, `command_name(tool: str) -> str` (levanta `KeyError` com mensagem útil se faltar), `group_of(command: str) -> str` retornando `"video"` ou `"kb"`, e `GROUP_TITLES: dict[str, str]`.

- [ ] **Step 1: Escrever os testes falhando**

Adicionar em `tests/unit_commands.py`, antes do bloco final de `print()`:

```python
print("== unit_commands: catalog ==")

from scripts.command_docs import catalog  # noqa: E402

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

if catalog.group_of("kb-buscar") == "kb" and catalog.group_of("minimax-health") == "video":
    ok("group_of splits the two product areas")
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
```

- [ ] **Step 2: Rodar e confirmar que falha**

Run: `python3 tests/unit_commands.py`
Expected: FAIL — `ModuleNotFoundError: ... catalog`

- [ ] **Step 3: Escrever `scripts/command_docs/catalog.py`**

```python
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
```

- [ ] **Step 4: Rodar o teste e confirmar que passa**

Run: `python3 tests/unit_commands.py`
Expected: `ALL PASS`, agora com 20 `[ok]`.

- [ ] **Step 5: Lint e commit**

```bash
uv run ruff check .
git add scripts/command_docs/catalog.py tests/unit_commands.py
git commit -m "feat(commands): catalog mapping each tool to its slash-command name"
```

---

### Task 3: Overrides — absorver o conhecimento curado

**Files:**
- Create: `scripts/command_docs/overrides.py`
- Modify: `tests/unit_commands.py`
- Modify: `docs/superpowers/specs/2026-08-07-slash-commands-generator-design.md`

**Interfaces:**
- Consumes: nada (dados puros).
- Produces: `Override` (dataclass congelada) e `OVERRIDES: dict[str, Override]`.

Esta é a task de maior risco do plano: é aqui que o texto validado em uso dos
três comandos existentes vira dado. Cada fato dos originais precisa aparecer
em algum campo do override.

- [ ] **Step 1: Escrever os testes falhando**

Adicionar em `tests/unit_commands.py`:

```python
print("== unit_commands: overrides ==")

from scripts.command_docs.overrides import OVERRIDES  # noqa: E402

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
    blob = " ".join([ov.resumo, *ov.param_notas.values(), *ov.params_extra.values(), *ov.passos])
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
```

- [ ] **Step 2: Rodar e confirmar que falha**

Run: `python3 tests/unit_commands.py`
Expected: FAIL — módulo `overrides` não existe.

- [ ] **Step 3: Escrever `scripts/command_docs/overrides.py`**

O conteúdo abaixo dos três primeiros veio de
`.opencode/command/minimax-{download,transcrever,gerar-video}.md`. Confira
contra os originais antes de apagar qualquer coisa.

```python
"""Operational knowledge the AST cannot see.

A tool signature says a parameter is an int with a default. It does not say
that raising it OOMs the card, that an error message means "close your
browser", or that a slow tool needs a two-call workaround. That knowledge was
learned by using the thing, and it lives here.

Every field is optional: a tool with no entry still generates a valid command,
just a drier one.
"""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Override:
    resumo: str = ""
    param_notas: Mapping[str, str] = field(default_factory=dict)
    params_extra: Mapping[str, str] = field(default_factory=dict)
    passos: tuple[str, ...] = ()


OVERRIDES: dict[str, Override] = {
    # ---------------------------------------------------------------- video
    "download_video": Override(
        resumo=(
            "Baixa um vídeo (Instagram Reel, YouTube) via MCP yt-dlp, "
            "opcionalmente transcreve com Whisper"
        ),
        param_notas={
            "browser": (
                'Se der erro de "database locked", oriente a fechar o navegador'
            ),
        },
        # This command chains into transcribe_video, so it accepts parameters
        # that download_video itself does not have.
        params_extra={
            "transcrever": "flag — se presente, transcreva o vídeo baixado com Whisper",
            "model_size": "tiny/base/small/medium/large-v3 (default `small`), se for transcrever",
            "language": "código do idioma (default `pt`), se for transcrever",
        },
        passos=(
            "Reporte o arquivo salvo (dir `downloads/`), título, duração e uploader.",
            "Se `transcrever` foi pedido, chame `transcribe_video` com o caminho "
            "baixado (GPU, `device=cuda`) e reporte o texto + segmentos com "
            "timestamps. Alternativamente, o usuário pode usar o comando dedicado "
            "`/minimax-transcrever <arquivo>` depois.",
            "Não gere vídeo a menos que o usuário peça explicitamente.",
        ),
    ),
    "transcribe_video": Override(
        resumo="Transcreve um vídeo local com Whisper (faster-whisper, GPU)",
        param_notas={
            "video_path": (
                "aceita path do host, ex.: `downloads/Video.mp4`; se vier relativo, "
                "assuma relativo ao diretório do projeto "
                "(`$PROJECT_ROOT`)"
            ),
            "model_size": "tiny/base/small/medium/large-v3",
        },
        passos=(
            "Reporte o texto transcrito + segmentos com timestamps + idioma detectado.",
            "Não gere vídeo nem crie prompt a menos que o usuário peça.",
        ),
    ),
    "generate_video": Override(
        resumo="Gera um vídeo no MiniMax H3 (texto→vídeo com áudio nativo estéreo) via MCP",
        param_notas={
            "duration": "4-15s; o servidor arredonda para a grade de 17 frames",
            "width": (
                "não suba de 1024 — 1344x768 dá OOM no sampler com 12 GB VRAM "
                "(`torch.OutOfMemoryError`). 512x320 é o mais rápido (~5 min)"
            ),
            "height": "não suba de 576 pelo mesmo motivo de VRAM",
        },
        passos=(
            "Se `prompt` vier em PT, traduza para uma descrição visual EN rica "
            "antes de chamar a tool.",
            "Aguarde o render completar (5-20 min; use `wait_for_video` se a tool "
            "retornar só o prompt_id). Reporte o caminho final do vídeo (host, via "
            "`OUTPUT_HOST_DIR`) e o prompt_id.",
            "Se houver erro de OOM, reduza para 512x320 e tente novamente.",
            "Se a tool travar com timeout de client MCP, chame primeiro "
            "`submit_scene` e depois `wait_for_video(prompt_id)` em separado.",
        ),
    ),
    "submit_scene": Override(
        resumo="Enfileira uma cena no ComfyUI e devolve o prompt_id, sem esperar o render",
        param_notas={
            "width": "não suba de 1024 — OOM no sampler com 12 GB VRAM",
            "height": "não suba de 576 pelo mesmo motivo de VRAM",
        },
        passos=(
            "Reporte o `prompt_id`. O render NÃO terminou: use "
            "`/minimax-wait <prompt_id>` para aguardar, ou `/minimax-status "
            "<prompt_id>` para checar sem bloquear.",
        ),
    ),
    "wait_for_video": Override(
        resumo="Bloqueia até um render terminar e devolve o caminho do .mp4",
        param_notas={
            "timeout": "default 1200s (20 min); renders de 1024x576 levam 5-20 min",
        },
        passos=(
            "Este comando BLOQUEIA. Se o usuário só quer saber o estado agora, "
            "use `/minimax-status` em vez deste.",
        ),
    ),
    "get_status": Override(
        resumo="Checa o estado de um render já submetido, sem bloquear",
        passos=(
            "Reporte o estado (`queued`, `running`, `completed`, `error`) e, se "
            "completo, o caminho do arquivo.",
        ),
    ),
    "health_check": Override(
        resumo="Verifica o ComfyUI e a presença dos modelos MiniMax H3",
        passos=(
            "Rode isto ANTES de um render longo: descobrir que falta um modelo "
            "depois de 20 minutos de espera é o desperdício que este comando evita.",
            "Se algum modelo estiver ausente, aponte `scripts/download_models.sh`.",
        ),
    ),
    "list_outputs": Override(
        resumo="Lista os vídeos .mp4 já gerados, do mais recente para o mais antigo",
    ),
    "compose_final": Override(
        resumo="Concatena cenas .mp4 em um vídeo final com ffmpeg",
        param_notas={
            "scene_paths": "ordem importa — é a ordem em que as cenas aparecem",
        },
        passos=("São necessárias ao menos 2 cenas; com menos, a tool recusa.",),
    ),
    "create_cinematic_prompt": Override(
        resumo="Converte uma transcrição em um prompt estruturado do MiniMax H3",
        param_notas={"style": "cinematic, educational ou social"},
        passos=(
            "Isto só monta o prompt — não gera vídeo. Para gerar, passe o "
            "resultado para `/minimax-gerar-video`.",
        ),
    ),
    "studio_pipeline": Override(
        resumo="Pipeline completo: URL → download → transcrição → prompt → vídeo",
        param_notas={
            "width": "não suba de 1024 — OOM no sampler com 12 GB VRAM",
            "height": "não suba de 576 pelo mesmo motivo de VRAM",
        },
        passos=(
            "É o mais demorado de todos (download + Whisper + render). Avise o "
            "usuário antes de começar.",
            "Reporte cada etapa conforme concluir, não só o resultado final.",
        ),
    ),
    # ------------------------------------------------------------------- kb
    "knowledge_ingest_text": Override(
        resumo="Resume e documenta um texto na base de conhecimento com a IA local",
        passos=(
            "Reporte o `document_id`, o título e as tags geradas.",
        ),
    ),
    "knowledge_ingest_markdown": Override(
        resumo="Importa arquivos markdown (ex.: Obsidian) para a base de conhecimento",
        param_notas={
            "path": "arquivo .md ou diretório; diretórios com ponto (.obsidian, .trash) são ignorados",
            "recursive": "cuidado ao apontar para um vault inteiro — pode ser milhares de arquivos",
        },
        passos=(
            "Quando a nota já tem uma seção `## Summary`, esse texto é "
            "reaproveitado e o LLM é pulado — é o que torna a importação em massa "
            "viável (minutos em vez de horas).",
            "Reporte quantos arquivos foram importados de quantos encontrados.",
        ),
    ),
    "knowledge_ingest_video": Override(
        resumo="Baixa, transcreve e documenta um vídeo na base de conhecimento",
        passos=(
            "Leva minutos: download + Whisper + LLM. Avise o usuário.",
        ),
    ),
    "knowledge_ingest_audio": Override(
        resumo="Transcreve e documenta um áudio/podcast na base de conhecimento",
        param_notas={
            "path_or_url": "caminho local OU URL; se for URL, baixa antes de transcrever",
        },
    ),
    "knowledge_search": Override(
        resumo="Busca na base de conhecimento (palavra-chave + semântica)",
        passos=(
            "Reporte título, trechos e URL de origem de cada resultado, para o "
            "usuário conseguir voltar à fonte.",
        ),
    ),
    "knowledge_ask": Override(
        resumo="Responde uma pergunta usando RAG sobre a base de conhecimento",
        passos=(
            "A resposta vem APENAS da base. Se ela disser que não sabe, isso é o "
            "comportamento correto — não complete com conhecimento próprio.",
            "Sempre mostre as fontes junto da resposta.",
        ),
    ),
    "knowledge_reindex": Override(
        resumo="Recalcula chunks e embeddings de todos os documentos da base",
        param_notas={
            "embedding_model": "default: EMBEDDING_MODEL do .env",
        },
        passos=(
            "Rode depois de trocar o modelo de embedding: vetores antigos não são "
            "comparáveis com os novos, e a busca degrada em silêncio até reindexar.",
            "Percorre a base inteira — pode demorar proporcionalmente ao tamanho dela.",
        ),
    ),
}
```

- [ ] **Step 4: Conferir contra os originais, fato a fato**

```bash
for f in minimax-download minimax-transcrever minimax-gerar-video; do
  echo "───────── $f"
  cat .opencode/command/$f.md
done
```

Marque cada item ao confirmar que ele existe em `overrides.py`:

- [ ] `minimax-download`: "database locked" → fechar navegador
- [ ] `minimax-download`: flag `transcrever` + `model_size` + `language`
- [ ] `minimax-download`: reportar arquivo, título, duração, uploader
- [ ] `minimax-download`: apontar `/minimax-transcrever` como alternativa
- [ ] `minimax-download`: não gerar vídeo sem pedido
- [ ] `minimax-transcrever`: aceita path do host, relativo ao projeto
- [ ] `minimax-transcrever`: lista de modelos tiny→large-v3
- [ ] `minimax-transcrever`: reportar texto + timestamps + idioma
- [ ] `minimax-gerar-video`: traduzir PT→EN antes de chamar
- [ ] `minimax-gerar-video`: 4-15s, grade de 17 frames
- [ ] `minimax-gerar-video`: teto de VRAM e 512x320 como o mais rápido
- [ ] `minimax-gerar-video`: aguardar 5-20 min, reportar caminho + prompt_id
- [ ] `minimax-gerar-video`: retry de OOM
- [ ] `minimax-gerar-video`: contorno `submit_scene` + `wait_for_video`

Se algo não couber em nenhum campo, **pare e ajuste o `Override`** — perder
uma dessas linhas é o risco que esta task inteira existe para evitar.

- [ ] **Step 5: Rodar o teste e confirmar que passa**

Run: `python3 tests/unit_commands.py`
Expected: `ALL PASS`.

- [ ] **Step 6: Sincronizar a spec**

Em `docs/superpowers/specs/2026-08-07-slash-commands-generator-design.md`,
a tabela "Um override contribui em três posições distintas" agora tem quatro.
Adicionar a linha:

```markdown
| `params_extra` | linha de uso + extração, como opcionais | `transcrever` no `/minimax-download` |
```

E ajustar o texto de "três posições" para "quatro posições", explicando que
`params_extra` existe porque `/minimax-download` encadeia `transcribe_video`.

- [ ] **Step 7: Lint e commit**

```bash
uv run ruff check .
git add scripts/command_docs/overrides.py tests/unit_commands.py docs/superpowers/specs/
git commit -m "feat(commands): curated overrides, absorbing the three hand-written commands"
```

---

### Task 4: Renderer

**Files:**
- Create: `scripts/command_docs/renderer.py`
- Modify: `tests/unit_commands.py`

**Interfaces:**
- Consumes: `ToolSpec` (Task 1), `Override` (Task 3), nomes (Task 2).
- Produces:
  - `render_usage(spec, override, command) -> str` — a linha `Uso: /cmd ...`
  - `render_command(spec, override, command) -> str` — o `.md` completo
  - `MCP_SERVER = "minimax-video-factory"`

- [ ] **Step 1: Escrever os testes falhando**

Adicionar em `tests/unit_commands.py`:

```python
print("== unit_commands: renderer ==")

from scripts.command_docs import renderer  # noqa: E402

dl_md = renderer.render_command(SPECS["download_video"], OVERRIDES["download_video"], "minimax-download")

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

usage = renderer.render_usage(SPECS["download_video"], OVERRIDES["download_video"], "minimax-download")
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

# Required before optional in the extraction list.
body = dl_md.split("Instruções obrigatórias:")[1]
if body.index("`url`") < body.index("`browser`"):
    ok("extraction list puts required parameters before optional ones")
else:
    bad("extraction list ordering is wrong")

if "database locked" in dl_md:
    ok("param_notas are appended to their parameter's line")
else:
    bad("param_notas did not reach the rendered command")

gen_md = renderer.render_command(SPECS["generate_video"], OVERRIDES["generate_video"], "minimax-gerar-video")
step_lines = [ln for ln in gen_md.splitlines() if ln[:2].strip().rstrip(".").isdigit()]
if len(step_lines) >= 6:
    ok("override passos become numbered steps, in order")
else:
    bad(f"generate_video rendered only {len(step_lines)} numbered steps")

if gen_md.index("traduza") < gen_md.index("OOM"):
    ok("passos keep their declared order")
else:
    bad("passos were reordered")

# A tool with no parameters and no override must still render.
health_md = renderer.render_command(SPECS["health_check"], OVERRIDES["health_check"], "minimax-health")
if "$ARGUMENTS" in health_md and "health_check" in health_md:
    ok("a zero-parameter tool renders a valid command")
else:
    bad("zero-parameter tool rendered badly")

from scripts.command_docs.overrides import Override as _Ov  # noqa: E402
bare = renderer.render_command(SPECS["list_outputs"], _Ov(), "minimax-outputs")
if bare.startswith("---\ndescription: ") and "$ARGUMENTS" in bare:
    ok("a tool with an empty override still renders")
else:
    bad("empty override broke the renderer")
```

- [ ] **Step 2: Rodar e confirmar que falha**

Run: `python3 tests/unit_commands.py`
Expected: FAIL — `renderer` não existe.

- [ ] **Step 3: Escrever `scripts/command_docs/renderer.py`**

```python
"""Turn a ToolSpec plus its Override into an OpenCode command file.

Pure string building: no file I/O, so every shape can be unit-tested. The
layout mirrors the three commands that were hand-written and used in anger --
frontmatter with a usage line, $ARGUMENTS, then numbered instructions.
"""
from __future__ import annotations

from scripts.command_docs.overrides import Override
from scripts.command_docs.parser import ParamSpec, ToolSpec

MCP_SERVER = "minimax-video-factory"

# Every command carries this: the user runs several server variants and the
# default one is not always the live one.
FALLBACK_STEP = (
    "Chame `{tool}` com esses parâmetros. Se a variante default do servidor MCP "
    "estiver indisponível, use a variante conectada (`{server}-remote` ou `{server}-uv`)."
)


def _sorted_params(spec: ToolSpec) -> tuple[list[ParamSpec], list[ParamSpec]]:
    required = [p for p in spec.params if p.required]
    optional = [p for p in spec.params if not p.required]
    return required, optional


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
        f"[{p.name}={_unquote(p.default_repr)}]" if p.default_repr not in (None, "None")
        else f"[{p.name}]"
        for p in optional
    ]
    parts += [f"[{name}]" for name in override.params_extra]
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


def _param_line(param: ParamSpec, override: Override) -> str:
    note = override.param_notas.get(param.name, "")
    desc = param.description or ""
    if param.required:
        line = f"   - `{param.name}` (obrigatória)"
        line += f" — {desc}" if desc else ""
    else:
        line = f"   - `{param.name}`: {desc}" if desc else f"   - `{param.name}`"
        if param.default_repr is not None:
            line += f" (default `{_unquote(param.default_repr)}`)"
    if note:
        line = line.rstrip(".") + f". {note}"
    return line.rstrip(".") + "."


def render_command(spec: ToolSpec, override: Override, command: str) -> str:
    """The complete .md body for one slash command."""
    summary = _summary(spec, override)
    usage = render_usage(spec, override, command)
    required, optional = _sorted_params(spec)

    lines = [
        "---",
        f"description: {summary}. Uso: {usage}",
        "---",
        "",
        f"Execute a ferramenta MCP **`{MCP_SERVER}_{spec.tool_name}`** "
        f"(server `{MCP_SERVER}`).",
        "",
        "Entrada do usuário (tudo depois do comando):",
        "$ARGUMENTS",
        "",
        "Instruções obrigatórias:",
    ]

    step = 1
    if required or optional or override.params_extra:
        lines.append(f"{step}. Extraia:")
        for param in required + optional:
            lines.append(_param_line(param, override))
        for name, desc in override.params_extra.items():
            lines.append(f"   - `{name}`: {desc}.")
        step += 1

    lines.append(
        f"{step}. " + FALLBACK_STEP.format(tool=spec.tool_name, server=MCP_SERVER)
    )
    step += 1

    for passo in override.passos:
        lines.append(f"{step}. {passo}")
        step += 1

    if not override.passos:
        lines.append(f"{step}. Reporte o resultado da tool ao usuário.")

    return "\n".join(lines) + "\n"
```

- [ ] **Step 4: Rodar o teste e confirmar que passa**

Run: `python3 tests/unit_commands.py`
Expected: `ALL PASS`.

- [ ] **Step 5: Lint e commit**

```bash
uv run ruff check .
git add scripts/command_docs/renderer.py tests/unit_commands.py
git commit -m "feat(commands): renderer turning tool specs into OpenCode command files"
```

---

### Task 5: CLI e geração dos 18 comandos

**Files:**
- Create: `scripts/generate_commands.py`
- Generate: 18 arquivos em `.opencode/command/`

**Interfaces:**
- Consumes: tudo das Tasks 1-4.
- Produces: o executável `uv run python scripts/generate_commands.py`, com `--check` para CI (não escreve, sai != 0 se algo estiver desatualizado).

- [ ] **Step 1: Escrever `scripts/generate_commands.py`**

```python
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

from scripts.command_docs import catalog, renderer  # noqa: E402
from scripts.command_docs.overrides import OVERRIDES, Override  # noqa: E402
from scripts.command_docs.parser import parse_tools  # noqa: E402

SERVER_PY = ROOT / "src" / "minimax_mcp" / "server.py"
COMMAND_DIR = ROOT / ".opencode" / "command"

GENERATED_HEADER = (
    "<!-- GERADO AUTOMATICAMENTE por scripts/generate_commands.py -->\n"
    "<!-- Não edite à mão: rode `uv run python scripts/generate_commands.py`. -->\n"
)


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
    return outputs


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="do not write; exit non-zero if any output is stale",
    )
    args = parser.parse_args()

    outputs = build()
    stale = [p for p, content in outputs.items()
             if not p.exists() or p.read_text(encoding="utf-8") != content]

    if args.check:
        if stale:
            print("stale, run scripts/generate_commands.py:")
            for p in sorted(stale):
                print(f"  {p.relative_to(ROOT)}")
            return 1
        print(f"up to date ({len(outputs)} commands)")
        return 0

    COMMAND_DIR.mkdir(parents=True, exist_ok=True)
    for path, content in outputs.items():
        path.write_text(content, encoding="utf-8")

    missing_notes = [
        f"{spec.tool_name}.{p.name}"
        for spec in parse_tools(SERVER_PY)
        for p in spec.params
        if not p.description and not OVERRIDES.get(spec.tool_name, Override()).param_notas.get(p.name)
    ]
    print(f"wrote {len(outputs)} commands to {COMMAND_DIR.relative_to(ROOT)}")
    if missing_notes:
        print("parameters with no description anywhere (consider an override):")
        for name in missing_notes:
            print(f"  {name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 2: Guardar os três originais antes de sobrescrevê-los**

```bash
BEFORE=$(mktemp -d)
cp .opencode/command/minimax-download.md \
   .opencode/command/minimax-transcrever.md \
   .opencode/command/minimax-gerar-video.md "$BEFORE/"
echo "originais em $BEFORE"
```

- [ ] **Step 3: Gerar**

```bash
chmod +x scripts/generate_commands.py
uv run python scripts/generate_commands.py
ls .opencode/command/
```
Expected: 20 arquivos — 18 gerados + `compress.md` + `search-sessions.md`.

- [ ] **Step 4: Comparar os três absorvidos, lado a lado**

```bash
for f in minimax-download minimax-transcrever minimax-gerar-video; do
  echo "═════════ $f"
  diff -u "$BEFORE/$f.md" ".opencode/command/$f.md" || true
done
```

O diff **vai** mostrar diferenças de forma — é esperado, o formato agora é
uniforme. O que não pode aparecer é **fato removido**. Percorra a checklist do
Step 4 da Task 3 contra os arquivos novos. Se algo sumiu, o conserto é em
`overrides.py`, nunca editando o `.md` gerado.

- [ ] **Step 5: Ler um comando gerado por inteiro**

```bash
cat .opencode/command/kb-perguntar.md
cat .opencode/command/minimax-gerar-video.md
```

Confira que se lê como instrução para um agente, não como despejo de schema.
Se estiver seco demais, o conserto é `overrides.py`.

- [ ] **Step 6: Verificar idempotência**

```bash
uv run python scripts/generate_commands.py
git diff --stat .opencode/command/
```
Expected: nenhuma mudança na segunda rodada.

- [ ] **Step 7: Verificar o modo `--check`**

```bash
uv run python scripts/generate_commands.py --check; echo "exit=$?"
printf '\nlixo\n' >> .opencode/command/minimax-health.md
uv run python scripts/generate_commands.py --check; echo "exit=$?"
uv run python scripts/generate_commands.py
```
Expected: `exit=0`, depois `exit=1` listando `minimax-health.md`, e a última
rodada restaura o arquivo.

- [ ] **Step 8: Lint e commit**

```bash
uv run ruff check .
git add scripts/generate_commands.py .opencode/command/
git commit -m "feat(commands): generate all 18 OpenCode slash commands from the MCP tools"
```

---

### Task 6: Página `docs/COMMANDS.md` e nav do MkDocs

**Files:**
- Modify: `scripts/generate_commands.py`
- Modify: `scripts/command_docs/renderer.py`
- Modify: `mkdocs.yml`
- Generate: `docs/COMMANDS.md`

**Interfaces:**
- Produces: `renderer.render_catalog_page(entries) -> str`, onde `entries` é uma lista de `(command, spec, override)` já ordenada.

- [ ] **Step 1: Escrever o teste falhando**

Adicionar em `tests/unit_commands.py`:

```python
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

if page.index("Pipeline de vídeo") < page.index("/kb-buscar"):
    ok("video group precedes the knowledge-base group")
else:
    bad("group order is wrong on the catalog page")
```

- [ ] **Step 2: Rodar e confirmar que falha**

Run: `python3 tests/unit_commands.py`
Expected: FAIL — `render_catalog_page` não existe.

- [ ] **Step 3: Adicionar `render_catalog_page` ao renderer**

```python
GENERATED_HEADER = (
    "<!-- GERADO AUTOMATICAMENTE por scripts/generate_commands.py -->\n"
    "<!-- Não edite à mão: rode `uv run python scripts/generate_commands.py`. -->\n"
)

GROUP_ORDER = ("video", "kb")


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
        "Um comando do OpenCode para cada ferramenta MCP. Esta página descreve o "
        "uso humano; a referência de programação das tools está em "
        "[MCP Tools Reference](MCP_TOOLS.md).",
        "",
        "| Comando | Tool | O que faz |",
        "|---|---|---|",
    ]
    for command, spec, override in entries:
        summary = override.resumo or (spec.docstring.splitlines()[0] if spec.docstring else "")
        lines.append(f"| `/{command}` | `{spec.tool_name}` | {summary.rstrip('.')} |")
    lines.append("")

    for group in GROUP_ORDER:
        in_group = [e for e in entries if group_of(e[0]) == group]
        if not in_group:
            continue
        lines += [f"## {GROUP_TITLES[group]}", ""]
        for command, spec, override in in_group:
            usage = render_usage(spec, override, command)
            lines += [
                f"### `/{command}`",
                "",
                (override.resumo or spec.docstring.splitlines()[0] if spec.docstring or override.resumo else ""),
                "",
                "```",
                usage,
                "```",
                "",
            ]
            required, optional = _sorted_params(spec)
            if required or optional or override.params_extra:
                lines += ["| Parâmetro | Obrigatório | Default | Descrição |", "|---|---|---|---|"]
                for p in required + optional:
                    default = "—" if p.default_repr is None else f"`{_unquote(p.default_repr)}`"
                    note = override.param_notas.get(p.name, "")
                    desc = " ".join(x for x in (p.description, note) if x).replace("|", "\\|")
                    lines.append(f"| `{p.name}` | {'sim' if p.required else 'não'} | {default} | {desc} |")
                for name, desc in override.params_extra.items():
                    lines.append(f"| `{name}` | não | — | {desc.replace('|', chr(92) + '|')} |")
                lines.append("")
            if override.passos:
                lines += ["**Notas operacionais:**", ""]
                lines += [f"- {passo}" for passo in override.passos]
                lines.append("")

    return "\n".join(lines) + "\n"
```

- [ ] **Step 4: Ligar na CLI**

Em `scripts/generate_commands.py`, dentro de `build()`, antes do `return`:

```python
    entries = sorted(
        (catalog.command_name(spec.tool_name), spec, OVERRIDES.get(spec.tool_name, Override()))
        for spec in specs
    )
    outputs[ROOT / "docs" / "COMMANDS.md"] = renderer.render_catalog_page(entries)
```

E trocar a mensagem final de `main()` para refletir os dois destinos:

```python
    print(f"wrote {len(outputs) - 1} commands + docs/COMMANDS.md")
```

- [ ] **Step 5: Gerar e conferir**

```bash
uv run python scripts/generate_commands.py
python3 tests/unit_commands.py
head -40 docs/COMMANDS.md
```
Expected: `ALL PASS`, e a tabela geral com 18 linhas.

- [ ] **Step 6: Adicionar ao nav do MkDocs**

Em `mkdocs.yml`, dentro de `User Guides`, depois de `MCP Tools Reference`:

```yaml
      - Slash Commands: COMMANDS.md
```

- [ ] **Step 7: Build do site**

```bash
uv sync --extra docs 2>/dev/null || true
uv run mkdocs build 2>&1 | tail -5
```
Expected: build sem warning de link quebrado.

- [ ] **Step 8: Lint e commit**

```bash
uv run ruff check .
git add scripts/ docs/COMMANDS.md mkdocs.yml tests/unit_commands.py
git commit -m "docs(commands): generated COMMANDS.md page wired into the MkDocs nav"
```

---

### Task 7: Trava contra deriva

**Files:**
- Modify: `tests/unit_commands.py`
- Modify: `AGENTS.md`, `README.md`

**Interfaces:**
- Produces: um teste que falha quando uma tool nova não tem comando, ou quando os arquivos gerados estão desatualizados.

Sem esta task, o gerador é uma ferramenta que alguém precisa lembrar de rodar —
e é exatamente por não lembrar que as 7 tools de knowledge base ficaram sem
comando por dias.

- [ ] **Step 1: Escrever os testes falhando**

Adicionar ao fim de `tests/unit_commands.py`, antes do bloco de saída:

```python
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
import generate_commands  # noqa: E402

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
```

- [ ] **Step 2: Rodar e confirmar que passa**

Run: `python3 tests/unit_commands.py`
Expected: `ALL PASS`. Se `stale` acusar algo, rode o gerador — é o teste
fazendo o trabalho dele.

- [ ] **Step 3: Provar que a trava realmente trava**

Simule uma tool nova sem comando:

```bash
python3 - <<'EOF'
from pathlib import Path
p = Path("src/minimax_mcp/server.py")
p.write_text(p.read_text() + '''

@mcp.tool()
def tool_de_teste_temporaria(x: str = Field(description="teste")) -> dict:
    """Ferramenta temporária para provar que a trava funciona."""
    return {"ok": True}
''', encoding="utf-8")
EOF
python3 tests/unit_commands.py; echo "exit=$?"
git checkout src/minimax_mcp/server.py
python3 tests/unit_commands.py | tail -2
```
Expected: a rodada do meio falha citando `tool_de_teste_temporaria`; depois do
`git checkout`, volta a `ALL PASS`.

- [ ] **Step 4: Documentar o fluxo em `AGENTS.md`**

Na seção que descreve como adicionar uma tool, acrescentar:

```markdown
Ao adicionar ou alterar uma `@mcp.tool()`:

1. Dê um nome de comando a ela em `scripts/command_docs/catalog.py`.
2. Se houver conhecimento operacional que a assinatura não expressa (limites de
   hardware, mensagens de erro conhecidas, encadeamento com outra tool),
   registre em `scripts/command_docs/overrides.py`.
3. Rode `uv run python scripts/generate_commands.py`.
4. Commite os `.md` gerados junto com a tool.

`tests/unit_commands.py` falha se você pular qualquer um desses passos.
```

- [ ] **Step 5: Documentar em `README.md`**

Na seção de tools, acrescentar um ponteiro:

```markdown
Cada tool tem um slash command do OpenCode correspondente — veja
[`docs/COMMANDS.md`](docs/COMMANDS.md). Os comandos são gerados a partir do
código: `uv run python scripts/generate_commands.py`.
```

- [ ] **Step 6: Suíte completa e lint**

```bash
uv run pytest -m unit -q
uv run ruff check .
```
Expected: 8 passed; ruff limpo.

- [ ] **Step 7: Commit**

```bash
git add tests/unit_commands.py AGENTS.md README.md
git commit -m "test(commands): fail the suite when a tool has no command or the docs are stale"
```

---

## Self-Review Notes

**Cobertura da spec.** Cada seção da spec mapeia para uma task: AST-não-import
(1), overrides curados incluindo a absorção dos 3 (3), um comando por tool sem
exceção (2 + 5), cobertura por teste (7), idempotência (5 Step 6 + 7),
formato do comando (4), `docs/COMMANDS.md` + nav (6), allowlist de
`compress`/`search-sessions` (2 + 7), erros de borda — tool sem docstring
(`_summary` levanta, Task 4), tool sem nome no catálogo (`command_name`
levanta, Task 2), override órfão (teste na Task 3), parâmetro sem `Field`
(teste na Task 1, relatado por `main()` na Task 5).

**Delta em relação à spec, corrigido dentro do plano.** A spec descrevia três
campos de override; o levantamento de `/minimax-download` mostrou que ele
aceita `transcrever`, `model_size` e `language` — parâmetros de
`transcribe_video`, não de `download_video`. Sem um quarto campo
(`params_extra`), absorver aquele comando perderia metade da interface dele.
O Step 6 da Task 3 sincroniza a spec.

**Consistência de tipos.** `ToolSpec`/`ParamSpec` são definidos na Task 1 e
consumidos com os mesmos nomes de campo nas Tasks 4, 5 e 6. `Override` é
definido na Task 3 e consumido nas 4, 5 e 6. `render_usage` e `render_command`
têm a mesma assinatura `(spec, override, command)` em todos os pontos de uso.
`catalog.NON_TOOL_COMMANDS` é declarado na Task 2 e usado na 7.

**Onde o risco está concentrado.** Task 3, Step 4: a conferência fato a fato
dos três comandos absorvidos. É a única etapa do plano que não é verificável
por teste automatizado — o teste `ABSORBED_FACTS` cobre catorze marcadores
textuais, mas não garante que o *tom* e a *ordem* das instruções continuem
úteis para um agente. Essa parte precisa de olho humano, e o Step 5 da Task 5
existe para isso.
