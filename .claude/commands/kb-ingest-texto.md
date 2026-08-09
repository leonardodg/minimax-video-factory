---
description: Resume e documenta um texto na base de conhecimento com a IA local
argument-hint: <text> [source_url] [title] [platform=manual]
---

<!-- GERADO AUTOMATICAMENTE por scripts/generate_commands.py -->
<!-- Não edite à mão: rode `uv run python scripts/generate_commands.py`. -->

Execute a ferramenta MCP **`mcp__minimax-knowledge-base__knowledge_ingest_text`**.

Entrada do usuário (tudo depois do comando):
$ARGUMENTS

Instruções obrigatórias:
1. Extraia:
   - `text` (obrigatória) — Texto/transcrição já pronta para processar.
   - `source_url`: URL de origem, se houver (default `None`).
   - `title`: Título do documento (default `None`).
   - `platform`: Origem: manual, instagram, youtube, podcast (default `manual`).
2. Chame `mcp__minimax-knowledge-base__knowledge_ingest_text` com esses parâmetros. Esta tool só existe no servidor `minimax-knowledge-base`, que roda no host com acesso direto a Postgres e Ollama. Se ele não estiver conectado, diga isso ao usuário — não tente as variantes do container, que não alcançam o Postgres e só devolvem timeout.
3. Reporte o `document_id`, o título e as tags geradas.
