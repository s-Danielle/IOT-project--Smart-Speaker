#!/usr/bin/env bash
#
# Moves the code on the Pi to a branch or tag, installs what it needs, restarts
# the speaker's services and runs the quick check. Run it ON THE PI as the
# normal user (iot-proj). It asks for sudo itself for the system steps.
#
#   bash pi_update.sh pi/audio-stack         a branch
#   bash pi_update.sh v1.0                   a tag
#   bash pi_update.sh --dry-run pi/audio-stack    show what it would do, change nothing
#   bash pi_update.sh --undo                 go back to where the Pi was before the last update
#
# Order (so a failure can't leave the Pi half-updated):
#   1. look for unexpected local edits and stop if there are any
#   2. save a snapshot of the speaker's data (to compare afterwards)
#   3. install the Python packages the NEW code needs (nothing has changed yet)
#   4. switch the code
#   5. copy changed service files, reload systemd, restart the services
#   6. run the quick check and compare the data with the snapshot

set -euo pipefail

REPO="${REPO:-/home/iot-proj/IOT-project--Smart-Speaker}"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
STATE="$HOME/.smart_speaker_updates"
VENV_PIP="$REPO/venv/bin/pip"
SERVICES=(smart_speaker_server smart_speaker smart_speaker_health)

DRY=0
UNDO=0
REF=""
for arg in "$@"; do
    case "$arg" in
        --dry-run) DRY=1 ;;
        --undo) UNDO=1 ;;
        -h|--help) sed -n '2,19p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'; exit 0 ;;
        -*) echo "Unknown option: $arg"; exit 1 ;;
        *) REF="$arg" ;;
    esac
done

say() { printf '%s\n' "$*"; }
step() { printf '\n== %s ==\n' "$*"; }
die() { printf '\nSTOPPED: %s\n' "$*" >&2; exit 1; }
act() { if [ "$DRY" -eq 1 ]; then say "[preview] $*"; else say "$*"; fi; }
do_it() { if [ "$DRY" -eq 1 ]; then say "[preview]   \$ $*"; else say "  \$ $*"; "$@"; fi; }

[ "$(id -u)" -ne 0 ] || die "Run this as iot-proj, not with sudo. It asks for sudo itself when needed."
[ -d "$REPO/.git" ] || die "$REPO is not a git checkout."
cd "$REPO"
mkdir -p "$STATE"

install_units() {   # copy only the service files that differ, then reload systemd
    local changed=0 f name
    for f in "$REPO"/services/*.service; do
        [ -f "$f" ] || continue
        name="$(basename "$f")"
        if ! diff -q "$f" "/etc/systemd/system/$name" >/dev/null 2>&1; then
            act "service file changed: $name"
            do_it sudo cp "$f" "/etc/systemd/system/$name"
            do_it sudo chown root:root "/etc/systemd/system/$name"
            do_it sudo chmod 644 "/etc/systemd/system/$name"
            changed=1
        fi
    done
    [ "$changed" -eq 1 ] && do_it sudo systemctl daemon-reload
    return 0
}

restart_services() {
    local s
    for s in "${SERVICES[@]}"; do
        if systemctl cat "$s" >/dev/null 2>&1; then
            do_it sudo systemctl restart "$s"
        fi
    done
}

run_check() {
    local extra=("$@")
    step "Quick check"
    if [ "$DRY" -eq 1 ]; then
        say "[preview] python3 $HERE/pi_smoke_test.py --stable-seconds 30 ${extra[*]:-}"
        return 0
    fi
    sleep 5
    # ${extra[@]+"${extra[@]}"} expands to nothing (not an empty argument) when extra is empty
    if python3 "$HERE/pi_smoke_test.py" --stable-seconds 30 ${extra[@]+"${extra[@]}"}; then
        say "The quick check is green."
    else
        say ""
        say "The quick check found problems (see above)."
        say "To go back to the previous code:  bash $HERE/pi_update.sh --undo"
        return 1
    fi
}

# ---- undo ---------------------------------------------------------------------
if [ "$UNDO" -eq 1 ]; then
    [ -f "$STATE/previous_ref" ] || die "Nothing to undo: $STATE/previous_ref does not exist."
    PREV_COMMIT="$(sed -n 1p "$STATE/previous_ref")"
    PREV_BRANCH="$(sed -n 2p "$STATE/previous_ref")"
    step "Undo: back to $PREV_BRANCH ($PREV_COMMIT)"
    git status --porcelain | grep -v '^??' | grep -vE 'web_app/index.html|Unit-tests/\.venv' && die "There are unexpected local edits (listed above)." || true
    [ -d Unit-tests/.venv ] && do_it git checkout -- Unit-tests/.venv 2>/dev/null || true
    if [ "$PREV_BRANCH" != "HEAD" ]; then
        # Point the branch back at the old commit. Unlike "reset --hard" this keeps local edits
        # that are not part of the switch (such as the deployed web app's index.html).
        do_it git checkout -B "$PREV_BRANCH" "$PREV_COMMIT"
    else
        do_it git checkout --detach "$PREV_COMMIT"
    fi
    install_units
    restart_services
    run_check
    exit $?
fi

[ -n "$REF" ] || die "Say which branch or tag, e.g.:  bash pi_update.sh pi/audio-stack   (or --help)"

# ---- 1. look before changing anything ------------------------------------------------
step "1. What would change"
git fetch origin --tags --prune --quiet
if git show-ref --verify --quiet "refs/remotes/origin/$REF"; then
    KIND=branch; TARGET="origin/$REF"
elif git show-ref --verify --quiet "refs/tags/$REF"; then
    KIND=tag; TARGET="refs/tags/$REF"
elif git rev-parse --verify --quiet "$REF^{commit}" >/dev/null; then
    KIND=commit; TARGET="$REF"
else
    die "No branch, tag or commit called '$REF' on origin. (Has it been pushed?)"
fi
CURRENT="$(git rev-parse HEAD)"
CURRENT_BRANCH="$(git rev-parse --abbrev-ref HEAD)"
TARGET_COMMIT="$(git rev-parse "$TARGET^{commit}")"
say "Now:    $(git log -1 --format='%h %s' "$CURRENT") (on $CURRENT_BRANCH)"
say "Target: $(git log -1 --format='%h %s' "$TARGET_COMMIT") ($KIND $REF)"
if [ "$CURRENT" = "$TARGET_COMMIT" ]; then
    say "The Pi is already on that commit. Nothing to switch; I'll still restart and check."
fi
git diff --stat "$CURRENT" "$TARGET_COMMIT" | tail -n 5 || true

UNEXPECTED="$(git status --porcelain | grep -v '^??' | grep -vE 'Main/web_app/index\.html|Unit-tests/\.venv' || true)"
if [ -n "$UNEXPECTED" ]; then
    printf 'These tracked files have local edits that I did not expect:\n%s\n' "$UNEXPECTED"
    die "I won't switch the code over local edits. Save them (git diff > ~/my-edits.patch) or ask for help."
fi
if [ "$KIND" = "branch" ] && git show-ref --verify --quiet "refs/heads/$REF"; then
    AHEAD="$(git rev-list --count "origin/$REF..$REF")"
    [ "$AHEAD" -eq 0 ] || die "The local branch '$REF' has $AHEAD commit(s) that are not on origin. I won't overwrite them."
fi

# ---- 2. data snapshot -----------------------------------------------------------------------
step "2. Snapshot of the speaker's data"
if [ "$DRY" -eq 1 ]; then
    say "[preview] python3 $HERE/pi_smoke_test.py --only data --save-data $STATE/data-before.json"
else
    if python3 "$HERE/pi_smoke_test.py" --only data --save-data "$STATE/data-before.json"; then
        :
    else
        say "(The speaker's API did not answer, so there is no snapshot to compare with afterwards.)"
        rm -f "$STATE/data-before.json"
    fi
fi

# ---- 3. packages for the NEW code -------------------------------------------------------------
step "3. Python packages the new code needs"
TMPREQ="$(mktemp)"
trap 'rm -f "$TMPREQ"' EXIT
git show "$TARGET_COMMIT:requirements.txt" > "$TMPREQ"
[ -x "$VENV_PIP" ] || die "$VENV_PIP not found."
if [ "$DRY" -eq 1 ]; then
    say "[preview] $VENV_PIP install -r (requirements.txt from $REF)"
    "$VENV_PIP" install --dry-run -r "$TMPREQ" 2>&1 | tail -n 8 || true
else
    "$VENV_PIP" install -r "$TMPREQ" 2>&1 | tail -n 12
    [ "${PIPESTATUS[0]}" -eq 0 ] || die "pip failed. Nothing has been changed yet: the Pi still runs the old code."
fi

# ---- 4. switch the code --------------------------------------------------------------------------
step "4. Switching the code"
if [ "$DRY" -eq 0 ]; then
    printf '%s\n%s\n' "$CURRENT" "$CURRENT_BRANCH" > "$STATE/previous_ref"
    say "Saved where we are now, for --undo: $CURRENT ($CURRENT_BRANCH)"
fi
[ -d Unit-tests/.venv ] && do_it git checkout -- Unit-tests/.venv 2>/dev/null || true
case "$KIND" in
    branch) do_it git checkout -B "$REF" "origin/$REF" ;;
    *)      do_it git checkout --detach "$TARGET_COMMIT" ;;
esac

# ---- 5. services ------------------------------------------------------------------------------------
step "5. Service files and restart"
install_units
restart_services

# ---- 6. check ------------------------------------------------------------------------------------------
if [ -f "$STATE/data-before.json" ]; then
    run_check --compare-data "$STATE/data-before.json"
else
    run_check
fi
