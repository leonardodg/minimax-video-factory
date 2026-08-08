---
description: Mostra a fila de renderização com barra de progresso. Uso: /minimax-fila [watch_seconds=20.0]
---

Execute a ferramenta MCP **`minimax-video-factory_queue_status`** (server `minimax-video-factory`).

Entrada do usuário (tudo depois do comando):
$ARGUMENTS

Instruções obrigatórias:
1. Extraia:
   - `watch_seconds`: quanto tempo ouvir o progresso. Um step em 1024x576 leva dezenas de segundos, então uma janela curta pode não capturar nada — use 0 para pular e ver só a fila (default `20.0`).
2. Chame `queue_status` com esses parâmetros. Se a variante default do servidor MCP estiver indisponível, use a variante conectada (`minimax-video-factory-remote` ou `minimax-video-factory-uv`).
3. Mostre o campo `summary`, que já vem formatado para leitura humana.
4. A porcentagem conta apenas os steps do sampler. O decode do VAE e a codificação do vídeo vêm depois e não aparecem — não anuncie 100% do sampler como vídeo pronto.
5. Se a fila tiver itens que o usuário não submeteu, avise: podem ser sobras de runs de CI cancelados, que já entupiram a fila antes.
