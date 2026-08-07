# Roadmap — Personal Knowledge Base → Product

This document complements the MVP implementation plan
(`docs/superpowers/plans/2026-08-07-knowledge-base-mvp.md`) and the technical
spec (`docs/superpowers/specs/2026-08-07-knowledge-base-mvp-design.md`). That
plan covers **what will be built this week**; this document covers **why**, and
the path to the end goal.

## End goal

Today: a personal tool that turns saved videos (Instagram), podcasts/audio,
and saved sites into one searchable, "askable" knowledge base powered by
local AI.

In the future: the same service offered to other people — a product you can
charge for that helps people organize their own knowledge, today scattered
across browser bookmarks, saved videos, and podcasts that "disappear" after
being saved.

**Explicit decision (confirmed with the user):** the next few weeks are only
about validating the value personally (dogfooding). No multi-tenant, auth,
billing, or public site now — building that too early, before knowing whether
the tool even solves the problem for its own creator, is the biggest risk of
wasting the week.

## Why this order

The biggest risk is not technical (Postgres, pgvector, local LLM — all well
understood). The risk is validation: does having the base + search/ask
actually solve the stated pain ("I use Google to recall a command I already
saw", "I saved a site/video and never found it again")? Only real use answers
that. So the phases below prioritize getting the tool into use as soon as
possible and only then investing in each extension.

## Phases

### Phase 1 — Ingest + search MVP (this week)

**What:** ingest pipeline (video/audio/text → LLM → summary+tutorial) writing
to local Postgres (pgvector), with `knowledge_search`/`knowledge_ask` over
MCP. Detailed in
`docs/superpowers/plans/2026-08-07-knowledge-base-mvp.md`.

**Decisions that preserve optionality for later phases** (no extra
engineering cost now, but avoid rework later):

- Database access only through the ORM (SQLAlchemy) — moving from local
  Postgres to a managed Postgres (Phase 4/5) is changing a connection string,
  not rewriting queries.
- Abstract LLM client (`llm.py`) with `LLM_PROVIDER=ollama|openai-compatible`
  — moving from a local model to a paid API (needed if this ever becomes a
  product for people without GPUs) is configuration, not a rewrite.
- Generic `documents.type` (`video`/`audio`/`text`, extensible to `site`) —
  Phase 3 (Karakeep) needs no schema migration, just a new ingestor.
- Ingest layer (`knowledge.py`) separate from the MCP layer (`server.py`) —
  if the interface ever stops being "chat with OpenCode" and becomes a real
  HTTP API (Phase 5), the business logic doesn't move.

**Success criterion to move on:** MVP running, `knowledge_ingest_*` and
`knowledge_search`/`knowledge_ask` working end-to-end (validated by
`tests/08_knowledge.sh`).

### Phase 2 — Real use (following weeks, no fixed deadline)

**What:** no new code by default — use the tool daily (every saved Reel, every
listened podcast) and pay attention to:

- Is the generated summary/tutorial quality good enough, or does the prompt in
  `llm.py::SUMMARY_PROMPT_TEMPLATE` need tuning?
- Does `knowledge_ask` actually answer "what have I saved about X" usefully,
  or does the hybrid search (full-text + cosine) need reranking?
- What kinds of questions do you ask that the base doesn't cover yet (e.g.
  "which command did I see in that Docker video?")?

**Success criterion to move on:** at least a few weeks of real use, enough
document volume for search to make sense, and a clear list of what else gets
in the way daily — that list becomes the next phase.

### Phase 3 — Bring saved sites (Karakeep) into the same base

**What:** today saved sites live only in Obsidian (`Hoarder/`, synced from
Karakeep) — outside the structured base. Write an ingestor that reads Karakeep
bookmarks (API or the `.md` files in the `Hoarder/` folder) and creates
`documents` with `type="site"`, reusing `llm.generate_structured` (with an
adapted prompt — sites don't have a step-by-step "tutorial" the way a video
does) and the same `knowledge_search`/`knowledge_ask`.

**Why after Phase 2, not with Phase 1:** the schema was already designed to fit
this without migration; there's no technical reason to rush it — it only makes
sense after confirming Phase 1 (video/audio) actually solves the problem, so
as not to spend the MVP week on three integrations at once.

**Success criterion to move on:** unified search/ask covering videos + sites +
podcasts without the user needing to know where the information "lives".

### Phase 4 — Product preparation (without building the product yet)

**What:** with the three sources proven and in real use, revisit the Phase 1
decisions that today assume "only I use this":

- Per-user authentication/data isolation (multi-tenant schema or per-user
  database?).
- AI cost model: local Ollama doesn't exist for a user without a GPU — decide
  between (a) a self-hosted/open-source product (user runs their own Ollama)
  or (b) a hosted service paying per-user LLM/embedding calls.
- Postgres hosting (managed) and hosting of the future service.

This phase is decision and design, not implementation — the output is a new
design document (spec) for Phase 5, not code.

### Phase 5 — Product (SaaS)

Out of scope for any current plan. Only starts after Phase 4 answers the open
questions above. It becomes its own spec → plan → implementation set, treated
as a separate project (auth, billing, multi-tenant, front-end, deploy,
support).

## Non-goals (for now)

To make explicit what does **not** enter any phase until Phase 5: public site,
sign-ups for other users, billing, multi-tenant, managed hosting, customer
support.

## Open questions (don't block Phase 1, but will need answers)

- Self-hosted vs. hosted: which of the two business models makes more sense
  to you by the time Phase 4 arrives?
- Does Obsidian still have a role (readable copy) in the final product, or is
  it just a crutch of the personal phase?
- Is Karakeep (Phase 3) something other people already use, or would it be
  replaced by a native "save a site" in the final product?
