---
description: Verifica o ComfyUI e a presença dos modelos MiniMax H3
---

<!-- GERADO AUTOMATICAMENTE por scripts/generate_commands.py -->
<!-- Não edite à mão: rode `uv run python scripts/generate_commands.py`. -->

Execute a ferramenta MCP **`mcp__minimax-video-factory__health_check`**.

Entrada do usuário (tudo depois do comando):
$ARGUMENTS

Instruções obrigatórias:
1. Chame `mcp__minimax-video-factory__health_check` com esses parâmetros. Se o servidor `minimax-video-factory` não estiver conectado, use `mcp__minimax-video-factory-remote__health_check` ou `mcp__minimax-video-factory-uv__health_check`.
2. Rode isto ANTES de um render longo: descobrir que falta um modelo depois de 20 minutos de espera é o desperdício que este comando evita.
3. Se algum modelo estiver ausente, aponte `scripts/download_models.sh`.
