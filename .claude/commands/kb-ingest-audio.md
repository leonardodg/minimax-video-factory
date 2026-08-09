---
description: Transcreve e documenta um áudio/podcast na base de conhecimento
argument-hint: <path_or_url> [browser=STUDIO_BROWSER] [whisper_model=WHISPER_MODEL]
---

<!-- GERADO AUTOMATICAMENTE por scripts/generate_commands.py -->
<!-- Não edite à mão: rode `uv run python scripts/generate_commands.py`. -->

Execute a ferramenta MCP **`mcp__minimax-knowledge-base__knowledge_ingest_audio`**.

Entrada do usuário (tudo depois do comando):
$ARGUMENTS

Instruções obrigatórias:
1. Extraia:
   - `path_or_url` (obrigatória) — caminho local OU URL; se for URL, baixa antes de transcrever.
   - `browser`: Navegador para cookies (se for URL) (default `STUDIO_BROWSER`).
   - `whisper_model`: Tamanho do modelo Whisper (default `WHISPER_MODEL`).
2. Chame `mcp__minimax-knowledge-base__knowledge_ingest_audio` com esses parâmetros. Esta tool só existe no servidor `minimax-knowledge-base`, que roda no host com acesso direto a Postgres e Ollama. Se ele não estiver conectado, diga isso ao usuário — não tente as variantes do container, que não alcançam o Postgres e só devolvem timeout.
3. Reporte o resultado da tool ao usuário.
