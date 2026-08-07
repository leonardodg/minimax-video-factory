---
description: Baixa um vídeo (Instagram Reel, YouTube) via MCP yt-dlp, opcionalmente transcreve com Whisper. Uso: /minimax-download <url> [browser=chrome] [transcrever] [model_size=small] [language=pt]
---

Execute a ferramenta MCP **`minimax-video-factory_download_video`** (server `minimax-video-factory`).

Entrada do usuário (tudo depois do comando):
$ARGUMENTS

Instruções obrigatórias:
1. Extraia:
   - `url` (obrigatória) — URL do vídeo — Instagram Reel, YouTube, etc.
   - `browser`: navegador de onde ler os cookies (chrome, firefox, edge, brave). Se der erro de "database locked", oriente a fechar o navegador (default `chrome`).
   - `transcrever`: flag — se presente, transcreva o vídeo baixado com Whisper.
   - `model_size`: tiny/base/small/medium/large-v3, se for transcrever (default `small`).
   - `language`: código do idioma, se for transcrever (default `pt`).
2. Chame `download_video` com esses parâmetros. Se a variante default do servidor MCP estiver indisponível, use a variante conectada (`minimax-video-factory-remote` ou `minimax-video-factory-uv`).
3. Reporte o arquivo salvo (dir `downloads/`), título, duração e uploader.
4. Se `transcrever` foi pedido, chame `transcribe_video` com o caminho baixado (GPU, `device=cuda`) e reporte o texto + segmentos com timestamps. Alternativamente, o usuário pode usar o comando dedicado `/minimax-transcrever <arquivo>` depois.
5. Não gere vídeo a menos que o usuário peça explicitamente.
