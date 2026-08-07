# Local Knowledge Base + Busca via IA — MVP (1 semana)

Status: aprovado pelo usuário, pronto para plano de implementação.

## Contexto

O projeto `minimax-video-factory` já é um MCP local (FastMCP) que baixa vídeos do
Instagram/YouTube (`download_video`) e transcreve localmente com faster-whisper
(`transcribe_video`), como parte de um "Audiovisual Studio" originalmente pensado
para gerar vídeos com MiniMax H3.

Objetivo maior do usuário: consolidar toda a base de conhecimento pessoal (vídeos
salvos do Instagram, sites salvos via Karakeep+Obsidian, podcasts/áudio) em um
lugar só, com IA local (Ollama) resumindo/documentando o conteúdo e permitindo
buscar e perguntar sobre o que já foi salvo — hoje frequentemente perdido
(comandos esquecidos, sites/vídeos salvos e nunca mais encontrados).

O vault Obsidian atual (`$HOME/Documents/Obsidian Vault`, ~158MB, 1067
arquivos, pasta `Hoarder/` sincronizada do Karakeep) é considerado pelo usuário
possivelmente problemático/grande demais para ser a fonte de verdade. Decisão:
o Obsidian deixa de ser a fonte de verdade; vira, no máximo, uma cópia legível
opcional. A fonte de verdade estruturada passa a ser um banco SQLite próprio.

**Escopo desta fase:** só o pipeline de ingestão + busca via MCP/OpenCode (sem
site/CLI, sem multi-usuário, sem produto). Validação de uso pessoal primeiro,
mas com peças desacopladas (LLM plugável, storage separado da ingestão) para
não travar uma eventual virada para produto no futuro — sem construir
multi-tenant/auth/billing agora.

## Arquitetura

```
Reel IG / Podcast / Áudio
  │  [ingestão] download → transcrição (Whisper, já existe)
  ▼
LLM  ──(interface plugável: Ollama local | OpenAI-compatible cloud free)
  │      JSON {resumo, tutorial, objetivos, tags}
  ▼
┌──────────────────────────────────────────┐
│  BASE PRÓPRIA  (knowledge.db, SQLite)     │  ← fonte de verdade estruturada
│  documents + chunks + embeddings + tags   │     separada do Obsidian
└──────────────────────────────────────────┘
  │  (cópia legível, opcional: nota .md no Obsidian)
  ▼
knowledge_search(query)  → FTS5 (palavra-chave) + cosseno (semântica, mxbai-embed-large)
knowledge_ask(query)     → RAG: contexto da base + resposta do LLM
```

- Busca e ingestão só via MCP/OpenCode — nada de site/CLI no MVP.
- Só entra na base o que o MCP produz — não escaneia o vault inteiro; cada item
  é uma entrada estruturada com metadados (fonte, URL, idioma, tags).
- Site web agregador ("produto final" mencionado pelo usuário) é visão de longo
  prazo, fora desta fase — só faz sentido depois de validar isto com uso real.

## Decisões técnicas-chave

1. **LLM abstrato** (`llm.py`): backend `ollama` (default local, ex.
   `qwen2.5:32b-instruct-q4_K_M`, já instalado) ou `openai-compatible`
   (URL + API key, ex. OpenRouter/Groq free tier). Selecionado via `.env`
   (`LLM_PROVIDER`) — mesmo código de chamada para os dois, zero lock-in em
   um provedor.
2. **Embeddings sempre locais** (`mxbai-embed-large`, já instalado no Ollama) —
   busca semântica privada e sem custo, independente do `LLM_PROVIDER`
   escolhido para geração de texto.
3. **SQLite é o produto final** (fonte de verdade estruturada); Obsidian só
   recebe, opcionalmente, uma cópia em markdown para leitura humana — fácil de
   desacoplar/desligar depois sem perder dados (os dados reais estão no SQLite).
4. **MCP roda em modo host** (`uv run`) — acesso direto a Ollama (`localhost:11434`),
   ao arquivo SQLite e ao vault, sem a complexidade de rede Docker que o modo
   containerizado (usado hoje para o ComfyUI) exigiria.

## Schema SQLite (`knowledge.db`)

Um schema único, genérico por tipo de conteúdo (`documents.type`), para caber
vídeo agora e podcast/site depois sem migração de schema:

- **`documents`**: `id`, `type` (`video`|`audio`|`text`), `source_url`,
  `platform` (`instagram`|`youtube`|`podcast`|`manual`), `title`, `language`,
  `transcription_text`, `summary`, `tutorial`, `objectives`, `tags` (JSON/CSV),
  `raw_file_path`, `llm_provider`, `llm_model`, `created_at`.
- **`chunks`**: `id`, `document_id` (FK), `chunk_text`, `chunk_index` — texto
  dividido em pedaços menores para embeddings (a transcrição/tutorial completos
  não cabem bem num único vetor de busca).
- **`embeddings`**: `chunk_id` (FK), `vector` (BLOB, `mxbai-embed-large`),
  `model`.
- **FTS5**: tabela virtual sobre `chunks.chunk_text` (e/ou `documents.title`,
  `summary`) para busca por palavra-chave, combinada com similaridade de
  cosseno sobre `embeddings` para busca semântica em `knowledge_search`.

## Novas tools MCP

Reaproveitam `download_video`/`transcribe_video` já existentes internamente
quando aplicável:

- `knowledge_ingest_video(url, style?)` — baixa (se URL) → transcreve →
  LLM gera `{resumo, tutorial, objetivos, tags}` → salva em `documents`
  (+ chunks + embeddings) → opcionalmente escreve cópia `.md` no vault.
- `knowledge_ingest_audio(path_or_url)` — mesma pipeline para podcast/áudio
  (sem etapa de vídeo; usa Whisper diretamente no áudio).
- `knowledge_ingest_text(text, source_url?, title?)` — pula download/transcrição;
  útil para colar uma transcrição já pronta ou texto de outra origem.
- `knowledge_search(query, top_k?)` — FTS5 (palavra-chave) + similaridade de
  cosseno (semântica) combinadas, retorna documentos/chunks mais relevantes.
- `knowledge_ask(query)` — RAG: busca contexto relevante via `knowledge_search`,
  monta prompt com esse contexto, pede resposta ao LLM configurado.
- `knowledge_reindex()` — recalcula embeddings/FTS para documentos existentes
  (útil após trocar de modelo de embedding ou corrigir dados).

## Novos arquivos

- `src/minimax_mcp/llm.py` — cliente abstrato LLM (Ollama / OpenAI-compatible)
  + prompts que pedem saída JSON estruturada (`resumo`, `tutorial`, `objetivos`,
  `tags`).
- `src/minimax_mcp/base.py` — schema SQLite + CRUD + FTS5 + geração/consulta
  de embeddings.
- `src/minimax_mcp/vault.py` — escrita opcional de cópia `.md` no Obsidian
  (best-effort; falha aqui não deve derrubar a ingestão).
- `tests/08_knowledge.sh` — teste de fumaça: ingest → search → ask, seguindo o
  padrão dos testes `0N_*.sh` existentes.
- Novas vars em `.env`/`.env.example`: `LLM_PROVIDER`, `OLLAMA_URL`, `LLM_MODEL`,
  `OPENAI_API_URL`, `OPENAI_API_KEY`, `EMBEDDING_MODEL`, `KB_DB_PATH`,
  `VAULT_PATH` (opcional — se ausente, pula a cópia `.md`).

## Erros e casos de borda

- LLM local indisponível (Ollama não rodando) ou saída não é JSON válido:
  `knowledge_ingest_*` retorna `{"ok": false, "error": ...}` sem gravar
  documento parcial no SQLite (evita entradas incompletas).
- Cópia para o Obsidian falha (vault ausente/corrompido): não deve bloquear a
  ingestão — o SQLite já tem os dados; log de aviso, `ok: true` mesmo assim.
- Download/transcrição falhando: já tratado pelas tools existentes
  (`download_video`/`transcribe_video`), reaproveitado sem mudança de contrato.
- `knowledge_search`/`knowledge_ask` com base vazia: retorna lista vazia /
  aviso claro, não erro.

## Testes

Seguir o padrão `tests/0N_*.sh` (bash, ecoa `[ok]`/`[MISS]`/`[BAD]`) já usado
no projeto:
- `tests/08_knowledge.sh`: cria DB de teste, ingere um texto de exemplo
  (`knowledge_ingest_text`, sem depender de rede/Instagram), confirma linha em
  `documents`, roda `knowledge_search` e `knowledge_ask` e valida que retornam
  resultado não vazio coerente com o texto ingerido.
- Reindexação (`knowledge_reindex`) testada separadamente contra os mesmos
  dados de fumaça.

## Entrega por dia (referência; plano detalhado fica a cargo do writing-plans)

| Dia | Entregável |
|---|---|
| D1 | `llm.py` — cliente abstrato (Ollama + OpenAI-compat) + prompts JSON |
| D2 | `base.py` — schema SQLite + CRUD + FTS5 + embeddings |
| D3 | `vault.py` + `knowledge_ingest_video` / `knowledge_ingest_audio` |
| D4 | `knowledge_search` (FTS+cosseno) + `knowledge_ask` (RAG) |
| D5 | `.env`, `opencode.json` (modo host), `tests/08_knowledge.sh`, docs |

## Pós-MVP (fora desta semana)

- Ingestor do Karakeep → base própria (migra os sites da pasta `Hoarder/` do
  Obsidian para o SQLite estruturado).
- Site web de busca sobre a base (o "produto final" de longo prazo).
- Dedup avançado, reranking, MOCs automáticos.
