---
description: Exporta os documentos selecionados como .md em output/kb-export/
argument-hint: <ids> [output_dir=output/kb-export/]
---

<!-- GERADO AUTOMATICAMENTE por scripts/generate_commands.py -->
<!-- Não edite à mão: rode `uv run python scripts/generate_commands.py`. -->

Execute a ferramenta MCP **`mcp__minimax-knowledge-base__kb_export`**.

Entrada do usuário (tudo depois do comando):
$ARGUMENTS

Instruções obrigatórias:
1. Extraia:
   - `ids` (obrigatória) — IDs confirmados na busca (kb-export-search).
   - `output_dir`: diretório de destino (default output/kb-export/) (default `output/kb-export/`).
2. Chame `mcp__minimax-knowledge-base__kb_export` com esses parâmetros. Esta tool só existe no servidor `minimax-knowledge-base`, que roda no host com acesso direto a Postgres e Ollama. Se ele não estiver conectado, diga isso ao usuário — não tente as variantes do container, que não alcançam o Postgres e só devolvem timeout.
3. Reporte o resultado da tool ao usuário.
