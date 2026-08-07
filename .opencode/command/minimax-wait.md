---
description: Bloqueia até um render terminar e devolve o caminho do .mp4. Uso: /minimax-wait <prompt_id> [timeout=1200.0]
---

Execute a ferramenta MCP **`minimax-video-factory_wait_for_video`** (server `minimax-video-factory`).

Entrada do usuário (tudo depois do comando):
$ARGUMENTS

Instruções obrigatórias:
1. Extraia:
   - `prompt_id` (obrigatória) — o id devolvido por `/minimax-submit-scene`.
   - `timeout`: segundos máximos de espera; renders de 1024x576 levam 5-20 min (default `1200.0`).
2. Chame `wait_for_video` com esses parâmetros. Se a variante default do servidor MCP estiver indisponível, use a variante conectada (`minimax-video-factory-remote` ou `minimax-video-factory-uv`).
3. Este comando BLOQUEIA. Se o usuário só quer saber o estado agora, use `/minimax-status` em vez deste.
