---
description: Responde uma pergunta usando RAG sobre a base de conhecimento. Uso: /kb-perguntar <query> [top_k=3]
---

Execute a ferramenta MCP **`minimax-video-factory_knowledge_ask`** (server `minimax-video-factory`).

Entrada do usuário (tudo depois do comando):
$ARGUMENTS

Instruções obrigatórias:
1. Extraia:
   - `query` (obrigatória) — Pergunta em linguagem natural sobre o que já foi salvo.
   - `top_k`: Quantos documentos usar como contexto (default `3`).
2. Chame `knowledge_ask` com esses parâmetros. Se a variante default do servidor MCP estiver indisponível, use a variante conectada (`minimax-video-factory-remote` ou `minimax-video-factory-uv`).
3. A resposta vem APENAS da base. Se ela disser que não sabe, isso é o comportamento correto — não complete com conhecimento próprio.
4. Sempre mostre as fontes junto da resposta.
