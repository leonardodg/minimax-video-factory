---
description: Mostra a fila de renderização com barra de progresso
argument-hint: [watch_seconds=20.0]
---

<!-- GERADO AUTOMATICAMENTE por scripts/generate_commands.py -->
<!-- Não edite à mão: rode `uv run python scripts/generate_commands.py`. -->

Execute a ferramenta MCP **`mcp__minimax-video-factory__queue_status`**.

Entrada do usuário (tudo depois do comando):
$ARGUMENTS

Instruções obrigatórias:
1. Extraia:
   - `watch_seconds`: quanto tempo ouvir o progresso. Um step em 1024x576 leva dezenas de segundos, então uma janela curta pode não capturar nada — use 0 para pular e ver só a fila (default `20.0`).
2. Chame `mcp__minimax-video-factory__queue_status` com esses parâmetros. Se o servidor `minimax-video-factory` não estiver conectado, use `mcp__minimax-video-factory-remote__queue_status` ou `mcp__minimax-video-factory-uv__queue_status`.
3. Mostre o campo `summary`, que já vem formatado para leitura humana.
4. A porcentagem conta apenas os steps do sampler. O decode do VAE e a codificação do vídeo vêm depois e não aparecem — não anuncie 100% do sampler como vídeo pronto.
5. Se a fila tiver itens que o usuário não submeteu, avise: podem ser sobras de runs de CI cancelados, que já entupiram a fila antes.
