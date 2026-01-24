#!/bin/bash
# Download Vosk small English model for PTT voice commands
# Model size: ~50MB, optimized for low CPU usage

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
MODEL_DIR="$PROJECT_ROOT/Main/models"
MODEL_NAME="vosk-model-small-en-us-0.15"
MODEL_URL="https://alphacephei.com/vosk/models/${MODEL_NAME}.zip"

echo "=== Vosk Model Downloader ==="
echo "Model: $MODEL_NAME (~50MB)"
echo "Target: $MODEL_DIR"
echo ""

# Create models directory
mkdir -p "$MODEL_DIR"
cd "$MODEL_DIR"

# Check if model already exists
if [ -d "vosk-model-small-en-us" ]; then
    echo "Model already exists at $MODEL_DIR/vosk-model-small-en-us"
    echo "Delete it first if you want to re-download."
    exit 0
fi

# Check disk space (need ~100MB)
AVAILABLE_MB=$(df -m "$MODEL_DIR" | awk 'NR==2 {print $4}')
if [ "$AVAILABLE_MB" -lt 100 ]; then
    echo "ERROR: Not enough disk space. Need 100MB, have ${AVAILABLE_MB}MB"
    exit 1
fi

echo "Downloading model..."
wget -q --show-progress "$MODEL_URL" -O "${MODEL_NAME}.zip"

echo "Extracting..."
unzip -q "${MODEL_NAME}.zip"

echo "Cleaning up..."
mv "$MODEL_NAME" vosk-model-small-en-us
rm "${MODEL_NAME}.zip"

echo ""
echo "Done! Model installed at: $MODEL_DIR/vosk-model-small-en-us"
echo "Size: $(du -sh vosk-model-small-en-us | cut -f1)"
