---
description: Concatena cenas .mp4 em um vídeo final com ffmpeg
argument-hint: <scene_paths> [output_path=output/final.mp4]
---

<!-- GERADO AUTOMATICAMENTE por scripts/generate_commands.py -->
<!-- Não edite à mão: rode `uv run python scripts/generate_commands.py`. -->

Execute a ferramenta MCP **`mcp__minimax-video-factory__compose_final`**.

Entrada do usuário (tudo depois do comando):
$ARGUMENTS

Instruções obrigatórias:
1. Extraia:
   - `scene_paths` (obrigatória) — lista ordenada de arquivos .mp4 — a ordem é a ordem em que as cenas aparecem no vídeo final.
   - `output_path`: onde escrever o vídeo composto (default `output/final.mp4`).
2. Chame `mcp__minimax-video-factory__compose_final` com esses parâmetros. Se o servidor `minimax-video-factory` não estiver conectado, use `mcp__minimax-video-factory-remote__compose_final` ou `mcp__minimax-video-factory-uv__compose_final`.
3. São necessárias ao menos 2 cenas; com menos, a tool recusa.
