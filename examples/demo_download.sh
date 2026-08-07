#!/usr/bin/env bash
# demo_download.sh —  demonstração download e transcrição de video pelo link

set -euo pipefail

# Resolve the project root from this script's location, so the demo
# runs from any checkout without editing a hardcoded path.
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUTFILE="$ROOT/output/demo_presentation_$(date +%Y%m%d_%H%M%S).mp4"
LINK="https://www.instagram.com/p/DbHIZl5Pk_0/"

echo ""
echo "=========================================="
echo " Download — Demostração"
echo "=========================================="
echo ""


cd $ROOT 
timeout 300 uv run python3 -c "
from minimax_mcp.orchestrator import AudiovisualStudio
studio = AudiovisualStudio(downloads_dir='downloads')

# Test with the downloaded Instagram Reel
video_path = 'downloads/example.mp4'
print('Testing full pipeline with save_only...')

# Step 1: Transcribe
print('Step 1: Transcribing...')
tr_result = studio.transcribe_video(video_path)
print('Transcription:', tr_result.get('ok'))
if tr_result.get('ok'):
    transcription = tr_result['text']
    print('Transcription length:', len(transcription))
    
    # Step 2: Create prompt
    prompt = studio.create_cinematic_prompt(transcription, style='cinematic')
    print('Prompt length:', len(prompt))
    
    # Step 3: Save both
    studio.save_transcription_and_prompt(
        transcription=transcription,
        cinematic_prompt=prompt,
        output_dir='output/transcriptions',
        url=$LINK
    )
    print('Saved!')
"

echo ""
echo "=========================================="
echo " LINK: $LINK"
echo " Output Transcription: output/transcriptions/"
echo " Output downloaded video: downloads/example.mp4"
echo " ✅ Demo concluída! "
echo "=========================================="
echo ""