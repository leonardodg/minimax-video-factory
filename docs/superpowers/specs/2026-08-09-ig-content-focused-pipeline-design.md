# Design — Pipeline IG focado no conteúdo principal (imagens/carousels/vídeos)

Date: 2026-08-09
Status: Approved by user
Scope: MiniMax video factory — Instagram saved-posts → Knowledge Base

## Problem

The current IG pipeline describes what is **visible** in the media, not what is
**said/taught**. Symptoms seen in production:

- **doc 104** (carousel "6 cursos de graça", `mariffernandesdaily`): the summary
  says "pessoa com roupas casuais segurando um copo" — the actual list of 6 free
  courses never reached the KB.
- Vision prompt (`llm.build_vision_prompt`) explicitly asks for "cores,
  composição, contexto", which produces clothing/setting detail instead of
  content.
- Carousels: `_pick_download_target` downloads only the **first** resource, so
  content spread across photos 2..N is lost.

The user's premise, generalized to ALL media: **the transcription/description is
only supporting material** for (a) the LLM to write the summary and (b) indexed
query material. The deliverables (`summary`, `tutorial`, `objetivos`) must
capture the **main content** — the tip, the recipe, the step-by-step, what was
taught — not a narration of the video/photo itself.

## Goals

1. Vision output becomes **structured**: `{tipo, categoria, conteudo_principal}`.
2. Category comes from the **user's Instagram collections** (49 names,
   normalized), always chosen by the LLM from that list.
3. Carousels: download **all** photos, describe each, concatenate the
   `conteudo_principal` into one indexed text.
4. Summary/tutorial/objectives for **every** type (video/image/audio) capture
   the main content, using transcription as support only.
5. Category lands as a tag (`categoria:<name>`) so search finds it.
6. After implementation: **wipe existing IG docs and re-ingest** everything with
   the new pipeline.

## Design

### 1. Category list from Instagram collections

New pure-ish helper `ig_sync.list_categories(client) -> list[str]`:

- Calls `client.collections()` once per worker process (cached at module level).
- Normalizes: `name.strip()`, collapse whitespace, drop the auto-collection
  (`"All posts"` / `"Todos os posts"`).
- Deduplicates case-insensitively (keeps first variant) — e.g. "Treino "/"Treino",
  "tips"/"tips ".
- Falls back to a small static list when the network call fails
  (receita, dica, tutorial, tech, curso, estudo, inglês, viagem, house,
  bitcoin, treino, car, dog, livro, notícia, outros).

The worker fetches this once per process and threads it through to the vision
prompt. No per-message network call.

### 2. Structured vision prompt

`llm.build_vision_prompt(categories: list[str] | None) -> str` returns a prompt
asking for JSON:

```json
{
  "tipo": "receita|dica|infografico|tutorial|noticia|outros",
  "categoria": "<uma das categorias, ou 'outros'>",
  "conteudo_principal": "a dica/receita/lista/conteudo em si"
}
```

Prompt rules (PT-BR):
- "Extraia o conteúdo principal: a dica, a receita, a lista, o que o post ensina.
  Ignore aparência física de pessoas, roupas, cenário e objetos de fundo."
- "categoria deve ser uma das listadas; se nenhuma combinar, use 'outros'."
- "Não invente; se não houver texto legível, diga o conteúdo pela cena."

`describe_image(image_path, *, model, categories) -> dict` now POSTs the new
prompt and parses the JSON reply, returning
`{ok, text, tipo, categoria, conteudo_principal}`. `text` is the
`conteudo_principal` (indexed), `categoria`/`tipo` ride along as metadata.

### 3. Carousels — all photos

- `_default_download(message)` returns `{"ok": True, "filepaths": [p1, p2, ...]}`
  instead of a single `filepath` (keep `filepath` = first, for back-compat in
  tests/delete logic).
- `process_message`: for image/carousel, iterate `filepaths`, call `describe`
  per photo, collect `conteudo_principal` (or `text`) pieces, join with `\n\n`,
  and use the **first** photo's `categoria` as the document tag (single
  category per document; the summary LLM sees the full joined text and may
  surface multiple themes in `objetivos`/`tags`).
- Same `filepaths` list is used by the delete-after-ingest step.

### 4. Summary stage — generalized premise

`llm.generate_structured(transcription, *, is_image=False, ...)`:

- `SUMMARY_PROMPT_TEMPLATE` gains an instruction block for ALL types:
  "O texto abaixo é apenas material de apoio (transcrição/descrição). O resumo,
  tutorial e objetivos devem capturar o CONTEÚDO PRINCIPAL — qual é a dica, a
  receita, o passo a passo, o que foi ensinado. Não descreva o vídeo/imagem em
  si, não repita a transcrição."
- For images, `ingest_text` passes `is_image=True` so the template can add:
  "A entrada é a descrição estruturada de uma imagem/post do Instagram."
- `ingest_text` already receives `doc_type`; thread `doc_type=="image"` into
  `generate_structured`.
- `transcription_text` stays as stored (raw transcript / joined
  `conteudo_principal`) and remains in `text_for_chunks` — it is the search
  query material.

### 5. Category → tag

- `process_message` passes `categoria` from the vision result into
  `ingest_text(..., extra_tags=[...])` as `categoria:<name>` alongside the
  existing `collection_name` tag.
- Chunking/indexing already includes tags in the text used for embedding where
  applicable; `knowledge_search` can find by tag + content.

### 6. Testing

- `tests/unit_ig_worker.py`:
  - `_default_download` with a carousel returns all `filepaths` (multiple files).
  - `process_message` with a fake describe returning `conteudo_principal`
    concatenates them into the ingested text.
- `tests/unit_knowledge.py`:
  - `build_vision_prompt(categories)` includes the category list and asks for a
    JSON object with `conteudo_principal`.
  - `describe_image` parses a JSON reply (fake httpx / injected transport).
  - summary prompt template contains the "material de apoio / conteúdo
    principal" instruction for both is_image=True and False.
- `tests/unit_ig_sync.py` (or unit_knowledge): `list_categories` normalization —
  trailing spaces collapsed, duplicates removed, auto-collection dropped.
- Integration (manual after code): re-run the pipeline on the carousel doc 104's
  post, expect `categoria:courses` + the real 6-course list in
  `conteudo_principal`/summary.

### 7. Wipe & re-ingest (final phase, after code + unit tests green)

- Delete all IG documents from the KB: `DELETE FROM documents WHERE ig_pk IS
  NOT NULL` (and cascade chunks/embeddings). Provide/run a one-liner.
- Clear the worker `state.json` (`downloads/ig/state.json`) so dedup doesn't
  skip re-upload.
- Re-run `ig_sync` → publish → worker, now with the new vision/summary prompts.
- Re-validate doc 89 (test E2E v3) and doc 104 (carousel) specifically.

## Out of scope

- Changing the video transcription itself (Whisper output stays as-is).
- Migrating existing non-IG documents.
- UI/CLI for re-ingest (a documented one-liner suffices).
