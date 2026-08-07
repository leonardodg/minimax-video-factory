---
description: Transcreve e documenta um áudio/podcast na base de conhecimento. Uso: /kb-ingest-audio <path_or_url> [browser=STUDIO_BROWSER] [whisper_model=WHISPER_MODEL]
---

Execute a ferramenta MCP **`minimax-video-factory_knowledge_ingest_audio`** (server `minimax-video-factory`).

Entrada do usuário (tudo depois do comando):
$ARGUMENTS

Instruções obrigatórias:
1. Extraia:
   - `path_or_url` (obrigatória) — caminho local OU URL; se for URL, baixa antes de transcrever.
   - `browser`: Navegador para cookies (se for URL) (default `STUDIO_BROWSER`).
   - `whisper_model`: Tamanho do modelo Whisper (default `WHISPER_MODEL`).
2. Chame `knowledge_ingest_audio` com esses parâmetros. Se a variante default do servidor MCP estiver indisponível, use a variante conectada (`minimax-video-factory-remote` ou `minimax-video-factory-uv`).
3. Reporte o resultado da tool ao usuário.
