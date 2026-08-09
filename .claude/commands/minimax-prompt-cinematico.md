---
description: Converte uma transcrição em um prompt estruturado do MiniMax H3
argument-hint: <transcription> [style=cinematic]
---

<!-- GERADO AUTOMATICAMENTE por scripts/generate_commands.py -->
<!-- Não edite à mão: rode `uv run python scripts/generate_commands.py`. -->

Execute a ferramenta MCP **`mcp__minimax-video-factory__create_cinematic_prompt`**.

Entrada do usuário (tudo depois do comando):
$ARGUMENTS

Instruções obrigatórias:
1. Extraia:
   - `transcription` (obrigatória) — texto completo da transcrição do vídeo.
   - `style`: cinematic, educational ou social (default `cinematic`).
2. Chame `mcp__minimax-video-factory__create_cinematic_prompt` com esses parâmetros. Se o servidor `minimax-video-factory` não estiver conectado, use `mcp__minimax-video-factory-remote__create_cinematic_prompt` ou `mcp__minimax-video-factory-uv__create_cinematic_prompt`.
3. Isto só monta o prompt — não gera vídeo. Para gerar, passe o resultado para `/minimax-gerar-video`.
