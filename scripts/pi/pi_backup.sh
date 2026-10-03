#!/usr/bin/env bash
#
# Backs up the speaker's data and the system files our scripts change, and can
# put them back. Run it on the Pi.
#
#   bash pi_backup.sh                         make a backup in /home/iot-proj/backups/<time>/
#   bash pi_backup.sh --list                  list the backups
#   bash pi_backup.sh --restore DIR [--only PART] [--dry-run] [--yes]
#
# PART is one of: data, mopidy, asound, units, sudoers, alsa  (default: all)
#
# What is in a backup:
#   data/       server_data.json (and its .bak / .migrated files), server_data.db
#   system/     mopidy.conf, asound.conf (and what it was), the service files,
#               the sudoers rules for the speaker, the saved mixer levels
#   repo/       which commit the Pi was on, and any local edits as a patch
#
# What is NOT copied: Spotify credentials.json, the SECRETS file, WiFi passwords.
# mopidy.conf IS copied whole (the undo needs it), so it is kept private:
# the backup folder is mode 700 and that file is mode 600. Nobody should paste it anywhere.
#
# It asks for sudo for the few root-only files.

set -euo pipefail

REPO="${REPO:-/home/iot-proj/IOT-project--Smart-Speaker}"
APP_USER="${APP_USER:-iot-proj}"
BACKUP_ROOT="${BACKUP_ROOT:-/home/$APP_USER/backups}"
ME="$(id -un)"

say() { printf '%s\n' "$*"; }
warn() { printf 'NOTE: %s\n' "$*" >&2; }
die() { printf 'STOPPED: %s\n' "$*" >&2; exit 1; }

# Run something that needs root: directly if we already are root, otherwise through sudo.
priv() {
    if [ "$(id -u)" -eq 0 ]; then "$@"; else sudo "$@"; fi
}

# Copy a file we may not be allowed to read. The destination only appears if the copy worked.
priv_copy() {   # priv_copy SOURCE DEST
    local tmp
    tmp="$(mktemp)"
    if priv cat "$1" > "$tmp" 2>/dev/null; then
        mv "$tmp" "$2"
        return 0
    fi
    rm -f "$tmp"
    return 1
}

usage() { sed -n '2,23p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'; }

# ---- make a backup -------------------------------------------------------
make_backup() {
    local dest="$BACKUP_ROOT/$(date +%Y%m%d-%H%M%S)"
    mkdir -p "$dest/data" "$dest/system/units" "$dest/system/sudoers.d" "$dest/repo"
    chmod 700 "$BACKUP_ROOT" "$dest"
    say "Backing up to $dest"

    # -- data
    local f
    for f in "$REPO"/Main/server_data.json*; do
        [ -f "$f" ] && cp -p "$f" "$dest/data/" && say "  data: $(basename "$f")"
    done
    if [ -f "$REPO/Main/server_data.db" ]; then
        # A live database must not be copied with cp: use SQLite's own backup.
        python3 - "$REPO/Main/server_data.db" "$dest/data/server_data.db" <<'PY'
import sqlite3, sys
src = sqlite3.connect("file:%s?mode=ro" % sys.argv[1], uri=True)
dst = sqlite3.connect(sys.argv[2])
src.backup(dst)
dst.close(); src.close()
PY
        say "  data: server_data.db (SQLite backup)"
    fi
    [ -z "$(ls -A "$dest/data")" ] && warn "no server_data.json or server_data.db found in $REPO/Main"

    # -- mopidy.conf (private)
    if [ -f /etc/mopidy/mopidy.conf ]; then
        if priv_copy /etc/mopidy/mopidy.conf "$dest/system/mopidy.conf"; then
            chmod 600 "$dest/system/mopidy.conf"
            stat -c '%u:%g %a' /etc/mopidy/mopidy.conf > "$dest/system/mopidy.conf.info"
            say "  system: mopidy.conf (private, mode 600)"
        else
            warn "could not read /etc/mopidy/mopidy.conf (needs sudo); it is NOT in this backup"
        fi
    else
        warn "/etc/mopidy/mopidy.conf not found"
    fi

    # -- asound.conf (and what kind of thing it was)
    if [ -L /etc/asound.conf ]; then
        echo "symlink $(readlink /etc/asound.conf)" > "$dest/system/asound.conf.info"
        cp -L /etc/asound.conf "$dest/system/asound.conf" 2>/dev/null || true
        say "  system: asound.conf (it was a symlink to $(readlink /etc/asound.conf))"
    elif [ -f /etc/asound.conf ]; then
        echo "file" > "$dest/system/asound.conf.info"
        cp -p /etc/asound.conf "$dest/system/asound.conf"
        say "  system: asound.conf"
    else
        echo "absent" > "$dest/system/asound.conf.info"
        say "  system: no /etc/asound.conf to save (recorded as absent)"
    fi

    # -- service files and sudoers
    for f in /etc/systemd/system/smart_speaker*.service; do
        [ -f "$f" ] && cp -p "$f" "$dest/system/units/" && say "  system: $(basename "$f")"
    done
    for f in /etc/sudoers.d/*smart* /etc/sudoers.d/*speaker*; do
        [ -e "$f" ] || continue
        if priv_copy "$f" "$dest/system/sudoers.d/$(basename "$f")"; then
            say "  system: sudoers.d/$(basename "$f")"
        else
            warn "could not read $f (needs sudo)"
        fi
    done

    # -- saved mixer levels and boot config (for reference)
    if command -v alsactl >/dev/null 2>&1; then
        local alsa_tmp
        alsa_tmp="$(mktemp)"
        if priv alsactl store -f "$alsa_tmp" 2>/dev/null && priv_copy "$alsa_tmp" "$dest/system/alsa-state.conf"; then
            say "  system: mixer levels (alsa-state.conf)"
        else
            warn "could not save the mixer levels"
        fi
        priv rm -f "$alsa_tmp" 2>/dev/null || rm -f "$alsa_tmp"
    fi
    for f in /boot/firmware/config.txt /boot/config.txt; do
        [ -f "$f" ] && cp "$f" "$dest/system/boot-config.txt" && break
    done

    # -- which code was running, and any local edits
    if [ -d "$REPO/.git" ]; then
        local g=(git -C "$REPO")
        [ "$(id -u)" -eq 0 ] && g=(runuser -u "$APP_USER" -- git -C "$REPO")
        {
            echo "commit: $("${g[@]}" rev-parse HEAD 2>/dev/null)"
            echo "branch: $("${g[@]}" rev-parse --abbrev-ref HEAD 2>/dev/null)"
            echo "--- git status -sb"
            "${g[@]}" status -sb 2>/dev/null | head -40
        } > "$dest/repo/state.txt"
        "${g[@]}" diff -- . ':!Unit-tests/.venv' > "$dest/repo/local-changes.patch" 2>/dev/null || true
        say "  repo: commit $("${g[@]}" rev-parse --short HEAD 2>/dev/null), local edits saved as a patch"
    fi

    # -- checksums, and make everything private
    (cd "$dest" && find . -type f ! -name MANIFEST.sha256 -print0 | xargs -0 sha256sum > MANIFEST.sha256)
    find "$dest" -type f -exec chmod 600 {} + 2>/dev/null || true
    say ""
    say "Backup finished: $dest"
    say "To go back: bash pi_backup.sh --restore $dest"
}

# ---- list ---------------------------------------------------------------------
list_backups() {
    [ -d "$BACKUP_ROOT" ] || { say "No backups yet in $BACKUP_ROOT"; return; }
    for d in "$BACKUP_ROOT"/*/; do
        [ -d "$d" ] && say "$d  ($(ls "$d/data" 2>/dev/null | tr '\n' ' '))"
    done
}

# ---- restore ---------------------------------------------------------------------
RESTORE_DRY=0
RESTORE_YES=0

do_step() {   # do_step "what it does" command...
    local what="$1"; shift
    if [ "$RESTORE_DRY" -eq 1 ]; then say "[preview] $what"; return 0; fi
    if [ "$RESTORE_YES" -ne 1 ]; then
        read -r -p "$what  -- do it? [y/N] " answer
        [ "$answer" = "y" ] || [ "$answer" = "Y" ] || { say "  skipped"; return 0; }
    fi
    "$@" && say "  done: $what"
}

restore_data_file() {      # $1 = backed-up file
    priv systemctl stop smart_speaker_server || true
    priv cp -p "$1" "$REPO/Main/"
    priv systemctl start smart_speaker_server || true
}
restore_db_file() {        # $1 = backed-up database
    priv systemctl stop smart_speaker_server || true
    priv rm -f "$REPO/Main/server_data.db-wal" "$REPO/Main/server_data.db-shm"
    priv cp -p "$1" "$REPO/Main/server_data.db"
    priv systemctl start smart_speaker_server || true
}
restore_mopidy_conf() {    # $1 = backed-up file, $2 = owner uid:gid, $3 = mode
    priv cp "$1" /etc/mopidy/mopidy.conf
    priv chown "$2" /etc/mopidy/mopidy.conf
    priv chmod "$3" /etc/mopidy/mopidy.conf
    priv systemctl restart mopidy
}
restore_asound_file()    { priv cp -p "$1" /etc/asound.conf && priv systemctl restart mopidy; }
restore_asound_link()    { priv rm -f /etc/asound.conf && priv ln -s "$1" /etc/asound.conf && priv systemctl restart mopidy; }
restore_asound_absent()  { priv rm -f /etc/asound.conf && priv systemctl restart mopidy; }
restore_unit()           { priv cp -p "$1" /etc/systemd/system/ && priv systemctl daemon-reload; }
restore_sudoers() {        # $1 = backed-up rule; checked before it is installed
    priv visudo -cf "$1" && priv install -m 440 -o root -g root "$1" "/etc/sudoers.d/$(basename "$1")"
}
restore_alsa_state()     { priv alsactl restore -f "$1"; }

restore_backup() {
    local dir="$1" only="$2" f
    [ -d "$dir" ] || die "no such backup folder: $dir"
    (cd "$dir" && sha256sum -c --quiet MANIFEST.sha256) || die "the backup in $dir does not match its checksums; not restoring"
    say "Restoring from $dir ${only:+(only: $only)}"
    want() { [ -z "$only" ] || [ "$only" = "$1" ]; }
    local did=0

    if want data; then
        for f in "$dir"/data/server_data.json*; do
            [ -f "$f" ] || continue
            did=1
            do_step "put $(basename "$f") back in $REPO/Main (the server is stopped for a moment)" restore_data_file "$f"
        done
        if [ -f "$dir/data/server_data.db" ]; then
            did=1
            do_step "put server_data.db back (the server is stopped for a moment)" restore_db_file "$dir/data/server_data.db"
        fi
        [ "$did" -eq 0 ] && warn "this backup holds no data files"
    fi
    if want mopidy && [ -f "$dir/system/mopidy.conf" ]; then
        local owner mode
        read -r owner mode < "$dir/system/mopidy.conf.info"
        do_step "restore /etc/mopidy/mopidy.conf (owner $owner, mode $mode) and restart Mopidy" \
            restore_mopidy_conf "$dir/system/mopidy.conf" "$owner" "$mode"
    fi
    if want asound && [ -f "$dir/system/asound.conf.info" ]; then
        local kind target
        read -r kind target < "$dir/system/asound.conf.info"
        case "$kind" in
            symlink) do_step "make /etc/asound.conf a link to $target again" restore_asound_link "$target" ;;
            file)    do_step "restore /etc/asound.conf" restore_asound_file "$dir/system/asound.conf" ;;
            absent)  do_step "remove /etc/asound.conf (there was none)" restore_asound_absent ;;
        esac
    fi
    if want units; then
        for f in "$dir"/system/units/*.service; do
            [ -f "$f" ] && do_step "restore $(basename "$f") and reload systemd (services are NOT restarted)" restore_unit "$f"
        done
    fi
    if want sudoers; then
        for f in "$dir"/system/sudoers.d/*; do
            [ -f "$f" ] && do_step "restore sudoers rule $(basename "$f") (checked with visudo first)" restore_sudoers "$f"
        done
    fi
    if want alsa && [ -f "$dir/system/alsa-state.conf" ]; then
        do_step "restore the saved mixer levels" restore_alsa_state "$dir/system/alsa-state.conf"
    fi
    say "Restore finished."
}

# ---- main -------------------------------------------------------------------------
case "${1:-}" in
    "" ) make_backup ;;
    --list) list_backups ;;
    --restore)
        [ -n "${2:-}" ] || die "give the backup folder: --restore DIR"
        dir="$2"; shift 2
        only=""
        while [ $# -gt 0 ]; do
            case "$1" in
                --only) only="${2:-}"; shift 2 ;;
                --dry-run) RESTORE_DRY=1; shift ;;
                --yes) RESTORE_YES=1; shift ;;
                *) die "unknown option: $1" ;;
            esac
        done
        restore_backup "$dir" "$only"
        ;;
    -h|--help) usage ;;
    *) usage; exit 1 ;;
esac
