---
description: Importa arquivos markdown (ex.: Obsidian) para a base de conhecimento
argument-hint: <path> [recursive=False] [doc_type=document]
---

<!-- GERADO AUTOMATICAMENTE por scripts/generate_commands.py -->
<!-- Não edite à mão: rode `uv run python scripts/generate_commands.py`. -->

Execute a ferramenta MCP **`mcp__minimax-knowledge-base__knowledge_ingest_markdown`**.

Entrada do usuário (tudo depois do comando):
$ARGUMENTS

Instruções obrigatórias:
1. Extraia:
   - `path` (obrigatória) — arquivo .md ou diretório; diretórios com ponto (.obsidian, .trash) são ignorados.
   - `recursive`: cuidado ao apontar para um vault inteiro — pode ser milhares de arquivos (default `False`).
   - `doc_type`: Tipo do documento na base (ex.: document, tutorial) (default `document`).
2. Chame `mcp__minimax-knowledge-base__knowledge_ingest_markdown` com esses parâmetros. Esta tool só existe no servidor `minimax-knowledge-base`, que roda no host com acesso direto a Postgres e Ollama. Se ele não estiver conectado, diga isso ao usuário — não tente as variantes do container, que não alcançam o Postgres e só devolvem timeout.
3. Quando a nota já tem uma seção `## Summary`, esse texto é reaproveitado e o LLM é pulado — é o que torna a importação em massa viável (minutos em vez de horas).
4. Reporte quantos arquivos foram importados de quantos encontrados.
