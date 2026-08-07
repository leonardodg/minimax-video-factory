# Development Environment

How to get a full development setup from scratch. This covers the host-side
tooling and the knowledge-base stack; the video-factory Docker/ComfyUI stack
is covered in [Installation](../INSTALLATION.md).

## Prerequisites

- Python ≥ 3.10 and [uv](https://docs.astral.sh/uv/)
- Docker with the compose plugin (for Postgres and the ComfyUI container)
- [Ollama](https://ollama.com) running locally with the models from `.env`

## 1. Install dependencies

```bash
cd $PROJECT_ROOT
uv sync --extra dev
```

`--extra dev` installs `pytest`, `ruff`, and the MkDocs toolchain (`mkdocs`,
`mkdocs-material`, `mkdocstrings`).

## 2. Configure `.env`

Copy `.env.example` to `.env` and review it. Key settings for development:

| Variable | Purpose |
|---|---|
| `KB_POSTGRES_PORT` | Host port for Postgres (default `5432`) |
| `KB_DATABASE_URL` | SQLAlchemy URL (`postgresql+psycopg://kb:kb@127.0.0.1:5432/knowledge`) |
| `LLM_PROVIDER` | `ollama` (default) or `openai-compatible` |
| `LLM_MODEL` / `EMBEDDING_MODEL` | Ollama models (defaults `lfm2:24b`, `mxbai-embed-large`) |
| `VAULT_PATH` | Obsidian export path; leave empty to skip exports |

## 3. Start the knowledge-base services

```bash
source scripts/config.sh
docker compose $COMPOSE_ARGS up -d postgres
uv run alembic upgrade head
```

Verify Postgres is up:

```bash
curl -s http://127.0.0.1:${KB_POSTGRES_PORT:-5432} >/dev/null || echo "check port"
```

Verify Ollama has the required models (pulls if missing):

```bash
ollama list
```

## 4. Run the MCP server (host mode)

The knowledge-base tools run in **host mode** because they need direct access
to `localhost:11434` (Ollama) and `127.0.0.1:${KB_POSTGRES_PORT}` (Postgres).

```bash
source scripts/config.sh
uv run --directory $PROJECT_ROOT python src/minimax_mcp/server.py
```

The FastMCP stdio server reads the request protocol from stdin — connect it
with an MCP client, or test the handshake:

```bash
printf '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"probe","version":"1"}}}\n' \
  | uv run python src/minimax_mcp/server.py
```

## 5. Serve the docs site

```bash
uv run mkdocs serve
```

Open `http://127.0.0.1:8000`. Build a strict static site (warnings become
errors) with:

```bash
uv run mkdocs build --strict
```

## 6. Run the diagnostics

```bash
./scripts/diagnose.sh          # full suite
./scripts/diagnose.sh 02 03    # specific blocks
```

See [Contributing & Testing](contributing.md) for the pytest workflow.

## Troubleshooting

- **`ImportError` when importing `minimax_mcp`** — make sure `uv sync` is
  complete and you run from the project root (`src` layout is on the path via
  the editable install).
- **Postgres connection refused** — the container may be down:
  `docker compose $COMPOSE_ARGS up -d postgres` (always use `$COMPOSE_ARGS`;
  see `scripts/config.sh`).
- **Ollama not reachable** — confirm `ollama list` works and that
  `LLM_MODEL`/`EMBEDDING_MODEL` are pulled.
- **MkDocs warnings on `mkdocs build --strict`** — broken internal links or
  nav entries pointing to missing files; fix them before committing.
