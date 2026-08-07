---
description: Pipeline completo: URL → download → transcrição → prompt → vídeo. Uso: /minimax-studio <url> [style=cinematic] [duration=10.0] [width=1024] [height=576]
---

Execute a ferramenta MCP **`minimax-video-factory_studio_pipeline`** (server `minimax-video-factory`).

Entrada do usuário (tudo depois do comando):
$ARGUMENTS

Instruções obrigatórias:
1. Extraia:
   - `url` (obrigatória) — URL do vídeo de origem — Instagram Reel, YouTube, etc.
   - `style`: cinematic, educational ou social (default `cinematic`).
   - `duration`: duração do clipe gerado, em segundos (default `10.0`).
   - `width`: largura; não suba de 1024 — OOM no sampler com 12 GB VRAM (default `1024`).
   - `height`: altura; não suba de 576 pelo mesmo motivo de VRAM (default `576`).
2. Chame `studio_pipeline` com esses parâmetros. Se a variante default do servidor MCP estiver indisponível, use a variante conectada (`minimax-video-factory-remote` ou `minimax-video-factory-uv`).
3. É o mais demorado de todos (download + Whisper + render). Avise o usuário antes de começar.
4. Reporte cada etapa conforme concluir, não só o resultado final.
