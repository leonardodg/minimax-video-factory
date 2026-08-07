---
description: Gera um vídeo no MiniMax H3 via MCP. Uso: /minimax-gerar-video "descrição do vídeo" [duration=5] [width=1024] [height=576] [seed=42] [filename_prefix=studio/]
---

Gere um vídeo com o modelo MiniMax H3 (texto→vídeo com áudio nativo estéreo) usando a ferramenta MCP **`minimax-video-factory_generate_video`** (server `minimax-video-factory`).

Entrada do usuário (tudo depois do comando):
$ARGUMENTS

Instruções obrigatórias:
1. Extraia os parâmetros aceitando tanto `chave=valor` quanto descrição em linguagem natural:
   - `prompt`: descrição cinematográfica/estruturada do vídeo (shots, câmera, iluminação, áudio).
   - `duration`: 4-15s (default 5; o servidor arredonda para a grade de 17 frames).
   - `width` / `height`: default **1024x576**. NUNCA use 1344x768 — OOM no sampler com 12 GB VRAM (`torch.OutOfMemoryError`); 1024x576 é o máximo estável. 512x320 é o mais rápido (~5 min).
   - `seed`: opcional (inteiro).
   - `filename_prefix`: default `studio/`.
2. Se `prompt` vier em PT, traduza para uma descrição visual EN rica antes de chamar a tool.
3. Aguarde o render completar (5-20 min; use `wait_for_video` se a tool retornar só o prompt_id). Reporte o caminho final do vídeo (host, via `OUTPUT_HOST_DIR`) e o prompt_id.
4. Se houver erro de OOM, reduza para 1024x576 ou 512x320 e tente novamente.
5. Se a tool `generate_video` travar com timeout de client MCP, chame primeiro `submit_scene` e depois `wait_for_video(prompt_id)` em separado.
