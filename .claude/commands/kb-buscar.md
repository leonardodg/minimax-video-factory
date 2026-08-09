---
description: Busca na base de conhecimento (palavra-chave + semântica)
argument-hint: <query> [top_k=5]
---

<!-- GERADO AUTOMATICAMENTE por scripts/generate_commands.py -->
<!-- Não edite à mão: rode `uv run python scripts/generate_commands.py`. -->

Execute a ferramenta MCP **`mcp__minimax-knowledge-base__knowledge_search`**.

Entrada do usuário (tudo depois do comando):
$ARGUMENTS

Instruções obrigatórias:
1. Extraia:
   - `query` (obrigatória) — Termo ou pergunta para buscar na base de conhecimento.
   - `top_k`: Número máximo de resultados (default `5`).
2. Chame `mcp__minimax-knowledge-base__knowledge_search` com esses parâmetros. Esta tool só existe no servidor `minimax-knowledge-base`, que roda no host com acesso direto a Postgres e Ollama. Se ele não estiver conectado, diga isso ao usuário — não tente as variantes do container, que não alcançam o Postgres e só devolvem timeout.
3. Reporte título, trechos e URL de origem de cada resultado, para o usuário conseguir voltar à fonte.
