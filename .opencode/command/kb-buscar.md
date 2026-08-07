---
description: Busca na base de conhecimento (palavra-chave + semântica). Uso: /kb-buscar <query> [top_k=5]
---

Execute a ferramenta MCP **`minimax-video-factory_knowledge_search`** (server `minimax-video-factory`).

Entrada do usuário (tudo depois do comando):
$ARGUMENTS

Instruções obrigatórias:
1. Extraia:
   - `query` (obrigatória) — Termo ou pergunta para buscar na base de conhecimento.
   - `top_k`: Número máximo de resultados (default `5`).
2. Chame `knowledge_search` com esses parâmetros. Se a variante default do servidor MCP estiver indisponível, use a variante conectada (`minimax-video-factory-remote` ou `minimax-video-factory-uv`).
3. Reporte título, trechos e URL de origem de cada resultado, para o usuário conseguir voltar à fonte.
