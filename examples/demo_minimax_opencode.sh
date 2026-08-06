#!/usr/bin/env bash
# demo_minimax_opencode.sh — Roteiro demonstrativo: usando opencode para gerar vídeo de apresentação
# Mostra o fluxo: abrir opencode → digitar prompt → gerar vídeo via MiniMax Video Factory MCP

set -euo pipefail

ROOT="$PROJECT_ROOT"

echo "=========================================="
echo "MiniMax Video Factory — Demo via opencode"
echo "=========================================="
echo ""
echo "Este demo mostra o fluxo natural de uso:"
echo "  1. Abre opencode (já com MCP minimax-video-factory configurado)"
echo "  2. Digita prompt em linguagem natural"
echo "  3. Gera vídeo via MiniMax H3 (ComfyUI + GPU)"
echo ""

# Verifica se o container está rodando
if ! docker ps --format '{{.Names}}' | grep -q '^minimax-comfyui$'; then
    echo "⚠️ Container minimax-comfyui não está rodando. Iniciando..."
    ./scripts/start_comfyui.sh
fi

echo ""
echo "--- CENA 1: Apresentação da ferramenta ---"
echo "Prompt: 'Crie um vídeo de 5s apresentando o MiniMax Video Factory: texto animado \"MiniMax Video Factory\" com efeito de digitação, fundo escuro técnico, partículas sutis, cor azul-neon, 16:9 24fps.'"
echo ""
opencode run "Crie um vídeo de 5 segundos apresentando o MiniMax Video Factory: texto animado 'MiniMax Video Factory' com efeito de digitação, fundo escuro técnico, partículas sutis, cor azul-neon, 16:9 24fps." --mcp minimax-video-factory 2>&1 | grep -E "(build|⚙|✓|Error)" | head -5
sleep 3

echo ""
echo "--- CENA 2: Fluxo de trabalho (arquitetura) ---"
echo "Prompt: 'Gere 5s: diagrama animado mostrando fluxo OpenCode → MCP (stdio) → ComfyUI Docker/GPU → MiniMax H3 INT4 → vídeo + áudio nativo. Setas animadas, labels, fundo técnico escuro.'"
echo ""
opencode run "Gere 5 segundos: diagrama animado mostrando fluxo OpenCode -> MCP (stdio) -> ComfyUI Docker/GPU -> MiniMax H3 INT4 -> vídeo + áudio nativo. Setas animadas, labels, fundo técnico escuro." --mcp minimax-video-factory 2>&1 | grep -E "(build|⚙|✓|Error)" | head -5
sleep 3

echo ""
echo "--- CENA 3: Prompt estruturado MiniMax H3 ---"
echo "Prompt: 'Vídeo 5s: close-up de terminal mostrando prompt MiniMax H3 estruturado — shots, camera, audio, duration, width, height, seed. Syntax highlighting, cursor piscando, fundo escuro.'"
echo ""
opencode run "Vídeo 5s: close-up de terminal mostrando prompt MiniMax H3 estruturado — shots, camera, audio, duration, width, height, seed. Syntax highlighting, cursor piscando, fundo escuro." --mcp minimax-video-factory 2>&1 | grep -E "(build|⚙|✓|Error)" | head -5
sleep 3

echo ""
echo "--- CENA 4: Exemplo renderizado — maçã girando ---"
echo "Prompt: 'Render 5s: uma maçã vermelha brilhante girando lentamente em mesa de madeira, luz suave de janela lateral, close-up, profundidade de campo rasa, 512x320, seed 42.'"
echo ""
opencode run "Render 5s: uma maçã vermelha brilhante girando lentamente em mesa de madeira, luz suave de janela lateral, close-up, profundidade de campo rasa, 512x320, seed 42." --mcp minimax-video-factory 2>&1 | grep -E "(build|⚙|✓|Error)" | head -5
sleep 10

echo ""
echo "--- CENA 5: Exemplo renderizado — cristal flutuando ---"
echo "Prompt: 'Render 5s: cristal azul translúcido flutuando no escuro, rotação orbital lenta, reflexos de luz, partículas de poeira no feixe, atmosfera misteriosa, 512x320, seed 123.'"
echo ""
opencode run "Render 5s: cristal azul translúcido flutuando no escuro, rotação orbital lenta, reflexos de luz, partículas de poeira no feixe, atmosfera misteriosa, 512x320, seed 123." --mcp minimax-video-factory 2>&1 | grep -E "(build|⚙|✓|Error)" | head -5
sleep 10

echo ""
echo "--- CENA 6: Composição final ---"
echo "Prompt: 'Concatene as duas cenas geradas (maçã + cristal) em vídeo final com crossfade suave 0.5s, mantendo áudio nativo estéreo.'"
echo ""
opencode run "Concatene as duas cenas geradas (maçã + cristal) em vídeo final com crossfade suave 0.5s, mantendo áudio nativo estéreo." --mcp minimax-video-factory 2>&1 | grep -E "(build|⚙|✓|Error)" | head -5
sleep 5

echo ""
echo "=========================================="
echo "Demo concluído! Vídeos em $ROOT/output/"
echo "=========================================="
ls -la "$ROOT/output"/demo_* 2>/dev/null || ls -la "$ROOT/output"/*.mp4 2>/dev/null | tail -10