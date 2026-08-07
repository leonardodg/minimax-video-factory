---
description: Transcreve um vídeo local com Whisper (faster-whisper, GPU). Uso: /minimax-transcrever <video_path> [model_size=small] [device=cuda] [language=pt]
---

Execute a ferramenta MCP **`minimax-video-factory_transcribe_video`** (server `minimax-video-factory`).

Entrada do usuário (tudo depois do comando):
$ARGUMENTS

Instruções obrigatórias:
1. Extraia:
   - `video_path` (obrigatória) — caminho do arquivo .mp4/.mkv/.webm (aceita path do host, ex.: `downloads/Video.mp4`); se vier relativo, assuma relativo ao diretório do projeto (`$PROJECT_ROOT`).
   - `model_size`: modelo Whisper: tiny/base/small/medium/large-v3 (default `small`).
   - `device`: `cuda` (GPU) ou `cpu` (default `cuda`).
   - `language`: código do idioma (pt, en, es, ...) (default `pt`).
2. Chame `transcribe_video` com esses parâmetros. Se a variante default do servidor MCP estiver indisponível, use a variante conectada (`minimax-video-factory-remote` ou `minimax-video-factory-uv`).
3. Reporte o texto transcrito + segmentos com timestamps + idioma detectado.
4. Não gere vídeo nem crie prompt a menos que o usuário peça.
