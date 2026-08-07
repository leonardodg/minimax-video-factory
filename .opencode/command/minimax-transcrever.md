---
description: Transcreve um vídeo local com Whisper (faster-whisper, GPU). Uso: /minimax-transcrever <caminho-do-video> [model_size=small] [device=cuda] [language=pt]
---

Transcreva o vídeo informado usando a ferramenta MCP **`minimax-video-factory_transcribe_video`** (server `minimax-video-factory`).

Entrada do usuário (tudo depois do comando):
$ARGUMENTS

Instruções obrigatórias:
1. Extraia:
   - `video_path` (obrigatória) — caminho do arquivo .mp4/.mkv/.webm (aceita path do host, ex.: `downloads/Video.mp4`).
   - `model_size`: tiny/base/small/medium/large-v3 (default `small`).
   - `device`: `cuda` (default, GPU) ou `cpu`.
   - `language`: default `pt` (pt, en, es, etc.).
2. Se o caminho vier relativo (ex.: `downloads/foo.mp4`), assuma relativo ao diretório do projeto (`$PROJECT_ROOT`).
3. Chame `transcribe_video` com esses parâmetros. Se a variante default do servidor MCP estiver indisponível, use a variante conectada (`minimax-video-factory-remote` ou `-uv`).
4. Reporte o texto transcrito + segmentos com timestamps + idioma detectado.
5. Não gere vídeo nem crie prompt a menos que o usuário peça.
