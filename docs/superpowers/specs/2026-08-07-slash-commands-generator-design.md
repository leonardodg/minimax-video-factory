# Gerador de slash commands + documentação — Design

Status: aprovado, pronto para o plano de implementação.

## Contexto e problema

O servidor MCP expõe **18 tools**, mas só **3** têm slash command no OpenCode
(`/minimax-download`, `/minimax-transcrever`, `/minimax-gerar-video`). As outras
15 só são alcançáveis pedindo em linguagem natural e torcendo para o agente
escolher a tool certa com os parâmetros certos.

O custo disso é concreto:

- **Descoberta.** Quem abre o projeto não tem como saber que existe
  `knowledge_ingest_markdown` ou `wait_for_video`. Um `/` no OpenCode lista o
  que existe; ler `server.py` não é uma interface.
- **Parâmetros tácitos.** `generate_video` tem default `width=1344, height=768`
  — que **estoura a VRAM de 12 GB**. O comando manual sabe disso e manda usar
  1024x576; a assinatura da tool não. Quem chama a tool direto bate no
  `torch.OutOfMemoryError`.
- **Deriva.** As 7 tools de knowledge base nasceram depois dos 3 comandos. Nada
  no projeto força um comando novo quando uma tool nova aparece, então a
  distância entre o que o servidor faz e o que está documentado só cresce.

**Objetivo:** um comando por tool, gerado do código, com a documentação
correspondente publicada no site — e um teste que quebra quando alguém adiciona
a 19ª tool sem documentá-la.

## Escopo

**Dentro:** um gerador que lê `server.py`, um arquivo de conhecimento curado por
tool, os 18 arquivos `.md` de comando, uma página `docs/COMMANDS.md`, e testes.

**Fora:** alterar qualquer tool, alterar `server.py`, mexer nos comandos
`/compress` e `/search-sessions` (que não mapeiam para tools MCP), suporte a
outros clientes além do OpenCode.

## Inventário

18 tools, agrupadas pelo prefixo do comando:

### `minimax-*` — pipeline de vídeo (11)

| Comando | Tool | Estado |
|---|---|---|
| `/minimax-health` | `health_check` | novo |
| `/minimax-submit-scene` | `submit_scene` | novo |
| `/minimax-status` | `get_status` | novo |
| `/minimax-wait` | `wait_for_video` | novo |
| `/minimax-outputs` | `list_outputs` | novo |
| `/minimax-compose` | `compose_final` | novo |
| `/minimax-download` | `download_video` | **existe** |
| `/minimax-transcrever` | `transcribe_video` | **existe** |
| `/minimax-prompt-cinematico` | `create_cinematic_prompt` | novo |
| `/minimax-gerar-video` | `generate_video` | **existe** |
| `/minimax-studio` | `studio_pipeline` | novo |

### `kb-*` — base de conhecimento (7)

| Comando | Tool | Estado |
|---|---|---|
| `/kb-ingest-texto` | `knowledge_ingest_text` | novo |
| `/kb-ingest-markdown` | `knowledge_ingest_markdown` | novo |
| `/kb-ingest-video` | `knowledge_ingest_video` | novo |
| `/kb-ingest-audio` | `knowledge_ingest_audio` | novo |
| `/kb-buscar` | `knowledge_search` | novo |
| `/kb-perguntar` | `knowledge_ask` | novo |
| `/kb-reindex` | `knowledge_reindex` | novo |

Os verbos são em português, seguindo os 3 comandos existentes
(`transcrever`, `gerar-video`) e não o nome cru da tool. O prefixo separa os
dois produtos que convivem no repositório: geração de vídeo e curadoria de
conhecimento.

## Decisões técnicas

### 1. AST, não import

O gerador lê `src/minimax_mcp/server.py` com `ast.parse`, não importando o
módulo. Importar `server.py` puxa `torch`, `faster_whisper` e uma conexão
Postgres — o gerador ficaria dependente de GPU, modelos baixados e banco de pé
para produzir texto. Com AST ele roda offline, em qualquer máquina, em
milissegundos, e num CI sem nada instalado.

O que o AST extrai por tool: nome da função, docstring, e para cada parâmetro o
nome, a anotação de tipo, o default e a `description` do `Field(...)`.

### 2. Overrides curados, versionados junto

O AST captura o que é verdade mecânica. Não captura:

- que **subir de 1024x576 arrisca OOM** com 12 GB de VRAM, e que 512x320 é o
  mais rápido (~5 min) quando você só quer ver se o pipeline anda
- que "database locked" no `/minimax-download` significa fechar o navegador
- que um prompt em PT deve ser traduzido para uma descrição visual em EN antes
  de chamar `generate_video`
- que `/kb-ingest-markdown` pula o LLM quando encontra `## Summary`
- que `/kb-reindex` invalida embeddings antigos e deve rodar depois de trocar
  `EMBEDDING_MODEL`
- que `generate_video` pode estourar o timeout do cliente MCP, e o contorno é
  `submit_scene` + `wait_for_video`

Esse conhecimento vive em `scripts/command_docs/overrides.py`, indexado pelo
nome da tool. Cada entrada é opcional e parcial: uma tool sem override ainda
gera um comando válido, só mais seco.

Um override contribui em **três posições distintas**, e as três são necessárias
para reproduzir os comandos existentes:

| Campo | Onde entra | Exemplo |
|---|---|---|
| `resumo` | frontmatter `description:` | "Gera um vídeo no MiniMax H3 via MCP" |
| `param_notas[<param>]` | anexado à linha daquele parâmetro na extração | "NUNCA acima de 1024x576 — OOM" |
| `passos` | passos numerados extras, **ordenados**, depois da chamada da tool | "Se houver OOM, reduza para 512x320 e tente de novo" |

`passos` ser uma lista ordenada, e não um bloco de notas solto, é o que permite
absorver `/minimax-gerar-video` sem perder nada: aquele comando tem quatro
instruções sequenciais depois da chamada (traduzir, aguardar, retry de OOM,
contorno de timeout). Um campo de notas único achataria as quatro em uma.

**Os 3 comandos existentes são absorvidos como overrides.** O texto que já foi
validado em uso vira dado do gerador, e passa a existir um só formato e uma só
fonte de verdade. A revisão precisa confirmar, comando a comando, que nenhuma
dica se perdeu na migração — é o único risco desta escolha.

### 3. Um comando por tool, sem exceção

Sem lista de exclusão. Tools triviais como `list_outputs` e `health_check`
também ganham comando: `/minimax-health` antes de renderizar economiza
descobrir que faltava um modelo depois de 20 minutos de espera.

### 4. Cobertura verificada por teste, não por disciplina

Um teste compara o conjunto de tools no AST com o conjunto de arquivos em
`.opencode/command/`. Adicionar uma tool sem gerar seu comando quebra a suíte.
É isso que impede a deriva de voltar — o gerador sozinho não impede, porque
ninguém lembra de rodá-lo.

O mesmo teste ignora comandos que não mapeiam para tools (`/compress`,
`/search-sessions`), via uma allowlist explícita.

### 5. Idempotência

Rodar o gerador duas vezes produz bytes idênticos. Isso é o que permite um teste
de "o diretório está atualizado?" e evita ruído de diff em cada execução.

## Arquitetura

```
scripts/
├── generate_commands.py          # CLI: orquestra parse → render → escrita
└── command_docs/
    ├── __init__.py
    ├── parser.py                 # AST → ToolSpec
    ├── overrides.py              # conhecimento curado por tool
    ├── renderer.py               # ToolSpec + override → markdown
    └── catalog.py                # nomes dos comandos + agrupamento
```

Fluxo:

```
src/minimax_mcp/server.py
        │  ast.parse
        ▼
   list[ToolSpec]  ──┐
                     ├──►  renderer  ──►  .opencode/command/*.md   (18)
   overrides.py    ──┘                └►  docs/COMMANDS.md          (1)
   catalog.py      ──┘
```

`ToolSpec` é o contrato entre as camadas:

```python
@dataclass(frozen=True)
class ParamSpec:
    name: str
    type_hint: str          # "str", "int | None", "list[str]"
    default: str | None     # repr do default, ou None se obrigatório
    description: str        # do Field(description=...), ou ""
    required: bool

@dataclass(frozen=True)
class ToolSpec:
    tool_name: str          # "knowledge_ingest_markdown"
    docstring: str
    params: list[ParamSpec]
    is_async: bool
```

## Formato do comando gerado

Segue o template dos 3 existentes — frontmatter com `description:` contendo a
linha de uso, `$ARGUMENTS`, e instruções numeradas:

```markdown
---
description: <resumo>. Uso: /<comando> <obrigatórios> [opcional=default]
---

<Frase de ação> usando a ferramenta MCP **`minimax-video-factory_<tool>`**
(server `minimax-video-factory`).

Entrada do usuário (tudo depois do comando):
$ARGUMENTS

Instruções obrigatórias:
1. Extraia:
   - `<param>` (obrigatória) — <descrição do Field><, + param_notas se houver>
   - `<param>`: <descrição> (default `<valor>`)<, + param_notas se houver>.
2. Chame `<tool>` com esses parâmetros. Se a variante default do servidor MCP
   estiver indisponível, use a variante conectada (`-remote` ou `-uv`).
3. <passos[0] do override>
4. <passos[1] do override>
...
N. Reporte <o que a tool retorna>.
```

Obrigatórios vêm antes de opcionais na lista de extração. O passo 2 (variantes
do servidor) é parte fixa do template, não override — vem dos comandos
existentes e vale para todas as tools. O passo final de reporte também é fixo,
derivado da docstring, e sempre fecha a lista.

## `docs/COMMANDS.md`

Página única, gerada, com:

1. Tabela geral: comando → tool → uma linha do que faz
2. Uma seção por comando, agrupada por prefixo (Vídeo / Base de conhecimento),
   com a tabela de parâmetros e as notas operacionais

Entra no `mkdocs.yml` sob **User Guides**, ao lado de `MCP_TOOLS.md`. As duas
páginas são complementares e não redundantes: `MCP_TOOLS.md` documenta a
interface de programação das tools; `COMMANDS.md` documenta a interface de uso
humana.

Cabeçalho de arquivo gerado, como em `MCP_TOOLS.md`:

```markdown
<!-- GERADO AUTOMATICAMENTE por scripts/generate_commands.py -->
<!-- Não edite à mão: rode `uv run python scripts/generate_commands.py`. -->
```

## Testes

Novo arquivo `tests/unit_commands.py`, marcador `unit`, sem I/O de rede nem
serviços. Registrado em `tests/test_scripts.py` como os demais.

| Nível | O que verifica |
|---|---|
| Parser | Extrai nome/tipo/default/description de `Field(...)`; trata param sem `Field`; trata `str \| None`; reconhece `async def` |
| Catálogo | Toda tool tem nome de comando; nenhum nome duplicado; prefixo correto por grupo |
| Renderer | Frontmatter tem `description:` e "Uso:"; corpo tem `$ARGUMENTS`; obrigatórios aparecem antes de opcionais; notas do override aparecem |
| **Cobertura** | **Toda tool no AST tem um `.md`; todo `.md` (fora a allowlist) mapeia para uma tool** |
| Idempotência | Gerar duas vezes produz bytes idênticos |

## Erros e casos de borda

- **Tool sem docstring** → usa a `description` da primeira `Field` como resumo;
  se não houver, o gerador **falha com erro claro** apontando a tool. Um comando
  sem descrição é pior que nenhum comando.
- **Tool nova sem entrada no catálogo** → falha, listando a tool. Nomear um
  comando é decisão humana; adivinhar produz nomes ruins.
- **Override para uma tool que não existe** (renomeada, removida) → falha,
  apontando a chave órfã. Silenciar isso deixa conhecimento curado apodrecendo.
- **`server.py` com erro de sintaxe** → `ast.parse` levanta; o gerador propaga
  com o número da linha.
- **Parâmetro sem `Field`** (ex.: `prompt_id: str` em `get_status`) → gerado com
  a descrição vazia e uma nota no relatório final do gerador, para o autor saber
  onde falta contexto.

## Impacto no que já existe

| Arquivo | Mudança |
|---|---|
| `.opencode/command/minimax-{download,transcrever,gerar-video}.md` | Passam a ser gerados; conteúdo preservado via overrides |
| `.opencode/command/{compress,search-sessions}.md` | **Intocados** (allowlist) |
| `src/minimax_mcp/server.py` | **Intocado** |
| `mkdocs.yml` | +1 entrada de nav |
| `docs/COMMANDS.md` | Novo, gerado |
| `AGENTS.md` / `README.md` | Ganham a instrução de rodar o gerador ao adicionar tools |

## Anexo: correção do default de resolução (feito)

O levantamento para esta spec revelou um bug real, e o usuário autorizou
corrigi-lo junto: o default `width=1344, height=768` **estoura a VRAM de 12 GB**
(`torch.OutOfMemoryError`), enquanto o comando manual `/minimax-gerar-video` já
mandava usar 1024x576 desde o primeiro dia. Quem chamava a tool sem argumentos
batia na falha; quem usava o slash command não.

Documentar o conflito no override seria tratar o sintoma. O default foi mudado
para **1024x576** em todas as camadas:

| Camada | O que tinha |
|---|---|
| `server.py` | `submit_scene`, `generate_video`, `studio_pipeline` |
| `core.py` | `submit_scene_core` |
| `orchestrator.py` | `generate_video`, `run_full_pipeline`, `run_studio_pipeline` |
| `workflows/minimax_h3_t2v_api.json` | nó 5 (carregado direto na UI do ComfyUI, onde nada sobrescreve) |
| `README.md`, `docs/INSTALLATION.md`, `docs/ARCHITECTURE.md` | exemplos |

As descrições dos `Field(...)` passaram a citar o teto de VRAM, então quem lê a
assinatura da tool vê o limite sem precisar do slash command.

`tests/unit_defaults.py` trava o valor. Vale registrar por que ele tem um teste
de *cobertura* além dos de valor: a primeira passada da correção arrumou
`server.py`, `core.py` e o workflow, mas **passou batido no `orchestrator.py`** —
a tool ficou segura enquanto a camada debaixo dela continuava com o default que
quebra. O teste de cobertura, que falha diante de qualquer função com default de
`width`/`height` não listada, é o que pegou isso. Funções que recebem
`width`/`height` como obrigatórios (`inject_scene`) ficam de fora: sem default,
não há o que estar errado.
