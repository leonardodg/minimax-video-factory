---
description: Gera um vídeo no MiniMax H3 (texto→vídeo com áudio nativo estéreo) via MCP
argument-hint: <prompt> [duration=10.0] [width=1024] [height=576] [seed] [filename_prefix=studio/] [first_frame] [steps] [wait_seconds=900.0]
---

<!-- GERADO AUTOMATICAMENTE por scripts/generate_commands.py -->
<!-- Não edite à mão: rode `uv run python scripts/generate_commands.py`. -->

Execute a ferramenta MCP **`mcp__minimax-video-factory__generate_video`**.

Entrada do usuário (tudo depois do comando):
$ARGUMENTS

Instruções obrigatórias:
1. Extraia:
   - `prompt` (obrigatória) — descrição cinematográfica/estruturada do vídeo (shots, câmera, iluminação, áudio).
   - `duration`: duração do clipe, 4-15s; o servidor arredonda para a grade de 17 frames (default `10.0`).
   - `width`: não suba de 1024 — 1344x768 dá OOM no sampler com 12 GB VRAM (`torch.OutOfMemoryError`). 512x320 é o mais rápido (~5 min) (default `1024`).
   - `height`: não suba de 576 pelo mesmo motivo de VRAM (default `576`).
   - `seed`: semente aleatória (inteiro); omita para aleatório (default `None`).
   - `filename_prefix`: prefixo do arquivo de saída (default `studio/`).
   - `first_frame`: Caminho de uma imagem de referência; o vídeo é animado a partir dela (o modelo é FL2VA, treinado para isso) (default `None`).
   - `steps`: Passos do sampler (default 20). Medido: 30 e 40 não melhoram e custam 8x o tempo (default `None`).
   - `wait_seconds`: Quanto esperar antes de devolver só o prompt_id. Medido: 512x320 leva ~4.5min, 1024x576 ~3min com modelo quente (default `900.0`).
2. Chame `mcp__minimax-video-factory__generate_video` com esses parâmetros. Se o servidor `minimax-video-factory` não estiver conectado, use `mcp__minimax-video-factory-remote__generate_video` ou `mcp__minimax-video-factory-uv__generate_video`.
3. Se `prompt` vier em PT, traduza para uma descrição visual EN rica antes de chamar a tool.
4. Aguarde o render completar (5-20 min; use `wait_for_video` se a tool retornar só o prompt_id). Reporte o caminho final do vídeo (host, via `OUTPUT_HOST_DIR`) e o prompt_id.
5. Se houver erro de OOM, reduza para 512x320 e tente novamente.
6. A tool espera até `wait_seconds` (default 240s). Se o render não terminar nesse prazo ela devolve `state=rendering` com o `prompt_id` — isso não é erro. Colete com `/minimax-wait <prompt_id>` ou acompanhe com `/minimax-fila`.
