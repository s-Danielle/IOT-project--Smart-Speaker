#!/bin/bash
# Setup script for Smart Speaker
#
# Makes the app's own Python environment (the "venv" folder next to Main/), installs the
# Python packages into it, and checks the system requirements. The services run from that
# venv, not from the system Python. Safe to run again.
#
# Usage, on the Pi as the normal user (not with sudo):
#   bash Main/setup.sh

# No "set -e": a failed step is reported and the checks below still run.

# This script lives in Main/; the venv and requirements.txt are one folder up.
REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV="$REPO_DIR/venv"
VENV_PY="$VENV/bin/python"

echo "=========================================="
echo "Smart Speaker - Environment Setup"
echo "=========================================="
echo ""

# Check Python version
echo "Checking Python version..."
python3 --version || { echo "❌ Python 3 not found!"; exit 1; }
echo "✅ Python 3 found"
echo ""

# pyalsaaudio is built from source and needs these (apt, not pip)
echo "Checking what pyalsaaudio needs to build..."
if dpkg -s libasound2-dev python3-dev >/dev/null 2>&1; then
    echo "✅ libasound2-dev and python3-dev installed"
else
    echo "❌ libasound2-dev / python3-dev missing (needed to build pyalsaaudio)"
    echo "   Install with: sudo apt-get install libasound2-dev python3-dev build-essential"
fi
echo ""

# The app's own Python environment
echo "Preparing the Python environment ($VENV)..."
if [ ! -x "$VENV_PY" ]; then
    python3 -m venv "$VENV" || { echo "❌ Could not create $VENV"; exit 1; }
    echo "✅ Created $VENV"
else
    echo "✅ $VENV already exists"
fi
echo ""

# Install Python dependencies into it
echo "Installing Python dependencies into the environment..."
if [ -f "$REPO_DIR/requirements.txt" ]; then
    if "$VENV/bin/pip" install -r "$REPO_DIR/requirements.txt"; then
        echo "✅ Python dependencies installed"
    else
        echo "❌ pip could not install everything (read the error above)"
    fi
else
    echo "⚠️  $REPO_DIR/requirements.txt not found, installing basic dependencies..."
    "$VENV/bin/pip" install requests
fi
echo ""

# Check for hardware libraries (required for full functionality), as the app sees them
echo "Checking hardware libraries (in the environment)..."
if "$VENV_PY" -c "import board, busio, adafruit_pn532" 2>/dev/null; then
    echo "✅ NFC hardware libraries available"
else
    echo "❌ NFC hardware libraries not found (required for NFC scanning)"
    echo "   Install with: $VENV/bin/pip install adafruit-circuitpython-pn532"
fi

if "$VENV_PY" -c "from smbus2 import SMBus" 2>/dev/null; then
    echo "✅ Button and LED hardware libraries available"
else
    echo "❌ Button and LED hardware libraries not found (required for buttons and lights)"
    echo "   Install with: $VENV/bin/pip install smbus2"
fi
if "$VENV_PY" -c "import alsaaudio" 2>/dev/null; then
    echo "✅ pyalsaaudio available"
else
    echo "❌ pyalsaaudio not found (required for volume control)"
    echo "   Install with: sudo apt-get install libasound2-dev python3-dev && $VENV/bin/pip install pyalsaaudio"
fi
echo ""

# Check for system tools
echo "Checking system tools..."
if command -v arecord &> /dev/null; then
    echo "✅ arecord found (for recording)"
else
    echo "❌ arecord not found (required for recording)"
    echo "   Install with: sudo apt-get install alsa-utils"
fi
if command -v aplay &> /dev/null; then
    echo "✅ aplay found (for UI feedback sounds)"
else
    echo "❌ aplay not found (required for UI feedback sounds)"
    echo "   Install with: sudo apt-get install alsa-utils"
fi
echo ""

# Check Mopidy connection (REQUIRED)
echo "Checking Mopidy connection (REQUIRED)..."
if "$VENV_PY" -c "from mpd import MPDClient; c=MPDClient(); c.timeout=2; c.connect('localhost', 6600); c.disconnect()" 2>/dev/null; then
    echo "✅ Mopidy is running and accessible via MPD (port 6600)"
else
    echo "❌ Mopidy not accessible at localhost:6600 (MPD protocol)"
    echo "   Mopidy is REQUIRED for all audio playback"
    echo "   Make sure Mopidy is running: sudo systemctl start mopidy"
    echo "   Or install Mopidy: sudo apt-get install mopidy"
    echo "   Note: Make sure Mopidy's MPD server is enabled (default port 6600)"
fi
echo ""

echo "=========================================="
echo "Setup complete!"
echo "=========================================="
echo ""
echo "To install and start the speaker's services:"
echo "  sudo bash $REPO_DIR/services/copy-and-enable-service.sh"
echo ""
echo "To run the controller by hand instead (stop the service first):"
echo "  cd $REPO_DIR/Main && $VENV_PY main.py"
echo ""
