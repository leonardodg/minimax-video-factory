---
description: Enfileira os posts salvos do Instagram (via IG_SESSIONID) na fila ig.saved
argument-hint: [reprocessar=False]
---

<!-- GERADO AUTOMATICAMENTE por scripts/generate_commands.py -->
<!-- Não edite à mão: rode `uv run python scripts/generate_commands.py`. -->

Execute a ferramenta MCP **`mcp__minimax-video-factory__ig_sync_saved`**.

Entrada do usuário (tudo depois do comando):
$ARGUMENTS

Instruções obrigatórias:
1. Extraia:
   - `reprocessar`: Reenfileira TUDO, inclusive o que já está no banco. O padrão (False) publica só os ig_pk novos. (default `False`).
2. Chame `mcp__minimax-video-factory__ig_sync_saved` com esses parâmetros. Se o servidor `minimax-video-factory` não estiver conectado, use `mcp__minimax-video-factory-remote__ig_sync_saved` ou `mcp__minimax-video-factory-uv__ig_sync_saved`.
3. Reporte o resultado da tool ao usuário.
