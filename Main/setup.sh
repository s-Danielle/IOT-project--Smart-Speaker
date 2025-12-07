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

# Check for hardware libraries (optional)
echo "Checking hardware libraries..."
if python3 -c "import board, busio, adafruit_pn532" 2>/dev/null; then
    echo "✅ NFC hardware libraries available"
else
    echo "⚠️  NFC hardware libraries not found (will run in simulation mode)"
fi

if python3 -c "from smbus2 import SMBus" 2>/dev/null; then
    echo "✅ Button hardware libraries available"
else
    echo "⚠️  Button hardware libraries not found (will run in simulation mode)"
fi
echo ""

# Check for system tools
echo "Checking system tools..."
if command -v aplay &> /dev/null; then
    echo "✅ aplay found (for sound playback)"
else
    echo "⚠️  aplay not found (sound playback may not work)"
fi

if command -v arecord &> /dev/null; then
    echo "✅ arecord found (for recording)"
else
    echo "⚠️  arecord not found (recording will run in simulation mode)"
fi
echo ""

# Check Mopidy connection
echo "Checking Mopidy connection..."
if python3 -c "import requests; requests.post('http://localhost:6680/mopidy/rpc', json={'jsonrpc':'2.0','id':1,'method':'core.get_version'}, timeout=2)" 2>/dev/null; then
    echo "✅ Mopidy is running and accessible"
else
    echo "⚠️  Mopidy not accessible at localhost:6680"
    echo "   Make sure Mopidy is running: sudo systemctl start mopidy"
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

