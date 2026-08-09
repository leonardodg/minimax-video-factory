---
description: Recalcula chunks e embeddings de todos os documentos da base
argument-hint: [embedding_model]
---

<!-- GERADO AUTOMATICAMENTE por scripts/generate_commands.py -->
<!-- Não edite à mão: rode `uv run python scripts/generate_commands.py`. -->

Execute a ferramenta MCP **`mcp__minimax-knowledge-base__knowledge_reindex`**.

Entrada do usuário (tudo depois do comando):
$ARGUMENTS

Instruções obrigatórias:
1. Extraia:
   - `embedding_model`: default: EMBEDDING_MODEL do .env (default `None`).
2. Chame `mcp__minimax-knowledge-base__knowledge_reindex` com esses parâmetros. Esta tool só existe no servidor `minimax-knowledge-base`, que roda no host com acesso direto a Postgres e Ollama. Se ele não estiver conectado, diga isso ao usuário — não tente as variantes do container, que não alcançam o Postgres e só devolvem timeout.
3. Rode depois de trocar o modelo de embedding: vetores antigos não são comparáveis com os novos, e a busca degrada em silêncio até reindexar.
4. Percorre a base inteira — pode demorar proporcionalmente ao tamanho dela.
