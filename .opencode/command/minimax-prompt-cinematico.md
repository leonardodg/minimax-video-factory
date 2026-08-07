---
description: Converte uma transcrição em um prompt estruturado do MiniMax H3. Uso: /minimax-prompt-cinematico <transcription> [style=cinematic]
---

Execute a ferramenta MCP **`minimax-video-factory_create_cinematic_prompt`** (server `minimax-video-factory`).

Entrada do usuário (tudo depois do comando):
$ARGUMENTS

Instruções obrigatórias:
1. Extraia:
   - `transcription` (obrigatória) — texto completo da transcrição do vídeo.
   - `style`: cinematic, educational ou social (default `cinematic`).
2. Chame `create_cinematic_prompt` com esses parâmetros. Se a variante default do servidor MCP estiver indisponível, use a variante conectada (`minimax-video-factory-remote` ou `minimax-video-factory-uv`).
3. Isto só monta o prompt — não gera vídeo. Para gerar, passe o resultado para `/minimax-gerar-video`.
