---
description: Verifica o ComfyUI e a presença dos modelos MiniMax H3. Uso: /minimax-health
---

Execute a ferramenta MCP **`minimax-video-factory_health_check`** (server `minimax-video-factory`).

Entrada do usuário (tudo depois do comando):
$ARGUMENTS

Instruções obrigatórias:
1. Chame `health_check` com esses parâmetros. Se a variante default do servidor MCP estiver indisponível, use a variante conectada (`minimax-video-factory-remote` ou `minimax-video-factory-uv`).
2. Rode isto ANTES de um render longo: descobrir que falta um modelo depois de 20 minutos de espera é o desperdício que este comando evita.
3. Se algum modelo estiver ausente, aponte `scripts/download_models.sh`.
