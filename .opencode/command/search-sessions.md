---
description: Busca sessões passadas salvas no Obsidian (vault "OpenCode Brain"). Uso: /search-sessions <termo ou pergunta>
---

Invoque a skill **search-sessions** (`~/.claude/skills/search-sessions/SKILL.md`) e siga-a exatamente para buscar sessões passadas salvas no vault do Obsidian.

Entrada do usuário (tudo depois do comando):
$ARGUMENTS

Regras obrigatórias:
1. Runtime = opencode → vault alvo `$HOME/obsidian-knowledge/OpenCode Brain/` (sessões em `Chats/`).
2. Use o termo/pergunta do usuário como escopo da busca. Se vazio, peça esclarecimento.
3. Busque os arquivos `.md` diretamente via filesystem (bash/read) — não dependa do MCP obsidian.
4. Retorne as sessões mais relevantes com caminho completo e um resumo do que cada uma contém.
