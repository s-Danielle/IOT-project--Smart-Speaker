#!/usr/bin/env bash
#
# Build the Flutter web app and deploy it to the Smart Speaker Pi.
#
# Usage: ./scripts/deploy_web.sh [user@host]
#   Default target: iot-proj@smart-speaker-iot.local
#
# The bundle is rsync'd to Main/web_app/ on the Pi, where the API server
# (port 8080) serves it. No service restart needed.

set -euo pipefail

TARGET="${1:-iot-proj@smart-speaker-iot.local}"
# Repo path on the Pi (matches WorkingDirectory in services/*.service)
REMOTE_WEB_DIR="/home/iot-proj/IOT-project--Smart-Speaker/Main/web_app"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR/../flutter_app"

echo "==> Building Flutter web app (release)..."
flutter build web --release

echo "==> Deploying to $TARGET:$REMOTE_WEB_DIR ..."
rsync -av --delete build/web/ "$TARGET:$REMOTE_WEB_DIR/"

HOST="${TARGET#*@}"
echo ""
echo "Done! Open http://$HOST:8080 in a browser to use the app."
