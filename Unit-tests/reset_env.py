#!/bin/bash
# Setup / refresh Python venv for the Smart Speaker project.

set -e

# Go to the directory this script lives in (project root)
cd "$(dirname "$0")"

VENV=".venv"

# If called with --reset, delete existing venv
if [ "$1" = "--reset" ] && [ -d "$VENV" ]; then
  echo "Removing existing virtualenv at $VENV"
  rm -rf "$VENV"
fi

# Create venv if it doesn't exist
if [ ! -d "$VENV" ]; then
  echo "Creating virtualenv in $VENV"
  python3 -m venv "$VENV"
fi

# Activate venv
# shellcheck disable=SC1090
source "$VENV/bin/activate"

echo "Upgrading pip..."
pip install --upgrade pip

echo "Installing Python dependencies..."
pip install \
  smbus2 \
  RPi.GPIO \
  spidev \
  adafruit-blinka \
  adafruit-circuitpython-pn532

echo
echo "✅ Environment ready."
echo "You are now in the venv. Use 'deactivate' to exit."
echo "Example: python Unit-tests/health_check.py"

