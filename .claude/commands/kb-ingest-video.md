---
description: Baixa, transcreve e documenta um vídeo na base de conhecimento
argument-hint: <url> [browser=STUDIO_BROWSER] [whisper_model=WHISPER_MODEL]
---

<!-- GERADO AUTOMATICAMENTE por scripts/generate_commands.py -->
<!-- Não edite à mão: rode `uv run python scripts/generate_commands.py`. -->

Execute a ferramenta MCP **`mcp__minimax-knowledge-base__knowledge_ingest_video`**.

Entrada do usuário (tudo depois do comando):
$ARGUMENTS

Instruções obrigatórias:
1. Extraia:
   - `url` (obrigatória) — URL do vídeo (Instagram Reel, YouTube, etc.).
   - `browser`: Navegador para cookies (default `STUDIO_BROWSER`).
   - `whisper_model`: Tamanho do modelo Whisper (default `WHISPER_MODEL`).
2. Chame `mcp__minimax-knowledge-base__knowledge_ingest_video` com esses parâmetros. Esta tool só existe no servidor `minimax-knowledge-base`, que roda no host com acesso direto a Postgres e Ollama. Se ele não estiver conectado, diga isso ao usuário — não tente as variantes do container, que não alcançam o Postgres e só devolvem timeout.
3. Leva minutos: download + Whisper + LLM. Avise o usuário.
