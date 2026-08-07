---
description: Baixa um vídeo (Instagram Reel, YouTube) via MCP yt-dlp, opcionalmente transcreve com Whisper. Uso: /minimax-download <URL> [browser=chrome] [transcrever] [model_size=small] [language=pt]
---

Baixe o vídeo da URL informada usando a ferramenta MCP **`minimax-video-factory_download_video`** (server `minimax-video-factory`).

Entrada do usuário (tudo depois do comando):
$ARGUMENTS

Instruções obrigatórias:
1. Extraia:
   - `url` (obrigatória) — Instagram Reel, YouTube, etc.
   - `browser`: qual navegador usar para cookies (default `chrome`). Se der erro de "database locked", oriente a fechar o navegador.
   - `transcrever`: flag — se presente, transcreva o vídeo baixado com Whisper.
   - `model_size`: tiny/base/small/medium/large-v3 (default `small`).
   - `language`: default `pt`.
2. Chame `download_video` com a URL e browser. Reporte o arquivo salvo (dir `downloads/`), título, duração e uploader.
3. Se `transcrever` foi pedido, chame `transcribe_video` com o caminho baixado (GPU, `device=cuda`) e reporte o texto + segmentos com timestamps. Alternativamente, o usuário pode usar o comando dedicado `/minimax-transcrever <arquivo>` para transcrever qualquer vídeo local depois.
4. Não gere vídeo a menos que o usuário peça explicitamente.
