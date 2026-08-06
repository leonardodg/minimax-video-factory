#!/usr/bin/env bash
# setup_whisper.sh — baixa e prepara modelos Whisper para uso local com faster-whisper
# Uso: bash scripts/setup_whisper.sh [tiny|base|small|medium|large-v3]
# Por padrão baixa 'small' (244MB, ótimo para PT-BR, roda em ~2GB VRAM)

set -euo pipefail

MODEL="${1:-small}"
MODELS_DIR="${MODELS_DIR:-/var/tmp/minimax/models/whisper}"

echo "=========================================="
echo "Setup Whisper Model: $MODEL"
echo "=========================================="

# Verifica se faster-whisper está instalado
if ! python3 -c "import faster_whisper" 2>/dev/null; then
    echo "[INFO] Instalando faster-whisper..."
    pip install --upgrade faster-whisper
fi

# Cria diretório
mkdir -p "$MODELS_DIR"

echo "[INFO] Baixando modelo Whisper '$MODEL' para $MODELS_DIR ..."
echo "[INFO] Tamanhos aproximados: tiny=39MB, base=74MB, small=244MB, medium=769MB, large-v3=1.5GB"

# Usa o faster-whisper CLI para baixar (ele faz cache automático)
# Forçamos o download rodando uma transcrição dummy
python3 -c "
from faster_whisper import WhisperModel
import os
model = WhisperModel('$MODEL', device='cuda', compute_type='float16', download_root='$MODELS_DIR')
print('Modelo carregado com sucesso!')
" 2>&1 | grep -v "^\[" || true

# Verifica se baixou
MODEL_PATH="$MODELS_DIR/models--Systran--faster-whisper-$MODEL"
if [ -d "$MODEL_PATH" ]; then
    SIZE=$(du -sh "$MODEL_PATH" | cut -f1)
    echo "[OK] Modelo '$MODEL' baixado e pronto em $MODEL_PATH ($SIZE)"
else
    # Tenta achar onde foi salvo
    FOUND=$(find "$MODELS_DIR" -name "*$MODEL*" -type d 2>/dev/null | head -1)
    if [ -n "$FOUND" ]; then
        SIZE=$(du -sh "$FOUND" | cut -f1)
        echo "[OK] Modelo '$MODEL' encontrado em $FOUND ($SIZE)"
    else
        echo "[AVISO] Não encontrou o modelo baixado. Verifique manualmente."
    fi
fi

echo ""
echo "Para usar: defina WHISPER_MODEL=$MODEL no .env ou passe model_size='$MODEL' nas tools."
echo "Exemplo: transcribe_video(video_path, model_size='$MODEL')"
echo ""
echo "Modelos disponíveis:"
echo "  tiny      - 39MB   - mais rápido, menos preciso"
echo "  base      - 74MB   - equilibrado"
echo "  small     - 244MB  - RECOMENDADO para PT-BR (padrão)"
echo "  medium    - 769MB  - mais preciso, mais lento"
echo "  large-v3  - 1.5GB  - máxima precisão, muito lento"