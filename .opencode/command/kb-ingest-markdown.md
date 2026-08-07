---
description: Importa arquivos markdown (ex.: Obsidian) para a base de conhecimento. Uso: /kb-ingest-markdown <path> [recursive=False] [doc_type=document]
---

Execute a ferramenta MCP **`minimax-video-factory_knowledge_ingest_markdown`** (server `minimax-video-factory`).

Entrada do usuário (tudo depois do comando):
$ARGUMENTS

Instruções obrigatórias:
1. Extraia:
   - `path` (obrigatória) — arquivo .md ou diretório; diretórios com ponto (.obsidian, .trash) são ignorados.
   - `recursive`: cuidado ao apontar para um vault inteiro — pode ser milhares de arquivos (default `False`).
   - `doc_type`: Tipo do documento na base (ex.: document, tutorial) (default `document`).
2. Chame `knowledge_ingest_markdown` com esses parâmetros. Se a variante default do servidor MCP estiver indisponível, use a variante conectada (`minimax-video-factory-remote` ou `minimax-video-factory-uv`).
3. Quando a nota já tem uma seção `## Summary`, esse texto é reaproveitado e o LLM é pulado — é o que torna a importação em massa viável (minutos em vez de horas).
4. Reporte quantos arquivos foram importados de quantos encontrados.
