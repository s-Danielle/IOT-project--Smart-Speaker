#!/bin/bash
# Installs and enables all Smart Speaker systemd services.
#
# WiFi provisioning (smart_speaker_wifi.service, nmcli sudoers rule, and
# the captive-portal DNS catch-all) is delegated to
# install-wifi-provisioner.sh, which this script invokes at the end.
#
# Usage: sudo ./copy-and-enable-service.sh

set -e

if [ "$EUID" -ne 0 ]; then
    echo "Please run with sudo: sudo ./copy-and-enable-service.sh"
    exit 1
fi

SOURCE_DIR="$(cd "$(dirname "$0")" && pwd)"
DESTINATION_DIR="/etc/systemd/system"

# Server first: smart_speaker.service Requires= it. The server starts
# unconditionally at boot (no network-online dependency) so the captive
# portal is available while in AP mode.
SERVICES=(
    smart_speaker_server.service
    smart_speaker.service
    smart_speaker_health.service
)

for SERVICE_NAME in "${SERVICES[@]}"; do
    SOURCE_FILE="$SOURCE_DIR/$SERVICE_NAME"
    if [ ! -f "$SOURCE_FILE" ]; then
        echo "Error: Source file '$SOURCE_FILE' not found."
        exit 1
    fi
    echo "Installing $SERVICE_NAME..."
    cp "$SOURCE_FILE" "$DESTINATION_DIR/"
    chown root:root "$DESTINATION_DIR/$SERVICE_NAME"
    chmod 644 "$DESTINATION_DIR/$SERVICE_NAME"
done

echo "Reloading systemd daemon..."
systemctl daemon-reload

for SERVICE_NAME in "${SERVICES[@]}"; do
    echo "Enabling and starting $SERVICE_NAME..."
    systemctl enable --now "$SERVICE_NAME" || true
    if systemctl is-active --quiet "$SERVICE_NAME"; then
        echo "  $SERVICE_NAME is active and enabled."
    else
        echo "  Warning: $SERVICE_NAME was enabled but is not active yet." \
             "Check 'systemctl status $SERVICE_NAME'."
    fi
done

echo ""
echo "Installing WiFi provisioner (service, sudoers, DNS catch-all)..."
bash "$SOURCE_DIR/install-wifi-provisioner.sh"

echo ""
echo "All Smart Speaker services installed and enabled."
