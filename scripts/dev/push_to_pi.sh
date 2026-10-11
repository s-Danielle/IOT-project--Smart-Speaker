#!/usr/bin/env bash
#
# Copies scripts/pi and the repo files it needs to /tmp/pi on the Pi. Run it on the
# development machine. It writes only to /tmp/pi on the Pi.
#
#   scripts/dev/push_to_pi.sh [user@host]       (default: iot-proj@rpi2.local)
#
# The bundle holds scripts/pi/*, services/ (whole folder, as pi_install_system.py
# reads it), services/audio/asound.conf and mopidy.conf, and requirements.txt.
# It also records the commit in BUNDLE_COMMIT.
#
# Plain `scp -r scripts/pi` would miss the files outside scripts/pi, so the bundle is
# assembled in a temporary folder first.

set -euo pipefail

TARGET="${1:-iot-proj@rpi2.local}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd "$SCRIPT_DIR/../.." && pwd)"
PI_SCRIPTS="$REPO/scripts/pi"

BUNDLE="$(mktemp -d)"
trap 'rm -rf "$BUNDLE"' EXIT
mkdir -p "$BUNDLE/pi/audio" "$BUNDLE/pi/units"

for file in "$PI_SCRIPTS"/*; do
    [ -f "$file" ] && cp "$file" "$BUNDLE/pi/"
done

cp "$REPO/services/audio/asound.conf" "$REPO/services/audio/mopidy.conf" "$BUNDLE/pi/audio/"
cp "$REPO"/services/*.service "$BUNDLE/pi/units/"
cp "$REPO/requirements.txt" "$BUNDLE/pi/"
# The whole services/ folder, laid out as in the repo: pi_install_system.py installs from it
cp -r "$REPO/services" "$BUNDLE/pi/services"
rm -rf "$BUNDLE/pi/services/__pycache__"
git -C "$REPO" rev-parse HEAD > "$BUNDLE/pi/BUNDLE_COMMIT" 2>/dev/null || echo unknown > "$BUNDLE/pi/BUNDLE_COMMIT"

chmod +x "$BUNDLE"/pi/*.sh "$BUNDLE"/pi/*.py 2>/dev/null || true

echo "==> Copying to $TARGET:/tmp/pi ..."
ssh "$TARGET" 'rm -rf /tmp/pi 2>/dev/null || sudo -n rm -rf /tmp/pi'
scp -r "$BUNDLE/pi" "$TARGET:/tmp/"

echo ""
echo "Done. On the Pi, in this order:"
echo "  sudo bash /tmp/pi/pi_report.sh > /tmp/report.txt"
echo "  python3 /tmp/pi/spotify_check.py > /tmp/spotify.txt"
echo "  bash /tmp/pi/pi_backup.sh"
