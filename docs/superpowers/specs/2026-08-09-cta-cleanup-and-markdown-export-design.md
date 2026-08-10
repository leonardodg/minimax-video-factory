# Design — CTA cleanup no pipeline IG + tool de export markdown

Date: 2026-08-09
Status: Approved by user
Scope: MiniMax video factory — Instagram saved-posts → Knowledge Base

## Problem

Os 12 documentos de Instagram já ingeridos foram validados e o pipeline está
aprovado para os 2145 posts restantes. Mas o conteúdo bruto ainda carrega
frases de **CTA** (call-to-action) — "segue pra não perder", "salva esse
vídeo", "compartilha com seus amigos", "link na bio", "comenta X que eu te
mando o passo a passo". Elas poluem:

- `summary` / `tutorial` / `tags` (gerados pelo LLM a partir da transcrição)
- `transcription_text` (salvo cru, usado nos chunks/embeddings e em buscas)

Além disso, hoje o conteúdo vive **apenas no Postgres** (`IG_DELETE_AFTER_INGEST
=true` apaga a mídia; `raw_file_path` é `None` nos 12 docs). Não há como ler
os documentos fora do banco. A mídia original não volta, mas o **texto** pode
ser exportado para `.md` legível.

## Goals

1. Remover frases de CTA dos campos gerados (summary/tutorial/objetivos/tags)
   — via instrução no `SUMMARY_PROMPT_TEMPLATE`.
2. Remover frases de CTA da `transcription_text` — via `strip_cta()` (regex),
   porque o LLM não regenera a transcrição; ela é salva crua.
3. Aplicar aos posts novos (2145) no fluxo do `ig_worker` e **reaplicar aos 12
   já ingeridos** via backfill, preservando snapshot do estado antigo em `.md`
   no disco para comparação/rollback.
4. Exportar documentos da base como `.md` legíveis em `output/kb-export/`,
   através de duas tools MCP novas: `kb-export-search` e `kb-export`.
5. Registrar as duas tools seguindo a checklist de 9 lugares do AGENTS.md.

Não faz parte deste escopo (projetos separados, a discutir depois):
- Schema expandido (`recipes`, `characters`, `content_ideas`, `scripts`,
  `prompts`, `videos`, `publishing_queue`, `published_posts`, `analytics`,
  `experiments`) e a relação `video → recipe → content_angle →
  prompt_version → video_generation_version → instagram_post → metrics`.
- Prompt de geração de vídeo como dado real no banco.

## Design

### 1. CTA cleanup no prompt do LLM

Em `src/minimax_mcp/llm.py`, no `SUMMARY_PROMPT_TEMPLATE`, acrescentar
instrução para o LLM **não incluir frases de call-to-action** no resumo,
tutorial, objetivos e tags. A transcrição continua sendo material de apoio;
pedidos para seguir/curtir/compartilhar/salvar/comentar são ignorados.

O LLM é o mecanismo principal para os campos gerados porque entende contexto
(CTA aparece com variações infinitas).

### 2. `strip_cta()` — limpeza da transcrição

Novo helper (em `src/minimax_mcp/ig_worker.py` ou módulo compartilhado), puro
e unit-testável: `strip_cta(text: str) -> str`.

Remove sentenças de CTA da transcrição antes do `ingest_text`. Padrões a
cobrir (regex, com variações típicas em PT):

- "segue pra não perder / siga para mais"
- "salva esse vídeo / salve para fazer depois"
- "compartilha com seus amigos"
- "link na bio"
- "comenta X que eu te mando o passo a passo" (e variações de "comenta ...")
- "ativa o sininho"
- "curte e compartilha"
- menções a "perfil certo", "já me segue aqui"

Regras:
- Remover apenas a **sentença** que contém o CTA (delimitada por pontuação
  `.`, `!`, `?`), preservando o conteúdo ao redor.
- Não remover conteúdo útil que coincidentemente cite essas palavras em
  contexto não-CTA (ex.: "compartilhe esse código com seu time" em tutorial
  técnico) — a sentença completa é avaliada, não só a palavra.
- Não lançar exceção; texto sem CTA retorna intacto.

Fluxo: `process_message()` → `strip_cta(text)` antes de `ingest()`.

### 3. Backfill dos 12 existentes

`scripts/backfill_cta.py` (script manual, não tool MCP):

1. Para cada doc com `ig_pk` (118–129):
   - Exportar snapshot atual como `.md` em `output/kb-backup/<id>-<ig_pk>.md`
     (formato do `vault.write_markdown_copy`), **antes** de qualquer mudança.
   - Aplicar `strip_cta()` na `transcription_text`.
   - Regenerar `summary`, `tutorial`, `objectives`, `tags` via
     `llm.generate_structured()` com o prompt novo (custo ~50 s/doc, ~10 min
     no total para os 12).
   - Gravar UPDATE no documento existente, preservando `id`, `ig_pk`,
     `source_url`, `platform`, `created_at`.
2. Imprimir resumo antes/depois (id, título, tamanho da transcrição, resumo
   truncado) para revisão.
3. **Rollback manual:** se o resultado piorar, restaurar a partir do snapshot
   em `output/kb-backup/` (docs instruem como — ou um `--restore <id>`).

Os campos gerados **são** regenerados (decisão do usuário), não apenas a
transcrição limpa. Snapshot no disco permite comparar e desfazer.

### 4. Tools de export markdown

Duas tools MCP, seguindo o padrão thin-wrapper do `server.py` e a checklist
de 9 lugares (catalog + overrides + generators + registry + README).

**`kb-export-search`** — lista documentos sem gravar nada.

- Params: `query: str | None` (busca em título/resumo/conteúdo), `ids:
  list[int] | None` (seleção direta), `limit: int = 20`.
- Lógica: se `ids` → filtra por eles; senão, se `query` → busca híbrida
  (reusa o mesmo mecanismo de `knowledge_search`); senão → últimos N docs.
- Retorno: lista no formato da tabela validada pelo usuário (id, tipo,
  título, tags, ig_pk, tamanhos) + total.

**`kb-export`** — escreve os `.md` dos documentos selecionados.

- Params: `ids: list[int]` (obrigatório — os confirmados na busca),
  `output_dir: str = "output/kb-export/"`.
- Lógica: para cada id, monta o dict do doc e chama
  `vault.write_markdown_copy(doc_dict, output_dir)`.
- Formato do `.md` (estendendo o do `vault.py`):
  frontmatter (`source_url`, `platform`, `type`, `ig_pk`, `created_at`,
  `llm_model`) + `# título` + tags + `## Resumo` + `## Tutorial` +
  `## Objetivos` + `## Transcrição completa` + seção **`## Prompt de geração
  de vídeo`** (placeholder vazio por ora, reservada para o schema futuro).
- Retorno: lista de arquivos escritos + caminho do diretório.

Arquivos em `output/kb-export/` (gitignored, como o resto de `output/`).

### 5. Integração MCP (checklist de 9 lugares)

| # | Lugar | Detalhe |
|---|---|---|
| 1 | Domínio em `knowledge.py` | `export_search()`, `export_documents()` — puros, unit-testáveis |
| 2 | `server.py` `@mcp.tool()` | `kb_export_search`, `kb_export` com `Field(description=…)` |
| 3 | `scripts/command_docs/catalog.py` | `kb-export-search`, `kb-export` |
| 4 | `scripts/command_docs/overrides.py` | notas operacionais se preciso |
| 5 | `scripts/generate_commands.py` | regenerar `.md` |
| 6 | `scripts/generate_mcp_docs.py` | atualizar `docs/MCP_TOOLS.md` |
| 7 | `tests/unit_registry.py` | adicionar os 2 nomes |
| 8 | `tests/unit_commands.py` | bump do total esperado (24 → 26) |
| 9 | README tool table | 2 linhas |

Slash commands: `kb-export-search` e `kb-export` (rótulo PT, padrão dos
`kb-*`).

## Data flow

```
worker (novo post):
  download → transcribe/describe → strip_cta(text) → ingest_text (prompt novo)
                                                          │
                                          summary/tutorial/objetivos/tags sem CTA
                                          transcription_text sem CTA

backfill (12 existentes):
  snapshot .md → strip_cta(transcription) → regenerar campos (prompt novo) → UPDATE

kb-export-search:  query/ids → tabela para confirmação (não grava)
kb-export:         ids confirmados → vault.write_markdown_copy() → output/kb-export/
```

## Error handling

- `strip_cta()`: nunca lança; entrada sem CTA retorna intacta.
- Backfill: se um doc falhar na regeneração, registra e segue; snapshot já
  existe em disco para esse doc. `--restore <id>` restaura do snapshot.
- `kb-export`: doc inexistente → item com `{"id": X, "ok": false,
  "error": "not found"}`; nunca interrompe os demais. Diretório de saída é
  criado se não existir.
- `kb-export-search`: retorna lista vazia + mensagem, não erro, quando nada
  casa.

## Testing

- `tests/unit_*` (marker `unit`): casos para `strip_cta()` (CTA removido,
  conteúdo preservado, sentença parcial, falsos positivos, texto limpo
  intacto) e para `export_search`/`export_documents` (filtro por ids, busca
  por query, escrita no disco, doc inexistente).
- `tests/unit_registry.py` e `tests/unit_commands.py`: incluem as 2 tools;
  a suíte fica vermelha se algum dos 9 lugares for esquecido.
- Backfill: teste idempotente em um doc de teste (cria, faz snapshot,
  regenera, compara, restaura/limpa).
