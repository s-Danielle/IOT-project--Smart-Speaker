#!/usr/bin/env bash
#
# Sets up shared audio for the Smart Speaker. Run it on the Pi.
#
#   bash pi_install_audio.sh --dry-run        # preview only, changes nothing
#   bash pi_install_audio.sh                  # Part A: sound card sharing
#   bash pi_install_audio.sh --mopidy-conf    # Part B: Mopidy settings
#   bash pi_install_audio.sh --rollback       # undo the newest run
#   bash pi_install_audio.sh --help           # everything it can do
#
# It asks for sudo when it needs it (the preview does not).

set -euo pipefail

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

needs_root=1
for arg in "$@"; do
    case "$arg" in
        --dry-run|--help|-h) needs_root=0 ;;
    esac
done

if [ "$needs_root" -eq 1 ] && [ "$(id -u)" -ne 0 ]; then
    exec sudo -- python3 "$here/pi_install_audio.py" "$@"
fi
exec python3 "$here/pi_install_audio.py" "$@"
