#!/usr/bin/env bash
# demo_minimax_video_factory.sh — Roteiro de demonstração do MiniMax Video Factory
# Executa uma sequência de prompts via opencode para gerar um vídeo de apresentação

set -euo pipefail

ROOT="$PROJECT_ROOT"
OUTFILE="$ROOT/output/demo_presentation_$(date +%Y%m%d_%H%M%S).mp4"

echo "=========================================="
echo "MiniMax Video Factory — Demo de Apresentação"
echo "=========================================="
echo ""

# Prompt 1: Cena de abertura — título
echo "▶ Cena 1: Título animado"
opencode run "Crie um vídeo de 5 segundos: texto 'MiniMax Video Factory' animando com efeito de digitação, fundo escuro com partículas sutis, fonte moderna, cor azul-neon. Formato 16:9, 24fps." --mcp minimax-video-factory 2>&1 | tee -a /tmp/demo.log
sleep 5

# Prompt 2: Arquitetura
echo ""
echo "▶ Cena 2: Diagrama da arquitetura"
opencode run "Gere 5 segundos: diagrama animado mostrando fluxo OpenCode → MCP (stdio) → ComfyUI (Docker/GPU) → MiniMax H3 (INT4) → vídeo + áudio nativo. Setas animadas, labels, fundo técnico escuro." --mcp minimax-video-factory 2>&1 | tee -a /tmp/demo.log
sleep 5

# Prompt 3: Prompt estruturado
echo ""
echo "▶ Cena 3: Exemplo de prompt estruturado MiniMax H3"
opencode run "Vídeo de 5s: close-up de terminal mostrando prompt MiniMax H3 estruturado — shots, camera, audio, duration, width, height, seed. Sintaxe highlighting, cursor piscando, fundo escuro." --mcp minimax-video-factory 2>&1 | tee -a /tmp/demo.log
sleep 5

# Prompt 4: Resultado — maçã girando
echo ""
echo "▶ Cena 4: Exemplo renderizado — maçã vermelha"
opencode run "Render 5s: uma maçã vermelha brilhante girando lentamente em uma mesa de madeira, luz suave de janela lateral, close-up, profundidade de campo rasa, 512x320, seed 42." --mcp minimax-video-factory 2>&1 | tee -a /tmp/demo.log
sleep 10

# Prompt 5: Cristal flutuando
echo ""
echo "▶ Cena 5: Exemplo renderizado — cristal azul"
opencode run "Render 5s: cristal azul translúcido flutuando no escuro, rotação orbital lenta, reflexos de luz, partículas de poeira no feixe, atmosfera misteriosa, 512x320, seed 123." --mcp minimax-video-factory 2>&1 | tee -a /tmp/demo.log
sleep 10

# Prompt 6: Compose final
echo ""
echo "▶ Cena 6: Composição final das cenas"
opencode run "Concatene as cenas geradas (maçã + cristal) em um vídeo final com transição suave de crossfade de 0.5s, mantendo áudio nativo estéreo." --mcp minimax-video-factory 2>&1 | tee -a /tmp/demo.log
sleep 5

echo ""
echo "=========================================="
echo "Demo concluída! Verifique em $ROOT/output/"
echo "=========================================="