---
description: Gera um vídeo no MiniMax H3 (texto→vídeo com áudio nativo estéreo) via MCP. Uso: /minimax-gerar-video <prompt> [duration=10.0] [width=1024] [height=576] [seed] [filename_prefix=studio/]
---

Execute a ferramenta MCP **`minimax-video-factory_generate_video`** (server `minimax-video-factory`).

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
2. Chame `generate_video` com esses parâmetros. Se a variante default do servidor MCP estiver indisponível, use a variante conectada (`minimax-video-factory-remote` ou `minimax-video-factory-uv`).
3. Se `prompt` vier em PT, traduza para uma descrição visual EN rica antes de chamar a tool.
4. Aguarde o render completar (5-20 min; use `wait_for_video` se a tool retornar só o prompt_id). Reporte o caminho final do vídeo (host, via `OUTPUT_HOST_DIR`) e o prompt_id.
5. Se houver erro de OOM, reduza para 512x320 e tente novamente.
6. Se a tool travar com timeout de client MCP, chame primeiro `submit_scene` e depois `wait_for_video(prompt_id)` em separado.
