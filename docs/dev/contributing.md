# Contributing & Testing

How to contribute and how the test suite is organized. Tests currently live
in `tests/` and use `pytest` with markers that let you run only the fast,
pure-logic tests in CI or locally without external services.

> The knowledge base / Instagram sync domain (and its tests) moved to
> [`insta_kb`](https://github.com/leonardodg/insta_kb) in 2026-10-06. This
> page covers the video pipeline only.

## Quick start

```bash
source scripts/config.sh          # loads .env + exports derived vars
uv run pytest -m unit             # fast: no external services
uv run ruff check src tests       # lint
```

## Test markers

Defined in `pyproject.toml` (`[tool.pytest.ini_options]`):

| Marker | Requires | When to run |
|---|---|---|
| `unit` | nothing | Always. Pure logic: prompt building, JSON parsing, workflow injection, frame math. |
| `integration_db` | the `comfyui` container up | `test_container_deps` — confirms the container's image actually imports every module `server.py` needs. Self-skips (rc=78) if the container isn't running. |

Run everything (needs the `comfyui` container up for the one integration test):

```bash
source scripts/config.sh
uv run pytest
```

Targeted runs:

```bash
uv run pytest -m unit
uv run pytest -m integration_db
```

## Test files

| File | Scope |
|---|---|
| `tests/test_scripts.py` | Wraps the bash diagnostic blocks (`scripts/diagnose.sh NN ...`) and the slash-command generator's own test. |
| `tests/00_*.sh` … `07_*.sh`, `09_*.sh` | Bash diagnostic scripts, runnable individually or via `./scripts/diagnose.sh`. |

## The diagnostic suite

The `scripts/diagnose.sh` runner aggregates the per-phase bash checks:

```bash
./scripts/diagnose.sh          # full run (aggregates PASS/FAIL)
./scripts/diagnose.sh 02 03    # single blocks
```

Blocks: `00` infra, `01` GPU in container, `02` ComfyUI API reachable,
`03` models present (exact byte sizes, ±2% tolerance), `04` workflow node
classes resolve, `05` smoke render, `06` MCP stdio handshake,
`07` end-to-end agent flow, `09` the `comfyui` image actually imports
`server.py`'s modules.

## Diagnostic gotchas worth remembering

- **Version check:** `0.30.2` → treat `major==0 && minor>=30` as OK, not
  `major>=1`.
- **VRAM:** a "12 GB" card reports ~12282 MiB — threshold is `>= 12000`, not
  `>= 12288`.
- **No `curl` in the container** — test from inside with Python `urllib`.
- **`--lowvram` is required** on 12 GB VRAM; torch must be ≥ 2.8 inside the
  image so ComfyUI uses DynamicVRAM (this is what makes lowvram actually
  work). Install torch from the **cu128** index and pin
  `torchvision==0.23.0` / `torchaudio==2.8.0` to the 2.8.0 release train.

## Before opening a PR

1. `uv run pytest -m unit` green.
2. `uv run ruff check src tests` clean.
3. If you touched the tool registry, regenerate `docs/MCP_TOOLS.md`/`docs/COMMANDS.md`
   (`uv run python scripts/generate_commands.py`) and rebuild the docs:
   `uv run mkdocs build --strict`.
4. Update `README.md` / `CLAUDE.md` / `docs/*` if behavior or tool lists
   changed.
