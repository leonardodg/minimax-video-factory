# Knowledge Base — Tutorial & Reference

Base de conhecimento pessoal alimentada por **Postgres + pgvector** (armazenamento
e busca semântica) e um **LLM local (Ollama)** que transforma transcrições/textos em
resumo, tutorial passo-a-passo, objetivos e tags. Tudo roda localmente (sem nuvem).

Neste documento:
- [1. O que é / quando usar](#1-o-que-é--quando-usar)
- [2. Prerequisitos & setup](#2-prerequisitos--setup)
- [3. As 6 tools (referência completa + melhores opções)](#3-as-6-tools)
- [4. Fluxos recomendados passo-a-passo](#4-fluxos-recomendados)
- [5. Usar pelo chat do OpenCode (exemplos de prompts)](#5-usar-pelo-chat-do-opencode)
- [6. Estrutura da base de dados](#6-estrutura-da-base-de-dados)
- [7. Configuração (.env)](#7-configuração-env)
- [8. Solução de problemas](#8-solução-de-problemas)

---

## 1. O que é / quando usar

O MCP de vídeo expõe **17 tools no total** (11 originais do MiniMax H3/Studio + 6 da
knowledge base). As 6 novas:

| Tool | O que faz | Precisa GPU? |
|---|---|---|
| `knowledge_ingest_text` | Salva um texto/transcrição pronto na base (resumo+tutorial via LLM) | Não |
| `knowledge_ingest_video` | Baixa + transcreve + documenta um vídeo (Reel/YouTube) | Sim (Whisper GPU) |
| `knowledge_ingest_audio` | Transcreve + documenta um áudio/podcast | Sim (Whisper GPU) |
| `knowledge_search` | Busca por palavra-chave + semântica na base | Não |
| `knowledge_ask` | Responde perguntas com RAG (busca + LLM) sobre o que já foi salvo | Não |
| `knowledge_reindex` | Recalcula chunks + embeddings de todos os documentos | Não |

**Ciclo de vida típico:** `ingest_*` → `search`/`ask` → (troca de modelo de
embedding?) → `reindex`.

---

## 2. Prerequisitos & setup

```bash
cd $PROJECT_ROOT
source scripts/config.sh

# 1. Postgres + pgvector (container dedicado minimax-kb-postgres)
docker compose $COMPOSE_ARGS up -d postgres

# 2. Tabelas (alembic) — só uma vez
uv run alembic upgrade head

# 3. Ollama rodando com os modelos
ollama list          # deve mostrar lfm2:24b e mxbai-embed-large
# se faltar:
# ollama pull lfm2:24b
# ollama pull mxbai-embed-large
```

> **Onde o servidor roda:** a knowledge base usa **host-uv** (`uv run python
> src/minimax_mcp/server.py`), não o container do ComfyUI — precisa acessar
> `localhost:11434` (Ollama) e `127.0.0.1:5432` (Postgres) direto do host.

---

## 3. As 6 tools

### `knowledge_ingest_text`

Guarda um texto/transcrição **já pronto** (colado, arquivo, transcrição de outro
lugar) e gera `resumo` + `tutorial` + `objetivos` + `tags` via LLM.

| Parâmetro | Obrigatório | Default | Melhor opção |
|---|---|---|---|
| `text` | ✅ | — | A transcrição completa; quanto mais contexto, melhor o tutorial |
| `source_url` | ❌ | `null` | URL de origem (Reel, YT, artigo) para linkar no resultado |
| `title` | ❌ | resumo[0:80] | Título curto e descritivo |
| `platform` | ❌ | `manual` | `manual`, `instagram`, `youtube`, `podcast` |

**Retorna:** `{ok, document_id, title, summary, tutorial, tags, vault}`

### `knowledge_ingest_video`

Baixa (yt-dlp + cookies), transcreve (Whisper GPU) e documenta um vídeo em um passo.

| Parâmetro | Obrigatório | Default | Melhor opção |
|---|---|---|---|
| `url` | ✅ | — | URL do Reel/YouTube |
| `browser` | ❌ | `chrome` | `chrome`, `firefox`, `edge`, `brave` — use o navegador logado |
| `whisper_model` | ❌ | `small` | `small` (bom equilíbrio), `medium` (mais preciso), `large-v3` (máx., lento) |

> **Atenção GPU:** usa Whisper em `cuda`; cada ingest consome VRAM por alguns minutos.

### `knowledge_ingest_audio`

Igual ao vídeo, mas para **áudio/podcast**. Aceita caminho local **ou** URL (baixa primeiro).

| Parâmetro | Obrigatório | Default | Melhor opção |
|---|---|---|---|
| `path_or_url` | ✅ | — | `/path/audio.mp3` ou URL de podcast |
| `browser` | ❌ | `chrome` | só relevante se passar URL |
| `whisper_model` | ❌ | `small` | idem acima |

### `knowledge_search`

Busca híbrida: **full-text em português** (Postgres `to_tsvector`) + **cosseno
semântico** (pgvector `mxbai-embed-large`). Retorna snippets ranqueados.

| Parâmetro | Obrigatório | Default | Melhor opção |
|---|---|---|---|
| `query` | ✅ | — | termo ou frase curta |
| `top_k` | ❌ | `5` | `5–10` para explorar, `3` para contexto de pergunta |

### `knowledge_ask`

RAG: busca os `top_k` documentos relevantes, monta contexto e o LLM responde **só
com base nisso** (não inventa — diz se não sabe). Retorna também `sources`.

| Parâmetro | Obrigatório | Default | Melhor opção |
|---|---|---|---|
| `query` | ✅ | — | pergunta em linguagem natural |
| `top_k` | ❌ | `3` | `3` típico; aumente para perguntas amplas |

### `knowledge_reindex`

Recalcula chunks + embeddings de **todos** os documentos. Use quando trocar o
modelo de embedding (o `model` fica gravado por chunk).

| Parâmetro | Obrigatório | Default | Melhor opção |
|---|---|---|---|
| `embedding_model` | ❌ | `EMBEDDING_MODEL` do `.env` | só informe se quiser forçar outro |

---

## 4. Fluxos recomendados

**Fluxo A — documentar um Reel de YouTube/Instagram e guardar:**
```
knowledge_ingest_video(url="https://www.youtube.com/watch?v=...", whisper_model="small")
```

**Fluxo B — transcrever um áudio que já está no disco:**
```
knowledge_ingest_audio(path_or_url="/path/meu_podcast.mp3")
```

**Fluxo C — guardar texto colado (notas, artigo, transcrição antiga):**
```
knowledge_ingest_text(text="<cole a transcrição>", title="Meu resumo", platform="manual")
```

**Fluxo D — perguntar à sua base (RAG):**
```
knowledge_ask(query="Como eu instalei o Docker no Ubuntu?")
```

**Fluxo E — manutenção (troca de embedding):**
```
# 1. mude EMBEDDING_MODEL no .env  2. depois:
knowledge_reindex()
```

---

## 5. Usar pelo chat do OpenCode

O servidor MCP `minimax-knowledge-base` já está configurado
(`~/.config/opencode/opencode.json`, `enabled: true`). **Reinicie o opencode** para
carregá-lo; depois é só conversar:

> **"Documente este texto na minha base de conhecimento: [colar texto]"**
> → OpenCode chama `knowledge_ingest_text` e mostra `document_id`, resumo, tutorial e tags.

> **"Baixe, transcreva e salve este Reel na base: https://www.instagram.com/p/DbHIZl5Pk_0/"**
> → `knowledge_ingest_video(url=..., whisper_model="small")` (precisa GPU/Whisper).

> **"Transcreve e documenta este podcast: /path/meu_podcast.mp3"**
> → `knowledge_ingest_audio(path_or_url=...)`.

> **"Pesquise na minha base por 'Docker Ubuntu'"**
> → `knowledge_search(query="Docker Ubuntu")`.

> **"O que eu já salvei sobre Docker? Me responda com base na minha base."**
> → `knowledge_ask(query="O que eu já salvei sobre Docker?")`.

> **"Acabei de trocar o modelo de embedding; reindexe tudo."**
> → `knowledge_reindex()`.

**Dicas de chat:**
1. Se o opencode não achar a tool, confirme que está numa **sessão nova** (MCP é
   carregado no start) e que Postgres + Ollama estão de pé.
2. Prefira `knowledge_ask` para **perguntas** e `knowledge_search` para **listar/explorar**.
3. `ingest_video`/`ingest_audio` usam GPU (Whisper). Se a VRAM estiver ocupada com
   render do H3, use `whisper_model="base"` (mais leve) ou espere terminar.

---

## 6. Estrutura da base de dados

Criada por `alembic upgrade head` (`alembic/versions/0001_initial.py`). Relação:
**1 documento → N chunks → 1 embedding por chunk.**

### `documents` — um registro por item ingerido

| Coluna | Tipo | Descrição |
|---|---|---|
| `id` | integer PK | |
| `type` | varchar(20) | `text`, `video`, `audio` |
| `source_url` | text nullable | URL de origem |
| `platform` | varchar(50) nullable | `manual`, `instagram`, `youtube`, `podcast` |
| `title` | text nullable | |
| `language` | varchar(10) nullable | ex.: `pt` |
| `transcription_text` | text nullable | texto/transcrição original |
| `summary` | text nullable | resumo gerado pelo LLM |
| `tutorial` | text nullable | tutorial passo-a-passo (markdown) |
| `objectives` | text nullable | objetivos, um por linha |
| `tags` | json nullable | lista de tags |
| `raw_file_path` | text nullable | caminho do arquivo original baixado |
| `llm_provider` | varchar(50) nullable | `ollama` |
| `llm_model` | varchar(100) nullable | ex.: `lfm2:24b` |
| `created_at` | datetime | default `now()` |

### `chunks` — trechos de texto com overlap para embedding

| Coluna | Tipo | Descrição |
|---|---|---|
| `id` | integer PK | |
| `document_id` | int FK → `documents.id` (ON DELETE CASCADE) | |
| `chunk_text` | text | trecho (até ~1000 chars, overlap 100) |
| `chunk_index` | integer | ordem dentro do documento |

### `embeddings` — vetor semântico por chunk

| Coluna | Tipo | Descrição |
|---|---|---|
| `id` | integer PK | |
| `chunk_id` | int FK → `chunks.id` (ON DELETE CASCADE, UNIQUE) | 1:1 |
| `model` | varchar(100) | modelo que gerou o vetor (ex.: `mxbai-embed-large`) |
| `vector` | `vector(1024)` (pgvector) | embedding |

### Índices

- GIN full-text em `documents.transcription_text` (linguagem `portuguese`) para
  `to_tsvector`/`plainto_tsquery`.
- Índice vetorial pgvector em `embeddings.vector` para cosseno.

### Como inspecionar

```bash
docker exec minimax-kb-postgres psql -U kb -d knowledge -c "\dt"
docker exec minimax-kb-postgres psql -U kb -d knowledge \
  -c "SELECT id, type, title, llm_model, tags FROM documents ORDER BY id;"
```

---

## 7. Configuração (.env)

| Var | Default | Descrição |
|---|---|---|
| `KB_DATABASE_URL` | `postgresql+psycopg://kb:kb@127.0.0.1:5432/knowledge` | conexão SQLAlchemy |
| `KB_POSTGRES_USER/PASSWORD/DB/PORT` | `kb`/`kb`/`knowledge`/`5432` | usadas pelo compose |
| `LLM_PROVIDER` | `ollama` | ou `openai-compatible` |
| `LLM_MODEL` | `lfm2:24b` | **melhor equilíbrio p/ ~30 GB RAM**. Alternativas: `qwen2.5-coder:14b` (mais rápido, ~1 min/ingest) ou `qwen2.5:32b-instruct-q4_K_M` (mais qualidade, porém 15+ min — swap). `gpt-oss:20b` **não funciona** (ignora `format=json`). |
| `LLM_TIMEOUT` | `900` | timeout por chamada (s); aumente p/ modelos 32B |
| `OLLAMA_URL` | `http://localhost:11434` | |
| `EMBEDDING_MODEL` | `mxbai-embed-large` | embeddings **sempre locais**, mesmo com `LLM_PROVIDER=openai-compatible` |
| `EMBEDDING_DIM` | `1024` | dimensão do vetor (must combinar com o modelo) |
| `VAULT_PATH` | vazio (desligado) | copia markdown p/ Obsidian, se preenchido |
| `WHISPER_MODEL` / `WHISPER_DEVICE` | `small` / `cuda` | transcrição |
| `STUDIO_DOWNLOADS_DIR` | `<projeto>/downloads` | onde arquivos baixados são salvos |

---

## 8. Solução de problemas

| Sintoma | Causa | Fix |
|---|---|---|
| `knowledge_*` retorna erro de conexão com `127.0.0.1:5432` | Postgres não está de pé | `docker compose $COMPOSE_ARGS up -d postgres` |
| Erro `42P01 relation "documents" does not exist` | migração não aplicada | `uv run alembic upgrade head` |
| `LLM generation failed: timed out` | `LLM_TIMEOUT` curto p/ o modelo | use `lfm2:24b` ou aumente `LLM_TIMEOUT` |
| `LLM generation failed: Expecting value... char 0` | modelo devolve texto não-JSON | troque `LLM_MODEL` (`gpt-oss:20b` é incompatível) |
| Ollama não responde | daemon parado | `ollama serve` (ou systemd) |
| OpenCode não vê as tools | sessão antiga / entry não carregado | reinicie o opencode; confira `enabled: true` |
| Embeddings não batem após trocar modelo | chunks com `model` antigo | `knowledge_reindex()` |
