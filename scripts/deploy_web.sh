#!/usr/bin/env bash
#
# Build the Flutter web app and deploy it to the Smart Speaker Pi.
#
# Usage: ./scripts/deploy_web.sh [user@host]          build and deploy
#        ./scripts/deploy_web.sh --undo [user@host]   put the previous web app back
#   Default target: iot-proj@rpi2.local
#
# The bundle is rsync'd to Main/web_app/ on the Pi, where the API server
# (port 8080) serves it. No service restart needed.
#
# The web app is not in git on the Pi (it is copied there), so `git checkout` cannot undo it.
# Before replacing it, the current one is kept as Main/web_app.prev, and --undo swaps the two
# (so running --undo twice brings the newer one back).

set -euo pipefail

UNDO=0
if [ "${1:-}" = "--undo" ]; then UNDO=1; shift; fi
TARGET="${1:-iot-proj@rpi2.local}"
# Repo path on the Pi (matches WorkingDirectory in services/*.service)
REMOTE_WEB_DIR="/home/iot-proj/IOT-project--Smart-Speaker/Main/web_app"

if [ "$UNDO" -eq 1 ]; then
    echo "==> Swapping the web app on $TARGET with the previous one ..."
    ssh "$TARGET" "set -e; cd '$(dirname "$REMOTE_WEB_DIR")'; [ -f web_app.prev/index.html ] || { echo 'There is no previous web app (web_app.prev) to go back to.'; exit 1; }; rm -rf web_app.swap; mv web_app web_app.swap; mv web_app.prev web_app; mv web_app.swap web_app.prev; echo done"
    echo "The previous web app is live. Run this again to go back to the newer one."
    exit 0
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR/../flutter_app"

echo "==> Building Flutter web app (release)..."
flutter build web --release

echo "==> Keeping the current web app on $TARGET as web_app.prev ..."
# (the first deploy has nothing to keep, and an empty folder must never become the "previous" app)
ssh "$TARGET" "if [ -f '$REMOTE_WEB_DIR/index.html' ]; then rm -rf '$REMOTE_WEB_DIR.prev' && cp -a '$REMOTE_WEB_DIR' '$REMOTE_WEB_DIR.prev'; else echo '(no web app on the Pi yet: nothing to keep)'; fi"

echo "==> Deploying to $TARGET:$REMOTE_WEB_DIR ..."
rsync -av --delete build/web/ "$TARGET:$REMOTE_WEB_DIR/"

HOST="${TARGET#*@}"
echo ""
echo "Done! Open http://$HOST:8080 in a browser to use the app."
echo "To go back to the previous one:  scripts/deploy_web.sh --undo $TARGET"
