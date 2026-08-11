---
description: Lista documentos para exportar — por IDs, por busca ou os mais recentes. Nao grava nada; use a lista para confirmar e depois chamar kb-export
argument-hint: [query] [ids] [limit=20]
---

<!-- GERADO AUTOMATICAMENTE por scripts/generate_commands.py -->
<!-- Não edite à mão: rode `uv run python scripts/generate_commands.py`. -->

Execute a ferramenta MCP **`mcp__minimax-knowledge-base__kb_export_search`**.

Entrada do usuário (tudo depois do comando):
$ARGUMENTS

Instruções obrigatórias:
1. Extraia:
   - `query`: texto para buscar em título/resumo/conteúdo (default `None`).
   - `ids`: IDs diretos (ex.: 118,121,125) (default `None`).
   - `limit`: Número máximo de resultados (default `20`).
2. Chame `mcp__minimax-knowledge-base__kb_export_search` com esses parâmetros. Esta tool só existe no servidor `minimax-knowledge-base`, que roda no host com acesso direto a Postgres e Ollama. Se ele não estiver conectado, diga isso ao usuário — não tente as variantes do container, que não alcançam o Postgres e só devolvem timeout.
3. Reporte o resultado da tool ao usuário.
