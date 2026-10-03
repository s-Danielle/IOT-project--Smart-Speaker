#!/usr/bin/env python3
"""Guided test of the 6 buttons (the PCF8574 chip at I2C address 0x20). Run it ON THE PI.

    python3 test_buttons.py          # guided: it asks you to press each button
    python3 test_buttons.py --live   # just show the buttons as you press them

It checks three things:
  1. at rest, no button reads as pressed (a button that is stuck or held down
     would make the speaker act as if someone is pressing it)
  2. each button, when pressed, is seen on its own pin
  3. pressing one button does not also trigger another (wiring or solder bridge)

Reading the chip is safe even while the speaker's services run, but stopping
them first gives a cleaner test:
    sudo systemctl stop smart_speaker smart_speaker_health

The pin numbers below must match Main/config/settings.py (a test checks that).
"""

import argparse
import sys
import time

sys.path.insert(0, __import__("os").path.dirname(__import__("os").path.abspath(__file__)))

from pi_common import have, sh  # noqa: E402

ADDRESS = 0x20
# (name, bit) in the order the controller uses them; P0..P5, active low (0 = pressed).
BUTTONS = [
    ("Play/Pause", 0),
    ("Record", 1),
    ("Stop", 2),
    ("Volume up (Vol+)", 3),
    ("Volume down (Vol-)", 4),
    ("Push-to-talk (PTT)", 5),
]
MASK = 0x3F  # P6 and P7 are LED pins, not buttons


def make_reader():
    """Return a function that reads the chip, or exit with a helpful message."""
    try:
        from smbus2 import SMBus  # type: ignore

        bus = SMBus(1)

        def read():
            return bus.read_byte(ADDRESS)

        read()
        return read
    except ImportError:
        pass
    except Exception as exc:
        print("Could not read the buttons chip at 0x%02x with smbus2: %s" % (ADDRESS, exc))
        sys.exit(2)
    if have("i2cget"):

        def read():
            rc, out = sh(["i2cget", "-y", "1", "0x%02x" % ADDRESS])
            if rc != 0:
                raise OSError(out.strip())
            return int(out.strip(), 16)

        try:
            read()
            return read
        except OSError as exc:
            print("Could not read the buttons chip at 0x%02x: %s" % (ADDRESS, exc))
            print("Is I2C on, and is the chip's address strap set to 0x20? Try: i2cdetect -y 1")
            sys.exit(2)
    print("Neither the smbus2 Python package nor the i2cget tool is available.")
    print("Use the app's Python:  /home/iot-proj/IOT-project--Smart-Speaker/venv/bin/python test_buttons.py")
    sys.exit(2)


def pressed(value):
    return [name for name, bit in BUTTONS if not value & (1 << bit)]


def live(read):
    print("Press buttons. Ctrl-C to stop.\n")
    last = None
    try:
        while True:
            value = read()
            now = pressed(value)
            if now != last:
                print("raw=0x%02x  pressed: %s" % (value, ", ".join(now) or "(none)"))
                last = now
            time.sleep(0.03)
    except KeyboardInterrupt:
        print("\nStopped.")
    return 0


def wait_for(read, condition, timeout):
    """Poll until condition(value) is true for 0.15 s straight. Returns (ok, last_value)."""
    start = time.time()
    good_since = None
    value = read()
    while time.time() - start < timeout:
        value = read()
        if condition(value):
            good_since = good_since or time.time()
            if time.time() - good_since >= 0.15:
                return True, value
        else:
            good_since = None
        time.sleep(0.02)
    return False, value


def guided(read):
    results = []

    print("Step 1: nobody touch the buttons for a moment...")
    time.sleep(1.0)
    stuck = set()
    for _ in range(30):
        stuck.update(pressed(read()))
        time.sleep(0.03)
    if stuck:
        print("  FAIL: these read as PRESSED at rest: %s" % ", ".join(sorted(stuck)))
        print("        A held-down or stuck button. Check the switch and its wiring to ground.")
        results.append(("idle (nothing pressed)", "FAIL", "pressed at rest: %s" % ", ".join(sorted(stuck))))
    else:
        print("  PASS: all 6 buttons read released.")
        results.append(("idle (nothing pressed)", "PASS", ""))

    for name, bit in BUTTONS:
        print("\nStep: press and HOLD  %s  (you have 15 seconds)..." % name)
        ok, value = wait_for(read, lambda v, b=bit: not v & (1 << b), 15)
        if not ok:
            print("  FAIL: never saw %s pressed." % name)
            results.append((name, "FAIL", "no press seen on P%d" % bit))
            continue
        others = [n for n in pressed(value) if n != name]
        print("  seen on P%d (raw=0x%02x)." % (bit, value))
        status, detail = "PASS", ""
        if others:
            status, detail = "FAIL", "also read as pressed: %s" % ", ".join(others)
            print("  FAIL: pressing it also reads as: %s (wires touching?)" % ", ".join(others))
        print("  Now let go.")
        released, _ = wait_for(read, lambda v: (v & MASK) == MASK, 10)
        if not released:
            status, detail = "FAIL", (detail + "; " if detail else "") + "did not read released afterwards"
            print("  FAIL: it still reads as pressed after you let go.")
        elif status == "PASS":
            print("  PASS")
        results.append((name, status, detail))

    print("\n" + "=" * 52)
    width = max(len(r[0]) for r in results)
    for name, status, detail in results:
        print("%s  %s  %s" % (name.ljust(width), status, detail))
    failed = [r for r in results if r[1] == "FAIL"]
    print("\n%s" % ("All buttons OK." if not failed else "%d problem(s). Tell me the lines above." % len(failed)))
    return 1 if failed else 0


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--live", action="store_true", help="only show button presses as they happen")
    args = parser.parse_args()
    read = make_reader()
    try:
        return live(read) if args.live else guided(read)
    except KeyboardInterrupt:
        print("\nStopped.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
