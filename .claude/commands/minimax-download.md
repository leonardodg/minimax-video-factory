---
description: Baixa um vídeo (Instagram Reel, YouTube) via MCP yt-dlp, opcionalmente transcreve com Whisper
argument-hint: <url> [browser=chrome] [transcrever] [model_size=small] [language=pt]
---

<!-- GERADO AUTOMATICAMENTE por scripts/generate_commands.py -->
<!-- Não edite à mão: rode `uv run python scripts/generate_commands.py`. -->

Execute a ferramenta MCP **`mcp__minimax-video-factory__download_video`**.

Entrada do usuário (tudo depois do comando):
$ARGUMENTS

Instruções obrigatórias:
1. Extraia:
   - `url` (obrigatória) — URL do vídeo — Instagram Reel, YouTube, etc.
   - `browser`: navegador de onde ler os cookies (chrome, firefox, edge, brave). Se der erro de "database locked", oriente a fechar o navegador (default `chrome`).
   - `transcrever`: flag — se presente, transcreva o vídeo baixado com Whisper.
   - `model_size`: tiny/base/small/medium/large-v3, se for transcrever (default `small`).
   - `language`: código do idioma, se for transcrever (default `pt`).
2. Chame `mcp__minimax-video-factory__download_video` com esses parâmetros. Se o servidor `minimax-video-factory` não estiver conectado, use `mcp__minimax-video-factory-remote__download_video` ou `mcp__minimax-video-factory-uv__download_video`.
3. Reporte o arquivo salvo (dir `downloads/`), título, duração e uploader.
4. Se `transcrever` foi pedido, chame `transcribe_video` com o caminho baixado (GPU, `device=cuda`) e reporte o texto + segmentos com timestamps. Alternativamente, o usuário pode usar o comando dedicado `/minimax-transcrever <arquivo>` depois.
5. Não gere vídeo a menos que o usuário peça explicitamente.
