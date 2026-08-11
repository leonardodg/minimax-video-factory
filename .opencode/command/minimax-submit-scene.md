---
description: Enfileira uma cena no ComfyUI e devolve o prompt_id, sem esperar o render. Uso: /minimax-submit-scene <prompt> [duration=5.0] [width=1024] [height=576] [seed] [filename_prefix=OUTPUT_PREFIX] [first_frame] [steps] [turbo=False] [turbo_lora] [turbo_strength] [turbo_low_vram]
---

Execute a ferramenta MCP **`minimax-video-factory_submit_scene`** (server `minimax-video-factory`).

Entrada do usuário (tudo depois do comando):
$ARGUMENTS

Instruções obrigatórias:
1. Extraia:
   - `prompt` (obrigatória) — prompt estruturado do MiniMax H3 (shots + câmera + áudio).
   - `duration`: duração do clipe, 4-15s; arredonda para a grade de 17 frames (default `5.0`).
   - `width`: largura (múltiplo de 32); não suba de 1024 — OOM no sampler com 12 GB VRAM (default `1024`).
   - `height`: altura (múltiplo de 32); não suba de 576 pelo mesmo motivo de VRAM (default `576`).
   - `seed`: semente aleatória (inteiro); omita para aleatório (default `None`).
   - `filename_prefix`: prefixo do arquivo de saída (default `OUTPUT_PREFIX`).
   - `first_frame`: Caminho de uma imagem de referência; o vídeo é animado a partir dela (o modelo é FL2VA, treinado para isso) (default `None`).
   - `steps`: Passos do sampler (default 20, ou 6 com turbo=True). Mais passos = mais detalhe e mais tempo, proporcionalmente (default `None`).
   - `turbo`: Usa a Turbo LoRA (4-8 steps em vez de 20, ~3x mais rápido). Exige o custom node ComfyUI-MiniMax-H3-Turbo e a LoRA em models/loras/ (default `False`).
   - `turbo_lora`: Nome do arquivo da Turbo LoRA (default minimax_h3_turbo_v4_step600_ema.safetensors). Só vale com turbo=True (default `None`).
   - `turbo_strength`: Força da Turbo LoRA (default 1.0; o autor recomenda não mexer). Só vale com turbo=True (default `None`).
   - `turbo_low_vram`: True funde a LoRA nos pesos (menor pico de VRAM, imagem mais macia num modelo quantizado); False aplica em tempo de execução (mais nítida, mais VRAM). Default True (default `None`).
2. Chame `submit_scene` com esses parâmetros. Se a variante default do servidor MCP estiver indisponível, use a variante conectada (`minimax-video-factory-remote` ou `minimax-video-factory-uv`).
3. Reporte o `prompt_id`. O render NÃO terminou: use `/minimax-wait <prompt_id>` para aguardar, ou `/minimax-status <prompt_id>` para checar sem bloquear.
