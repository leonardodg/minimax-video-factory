---
description: Compacta e salva a sessão atual no Obsidian (vault "OpenCode Brain"). Uso: /compress
---

Invoque a skill **compress** (`~/.claude/skills/compress/SKILL.md`) e siga-a exatamente para salvar esta sessão no vault do Obsidian.

Entrada do usuário (se houver):
$ARGUMENTS

Regras obrigatórias:
1. Runtime = opencode → vault alvo `$HOME/obsidian-knowledge/OpenCode Brain/`, frontmatter `type: opencode-session`, tags `opencode`.
2. Nome do projeto = última pasta do cwd (aqui: `minimax-video-factory`).
3. Salve em `<vault>/Chats/<projeto>/<YYYY-MM-DD>-<titulo-curto>.md` usando o Write tool via bash (o MCP filesystem não cobre o vault; o MCP obsidian pode estar fora).
4. Estrutura da nota: Summary, Key Decisions, Changes Made, Problems Solved, Open Items, Session Log (só o essencial, sem outputs verbosos).
5. Confirme o path completo salvo e liste os open items.
