#!/bin/bash
# Installation script for WiFi Provisioner Service
# Run this script on the Raspberry Pi to set up WiFi provisioning

set -e  # Exit on error

echo "========================================="
echo "Smart Speaker WiFi Provisioner Setup"
echo "========================================="

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
NC='\033[0m' # No Color

# Check if running as root or with sudo
if [ "$EUID" -ne 0 ]; then
    echo -e "${RED}Please run with sudo: sudo ./install-wifi-provisioner.sh${NC}"
    exit 1
fi

# Get the actual user (not root) if running with sudo
ACTUAL_USER="${SUDO_USER:-iot-proj}"

echo ""
echo "Step 1: Installing NetworkManager (if not installed)..."
if ! command -v nmcli &> /dev/null; then
    apt update
    apt install -y network-manager
    echo -e "${GREEN}NetworkManager installed${NC}"
else
    echo -e "${GREEN}NetworkManager already installed${NC}"
fi

echo ""
echo "Step 2: Configuring sudoers for nmcli..."
SUDOERS_FILE="/etc/sudoers.d/smart_speaker_wifi"
cat > "$SUDOERS_FILE" << EOF
# Smart Speaker WiFi Provisioner
# Allows the service user to manage WiFi without password
$ACTUAL_USER ALL=(ALL) NOPASSWD: /usr/bin/nmcli
EOF
chmod 440 "$SUDOERS_FILE"
echo -e "${GREEN}Sudoers configured: $SUDOERS_FILE${NC}"

echo ""
echo "Step 3: Creating log file..."
LOG_FILE="/var/log/smart_speaker_wifi.log"
touch "$LOG_FILE"
chown "$ACTUAL_USER:$ACTUAL_USER" "$LOG_FILE"
echo -e "${GREEN}Log file created: $LOG_FILE${NC}"

echo ""
echo "Step 4: Installing systemd service..."
SERVICE_FILE="smart_speaker_wifi.service"
SOURCE_DIR="$(dirname "$0")"

if [ -f "$SOURCE_DIR/$SERVICE_FILE" ]; then
    cp "$SOURCE_DIR/$SERVICE_FILE" /etc/systemd/system/
    chown root:root "/etc/systemd/system/$SERVICE_FILE"
    chmod 644 "/etc/systemd/system/$SERVICE_FILE"
    echo -e "${GREEN}Service file installed${NC}"
else
    echo -e "${RED}Error: $SERVICE_FILE not found in $SOURCE_DIR${NC}"
    exit 1
fi

echo ""
echo "Step 5: Reloading systemd and enabling service..."
systemctl daemon-reload
systemctl enable smart_speaker_wifi.service
echo -e "${GREEN}Service enabled${NC}"

echo ""
echo "========================================="
echo -e "${GREEN}Installation Complete!${NC}"
echo "========================================="
echo ""
echo "The WiFi provisioner will run on boot."
echo ""
echo "How it works:"
echo "  1. On boot, waits 30 seconds for WiFi to connect"
echo "  2. If no WiFi, starts 'SmartSpeaker-Setup' hotspot"
echo "  3. Connect your phone to that network to configure"
echo ""
echo "To test AP mode manually:"
echo "  sudo nmcli device wifi hotspot ssid SmartSpeaker-Setup"
echo ""
echo "To check service status:"
echo "  sudo systemctl status smart_speaker_wifi"
echo ""
echo "To view logs:"
echo "  tail -f /var/log/smart_speaker_wifi.log"
echo ""
