---
description: Transcreve um vídeo local com Whisper (faster-whisper, GPU)
argument-hint: <video_path> [model_size=small] [device=cuda] [language=pt]
---

<!-- GERADO AUTOMATICAMENTE por scripts/generate_commands.py -->
<!-- Não edite à mão: rode `uv run python scripts/generate_commands.py`. -->

Execute a ferramenta MCP **`mcp__minimax-video-factory__transcribe_video`**.

Entrada do usuário (tudo depois do comando):
$ARGUMENTS

Instruções obrigatórias:
1. Extraia:
   - `video_path` (obrigatória) — caminho do arquivo .mp4/.mkv/.webm (aceita path do host, ex.: `downloads/Video.mp4`); se vier relativo, assuma relativo ao diretório do projeto (`$PROJECT_ROOT`).
   - `model_size`: modelo Whisper: tiny/base/small/medium/large-v3 (default `small`).
   - `device`: `cuda` (GPU) ou `cpu` (default `cuda`).
   - `language`: código do idioma (pt, en, es, ...) (default `pt`).
2. Chame `mcp__minimax-video-factory__transcribe_video` com esses parâmetros. Se o servidor `minimax-video-factory` não estiver conectado, use `mcp__minimax-video-factory-remote__transcribe_video` ou `mcp__minimax-video-factory-uv__transcribe_video`.
3. Reporte o texto transcrito + segmentos com timestamps + idioma detectado.
4. Não gere vídeo nem crie prompt a menos que o usuário peça.
