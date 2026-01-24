#!/bin/bash
# Install PTT (Push-to-Talk) voice command dependencies
# Run this on Raspberry Pi before using voice commands

set -e

echo "=== Installing PTT Voice Command Dependencies ==="

# System dependencies
echo "Installing system packages..."
sudo apt-get update
sudo apt-get install -y flac alsa-utils

# Python dependencies (run in venv)
echo ""
echo "Installing Python packages..."
if [ -n "$VIRTUAL_ENV" ]; then
    pip install SpeechRecognition
else
    echo "Warning: Not in virtualenv. Activate venv first:"
    echo "  source /home/iot-proj/IOT-project--Smart-Speaker/venv/bin/activate"
    echo "Then run: pip install SpeechRecognition"
fi

echo ""
echo "=== Done! ==="
echo ""
echo "Test with: cd Main && python3 ../scripts/test-ptt.py"
echo ""
echo "Note: PTT requires internet connection for Google Speech API"
