#!/bin/bash
# Setup script for Smart Speaker
# Installs Python dependencies and checks system requirements

set -e

echo "=========================================="
echo "Smart Speaker - Environment Setup"
echo "=========================================="
echo ""

# Check Python version
echo "Checking Python version..."
python3 --version || { echo "❌ Python 3 not found!"; exit 1; }
echo "✅ Python 3 found"
echo ""

# Install Python dependencies
echo "Installing Python dependencies..."
if [ -f "requirements.txt" ]; then
    pip3 install -r requirements.txt
    echo "✅ Python dependencies installed"
else
    echo "⚠️  requirements.txt not found, installing basic dependencies..."
    pip3 install requests
fi
echo ""

# Check for hardware libraries (required for full functionality)
echo "Checking hardware libraries..."
if python3 -c "import board, busio, adafruit_pn532" 2>/dev/null; then
    echo "✅ NFC hardware libraries available"
else
    echo "❌ NFC hardware libraries not found (required for NFC scanning)"
    echo "   Install with: pip3 install adafruit-circuitpython-pn532"
fi

if python3 -c "from smbus2 import SMBus" 2>/dev/null; then
    echo "✅ Button hardware libraries available"
else
    echo "❌ Button hardware libraries not found (required for button input)"
    echo "   Install with: pip3 install smbus2"
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
echo ""

# Check Mopidy connection (REQUIRED)
echo "Checking Mopidy connection (REQUIRED)..."
if python3 -c "from mpd import MPDClient; c=MPDClient(); c.timeout=2; c.connect('localhost', 6600); c.disconnect()" 2>/dev/null; then
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
echo "To run the Smart Speaker:"
echo "  cd Main"
echo "  python3 main.py"
echo ""

