---
description: Baixa, transcreve e documenta um vídeo na base de conhecimento. Uso: /kb-ingest-video <url> [browser=STUDIO_BROWSER] [whisper_model=WHISPER_MODEL]
---

Execute a ferramenta MCP **`minimax-video-factory_knowledge_ingest_video`** (server `minimax-video-factory`).

Entrada do usuário (tudo depois do comando):
$ARGUMENTS

Instruções obrigatórias:
1. Extraia:
   - `url` (obrigatória) — URL do vídeo (Instagram Reel, YouTube, etc.).
   - `browser`: Navegador para cookies (default `STUDIO_BROWSER`).
   - `whisper_model`: Tamanho do modelo Whisper (default `WHISPER_MODEL`).
2. Chame `knowledge_ingest_video` com esses parâmetros. Se a variante default do servidor MCP estiver indisponível, use a variante conectada (`minimax-video-factory-remote` ou `minimax-video-factory-uv`).
3. Leva minutos: download + Whisper + LLM. Avise o usuário.
