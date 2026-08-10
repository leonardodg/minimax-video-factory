---
description: Lista documentos para exportar — por IDs, por busca ou os mais recentes. Nao grava nada; use a lista para confirmar e depois chamar kb-export. Uso: /kb-export-search [query] [ids] [limit=20]
---

Execute a ferramenta MCP **`minimax-video-factory_kb_export_search`** (server `minimax-video-factory`).

Entrada do usuário (tudo depois do comando):
$ARGUMENTS

Instruções obrigatórias:
1. Extraia:
   - `query`: texto para buscar em título/resumo/conteúdo (default `None`).
   - `ids`: IDs diretos (ex.: 118,121,125) (default `None`).
   - `limit`: Número máximo de resultados (default `20`).
2. Chame `kb_export_search` com esses parâmetros. Se a variante default do servidor MCP estiver indisponível, use a variante conectada (`minimax-video-factory-remote` ou `minimax-video-factory-uv`).
3. Reporte o resultado da tool ao usuário.
