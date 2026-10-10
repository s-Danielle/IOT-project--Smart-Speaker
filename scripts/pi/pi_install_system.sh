#!/usr/bin/env bash
#
# Installs the speaker's SYSTEM files (service files, the saved system log, log rotation).
# These are the changes `git checkout` cannot undo, so pi_update.sh leaves them alone.
# Run it on the Pi.
#
#   bash pi_install_system.sh --dry-run     # preview only, changes nothing
#   bash pi_install_system.sh               # install and restart what changed
#   bash pi_install_system.sh --rollback    # put the old files back
#   bash pi_install_system.sh --check       # does this Pi match? (no sudo)
#   bash pi_install_system.sh --help        # everything it can do
#
# It asks for sudo when it needs it (the preview and --check do not).

set -euo pipefail

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

needs_root=1
for arg in "$@"; do
    case "$arg" in
        --dry-run|--check|--help|-h) needs_root=0 ;;
    esac
done

if [ "$needs_root" -eq 1 ] && [ "$(id -u)" -ne 0 ]; then
    exec sudo -- python3 "$here/pi_install_system.py" "$@"
fi
exec python3 "$here/pi_install_system.py" "$@"
