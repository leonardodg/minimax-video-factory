#!/usr/bin/env bash
# install_deps.sh — instala dependências extras do estúdio audiovisual
# Uso: bash scripts/install_deps.sh

set -euo pipefail

echo "=========================================="
echo "Instalando dependências do estúdio audiovisual"
echo "=========================================="

# Atualiza pip
pip install --upgrade pip

# Dependências principais (já no pyproject.toml)
echo "[INFO] Instalando yt-dlp, faster-whisper, requests..."
pip install --upgrade yt-dlp faster-whisper requests

# Torch (já instalado via Dockerfile, mas garante versão compatível)
echo "[INFO] Verificando PyTorch com CUDA..."
python3 -c "import torch; print(f'PyTorch {torch.__version__}, CUDA: {torch.version.cuda}, GPU: {torch.cuda.get_device_name(0) if torch.cuda.is_available() else \"N/A\"}')"

# ffmpeg (necessário para yt-dlp e transcrição)
if ! command -v ffmpeg >/dev/null 2>&1; then
    echo "[AVISO] ffmpeg não encontrado. Instale com: sudo apt install ffmpeg"
else
    echo "[OK] ffmpeg encontrado: $(ffmpeg -version | head -1)"
fi

# Verifica yt-dlp
echo "[INFO] Testando yt-dlp..."
yt-dlp --version

# Verifica faster-whisper
echo "[INFO] Testando faster-whisper..."
python3 -c "from faster_whisper import WhisperModel; print('faster-whisper OK')"

echo ""
echo "=========================================="
echo "Dependências instaladas com sucesso!"
echo "=========================================="
echo ""
echo "Próximos passos:"
echo "  1. Baixar modelo Whisper: bash scripts/setup_whisper.sh small"
echo "  2. Verificar .env tem STUDIO_DOWNLOADS_DIR, WHISPER_MODEL, etc."
echo "  3. Rodar MCP server: uv run --directory . python src/minimax_mcp/server.py"