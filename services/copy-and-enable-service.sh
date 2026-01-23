#!/bin/bash

# Configuration
SERVICE_NAME="smart_speaker.service"
SOURCE_FILE="./$SERVICE_NAME"
DESTINATION_DIR="/etc/systemd/system"

# Check if the service is already enabled
if systemctl is-enabled --quiet "$SERVICE_NAME"; then
    echo "Service '$SERVICE_NAME' is already enabled."
else
    echo "Service not enabled. Proceeding with installation..."

    if [ ! -f "$SOURCE_FILE" ]; then
        echo "Error: Source file '$SOURCE_FILE' not found."
        exit 1
    fi

    echo "Copying $SOURCE_FILE to $DESTINATION_DIR..."
    sudo cp "$SOURCE_FILE" "$DESTINATION_DIR/"

    # Set correct permissions (root:root, 644)
    sudo chown root:root "$DESTINATION_DIR/$SERVICE_NAME"
    sudo chmod 644 "$DESTINATION_DIR/$SERVICE_NAME"

    echo "Reloading systemd daemon..."
    sudo systemctl daemon-reload

    echo "Enabling and starting $SERVICE_NAME..."
    sudo systemctl enable --now "$SERVICE_NAME"

    if systemctl is-active --quiet "$SERVICE_NAME"; then
        echo "Success: Service is now active and enabled."
    else
        echo "Warning: Service was enabled but failed to start. Check 'systemctl status $SERVICE_NAME'."
    fi
fi
