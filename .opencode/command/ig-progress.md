---
description: Mostra os últimos N posts do Instagram processados pelo ig-worker (state em downloads/ig). Uso: /ig-progress [last_n=10]
---

Execute a ferramenta MCP **`minimax-video-factory_ig_get_progress`** (server `minimax-video-factory`).

Entrada do usuário (tudo depois do comando):
$ARGUMENTS

Instruções obrigatórias:
1. Extraia:
   - `last_n`: Quantos últimos resultados processados mostrar (default `10`).
2. Chame `ig_get_progress` com esses parâmetros. Se a variante default do servidor MCP estiver indisponível, use a variante conectada (`minimax-video-factory-remote` ou `minimax-video-factory-uv`).
3. Reporte o resultado da tool ao usuário.
