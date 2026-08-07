---
description: Recalcula chunks e embeddings de todos os documentos da base. Uso: /kb-reindex [embedding_model]
---

Execute a ferramenta MCP **`minimax-video-factory_knowledge_reindex`** (server `minimax-video-factory`).

Entrada do usuário (tudo depois do comando):
$ARGUMENTS

Instruções obrigatórias:
1. Extraia:
   - `embedding_model`: default: EMBEDDING_MODEL do .env (default `None`).
2. Chame `knowledge_reindex` com esses parâmetros. Se a variante default do servidor MCP estiver indisponível, use a variante conectada (`minimax-video-factory-remote` ou `minimax-video-factory-uv`).
3. Rode depois de trocar o modelo de embedding: vetores antigos não são comparáveis com os novos, e a busca degrada em silêncio até reindexar.
4. Percorre a base inteira — pode demorar proporcionalmente ao tamanho dela.
