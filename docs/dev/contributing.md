# Contributing & Testing

How to contribute and how the test suite is organized. Tests currently live
in `tests/` and use `pytest` with markers that let you run only the fast,
pure-logic tests in CI or locally without external services.

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
| `unit` | nothing | Always. Pure logic: chunking, prompt building, JSON parsing, workflow injection, frame math. |
| `integration_db` | Postgres up + migrated | `docker compose $COMPOSE_ARGS up -d postgres` + `uv run alembic upgrade head`. |
| `integration_llm` | local Ollama daemon with `LLM_MODEL`/`EMBEDDING_MODEL` pulled | KB ingest/search/ask paths. |

Run everything (needs the full stack up):

```bash
source scripts/config.sh
uv run pytest
```

Targeted runs:

```bash
uv run pytest -m unit
uv run pytest -m integration_db
uv run pytest -m integration_llm
uv run pytest tests/test_scripts.py::test_integration_knowledge_db -v
```

## Test files

| File | Scope |
|---|---|
| `tests/unit_knowledge.py` | Unit tests for `knowledge.py` / `db.py` chunking and parsing (no external services). |
| `tests/integration_knowledge_db.py` | Full DB path against Postgres. **Idempotent**: cleans up its own `example.com/test` docs via `delete_documents`, so repeated runs don't accumulate stale docs. |
| `tests/integration_knowledge_llm.py` | Ingest/search/ask with Ollama. |
| `tests/test_scripts.py` | Wraps the bash diagnostic blocks (`scripts/diagnose.sh NN ...`) and the MCP tool docs generator. |
| `tests/00_*.sh` … `08_*.sh` | Bash diagnostic scripts, runnable individually or via `./scripts/diagnose.sh`. |

## The diagnostic suite

The `scripts/diagnose.sh` runner aggregates the per-phase bash checks:

```bash
./scripts/diagnose.sh          # full run (aggregates PASS/FAIL)
./scripts/diagnose.sh 02 03    # single blocks
```

Blocks: `00` infra, `01` GPU in container, `02` ComfyUI API reachable,
`03` models present (exact byte sizes, ±2% tolerance), `04` workflow node
classes resolve, `05` smoke render, `06` MCP stdio handshake,
`07` end-to-end agent flow, `08` knowledge base (Postgres + Ollama).

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
3. If you touched the KB, run `tests/08_knowledge.sh` (Postgres + Ollama up).
4. If you touched the tool registry, regenerate `docs/MCP_TOOLS.md` and
   rebuild the docs: `uv run mkdocs build --strict`.
5. Update `README.md` / `AGENTS.md` / `docs/*` if behavior or tool lists
   changed.
