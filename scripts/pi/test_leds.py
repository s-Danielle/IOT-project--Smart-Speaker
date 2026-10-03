#!/usr/bin/env python3
"""Guided test of the status LEDs. Run it ON THE PI.

    sudo systemctl stop smart_speaker smart_speaker_health
    python3 test_leds.py

It lights each light in each colour and asks you what you see. The answers show
which physical LED is which, and whether the colour order is the one the code
assumes (blue, green, red on pins 0, 1, 2 of each light).

The speaker has 3 lights in the code:
  Light 1 (Health)  pins P0-P2 of the chip at 0x21
  Light 2 (PTT)     pins P3-P5 of the chip at 0x21
  Light 3 (Speaker) ONE LED split over two chips: blue = 0x21 P6, green = 0x21 P7,
                    red = 0x20 P6 (the buttons chip, whose P0-P5 must stay high)

The pins must match Main/hardware/leds.py (a test checks that).
Everything is switched off again when this ends, even if you press Ctrl-C.
"""

import argparse
import json
import sys

sys.path.insert(0, __import__("os").path.dirname(__import__("os").path.abspath(__file__)))

from pi_common import have, sh  # noqa: E402

LED_ADDRESS = 0x21
BUTTON_ADDRESS = 0x20
BUTTONS_RELEASED = 0x3F  # P0-P5 of 0x20 stay high so no button looks pressed

# (light number, code name, B pin, G pin, R pin); pin is (chip, bit)
LIGHTS = [
    (1, "Health", (0x21, 0), (0x21, 1), (0x21, 2)),
    (2, "PTT", (0x21, 3), (0x21, 4), (0x21, 5)),
    (3, "Speaker (split LED)", (0x21, 6), (0x21, 7), (0x20, 6)),
]
COLOURS = [
    ("blue", (1, 0, 0)),
    ("green", (0, 1, 0)),
    ("red", (0, 0, 1)),
    ("yellow (green + red)", (0, 1, 1)),
    ("white (all three)", (1, 1, 1)),
]


class Chips:
    """Writes the two chips, keeping the button pins safe."""

    def __init__(self):
        self.bus = None
        try:
            from smbus2 import SMBus  # type: ignore

            self.bus = SMBus(1)
        except ImportError:
            if not have("i2cset"):
                print("Neither the smbus2 package nor the i2cset tool is available.")
                print("Use the app's Python:  /home/iot-proj/IOT-project--Smart-Speaker/venv/bin/python test_leds.py")
                sys.exit(2)
        self.led = 0x00
        self.buttons = BUTTONS_RELEASED

    def _write(self, address, value):
        if self.bus is not None:
            self.bus.write_byte(address, value)
        else:
            rc, out = sh(["i2cset", "-y", "1", "0x%02x" % address, "0x%02x" % value])
            if rc != 0:
                raise OSError(out.strip())

    def show(self, light, colour):
        """Show `colour` (b, g, r) on `light`, everything else off."""
        self.led = 0x00
        self.buttons = BUTTONS_RELEASED
        if light is not None:
            _, _, blue, green, red = light
            for on, (chip, bit) in zip(colour, (blue, green, red)):
                if on:
                    if chip == LED_ADDRESS:
                        self.led |= 1 << bit
                    else:
                        self.buttons |= 1 << bit
        self._write(LED_ADDRESS, self.led)
        self._write(BUTTON_ADDRESS, self.buttons)

    def off(self):
        self.show(None, (0, 0, 0))

    def close(self):
        try:
            self.off()
        finally:
            if self.bus is not None:
                self.bus.close()


def ask(prompt, allowed=None):
    while True:
        answer = input(prompt).strip().lower()
        if allowed is None or answer in allowed:
            return answer
        print("  please answer one of: %s" % "/".join(allowed))


def services_running():
    running = []
    for unit in ("smart_speaker", "smart_speaker_health", "smart_speaker_wifi"):
        rc, out = sh(["systemctl", "is-active", unit])
        if out.strip() == "active":
            running.append(unit)
    return running


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--force", action="store_true", help="run even though the speaker's services are running")
    parser.add_argument("--json", metavar="PATH", help="also save the answers as JSON")
    args = parser.parse_args()

    running = services_running()
    if running and not args.force:
        print("These services are running and would fight over the LEDs: %s" % ", ".join(running))
        print("Stop them first:  sudo systemctl stop smart_speaker smart_speaker_health")
        print("(They start again after a reboot, or with: sudo systemctl start smart_speaker smart_speaker_health)")
        return 2

    chips = Chips()
    results = []
    try:
        chips.off()
        print("All LEDs are off now. Look at the three lights while I drive them one at a time.")
        print("Answer y (yes), n (no) or s (skip this light).\n")
        for light in LIGHTS:
            number, name = light[0], light[1]
            print("-" * 60)
            print("Light %d (the code calls it '%s')" % (number, name))
            chips.show(light, COLOURS[0][1])
            which = input("  I'm driving it BLUE now. Which LED lit up? Type its label "
                          "(e.g. Health, PTT, Speaker, or 'none'): ").strip()
            entry = {"light": number, "code_name": name, "physical_led": which, "colours": {}}
            if which.lower() in ("none", "no", "n", ""):
                print("  OK, nothing lit: that LED may not be installed or wired.")
                entry["installed"] = False
                results.append(entry)
                continue
            entry["installed"] = True
            skip = False
            for colour_name, rgb in COLOURS:
                chips.show(light, rgb)
                answer = ask("  Is it showing %s? [y/n/s] " % colour_name.upper(), ("y", "n", "s"))
                if answer == "s":
                    skip = True
                    break
                entry["colours"][colour_name] = answer == "y"
                if answer == "n":
                    seen = input("    What colour do you see instead? ").strip()
                    entry["colours"][colour_name] = "no, saw: %s" % seen
            chips.off()
            results.append(entry)
            if skip:
                print("  skipped the rest of this light.")
    except KeyboardInterrupt:
        print("\nStopped.")
    finally:
        chips.close()
        print("\nAll LEDs are off again.")

    print("\n" + "=" * 60)
    print("Summary")
    for entry in results:
        if not entry.get("installed"):
            print("  Light %d (%s): nothing lit" % (entry["light"], entry["code_name"]))
            continue
        wrong = [c for c, v in entry["colours"].items() if v is not True]
        print("  Light %d (%s): physical LED '%s', %s" % (
            entry["light"], entry["code_name"], entry["physical_led"],
            "all colours as expected" if not wrong else "DIFFERENT: " + ", ".join(
                "%s -> %s" % (c, entry["colours"][c]) for c in wrong)))
    if args.json:
        with open(args.json, "w") as handle:
            json.dump(results, handle, indent=2)
        print("Saved %s" % args.json)
    print("\nTell me these lines, especially any 'DIFFERENT' or 'nothing lit'.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
