#!/usr/bin/env bash
#
# Run this on the computer where the repo is (not on the Pi). It copies the Pi
# helper scripts, and the few repo files they need, to /tmp/pi on the Pi. It
# changes nothing else on the Pi.
#
#   scripts/pi/push_to_pi.sh [user@host]       (default: iot-proj@rpi2.local)
#
# Then, on the Pi:
#   sudo bash /tmp/pi/pi_report.sh > /tmp/report.txt
#
# Why not just `scp -r scripts/pi`? The scripts also need services/audio/*,
# the service files and requirements.txt, and this puts them in one folder.

set -euo pipefail

TARGET="${1:-iot-proj@rpi2.local}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd "$SCRIPT_DIR/../.." && pwd)"

BUNDLE="$(mktemp -d)"
trap 'rm -rf "$BUNDLE"' EXIT
mkdir -p "$BUNDLE/pi/audio" "$BUNDLE/pi/units"

# The scripts themselves (not this laptop-side one, and no caches)
for file in "$SCRIPT_DIR"/*; do
    case "$(basename "$file")" in
        push_to_pi.sh|__pycache__) continue ;;
    esac
    [ -f "$file" ] && cp "$file" "$BUNDLE/pi/"
done

cp "$REPO/services/audio/asound.conf" "$REPO/services/audio/mopidy.conf" "$BUNDLE/pi/audio/"
cp "$REPO"/services/*.service "$BUNDLE/pi/units/"
cp "$REPO/requirements.txt" "$BUNDLE/pi/"
git -C "$REPO" rev-parse HEAD > "$BUNDLE/pi/BUNDLE_COMMIT" 2>/dev/null || echo unknown > "$BUNDLE/pi/BUNDLE_COMMIT"

chmod +x "$BUNDLE"/pi/*.sh "$BUNDLE"/pi/*.py 2>/dev/null || true

echo "==> Copying to $TARGET:/tmp/pi ..."
ssh "$TARGET" 'rm -rf /tmp/pi'
scp -r "$BUNDLE/pi" "$TARGET:/tmp/"

echo ""
echo "Done. On the Pi, in this order:"
echo "  sudo bash /tmp/pi/pi_report.sh > /tmp/report.txt"
echo "  python3 /tmp/pi/spotify_check.py > /tmp/spotify.txt"
echo "  bash /tmp/pi/pi_backup.sh"
