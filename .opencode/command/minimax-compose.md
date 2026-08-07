---
description: Concatena cenas .mp4 em um vídeo final com ffmpeg. Uso: /minimax-compose <scene_paths> [output_path=output/final.mp4]
---

Execute a ferramenta MCP **`minimax-video-factory_compose_final`** (server `minimax-video-factory`).

Entrada do usuário (tudo depois do comando):
$ARGUMENTS

Instruções obrigatórias:
1. Extraia:
   - `scene_paths` (obrigatória) — lista ordenada de arquivos .mp4 — a ordem é a ordem em que as cenas aparecem no vídeo final.
   - `output_path`: onde escrever o vídeo composto (default `output/final.mp4`).
2. Chame `compose_final` com esses parâmetros. Se a variante default do servidor MCP estiver indisponível, use a variante conectada (`minimax-video-factory-remote` ou `minimax-video-factory-uv`).
3. São necessárias ao menos 2 cenas; com menos, a tool recusa.
