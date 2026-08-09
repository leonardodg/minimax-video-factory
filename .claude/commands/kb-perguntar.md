---
description: Responde uma pergunta usando RAG sobre a base de conhecimento
argument-hint: <query> [top_k=3]
---

<!-- GERADO AUTOMATICAMENTE por scripts/generate_commands.py -->
<!-- Não edite à mão: rode `uv run python scripts/generate_commands.py`. -->

Execute a ferramenta MCP **`mcp__minimax-knowledge-base__knowledge_ask`**.

Entrada do usuário (tudo depois do comando):
$ARGUMENTS

Instruções obrigatórias:
1. Extraia:
   - `query` (obrigatória) — Pergunta em linguagem natural sobre o que já foi salvo.
   - `top_k`: Quantos documentos usar como contexto (default `3`).
2. Chame `mcp__minimax-knowledge-base__knowledge_ask` com esses parâmetros. Esta tool só existe no servidor `minimax-knowledge-base`, que roda no host com acesso direto a Postgres e Ollama. Se ele não estiver conectado, diga isso ao usuário — não tente as variantes do container, que não alcançam o Postgres e só devolvem timeout.
3. A resposta vem APENAS da base. Se ela disser que não sabe, isso é o comportamento correto — não complete com conhecimento próprio.
4. Sempre mostre as fontes junto da resposta.
