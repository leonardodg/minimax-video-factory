---
description: Pipeline completo: URL → download → transcrição → prompt → vídeo
argument-hint: <url> [style=cinematic] [duration=10.0] [width=1024] [height=576]
---

<!-- GERADO AUTOMATICAMENTE por scripts/generate_commands.py -->
<!-- Não edite à mão: rode `uv run python scripts/generate_commands.py`. -->

Execute a ferramenta MCP **`mcp__minimax-video-factory__studio_pipeline`**.

Entrada do usuário (tudo depois do comando):
$ARGUMENTS

Instruções obrigatórias:
1. Extraia:
   - `url` (obrigatória) — URL do vídeo de origem — Instagram Reel, YouTube, etc.
   - `style`: cinematic, educational ou social (default `cinematic`).
   - `duration`: duração do clipe gerado, em segundos (default `10.0`).
   - `width`: largura; não suba de 1024 — OOM no sampler com 12 GB VRAM (default `1024`).
   - `height`: altura; não suba de 576 pelo mesmo motivo de VRAM (default `576`).
2. Chame `mcp__minimax-video-factory__studio_pipeline` com esses parâmetros. Se o servidor `minimax-video-factory` não estiver conectado, use `mcp__minimax-video-factory-remote__studio_pipeline` ou `mcp__minimax-video-factory-uv__studio_pipeline`.
3. É o mais demorado de todos (download + Whisper + render). Avise o usuário antes de começar.
4. Reporte cada etapa conforme concluir, não só o resultado final.
