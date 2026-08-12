# Separar o Python (MCP + worker) do ComfyUI

> Proposta para revisão. **Nenhuma imagem foi construída** e nada foi aplicado.
> Branch `worktree-separar-python-comfyui`.

## O problema, em um número

O `ig-worker` roda a imagem do ComfyUI: **36,2 GB**. Ele não usa o ComfyUI para
nada — baixa com `yt-dlp`, transcreve com Whisper, descreve com Ollama, grava
no Postgres. Ocupa **52 MiB de RAM** em repouso.

O servidor MCP não é nem serviço: roda dentro do container do `comfyui` por
`docker exec`.

## O que isso já custou

O bug de 2026-08-12. As tools `ig_queue_status`, `ig_worker_stop` e
`ig_sync_saved` falhavam com **erro vazio**, enquanto as `kb_*` funcionavam.

A causa: o servidor MCP herdava o ambiente do container do ComfyUI. Ali havia
`KB_DATABASE_URL` (alguém precisou das tools `kb_*` e reescreveu para a rede do
compose) mas nunca houve `RABBITMQ_URL` — o ComfyUI não fala com fila. Sem ela,
o código caía no default `amqp://guest:guest@localhost:5672/`, que no host
acerta a porta publicada e dentro do container aponta para o próprio container.

**Não foi bug de código.** Foi um serviço herdando configuração de outro.

## O que muda

### Imagem nova: `docker/Dockerfile.python`

`python:3.11-slim` + ffmpeg + `uv sync --no-dev` + as libs cu12 do
faster-whisper. Sem ComfyUI, sem custom nodes.

O `/opt/mcp-venv` **já era autocontido** — construído do `pyproject.toml`, sem
depender do ComfyUI. Só morava na imagem errada.

### Serviço novo: `mcp`

Container próprio, com o próprio bloco de ambiente. Três acoplamentos, e os
três são de configuração:

| | antes | agora |
|---|---|---|
| `COMFYUI_URL` | `127.0.0.1:8188` (estava dentro) | `http://comfyui:8188` |
| `MODELS_DIR` | `/comfy/ComfyUI/models` | mount `:ro` em `/models` |
| `OUTPUT_DIR` | `/comfy/ComfyUI/output` | **mesmo volume**, em `/output` |

O `OUTPUT_DIR` é o único que não se resolve com env var: o MCP lê os `.mp4` que
o ComfyUI escreve. Precisa do mesmo bind-mount nos dois.

### `ig-worker` troca de imagem

De `minimax-comfyui:local` para `minimax-python:local`. Nada mais muda.

### O `comfyui` devolve o que não é dele

Saem `KB_DATABASE_URL`, `OLLAMA_URL`, `LLM_MODEL`, `EMBEDDING_MODEL`,
`RABBITMQ_URL`, `RABBITMQ_QUEUE` e os `MCP_*`. Ficam 15 chaves, todas de
render. A porta `8848` vai para o serviço `mcp`.

## O que isto NÃO resolve

**A GPU.** Quatro tools do MCP usam a placa direto — `transcribe_video`,
`studio_pipeline`, `knowledge_ingest_video`, `knowledge_ingest_audio`, todas
faster-whisper com `device=cuda`. O container do `mcp` precisa de GPU.

Continuam **três consumidores dos mesmos 12 GB**. Separar containers não separa
VRAM. O que resolve é serialização, e o mecanismo já existe: o canal
`ig.worker.command`, hoje acionado à mão.

## Antes de aplicar — o que ainda não foi feito

1. **A imagem não foi construída.** `docker compose build mcp` (~5 GB, alguns
   minutos). Nada foi validado em execução.
2. **O `.mcp.json` continua apontando para o caminho antigo:**
   ```json
   "minimax-video-factory": {
     "command": "docker",
     "args": ["exec","-i","minimax-comfyui","bash","/workspace/scripts/mcp_runner.sh"]
   }
   ```
   Com o serviço próprio vira `minimax-mcp` no lugar de `minimax-comfyui`, ou o
   modo HTTP — a entrada `minimax-video-factory-remote` já existe apontando para
   `http://127.0.0.1:8848/mcp`, e nunca foi ligada porque o `mcp_runner.sh`
   força `stdio`.
3. **`mcp_runner.sh` não foi tocado.** Ele ainda serve, mas o `command:` do
   serviço chama o módulo direto (`python -m minimax_mcp.server`), então o
   script vira legado quando o modo HTTP entrar.
4. **`torch` continua no `pyproject.toml`** (~2,5 GB). O faster-whisper usa
   ctranslate2, não torch. Se nada mais no Python usar, tirar derruba a imagem
   para ~2 GB. **Não verifiquei** se algo usa — é o próximo teste.

## Como validar quando decidir aplicar

```bash
docker compose build mcp
docker compose up -d
docker compose ps                      # 5 serviços de pé

# o que estava quebrado hoje
docker exec -i minimax-mcp /opt/mcp-venv/bin/python -c \
  "from minimax_mcp import ig_queue; c=ig_queue.connect(); \
   print(ig_queue.queue_status(c.channel()))"

# o acoplamento que importa: o MCP enxerga os .mp4 do ComfyUI?
docker exec minimax-mcp ls /output/rosy/reel | head

# e o ComfyUI, alcançável por nome?
docker exec minimax-mcp curl -s http://comfyui:8188/system_stats | head -c 80
```

Se algo falhar, o caminho de volta é `git revert` do merge e `docker compose
up -d` — a imagem do ComfyUI não foi tocada.
