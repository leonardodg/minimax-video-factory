---
description: Enfileira os posts salvos do Instagram (via IG_SESSIONID) na fila ig.saved. Uso: /ig-sync [reprocessar=False]
---

Execute a ferramenta MCP **`minimax-video-factory_ig_sync_saved`** (server `minimax-video-factory`).

Entrada do usuário (tudo depois do comando):
$ARGUMENTS

Instruções obrigatórias:
1. Extraia:
   - `reprocessar`: Reenfileira TUDO, inclusive o que já está no banco. O padrão (False) publica só os ig_pk novos. (default `False`).
2. Chame `ig_sync_saved` com esses parâmetros. Se a variante default do servidor MCP estiver indisponível, use a variante conectada (`minimax-video-factory-remote` ou `minimax-video-factory-uv`).
3. Reporte o resultado da tool ao usuário.
