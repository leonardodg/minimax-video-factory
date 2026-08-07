# Roadmap — Base de Conhecimento Pessoal → Produto

Este documento complementa o plano de implementação do MVP
(`docs/superpowers/plans/2026-08-07-knowledge-base-mvp.md`) e a spec técnica
(`docs/superpowers/specs/2026-08-07-knowledge-base-mvp-design.md`). Aquele
plano cobre **o que será construído nesta semana**; este documento cobre
**por que**, e o caminho até o objetivo final.

## Objetivo final

Hoje: uma ferramenta pessoal que transforma vídeos salvos (Instagram),
podcasts/áudio e sites salvos numa base de conhecimento única, pesquisável e
"perguntável" via IA local.

No futuro: o mesmo serviço, oferecido para outras pessoas — um produto pelo
qual o usuário possa cobrar e que ajude outras pessoas a organizar o próprio
conhecimento, hoje espalhado entre favoritos do navegador, vídeos salvos e
podcasts que "somem" depois de salvos.

**Decisão explícita (confirmada com o usuário):** as próximas semanas são só
sobre validar o valor pessoalmente (dogfooding). Nada de multi-tenant, auth,
billing ou site público agora — construir isso cedo demais, antes de saber se
a ferramenta resolve o problema nem para o próprio criador, é o maior risco
de desperdiçar a semana.

## Por que essa ordem

O risco maior não é técnico (Postgres, pgvector, LLM local — tudo isso é bem
conhecido). O risco é validação: será que ter a base + busca/pergunta
realmente resolve a dor citada ("uso o Google pra lembrar um comando que já
vi", "salvei um site/vídeo e nunca mais achei")? Só uso real responde isso.
Por isso as fases abaixo priorizam colocar a ferramenta em uso o quanto antes
e só then investir em cada extensão.

## Fases

### Fase 1 — MVP de ingestão + busca (esta semana)

**O quê:** pipeline de ingestão (vídeo/áudio/texto → LLM → resumo+tutorial)
gravando em Postgres local (pgvector), com `knowledge_search`/`knowledge_ask`
via MCP. Detalhado em `docs/superpowers/plans/2026-08-07-knowledge-base-mvp.md`.

**Decisões que preservam opcionalidade para as fases seguintes** (sem custo
extra de engenharia agora, mas evitam retrabalho depois):
- Acesso ao banco só via ORM (SQLAlchemy) — trocar de Postgres local para um
  Postgres gerenciado (Fase 4/5) é mudar uma connection string, não reescrever
  queries.
- Cliente LLM abstrato (`llm.py`) com `LLM_PROVIDER=ollama|openai-compatible`
  — trocar de modelo local para uma API paga (necessário se um dia virar
  produto para pessoas sem GPU) é configuração, não reescrita.
- `documents.type` genérico (`video`/`audio`/`text`, extensível a `site`) —
  a Fase 3 (Karakeep) não exige migração de schema, só um novo ingestor.
- Camada de ingestão (`knowledge.py`) separada da camada MCP (`server.py`) —
  se um dia a interface deixar de ser "chat com OpenCode" e virar uma API
  HTTP de verdade (Fase 5), a lógica de negócio não muda de lugar.

**Critério de sucesso para avançar:** MVP rodando, `knowledge_ingest_*` e
`knowledge_search`/`knowledge_ask` funcionando de ponta a ponta (validado por
`tests/08_knowledge.sh`).

### Fase 2 — Uso real (semanas seguintes, sem prazo fixo)

**O quê:** nada de código novo por padrão — usar a ferramenta no dia a dia
(cada Reel salvo, cada podcast ouvido) e prestar atenção em:
- A qualidade do resumo/tutorial gerado é boa o suficiente, ou o prompt em
  `llm.py::SUMMARY_PROMPT_TEMPLATE` precisa de ajuste?
- `knowledge_ask` realmente responde "o que eu já salvei sobre X" de forma
  útil, ou a busca híbrida (full-text + cosseno) precisa de reranking?
- Que tipo de pergunta você faz que a base ainda não cobre (ex.: "que
  comando eu vi naquele vídeo sobre Docker?")?

**Critério de sucesso para avançar:** pelo menos algumas semanas de uso real,
volume suficiente de documentos para a busca fazer sentido, e uma lista clara
do que mais atrapalha no dia a dia — essa lista vira a próxima fase.

### Fase 3 — Trazer os sites (Karakeep) para a mesma base

**O quê:** hoje os sites salvos vivem só no Obsidian (`Hoarder/`, sincronizado
do Karakeep) — fora da base estruturada. Escrever um ingestor que lê os
bookmarks do Karakeep (API ou os próprios `.md` da pasta `Hoarder/`) e cria
`documents` com `type="site"`, reaproveitando `llm.generate_structured` (com
um prompt adaptado — sites não têm "tutorial passo a passo" da mesma forma
que um vídeo) e o mesmo `knowledge_search`/`knowledge_ask`.

**Por que depois da Fase 2, não junto com a Fase 1:** o schema já foi
desenhado para caber isso sem migração; não há motivo técnico para
apressar — só faz sentido depois de confirmar que a Fase 1 (vídeo/áudio)
realmente resolve o problema, pra não gastar a semana de MVP em três
integrações ao mesmo tempo.

**Critério de sucesso para avançar:** busca/pergunta unificada cobrindo
vídeos + sites + podcasts sem o usuário precisar saber onde a informação
"mora".

### Fase 4 — Preparação para produto (sem construir o produto ainda)

**O quê:** com as três fontes provadas e em uso real, revisar as decisões da
Fase 1 que hoje assumem "só eu uso isso":
- Autenticação/isolamento de dados por usuário (schema multi-tenant ou
  banco por usuário?).
- Modelo de custo de IA: Ollama local não existe para um usuário sem GPU —
  decidir entre (a) produto self-hosted/open-source (usuário roda o próprio
  Ollama) ou (b) serviço hospedado pagando por chamadas de LLM/embedding por
  usuário.
- Hospedagem do Postgres (gerenciado) e do futuro serviço.

Esta fase é decisão e desenho, não implementação — o resultado é um novo
documento de design (spec) para a Fase 5, não código.

### Fase 5 — Produto (SaaS)

Fora do escopo de qualquer plano atual. Só começa depois da Fase 4 responder
as perguntas em aberto acima. Vira seu próprio conjunto spec → plano →
implementação, tratado como projeto separado (auth, billing, multi-tenant,
front-end, deploy, suporte).

## Não-objetivos (por enquanto)

Para deixar explícito o que **não** entra em nenhuma fase até a Fase 5:
site público, cadastro de outros usuários, cobrança, multi-tenant, hospedagem
gerenciada, suporte a clientes.

## Perguntas em aberto (não bloqueiam a Fase 1, mas vão precisar de resposta)

- Self-hosted vs. hospedado: qual dos dois modelos de negócio faz mais
  sentido pra você quando chegar na Fase 4?
- O Obsidian continua tendo algum papel (cópia legível) no produto final, ou
  é só uma muleta da fase pessoal?
- Karakeep (Fase 3) é algo que outras pessoas já usam, ou seria substituído
  por um "save de site" próprio no produto final?
