#!/usr/bin/env bash
#
# Collects facts about the Smart Speaker Pi. It ONLY READS: nothing is changed,
# nothing is installed, and nothing is played. Secrets are hidden, and
# credential files are only looked at with `stat` (size, age, owner), never read.
#
#   sudo bash /tmp/pi/pi_report.sh > /tmp/report.txt
#
# Use sudo so it can read root-only files and the Mopidy log. Without sudo it
# still works and just notes what it could not read.
#
# Settings you can override: REPO, APP_USER, DAYS (days of Mopidy log to scan).

set -u

REPO="${REPO:-/home/iot-proj/IOT-project--Smart-Speaker}"
APP_USER="${APP_USER:-iot-proj}"
DAYS="${DAYS:-14}"
VENV_PY="$REPO/venv/bin/python"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [ "${1:-}" = "--help" ] || [ "${1:-}" = "-h" ]; then
    sed -n '2,13p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'
    exit 0
fi

IS_ROOT=0
[ "$(id -u)" -eq 0 ] && IS_ROOT=1

# Run things as the mopidy user when we can (that is who really uses GStreamer).
MOPIDY_AS=()
if [ "$IS_ROOT" -eq 1 ] && command -v runuser >/dev/null 2>&1 && id mopidy >/dev/null 2>&1; then
    MOPIDY_AS=(runuser -u mopidy --)
fi

# ---- helpers ----------------------------------------------------------

# Hide secret-looking values and long token-like strings.
mask() {
    sed -E \
        -e 's/((password|passwd|secret|token|api[_-]?key|auth[_-]?data|refresh[_-]?token|access[_-]?token)[A-Za-z_]*[[:space:]]*[=:][[:space:]]*).*/\1********/I' \
        -e 's/[A-Za-z0-9_+\/=-]{40,}/<masked>/g'
}
export -f mask

hr() { printf '\n=== %s ===\n' "$1"; }
kv() { printf '%-30s %s\n' "$1" "$2"; }
note() { printf '(%s)\n' "$1"; }

# Run a command, show it and its output (limited), never fail the script.
run() {
    printf '$ %s\n' "$*"
    timeout 30 "$@" 2>&1 | head -n "${MAXLINES:-120}"
    echo
}
runsh() {
    printf '$ %s\n' "$1"
    timeout 60 bash -c "$1" 2>&1 | head -n "${MAXLINES:-120}"
    echo
}

SUMMARY=()
summ() { SUMMARY+=("$(printf '%-34s %s' "$1" "$2")"); }

OUT="$(mktemp)"
exec 3>&1
exec >"$OUT"

echo "Smart Speaker Pi report, made $(date '+%Y-%m-%d %H:%M:%S %Z') by pi_report.sh"
echo "Bundle commit: $(cat "$HERE/BUNDLE_COMMIT" 2>/dev/null || echo unknown). Running as: $(id -un) (root: $IS_ROOT)"
[ "$IS_ROOT" -eq 0 ] && note "Not running as root: root-only files and the Mopidy log may be skipped. Re-run with sudo."

# ---- 1. The Pi ----------------------------------------------------------
hr "THE PI"
MODEL="$(tr -d '\0' </proc/device-tree/model 2>/dev/null || echo unknown)"
ARCH="$(uname -m)"
OSNAME="$(grep PRETTY_NAME /etc/os-release 2>/dev/null | cut -d= -f2- | tr -d '"')"
kv "Model" "$MODEL"
kv "Machine / CPU architecture" "$ARCH (dpkg: $(dpkg --print-architecture 2>/dev/null))"
kv "OS" "$OSNAME"
kv "Kernel" "$(uname -r)"
kv "Hostname" "$(hostname)"
kv "Uptime" "$(uptime -p 2>/dev/null)"
run free -m
run df -h /
if command -v vcgencmd >/dev/null 2>&1; then
    run vcgencmd measure_temp
    THROTTLED="$(vcgencmd get_throttled 2>/dev/null)"
    kv "Under-voltage flags" "$THROTTLED   (0x0 is good)"
    summ "Power / throttling" "$THROTTLED (0x0 = good)"
fi
runsh "lscpu | head -20"
summ "Pi model" "$MODEL"
summ "OS / architecture" "$OSNAME, $ARCH"

# ---- 2. Network and time ------------------------------------------------
hr "NETWORK AND TIME"
run ip -br addr
runsh "iwgetid -r 2>/dev/null || nmcli -t -f ACTIVE,SSID dev wifi 2>/dev/null | grep '^yes' || echo 'no WiFi name found'"
run timedatectl
NTP="$(timedatectl show -p NTPSynchronized --value 2>/dev/null)"
TZ_NAME="$(timedatectl show -p Timezone --value 2>/dev/null)"
summ "Clock synced / time zone" "synced=$NTP, zone=$TZ_NAME"

# ---- 3. The code on the Pi ----------------------------------------------
hr "THE CODE ON THE PI"
if [ -d "$REPO/.git" ]; then
    # As root, run git as the repo's owner so git does not refuse with "dubious ownership".
    G=(git -C "$REPO")
    if [ "$IS_ROOT" -eq 1 ] && command -v runuser >/dev/null 2>&1; then
        G=(runuser -u "$APP_USER" -- git -C "$REPO")
    fi
    run "${G[@]}" log -1 --format='%h %ad %s' --date=short
    run "${G[@]}" status -sb
    run "${G[@]}" remote -v
    DIRTY="$("${G[@]}" status --porcelain 2>/dev/null | grep -vc '^??')"
    kv "Tracked files with local changes" "$DIRTY"
    echo "Locally changed tracked files (first 30):"
    "${G[@]}" status --porcelain 2>/dev/null | grep -v '^??' | head -30
    echo
    summ "Code on the Pi" "$("${G[@]}" log -1 --format='%h' 2>/dev/null) on $("${G[@]}" rev-parse --abbrev-ref HEAD 2>/dev/null), $DIRTY locally changed files"
else
    note "$REPO is not a git checkout"
    summ "Code on the Pi" "NOT FOUND at $REPO"
fi

# ---- 4. Services ----------------------------------------------------------
hr "SERVICES"
for unit in smart_speaker smart_speaker_server smart_speaker_health smart_speaker_wifi mopidy NetworkManager avahi-daemon seeed-voicecard systemd-timesyncd; do
    if systemctl cat "$unit" >/dev/null 2>&1; then
        active="$(systemctl is-active "$unit" 2>/dev/null)"
        enabled="$(systemctl is-enabled "$unit" 2>/dev/null)"
        restarts="$(systemctl show -p NRestarts --value "$unit" 2>/dev/null)"
        user="$(systemctl show -p User --value "$unit" 2>/dev/null)"
        since="$(systemctl show -p ActiveEnterTimestamp --value "$unit" 2>/dev/null)"
        kv "$unit" "$active, $enabled, restarts=$restarts, user=${user:-root}, since $since"
        case "$unit" in smart_speaker*|mopidy) summ "Service $unit" "$active, restarts=$restarts" ;; esac
    else
        kv "$unit" "(not installed)"
    fi
done
echo
echo "Installed unit files compared with the repo's copies (no output = identical):"
for f in "$REPO"/services/*.service; do
    [ -f "$f" ] || continue
    name="$(basename "$f")"
    if [ -f "/etc/systemd/system/$name" ]; then
        diff -q "/etc/systemd/system/$name" "$f" >/dev/null 2>&1 || echo "  DIFFERENT: $name"
    else
        echo "  NOT INSTALLED: $name"
    fi
done
for u in "$HERE"/units/*.service; do
    [ -f "$u" ] || continue
    name="$(basename "$u")"
    [ -f "/etc/systemd/system/$name" ] && { diff -q "/etc/systemd/system/$name" "$u" >/dev/null 2>&1 || echo "  DIFFERENT from the new version: $name"; }
done

# ---- 5. Python ---------------------------------------------------------------
hr "PYTHON"
kv "System python3" "$(python3 --version 2>&1)"
if [ -x "$VENV_PY" ]; then
    kv "App venv python" "$("$VENV_PY" --version 2>&1)"
    for mod in alsaaudio smbus2 mpd board busio adafruit_pn532 speech_recognition; do
        if "$VENV_PY" -c "import $mod" >/dev/null 2>&1; then
            kv "venv imports $mod" "yes"
        else
            kv "venv imports $mod" "NO"
            [ "$mod" = "alsaaudio" ] && summ "venv can import alsaaudio" "NO (the new code needs it)"
        fi
    done
    "$VENV_PY" -c "import alsaaudio" >/dev/null 2>&1 && summ "venv can import alsaaudio" "yes"
else
    note "no venv at $VENV_PY"
    summ "App venv" "NOT FOUND at $VENV_PY"
fi
if python3 -c "import smbus2" >/dev/null 2>&1; then
    kv "system python3 imports smbus2" "yes (the health service needs this)"
else
    kv "system python3 imports smbus2" "NO (the health service runs on system Python)"
    summ "system python3 has smbus2" "NO (health service would crash)"
fi

# ---- 6. Audio -----------------------------------------------------------------
hr "AUDIO"
APLAY="$(aplay -l 2>&1)"
echo '$ aplay -l'; echo "$APLAY"; echo
run arecord -l
run cat /proc/asound/cards
CARD="$(echo "$APLAY" | sed -n 's/^card \([0-9]*\): seeed2micvoicec.*/\1/p' | head -1)"
[ -z "$CARD" ] && CARD="$(echo "$APLAY" | sed -n 's/^card \([0-9]*\):.*/\1/p' | head -1)"
[ -z "$CARD" ] && CARD=0
kv "Sound card used below" "$CARD"
summ "Sound card" "$(echo "$APLAY" | sed -n 's/^card \([0-9]*: [^,]*\),.*/\1/p' | head -1)"
run amixer -c "$CARD" scontrols
if amixer -c "$CARD" sget PCM >/dev/null 2>&1; then
    run amixer -c "$CARD" sget PCM
    summ "Volume control 'PCM' on card $CARD" "present"
else
    echo "(no control named PCM on card $CARD)"
    summ "Volume control 'PCM' on card $CARD" "MISSING (volume buttons would do nothing)"
fi
echo "/etc/asound.conf:"
if [ -L /etc/asound.conf ]; then
    kv "  type" "SYMLINK -> $(readlink -f /etc/asound.conf)"
    summ "/etc/asound.conf" "symlink -> $(readlink -f /etc/asound.conf)"
elif [ -f /etc/asound.conf ]; then
    kv "  type" "regular file, $(stat -c '%s bytes, modified %y' /etc/asound.conf | cut -c1-40)"
    summ "/etc/asound.conf" "regular file"
else
    kv "  type" "absent"
    summ "/etc/asound.conf" "absent"
fi
runsh "head -60 /etc/asound.conf 2>/dev/null"
for f in "/home/$APP_USER/.asoundrc" /var/lib/mopidy/.asoundrc /root/.asoundrc; do
    [ -e "$f" ] && echo "FOUND personal ALSA config: $f (it overrides /etc/asound.conf for that user)"
done
echo "HAT driver service:"
for f in /usr/bin/seeed-voicecard /usr/local/bin/seeed-voicecard /etc/systemd/system/seeed-voicecard.service /lib/systemd/system/seeed-voicecard.service; do
    if [ -f "$f" ]; then
        echo "  found $f"
        grep -n 'asound' "$f" 2>/dev/null | sed 's/^/    /' | head -10
    fi
done
if grep -qs 'asound.conf' /usr/bin/seeed-voicecard /usr/local/bin/seeed-voicecard /etc/systemd/system/seeed-voicecard.service /lib/systemd/system/seeed-voicecard.service 2>/dev/null; then
    summ "HAT boot script touches asound.conf" "YES (our file could be overwritten at boot)"
else
    summ "HAT boot script touches asound.conf" "no"
fi
runsh "pgrep -a 'pulseaudio|pipewire|wireplumber' || echo 'no PulseAudio/PipeWire running'"
if [ "$IS_ROOT" -eq 1 ] && command -v fuser >/dev/null 2>&1; then
    runsh "fuser -v /dev/snd/* 2>&1 | head -20"
fi

# ---- 7. Users, groups, folders -------------------------------------------------
hr "USERS, GROUPS AND FOLDERS"
run id "$APP_USER"
run id mopidy
runsh "getent group audio"
summ "audio group members" "$(getent group audio | cut -d: -f4)"
if [ "$IS_ROOT" -eq 1 ]; then
    runsh "sudo -l -U '$APP_USER' 2>&1 | head -30"
    runsh "ls -la /etc/sudoers.d/"
    for f in /etc/sudoers.d/*smart* /etc/sudoers.d/*speaker* /etc/sudoers.d/*iot*; do
        [ -f "$f" ] && { echo "--- $f"; cat "$f"; }
    done
else
    note "sudo rules skipped (needs root)"
fi
echo "Owner, group and mode of the folders and files that matter:"
for p in "/home/$APP_USER" "$REPO" "$REPO/Main" "$REPO/Main/local_files" "$REPO/Main/local_files/recordings" \
         "$REPO/Main/local_files/uploads" "$REPO/Main/server_data.json" "$REPO/Main/server_data.db" \
         /var/log/smart_speaker /var/log/smart_speaker_server.log "/home/$APP_USER/music"; do
    [ -e "$p" ] && stat -c '  %U:%G  %a  %n' "$p" || echo "  (missing)  $p"
done
if [ "$IS_ROOT" -eq 1 ] && id mopidy >/dev/null 2>&1; then
    echo "Can the mopidy user reach the recordings and uploads folders?"
    for p in "/home/$APP_USER" "$REPO/Main/local_files/recordings" "$REPO/Main/local_files/uploads"; do
        if [ -e "$p" ]; then
            if runuser -u mopidy -- test -r "$p" && runuser -u mopidy -- test -x "$p"; then
                echo "  yes  $p"
            else
                echo "  NO   $p"
                summ "mopidy can read $(basename "$p")" "NO"
            fi
        fi
    done
fi

# ---- 8. Mopidy ----------------------------------------------------------------------
hr "MOPIDY"
run "${MOPIDY_AS[@]}" mopidy --version
runsh "systemctl cat mopidy 2>/dev/null | head -30"
runsh "ss -ltnp 2>/dev/null | grep -E ':(6600|6680|8080|80)\\b'"
echo "Live /etc/mopidy/mopidy.conf (the [spotify] section shows setting NAMES only; anything secret-looking is hidden):"
if [ -r /etc/mopidy/mopidy.conf ]; then
    awk '
        /^\[/ { section = tolower($0); print; next }
        section == "[spotify]" { if ($0 ~ /^[[:space:]]*[A-Za-z_]+[[:space:]]*[=:]/) { sub(/[=:].*/, "= <hidden>"); print } ; next }
        { print }
    ' /etc/mopidy/mopidy.conf | mask
    summ "mopidy.conf [audio] mixer" "$(awk '/^\[audio\]/{s=1;next} /^\[/{s=0} s && /^mixer/{print $0}' /etc/mopidy/mopidy.conf | head -1)"
else
    note "/etc/mopidy/mopidy.conf is not readable by this user (run with sudo)"
fi
echo
run "${MOPIDY_AS[@]}" mopidy deps

# ---- 9. Spotify ---------------------------------------------------------------------
hr "SPOTIFY"
SPV="$(python3 -m pip show mopidy-spotify 2>/dev/null | sed -n 's/^Version: //p')"
kv "Mopidy-Spotify (system pip)" "${SPV:-not found}"
GST="not found"
if command -v gst-inspect-1.0 >/dev/null 2>&1; then
    GSTOUT="$(timeout 90 "${MOPIDY_AS[@]}" gst-inspect-1.0 spotifyaudiosrc 2>&1)"
    if echo "$GSTOUT" | grep -qi 'Factory Details'; then
        GST="found, $(echo "$GSTOUT" | sed -n 's/^ *Version *//p' | head -1)"
    fi
fi
kv "Spotify GStreamer plugin" "$GST"
runsh "dpkg -l 2>/dev/null | grep -i gst-plugin-spotify"
summ "Mopidy-Spotify version" "${SPV:-not found}"
summ "Spotify GStreamer plugin" "$GST"
echo "Credentials files (size, date and owner only; the contents are never read):"
FOUND_CREDS=0
for base in /var/lib/mopidy "/home/$APP_USER"; do
    while IFS= read -r line; do
        [ -n "$line" ] && { echo "  $line"; FOUND_CREDS=1; }
    done < <(find "$base" -maxdepth 8 -name credentials.json -printf '%p  %s bytes  modified %TY-%Tm-%Td  owner %u:%g  mode %m\n' 2>/dev/null)
done
[ "$FOUND_CREDS" -eq 0 ] && echo "  none found (or not readable by this user)"
summ "Spotify credentials.json" "$([ "$FOUND_CREDS" -eq 1 ] && echo present || echo 'none found')"
echo
# The Pi has no clock battery. Early in a boot its clock can be weeks off, and the log lines get
# those wrong times. So look at "this boot" and "the boot before" as well as the last N days.
mopidy_log_scan() {   # mopidy_log_scan "label" <journalctl time options>
    local label="$1"; shift
    local log
    log="$(journalctl -u mopidy "$@" --no-pager -o short-iso 2>&1)"
    echo "Mopidy log, $label: how often each known problem appears"
    if echo "$log" | grep -qE 'not seeing messages from other users|insufficient permissions'; then
        note "journal not readable (run with sudo)"; echo; return
    fi
    if echo "$log" | grep -qiE 'data from the specified boot|no such boot'; then
        echo "  (that boot is not in the journal)"; echo; return
    fi
    if [ "$(echo "$log" | grep -vc -- '-- No entries --')" -le 0 ]; then
        echo "  (no entries)"; echo; return
    fi
    for pat in 'login5' 'INVALID_CREDENTIALS' ' 401' ' 403' ' 429' 'spotifyaudiosrc' 'xrun' 'underrun' 'Traceback' 'Resource not found'; do
        printf '  %-22s %s\n' "$pat" "$(echo "$log" | grep -c -- "$pat")"
    done
    echo "  Last 20 matching lines (secrets masked):"
    echo "$log" | grep -E 'login5|INVALID_CREDENTIALS| 401| 403| 429|spotifyaudiosrc|xrun|underrun|Traceback|Resource not found|ERROR|CRITICAL' | tail -n 20 | mask | sed 's/^/    /'
    echo "  First 12 lines of that log (start-up messages, masked):"
    echo "$log" | head -n 12 | mask | sed 's/^/    /'
    summ "Mopidy log ($label): login5 lines" "$(echo "$log" | grep -c 'login5')"
    echo
}
mopidy_log_scan "this boot" -b
mopidy_log_scan "the boot before" -b -1
mopidy_log_scan "last $DAYS days" --since "$DAYS days ago"

# ---- 10. The speaker's own API and data -------------------------------------------------
hr "SPEAKER API AND DATA"
# Only /status is called. The data endpoints are left alone: the first data request after a
# server start can trigger the server's one-time chip seeding, and this report must not change anything.
if command -v curl >/dev/null 2>&1; then
    runsh "curl -s -m 5 http://localhost:8080/status"
fi
for f in "$REPO"/Main/server_data.json* "$REPO"/Main/server_data.db*; do
    [ -f "$f" ] && stat -c '  %n  %s bytes  modified %y' "$f" | cut -c1-120
done
if [ -f "$REPO/Main/server_data.json" ]; then
    python3 - "$REPO/Main/server_data.json" <<'PY' 2>&1
import json, sys
try:
    data = json.load(open(sys.argv[1]))
    chips, library = data.get("chips", []), data.get("library", [])
    print("  server_data.json is valid JSON: %d chips, %d songs" % (len(chips), len(library)))
    kinds = {}
    for song in library:
        kind = (song.get("uri") or "").split(":")[0] + ":" + ((song.get("uri") or "").split(":")[1] if (song.get("uri") or "").startswith("spotify:") else "")
        kinds[kind] = kinds.get(kind, 0) + 1
    print("  kinds of song links: %s" % (", ".join("%s x%d" % kv for kv in sorted(kinds.items())) or "none"))
    print("  parental settings: %s" % ("set" if data.get("parental_controls") else "empty (defaults)"))
    print("  daily usage record: %s" % (data.get("daily_usage") or "none"))
except Exception as exc:
    print("  server_data.json is NOT valid JSON: %s" % exc)
PY
fi

# ---- 11. I2C and boot config ---------------------------------------------------------------
hr "I2C AND BOOT CONFIG"
runsh "ls -l /dev/i2c-* 2>&1"
runsh "lsmod | grep -E 'i2c|snd' | head -20"
BOOTCFG=/boot/firmware/config.txt
[ -f "$BOOTCFG" ] || BOOTCFG=/boot/config.txt
echo "$BOOTCFG (active lines only):"
grep -vE '^[[:space:]]*(#|$)' "$BOOTCFG" 2>/dev/null | head -40
note "i2cdetect is deliberately not run here, because the speaker's services poll the bus. See Step 4."

# ---- 12. Logs --------------------------------------------------------------------------------
hr "SMART SPEAKER LOGS (last lines, secrets masked)"
for f in /var/log/smart_speaker/controller.log /var/log/smart_speaker_server.log /var/log/smart_speaker_health.log /var/log/smart_speaker_wifi.log; do
    if [ -r "$f" ]; then
        echo "--- $f ($(stat -c '%s bytes' "$f")), tracebacks in last 500 lines: $(tail -n 500 "$f" | grep -c Traceback)"
        tail -n 15 "$f" | mask
    elif [ -e "$f" ]; then
        echo "--- $f exists but is not readable by this user"
    fi
done
runsh "journalctl -u smart_speaker --no-pager -n 25 2>&1 | tail -n 25"
runsh "journalctl --disk-usage 2>&1"

# ---- print the summary first, then everything ------------------------------------------------------
exec 1>&3
echo "############################################################"
echo "# QUICK SUMMARY (details follow)"
echo "############################################################"
for line in "${SUMMARY[@]}"; do echo "$line"; done
echo
cat "$OUT"
rm -f "$OUT"
