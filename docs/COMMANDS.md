# Slash commands

<!-- GERADO AUTOMATICAMENTE por scripts/generate_commands.py -->
<!-- Não edite à mão: rode `uv run python scripts/generate_commands.py`. -->

Um comando para cada ferramenta MCP, gerado para os dois clientes: OpenCode (`.opencode/command/`) e Claude Code (`.claude/commands/`). Esta página descreve o uso humano; a referência de programação das tools está em [MCP Tools Reference](MCP_TOOLS.md).

Os comandos `kb-*` só funcionam contra o servidor **host** (`minimax-knowledge-base`): as tools `knowledge_*` falam direto com Postgres e Ollama, que o container não alcança. Os demais rodam no container.

| Comando | Tool | O que faz |
|---|---|---|
| `/minimax-compose` | `compose_final` | Concatena cenas .mp4 em um vídeo final com ffmpeg |
| `/minimax-download` | `download_video` | Baixa um vídeo (Instagram Reel, YouTube) via MCP yt-dlp, opcionalmente transcreve com Whisper |
| `/minimax-fila` | `queue_status` | Mostra a fila de renderização com barra de progresso |
| `/minimax-gerar-video` | `generate_video` | Gera um vídeo no MiniMax H3 (texto→vídeo com áudio nativo estéreo) via MCP |
| `/minimax-health` | `health_check` | Verifica o ComfyUI e a presença dos modelos MiniMax H3 |
| `/minimax-outputs` | `list_outputs` | Lista os vídeos .mp4 já gerados, do mais recente para o mais antigo |
| `/minimax-prompt-cinematico` | `create_cinematic_prompt` | Converte uma transcrição em um prompt estruturado do MiniMax H3 |
| `/minimax-status` | `get_status` | Checa o estado de um render já submetido, sem bloquear |
| `/minimax-studio` | `studio_pipeline` | Pipeline completo: URL → download → transcrição → prompt → vídeo |
| `/minimax-submit-scene` | `submit_scene` | Enfileira uma cena no ComfyUI e devolve o prompt_id, sem esperar o render |
| `/minimax-transcrever` | `transcribe_video` | Transcreve um vídeo local com Whisper (faster-whisper, GPU) |
| `/minimax-wait` | `wait_for_video` | Bloqueia até um render terminar e devolve o caminho do .mp4 |

## Pipeline de vídeo

### `/minimax-compose`

Concatena cenas .mp4 em um vídeo final com ffmpeg.

```
/minimax-compose <scene_paths> [output_path=output/final.mp4]
```

| Parâmetro | Obrigatório | Default | Descrição |
|---|---|---|---|
| `scene_paths` | sim | — | lista ordenada de arquivos .mp4 — a ordem é a ordem em que as cenas aparecem no vídeo final |
| `output_path` | não | `output/final.mp4` | onde escrever o vídeo composto |

**Notas operacionais:**

- São necessárias ao menos 2 cenas; com menos, a tool recusa.

### `/minimax-download`

Baixa um vídeo (Instagram Reel, YouTube) via MCP yt-dlp, opcionalmente transcreve com Whisper.

```
/minimax-download <url> [browser=chrome] [transcrever] [model_size=small] [language=pt]
```

| Parâmetro | Obrigatório | Default | Descrição |
|---|---|---|---|
| `url` | sim | — | URL do vídeo — Instagram Reel, YouTube, etc |
| `browser` | não | `chrome` | navegador de onde ler os cookies (chrome, firefox, edge, brave). Se der erro de "database locked", oriente a fechar o navegador |
| `transcrever` | não | — | flag — se presente, transcreva o vídeo baixado com Whisper |
| `model_size` | não | `small` | tiny/base/small/medium/large-v3, se for transcrever |
| `language` | não | `pt` | código do idioma, se for transcrever |

**Notas operacionais:**

- Reporte o arquivo salvo (dir `downloads/`), título, duração e uploader.
- Se `transcrever` foi pedido, chame `transcribe_video` com o caminho baixado (GPU, `device=cuda`) e reporte o texto + segmentos com timestamps. Alternativamente, o usuário pode usar o comando dedicado `/minimax-transcrever <arquivo>` depois.
- Não gere vídeo a menos que o usuário peça explicitamente.

### `/minimax-fila`

Mostra a fila de renderização com barra de progresso.

```
/minimax-fila [watch_seconds=20.0]
```

| Parâmetro | Obrigatório | Default | Descrição |
|---|---|---|---|
| `watch_seconds` | não | `20.0` | quanto tempo ouvir o progresso. Um step em 1024x576 leva dezenas de segundos, então uma janela curta pode não capturar nada — use 0 para pular e ver só a fila |

**Notas operacionais:**

- Mostre o campo `summary`, que já vem formatado para leitura humana.
- A porcentagem conta apenas os steps do sampler. O decode do VAE e a codificação do vídeo vêm depois e não aparecem — não anuncie 100% do sampler como vídeo pronto.
- Se a fila tiver itens que o usuário não submeteu, avise: podem ser sobras de runs de CI cancelados, que já entupiram a fila antes.

### `/minimax-gerar-video`

Gera um vídeo no MiniMax H3 (texto→vídeo com áudio nativo estéreo) via MCP.

```
/minimax-gerar-video <prompt> [duration=10.0] [width=1024] [height=576] [seed] [filename_prefix=studio/] [first_frame] [last_frame] [steps] [turbo=False] [turbo_lora] [turbo_strength] [turbo_low_vram] [wait_seconds=900.0]
```

| Parâmetro | Obrigatório | Default | Descrição |
|---|---|---|---|
| `prompt` | sim | — | descrição cinematográfica/estruturada do vídeo (shots, câmera, iluminação, áudio) |
| `duration` | não | `10.0` | duração do clipe, 4-15s; o servidor arredonda para a grade de 17 frames |
| `width` | não | `1024` | não suba de 1024 — 1344x768 dá OOM no sampler com 12 GB VRAM (`torch.OutOfMemoryError`). 512x320 é o mais rápido (~5 min) |
| `height` | não | `576` | não suba de 576 pelo mesmo motivo de VRAM |
| `seed` | não | `None` | semente aleatória (inteiro); omita para aleatório |
| `filename_prefix` | não | `studio/` | prefixo do arquivo de saída |
| `first_frame` | não | `None` | Caminho de uma imagem de referência; o vídeo é animado a partir dela (o modelo é FL2VA, treinado para isso) |
| `last_frame` | não | `None` | Caminho de uma imagem onde o clipe deve TERMINAR. Com os dois âncoras o movimento desacelera até um quadro escolhido, em vez de ser cortado onde derivou — é o que emenda bem quando vários clipes viram um vídeo só |
| `steps` | não | `None` | Passos do sampler (default 20, ou 6 com turbo=True). Medido: 30 e 40 não melhoram e custam 8x o tempo |
| `turbo` | não | `False` | Usa a Turbo LoRA (4-8 steps em vez de 20, ~3x mais rápido). Exige o custom node ComfyUI-MiniMax-H3-Turbo e a LoRA em models/loras/ |
| `turbo_lora` | não | `None` | Nome do arquivo da Turbo LoRA (default minimax_h3_turbo_v4_step600_ema.safetensors). Só vale com turbo=True |
| `turbo_strength` | não | `None` | Força da Turbo LoRA (default 1.0; o autor recomenda não mexer). Só vale com turbo=True |
| `turbo_low_vram` | não | `None` | True funde a LoRA nos pesos (menor pico de VRAM, imagem mais macia num modelo quantizado); False aplica em tempo de execução (mais nítida, mais VRAM). Default True |
| `wait_seconds` | não | `900.0` | Quanto esperar antes de devolver só o prompt_id. Medido: 512x320 leva ~4.5min, 1024x576 ~3min com modelo quente |

**Notas operacionais:**

- Se `prompt` vier em PT, traduza para uma descrição visual EN rica antes de chamar a tool.
- Aguarde o render completar (5-20 min; use `wait_for_video` se a tool retornar só o prompt_id). Reporte o caminho final do vídeo (host, via `OUTPUT_HOST_DIR`) e o prompt_id.
- Se houver erro de OOM, reduza para 512x320 e tente novamente.
- A tool espera até `wait_seconds` (default 240s). Se o render não terminar nesse prazo ela devolve `state=rendering` com o `prompt_id` — isso não é erro. Colete com `/minimax-wait <prompt_id>` ou acompanhe com `/minimax-fila`.

### `/minimax-health`

Verifica o ComfyUI e a presença dos modelos MiniMax H3.

```
/minimax-health
```

**Notas operacionais:**

- Rode isto ANTES de um render longo: descobrir que falta um modelo depois de 20 minutos de espera é o desperdício que este comando evita.
- Se algum modelo estiver ausente, aponte `scripts/download_models.sh`.

### `/minimax-outputs`

Lista os vídeos .mp4 já gerados, do mais recente para o mais antigo.

```
/minimax-outputs
```

### `/minimax-prompt-cinematico`

Converte uma transcrição em um prompt estruturado do MiniMax H3.

```
/minimax-prompt-cinematico <transcription> [style=cinematic]
```

| Parâmetro | Obrigatório | Default | Descrição |
|---|---|---|---|
| `transcription` | sim | — | texto completo da transcrição do vídeo |
| `style` | não | `cinematic` | cinematic, educational ou social |

**Notas operacionais:**

- Isto só monta o prompt — não gera vídeo. Para gerar, passe o resultado para `/minimax-gerar-video`.

### `/minimax-status`

Checa o estado de um render já submetido, sem bloquear.

```
/minimax-status <prompt_id>
```

| Parâmetro | Obrigatório | Default | Descrição |
|---|---|---|---|
| `prompt_id` | sim | — | o id devolvido por `/minimax-submit-scene` |

**Notas operacionais:**

- Reporte o estado (`queued`, `running`, `completed`, `error`) e, se completo, o caminho do arquivo.

### `/minimax-studio`

Pipeline completo: URL → download → transcrição → prompt → vídeo.

```
/minimax-studio <url> [style=cinematic] [duration=10.0] [width=1024] [height=576]
```

| Parâmetro | Obrigatório | Default | Descrição |
|---|---|---|---|
| `url` | sim | — | URL do vídeo de origem — Instagram Reel, YouTube, etc |
| `style` | não | `cinematic` | cinematic, educational ou social |
| `duration` | não | `10.0` | duração do clipe gerado, em segundos |
| `width` | não | `1024` | largura; não suba de 1024 — OOM no sampler com 12 GB VRAM |
| `height` | não | `576` | altura; não suba de 576 pelo mesmo motivo de VRAM |

**Notas operacionais:**

- É o mais demorado de todos (download + Whisper + render). Avise o usuário antes de começar.
- Reporte cada etapa conforme concluir, não só o resultado final.

### `/minimax-submit-scene`

Enfileira uma cena no ComfyUI e devolve o prompt_id, sem esperar o render.

```
/minimax-submit-scene <prompt> [duration=5.0] [width=1024] [height=576] [seed] [filename_prefix=OUTPUT_PREFIX] [first_frame] [last_frame] [steps] [turbo=False] [turbo_lora] [turbo_strength] [turbo_low_vram]
```

| Parâmetro | Obrigatório | Default | Descrição |
|---|---|---|---|
| `prompt` | sim | — | prompt estruturado do MiniMax H3 (shots + câmera + áudio) |
| `duration` | não | `5.0` | duração do clipe, 4-15s; arredonda para a grade de 17 frames |
| `width` | não | `1024` | largura (múltiplo de 32); não suba de 1024 — OOM no sampler com 12 GB VRAM |
| `height` | não | `576` | altura (múltiplo de 32); não suba de 576 pelo mesmo motivo de VRAM |
| `seed` | não | `None` | semente aleatória (inteiro); omita para aleatório |
| `filename_prefix` | não | `OUTPUT_PREFIX` | prefixo do arquivo de saída |
| `first_frame` | não | `None` | Caminho de uma imagem de referência; o vídeo é animado a partir dela (o modelo é FL2VA, treinado para isso) |
| `last_frame` | não | `None` | Caminho de uma imagem onde o clipe deve TERMINAR. Com os dois âncoras o movimento desacelera até um quadro escolhido, em vez de ser cortado onde derivou — é o que emenda bem quando vários clipes viram um vídeo só |
| `steps` | não | `None` | Passos do sampler (default 20, ou 6 com turbo=True). Mais passos = mais detalhe e mais tempo, proporcionalmente |
| `turbo` | não | `False` | Usa a Turbo LoRA (4-8 steps em vez de 20, ~3x mais rápido). Exige o custom node ComfyUI-MiniMax-H3-Turbo e a LoRA em models/loras/ |
| `turbo_lora` | não | `None` | Nome do arquivo da Turbo LoRA (default minimax_h3_turbo_v4_step600_ema.safetensors). Só vale com turbo=True |
| `turbo_strength` | não | `None` | Força da Turbo LoRA (default 1.0; o autor recomenda não mexer). Só vale com turbo=True |
| `turbo_low_vram` | não | `None` | True funde a LoRA nos pesos (menor pico de VRAM, imagem mais macia num modelo quantizado); False aplica em tempo de execução (mais nítida, mais VRAM). Default True |

**Notas operacionais:**

- Reporte o `prompt_id`. O render NÃO terminou: use `/minimax-wait <prompt_id>` para aguardar, ou `/minimax-status <prompt_id>` para checar sem bloquear.

### `/minimax-transcrever`

Transcreve um vídeo local com Whisper (faster-whisper, GPU).

```
/minimax-transcrever <video_path> [model_size=small] [device=cuda] [language=pt]
```

| Parâmetro | Obrigatório | Default | Descrição |
|---|---|---|---|
| `video_path` | sim | — | caminho do arquivo .mp4/.mkv/.webm (aceita path do host, ex.: `downloads/Video.mp4`); se vier relativo, assuma relativo ao diretório do projeto (`$PROJECT_ROOT`) |
| `model_size` | não | `small` | modelo Whisper: tiny/base/small/medium/large-v3 |
| `device` | não | `cuda` | `cuda` (GPU) ou `cpu` |
| `language` | não | `pt` | código do idioma (pt, en, es, ...) |

**Notas operacionais:**

- Reporte o texto transcrito + segmentos com timestamps + idioma detectado.
- Não gere vídeo nem crie prompt a menos que o usuário peça.

### `/minimax-wait`

Bloqueia até um render terminar e devolve o caminho do .mp4.

```
/minimax-wait <prompt_id> [timeout=1200.0]
```

| Parâmetro | Obrigatório | Default | Descrição |
|---|---|---|---|
| `prompt_id` | sim | — | o id devolvido por `/minimax-submit-scene` |
| `timeout` | não | `1200.0` | segundos máximos de espera; renders de 1024x576 levam 5-20 min |

**Notas operacionais:**

- Este comando BLOQUEIA. Se o usuário só quer saber o estado agora, use `/minimax-status` em vez deste.

