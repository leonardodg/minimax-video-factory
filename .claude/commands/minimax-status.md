---
description: Checa o estado de um render já submetido, sem bloquear
argument-hint: <prompt_id>
---

<!-- GERADO AUTOMATICAMENTE por scripts/generate_commands.py -->
<!-- Não edite à mão: rode `uv run python scripts/generate_commands.py`. -->

Execute a ferramenta MCP **`mcp__minimax-video-factory__get_status`**.

Entrada do usuário (tudo depois do comando):
$ARGUMENTS

Instruções obrigatórias:
1. Extraia:
   - `prompt_id` (obrigatória) — o id devolvido por `/minimax-submit-scene`.
2. Chame `mcp__minimax-video-factory__get_status` com esses parâmetros. Se o servidor `minimax-video-factory` não estiver conectado, use `mcp__minimax-video-factory-remote__get_status` ou `mcp__minimax-video-factory-uv__get_status`.
3. Reporte o estado (`queued`, `running`, `completed`, `error`) e, se completo, o caminho do arquivo.
