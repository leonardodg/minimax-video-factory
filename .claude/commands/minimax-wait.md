---
description: Bloqueia até um render terminar e devolve o caminho do .mp4
argument-hint: <prompt_id> [timeout=1200.0]
---

<!-- GERADO AUTOMATICAMENTE por scripts/generate_commands.py -->
<!-- Não edite à mão: rode `uv run python scripts/generate_commands.py`. -->

Execute a ferramenta MCP **`mcp__minimax-video-factory__wait_for_video`**.

Entrada do usuário (tudo depois do comando):
$ARGUMENTS

Instruções obrigatórias:
1. Extraia:
   - `prompt_id` (obrigatória) — o id devolvido por `/minimax-submit-scene`.
   - `timeout`: segundos máximos de espera; renders de 1024x576 levam 5-20 min (default `1200.0`).
2. Chame `mcp__minimax-video-factory__wait_for_video` com esses parâmetros. Se o servidor `minimax-video-factory` não estiver conectado, use `mcp__minimax-video-factory-remote__wait_for_video` ou `mcp__minimax-video-factory-uv__wait_for_video`.
3. Este comando BLOQUEIA. Se o usuário só quer saber o estado agora, use `/minimax-status` em vez deste.
