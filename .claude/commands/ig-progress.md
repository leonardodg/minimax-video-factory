---
description: Mostra os últimos N posts do Instagram processados pelo ig-worker (state em downloads/ig)
argument-hint: [last_n=10]
---

<!-- GERADO AUTOMATICAMENTE por scripts/generate_commands.py -->
<!-- Não edite à mão: rode `uv run python scripts/generate_commands.py`. -->

Execute a ferramenta MCP **`mcp__minimax-video-factory__ig_get_progress`**.

Entrada do usuário (tudo depois do comando):
$ARGUMENTS

Instruções obrigatórias:
1. Extraia:
   - `last_n`: Quantos últimos resultados processados mostrar (default `10`).
2. Chame `mcp__minimax-video-factory__ig_get_progress` com esses parâmetros. Se o servidor `minimax-video-factory` não estiver conectado, use `mcp__minimax-video-factory-remote__ig_get_progress` ou `mcp__minimax-video-factory-uv__ig_get_progress`.
3. Reporte o resultado da tool ao usuário.
