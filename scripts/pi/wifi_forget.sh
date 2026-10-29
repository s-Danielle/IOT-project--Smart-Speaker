#!/usr/bin/env bash
#
# Forgets the saved WiFi networks, so the WiFi setup can be tested from the start.
# Runs on the Pi as the normal user (iot-proj); it asks for sudo itself.
#
#   bash wifi_forget.sh --list            show the saved WiFi networks, change nothing
#   bash wifi_forget.sh --dry-run         show what it would delete, change nothing
#   bash wifi_forget.sh                   delete them all (it asks first)
#   bash wifi_forget.sh --keep-hotspot    ... but keep the SmartSpeaker-Setup profile
#   bash wifi_forget.sh --reboot          ... and reboot, for the fresh-boot test
#   bash wifi_forget.sh --yes             do not ask
#   bash wifi_forget.sh --undo [FOLDER]   put the deleted networks back (newest backup by default)
#
# Before deleting anything it copies /etc/NetworkManager/system-connections into
# /var/backups/smart-speaker-wifi/<time>/. Those files hold the WiFi passwords, so the
# copy is root-only (folder 700, files 600): do not move it into a user's backups.
#
# After the delete the speaker has no network. The WiFi service notices within a minute
# (NO_NETWORK_GRACE in Main/wifi_provisioner.py) and opens the SmartSpeaker-Setup hotspot.
# With --reboot you get the fresh-boot path instead. Watch either one with:
#   journalctl -u smart_speaker_wifi -f    or    tail -f /var/log/smart_speaker_wifi.log
#
# If you are logged in over the very WiFi this is about to delete, the deleting runs as a
# detached systemd unit, so losing the SSH session cannot stop it half-way.

set -euo pipefail

BACKUP_ROOT="${BACKUP_ROOT:-/var/backups/smart-speaker-wifi}"
NM_DIR="${NM_DIR:-/etc/NetworkManager/system-connections}"
# Must match AP_SSID in Main/hardware/wifi_manager.py
AP_SSID="${AP_SSID:-SmartSpeaker-Setup}"
STAGE_SCRIPT=/run/smart-speaker-wifi-forget.sh

LIST=0
DRY=0
YES=0
KEEP_HOTSPOT=0
REBOOT=0
UNDO=0
UNDO_DIR=""

while [ $# -gt 0 ]; do
    case "$1" in
        --list) LIST=1 ;;
        --dry-run) DRY=1 ;;
        --yes|-y) YES=1 ;;
        --keep-hotspot) KEEP_HOTSPOT=1 ;;
        --reboot) REBOOT=1 ;;
        --undo)
            UNDO=1
            # An optional folder may follow, but not another option
            if [ $# -gt 1 ] && [ "${2#-}" = "$2" ]; then
                UNDO_DIR="$2"
                shift
            fi
            ;;
        -h|--help) sed -n '2,25p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'; exit 0 ;;
        *) echo "Unknown option: $1  (try --help)" >&2; exit 1 ;;
    esac
    shift
done

say() { printf '%s\n' "$*"; }
step() { printf '\n== %s ==\n' "$*"; }
die() { printf '\nSTOPPED: %s\n' "$*" >&2; exit 1; }

# Run something that needs root: directly if we already are root, otherwise through sudo.
priv() {
    if [ "$(id -u)" -eq 0 ]; then "$@"; else sudo "$@"; fi
}

command -v nmcli >/dev/null 2>&1 || die "nmcli is not installed, so there is nothing for this script to do."

# ---- what NetworkManager knows -------------------------------------------

# The WiFi interface name, the same way Main/hardware/wifi_manager.py finds it.
wifi_interface() {
    local iface
    iface="$(nmcli -t -f DEVICE,TYPE device 2>/dev/null \
             | awk -F: '$2 == "wifi" && $1 != "" { print $1; exit }')"
    printf '%s\n' "${iface:-wlan0}"
}

# One line per saved WiFi profile: "<uuid> <tab> <name>".
# Asking for UUID first keeps the parsing safe: a name may contain a colon (nmcli
# escapes it as "\:"), a UUID never does, so only the name needs unescaping.
wifi_profiles() {
    nmcli -t -f UUID,TYPE,NAME connection show 2>/dev/null \
        | awk -F: -v OFS='\t' '$2 == "802-11-wireless" {
              name = $3
              for (i = 4; i <= NF; i++) name = name ":" $i   # a name that held an escaped colon
              gsub(/\\/, "", name)
              print $1, name
          }'
}

# The UUID of the profile the WiFi interface is using right now ('' if none).
active_wifi_uuid() {
    local iface
    iface="$(wifi_interface)"
    nmcli -t -f UUID,DEVICE connection show --active 2>/dev/null \
        | awk -F: -v iface="$iface" '$2 == iface { print $1; exit }'
}

# True if this session arrived over the WiFi interface, so deleting its profile
# would cut the connection this script is running on.
logged_in_over_wifi() {
    local local_ip iface
    [ -n "${SSH_CONNECTION:-}" ] || return 1
    local_ip="$(printf '%s\n' "$SSH_CONNECTION" | awk '{print $3}')"
    [ -n "$local_ip" ] || return 1
    iface="$(wifi_interface)"
    ip -o -4 addr show dev "$iface" 2>/dev/null | grep -qw "$local_ip"
}

# ---- --list ---------------------------------------------------------------

show_profiles() {
    local active uuid name mark found=0
    active="$(active_wifi_uuid)"
    printf '%-38s %-5s %s\n' "UUID" "NOW" "NAME"
    while IFS=$'\t' read -r uuid name; do
        [ -n "$uuid" ] || continue
        found=1
        mark=" "
        [ "$uuid" = "$active" ] && mark="*"
        printf '%-38s %-5s %s\n' "$uuid" "$mark" "$name"
    done < <(wifi_profiles)
    [ "$found" -eq 1 ] || say "(no saved WiFi networks)"
    [ -n "$active" ] && say $'\n* = in use right now'
    return 0
}

# ---- backup and undo -------------------------------------------------------

backup_profiles() {   # prints the folder it made
    local dest="$BACKUP_ROOT/$(date +%Y%m%d-%H%M%S)"
    priv mkdir -p "$dest"
    priv chmod 700 "$BACKUP_ROOT" "$dest"
    priv cp -a "$NM_DIR"/. "$dest"/
    priv chmod -R go-rwx "$dest"
    printf '%s\n' "$dest"
}

# The newest backup folder ('' if there is none). The names sort by time.
latest_backup() {
    priv bash -c 'shopt -s nullglob
        dirs=("'"$BACKUP_ROOT"'"/*/)
        [ "${#dirs[@]}" -gt 0 ] && printf "%s\n" "${dirs[-1]%/}"' || true
}

do_undo() {
    local dir="$UNDO_DIR"
    [ -n "$dir" ] || dir="$(latest_backup)"
    [ -n "$dir" ] || die "No backup found in $BACKUP_ROOT. Name the folder yourself: --undo FOLDER"
    priv test -d "$dir" || die "$dir is not a folder."

    step "Putting the saved networks back from $dir"
    priv ls -1 "$dir" | sed 's/^/  /' || true
    if [ "$DRY" -eq 1 ]; then
        say "[preview] would copy those into $NM_DIR and reload NetworkManager"
        return 0
    fi
    priv cp -a "$dir"/. "$NM_DIR"/
    priv chown -R root:root "$NM_DIR"
    # NetworkManager ignores a profile file that others can read
    priv bash -c 'shopt -s nullglob; for f in "'"$NM_DIR"'"/*; do chmod 600 "$f"; done'
    priv nmcli connection reload
    say "Done. The WiFi service tries the saved network again every two minutes"
    say "(AP_RETRY_INTERVAL in Main/wifi_provisioner.py), or do it now yourself:"
    say "  sudo nmcli connection up <name>"
}

# ---- deleting ---------------------------------------------------------------

# The script that does the deleting. It takes the UUIDs, so a profile renamed or
# re-read in the meantime cannot change which ones go.
stage_script() {   # stage_script UUID...
    local uuid
    printf '#!/bin/bash\n'
    printf 'set -u\n'
    for uuid in "$@"; do
        printf 'echo "deleting %s"\n' "$uuid"
        printf 'nmcli connection delete "%s" || echo "  that one failed: %s"\n' "$uuid" "$uuid"
    done
    printf 'rm -f %s\n' "$STAGE_SCRIPT"
    if [ "$REBOOT" -eq 1 ]; then
        printf 'echo "rebooting"\nsleep 2\nsystemctl reboot\n'
    fi
}

delete_here() {   # delete_here UUID...
    local uuid
    for uuid in "$@"; do
        say "  deleting $uuid"
        priv nmcli connection delete "$uuid" || say "  that one failed: $uuid"
    done
    if [ "$REBOOT" -eq 1 ]; then
        say "  rebooting"
        priv systemctl reboot
    fi
}

delete_detached() {   # delete_detached UUID...
    local unit="wifi-forget-$(date +%s)"
    stage_script "$@" | priv tee "$STAGE_SCRIPT" >/dev/null
    priv chmod 700 "$STAGE_SCRIPT"
    priv systemd-run --collect --unit="$unit" \
        --description="Forget the saved WiFi networks" \
        /bin/bash "$STAGE_SCRIPT"
    say ""
    say "Running detached as $unit, because this session came in over the WiFi being deleted."
    say "Your SSH connection is about to drop. What it did, once the Pi is reachable again:"
    say "  journalctl -u $unit"
}

# ---- main -------------------------------------------------------------------

if [ "$LIST" -eq 1 ]; then
    show_profiles
    exit 0
fi

if [ "$UNDO" -eq 1 ]; then
    do_undo
    exit 0
fi

step "The saved WiFi networks"
show_profiles

UUIDS=()
NAMES=()
ACTIVE_UUID="$(active_wifi_uuid)"
while IFS=$'\t' read -r uuid name; do
    [ -n "$uuid" ] || continue
    if [ "$KEEP_HOTSPOT" -eq 1 ] && [ "$name" = "$AP_SSID" ]; then
        continue
    fi
    UUIDS+=("$uuid")
    NAMES+=("$name")
done < <(wifi_profiles)

if [ "${#UUIDS[@]}" -eq 0 ]; then
    say ""
    say "Nothing to delete: the speaker has no saved WiFi network."
    if [ "$REBOOT" -eq 1 ] && [ "$DRY" -eq 0 ]; then
        say "Rebooting anyway, as asked."
        priv systemctl reboot
    fi
    exit 0
fi

step "About to delete"
for i in "${!UUIDS[@]}"; do
    say "  ${NAMES[$i]}  (${UUIDS[$i]})"
done
[ "$KEEP_HOTSPOT" -eq 1 ] && say "  (keeping $AP_SSID)"
if [ "$KEEP_HOTSPOT" -eq 0 ] && printf '%s\n' "${NAMES[@]}" | grep -qxF "$AP_SSID"; then
    say ""
    say "The $AP_SSID profile goes too. That is usually fine: the speaker makes it"
    say "again when it opens the hotspot, picking up the current AP_PASSWORD from SECRETS."
fi

if [ "$DRY" -eq 1 ]; then
    say ""
    say "[preview] nothing was changed. Drop --dry-run to do it."
    exit 0
fi

if [ "$YES" -eq 0 ]; then
    say ""
    say "Once these are gone, the setup hotspot is the only way back in. Keep a keyboard"
    say "and a screen, or a network cable, within reach."
    printf 'Delete them? [y/N] '
    read -r answer
    case "$answer" in
        y|Y|yes|YES) ;;
        *) die "Nothing was changed." ;;
    esac
fi

step "Copying the profiles first"
BACKUP_DIR="$(backup_profiles)"
say "Saved in $BACKUP_DIR (root-only: it holds the WiFi passwords)"
say "To put them back:  bash ${BASH_SOURCE[0]} --undo"

step "Deleting"
if [ -n "$ACTIVE_UUID" ] && printf '%s\n' "${UUIDS[@]}" | grep -qxF "$ACTIVE_UUID" && logged_in_over_wifi; then
    delete_detached "${UUIDS[@]}"
else
    delete_here "${UUIDS[@]}"
    say ""
    if [ "$REBOOT" -eq 0 ]; then
        say "Done. Within a minute the WiFi service should open the $AP_SSID hotspot"
        say "(Light 1 pulsing blue). Follow it with:"
        say "  journalctl -u smart_speaker_wifi -f"
    fi
fi
