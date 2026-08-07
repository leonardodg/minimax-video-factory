---
description: Checa o estado de um render já submetido, sem bloquear. Uso: /minimax-status <prompt_id>
---

Execute a ferramenta MCP **`minimax-video-factory_get_status`** (server `minimax-video-factory`).

Entrada do usuário (tudo depois do comando):
$ARGUMENTS

Instruções obrigatórias:
1. Extraia:
   - `prompt_id` (obrigatória) — o id devolvido por `/minimax-submit-scene`.
2. Chame `get_status` com esses parâmetros. Se a variante default do servidor MCP estiver indisponível, use a variante conectada (`minimax-video-factory-remote` ou `minimax-video-factory-uv`).
3. Reporte o estado (`queued`, `running`, `completed`, `error`) e, se completo, o caminho do arquivo.
