# Slash commands

<!-- GERADO AUTOMATICAMENTE por scripts/generate_commands.py -->
<!-- Não edite à mão: rode `uv run python scripts/generate_commands.py`. -->

Um comando do OpenCode para cada ferramenta MCP. Esta página descreve o uso humano; a referência de programação das tools está em [MCP Tools Reference](MCP_TOOLS.md).

| Comando | Tool | O que faz |
|---|---|---|
| `/kb-buscar` | `knowledge_search` | Busca na base de conhecimento (palavra-chave + semântica) |
| `/kb-ingest-audio` | `knowledge_ingest_audio` | Transcreve e documenta um áudio/podcast na base de conhecimento |
| `/kb-ingest-markdown` | `knowledge_ingest_markdown` | Importa arquivos markdown (ex.: Obsidian) para a base de conhecimento |
| `/kb-ingest-texto` | `knowledge_ingest_text` | Resume e documenta um texto na base de conhecimento com a IA local |
| `/kb-ingest-video` | `knowledge_ingest_video` | Baixa, transcreve e documenta um vídeo na base de conhecimento |
| `/kb-perguntar` | `knowledge_ask` | Responde uma pergunta usando RAG sobre a base de conhecimento |
| `/kb-reindex` | `knowledge_reindex` | Recalcula chunks e embeddings de todos os documentos da base |
| `/minimax-compose` | `compose_final` | Concatena cenas .mp4 em um vídeo final com ffmpeg |
| `/minimax-download` | `download_video` | Baixa um vídeo (Instagram Reel, YouTube) via MCP yt-dlp, opcionalmente transcreve com Whisper |
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

### `/minimax-gerar-video`

Gera um vídeo no MiniMax H3 (texto→vídeo com áudio nativo estéreo) via MCP.

```
/minimax-gerar-video <prompt> [duration=10.0] [width=1024] [height=576] [seed] [filename_prefix=studio/] [first_frame]
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

**Notas operacionais:**

- Se `prompt` vier em PT, traduza para uma descrição visual EN rica antes de chamar a tool.
- Aguarde o render completar (5-20 min; use `wait_for_video` se a tool retornar só o prompt_id). Reporte o caminho final do vídeo (host, via `OUTPUT_HOST_DIR`) e o prompt_id.
- Se houver erro de OOM, reduza para 512x320 e tente novamente.
- Se a tool travar com timeout de client MCP, chame primeiro `submit_scene` e depois `wait_for_video(prompt_id)` em separado.

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
/minimax-submit-scene <prompt> [duration=5.0] [width=1024] [height=576] [seed] [filename_prefix=OUTPUT_PREFIX] [first_frame]
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

## Base de conhecimento

### `/kb-buscar`

Busca na base de conhecimento (palavra-chave + semântica).

```
/kb-buscar <query> [top_k=5]
```

| Parâmetro | Obrigatório | Default | Descrição |
|---|---|---|---|
| `query` | sim | — | Termo ou pergunta para buscar na base de conhecimento |
| `top_k` | não | `5` | Número máximo de resultados |

**Notas operacionais:**

- Reporte título, trechos e URL de origem de cada resultado, para o usuário conseguir voltar à fonte.

### `/kb-ingest-audio`

Transcreve e documenta um áudio/podcast na base de conhecimento.

```
/kb-ingest-audio <path_or_url> [browser=STUDIO_BROWSER] [whisper_model=WHISPER_MODEL]
```

| Parâmetro | Obrigatório | Default | Descrição |
|---|---|---|---|
| `path_or_url` | sim | — | caminho local OU URL; se for URL, baixa antes de transcrever |
| `browser` | não | `STUDIO_BROWSER` | Navegador para cookies (se for URL) |
| `whisper_model` | não | `WHISPER_MODEL` | Tamanho do modelo Whisper |

### `/kb-ingest-markdown`

Importa arquivos markdown (ex.: Obsidian) para a base de conhecimento.

```
/kb-ingest-markdown <path> [recursive=False] [doc_type=document]
```

| Parâmetro | Obrigatório | Default | Descrição |
|---|---|---|---|
| `path` | sim | — | arquivo .md ou diretório; diretórios com ponto (.obsidian, .trash) são ignorados |
| `recursive` | não | `False` | cuidado ao apontar para um vault inteiro — pode ser milhares de arquivos |
| `doc_type` | não | `document` | Tipo do documento na base (ex.: document, tutorial) |

**Notas operacionais:**

- Quando a nota já tem uma seção `## Summary`, esse texto é reaproveitado e o LLM é pulado — é o que torna a importação em massa viável (minutos em vez de horas).
- Reporte quantos arquivos foram importados de quantos encontrados.

### `/kb-ingest-texto`

Resume e documenta um texto na base de conhecimento com a IA local.

```
/kb-ingest-texto <text> [source_url] [title] [platform=manual]
```

| Parâmetro | Obrigatório | Default | Descrição |
|---|---|---|---|
| `text` | sim | — | Texto/transcrição já pronta para processar |
| `source_url` | não | `None` | URL de origem, se houver |
| `title` | não | `None` | Título do documento |
| `platform` | não | `manual` | Origem: manual, instagram, youtube, podcast |

**Notas operacionais:**

- Reporte o `document_id`, o título e as tags geradas.

### `/kb-ingest-video`

Baixa, transcreve e documenta um vídeo na base de conhecimento.

```
/kb-ingest-video <url> [browser=STUDIO_BROWSER] [whisper_model=WHISPER_MODEL]
```

| Parâmetro | Obrigatório | Default | Descrição |
|---|---|---|---|
| `url` | sim | — | URL do vídeo (Instagram Reel, YouTube, etc.) |
| `browser` | não | `STUDIO_BROWSER` | Navegador para cookies |
| `whisper_model` | não | `WHISPER_MODEL` | Tamanho do modelo Whisper |

**Notas operacionais:**

- Leva minutos: download + Whisper + LLM. Avise o usuário.

### `/kb-perguntar`

Responde uma pergunta usando RAG sobre a base de conhecimento.

```
/kb-perguntar <query> [top_k=3]
```

| Parâmetro | Obrigatório | Default | Descrição |
|---|---|---|---|
| `query` | sim | — | Pergunta em linguagem natural sobre o que já foi salvo |
| `top_k` | não | `3` | Quantos documentos usar como contexto |

**Notas operacionais:**

- A resposta vem APENAS da base. Se ela disser que não sabe, isso é o comportamento correto — não complete com conhecimento próprio.
- Sempre mostre as fontes junto da resposta.

### `/kb-reindex`

Recalcula chunks e embeddings de todos os documentos da base.

```
/kb-reindex [embedding_model]
```

| Parâmetro | Obrigatório | Default | Descrição |
|---|---|---|---|
| `embedding_model` | não | `None` | default: EMBEDDING_MODEL do .env |

**Notas operacionais:**

- Rode depois de trocar o modelo de embedding: vetores antigos não são comparáveis com os novos, e a busca degrada em silêncio até reindexar.
- Percorre a base inteira — pode demorar proporcionalmente ao tamanho dela.

