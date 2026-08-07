---
description: Resume e documenta um texto na base de conhecimento com a IA local. Uso: /kb-ingest-texto <text> [source_url] [title] [platform=manual]
---

Execute a ferramenta MCP **`minimax-video-factory_knowledge_ingest_text`** (server `minimax-video-factory`).

Entrada do usuário (tudo depois do comando):
$ARGUMENTS

Instruções obrigatórias:
1. Extraia:
   - `text` (obrigatória) — Texto/transcrição já pronta para processar.
   - `source_url`: URL de origem, se houver (default `None`).
   - `title`: Título do documento (default `None`).
   - `platform`: Origem: manual, instagram, youtube, podcast (default `manual`).
2. Chame `knowledge_ingest_text` com esses parâmetros. Se a variante default do servidor MCP estiver indisponível, use a variante conectada (`minimax-video-factory-remote` ou `minimax-video-factory-uv`).
3. Reporte o `document_id`, o título e as tags geradas.
