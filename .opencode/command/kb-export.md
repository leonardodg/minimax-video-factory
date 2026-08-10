---
description: Exporta os documentos selecionados como .md em output/kb-export/. Uso: /kb-export <ids> [output_dir=output/kb-export/]
---

Execute a ferramenta MCP **`minimax-video-factory_kb_export`** (server `minimax-video-factory`).

Entrada do usuário (tudo depois do comando):
$ARGUMENTS

Instruções obrigatórias:
1. Extraia:
   - `ids` (obrigatória) — IDs confirmados na busca (kb-export-search).
   - `output_dir`: diretório de destino (default output/kb-export/) (default `output/kb-export/`).
2. Chame `kb_export` com esses parâmetros. Se a variante default do servidor MCP estiver indisponível, use a variante conectada (`minimax-video-factory-remote` ou `minimax-video-factory-uv`).
3. Reporte o resultado da tool ao usuário.
