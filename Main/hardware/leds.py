"""
RGB LED control via PCF8574 I2C expanders

Light 1 (P0-P2 on 0x21): Health LED - controlled by health_monitor.py (and the WiFi setup service)
Light 2 (P3-P5 on 0x21): PTT LED - controlled by controller.py
Light 3 (Divided LED):   Speaker LED - controlled by ui/lights.py
    - P6 on 0x21 = Blue
    - P7 on 0x21 = Green
    - P6 on 0x20 = Red

Several programs drive these LEDs at once, and all of Light 1, 2 and half of Light 3 sit on
the same chip, so every write sends the whole byte. If each program kept its own copy of the
pin states, every write would put the other lights back to whatever they were when that
program started (the health monitor wiped the other lights every few seconds). So the one
true state lives in a small shared file, and every change does: lock it, read it, change only
this light's pins, save it, write the chips, unlock.
"""

import json
import os
import time

from smbus2 import SMBus
from utils.logger import log

try:
    import fcntl
except ImportError:  # not Linux: fall back to a private copy per program
    fcntl = None

# I2C Configuration
I2C_BUS = 1
LED_EXPANDER_ADDRESS = 0x21    # Main LED expander
BUTTON_EXPANDER_ADDRESS = 0x20  # Button expander (has divided LED red pin)

# Pin mappings - all LEDs are B, G, R order (active-high: set bit = LED ON)
LIGHT1_PINS = (0, 1, 2)  # P0=B, P1=G, P2=R (Health LED)
LIGHT2_PINS = (3, 4, 5)  # P3=B, P4=G, P5=R (PTT LED)
# Light 3 is divided: P6=B, P7=G on 0x21, P6=R on 0x20

# On 0x20, P0-P5 are the buttons (inputs). They must always be written high, or a pin is held
# low and reads as "pressed". Only P6 (Light 3's red) is ours.
BUTTONS_RELEASED = 0x3F
RED3_PIN = 6

STATE_PATH_ENV = "SPEAKER_LED_STATE"
DEFAULT_STATE_PATH = "/tmp/smart_speaker_leds.json"
ERROR_LOG_INTERVAL = 5.0  # seconds between repeated "write error" log lines


class Colors:
    """RGB color tuples (B, G, R) as booleans - matches pin order"""
    OFF =    (False, False, False)
    BLUE =   (True,  False, False)
    GREEN =  (False, True,  False)
    RED =    (False, False, True)
    YELLOW = (False, True,  True)   # Green + Red = Yellow


def _with_bit(value: int, bit: int, on: bool) -> int:
    return (value | (1 << bit)) if on else (value & ~(1 << bit))


class RGBLeds:
    """
    Control 3 RGB LEDs via PCF8574 I2C expanders.

    Light 1 (Health): P0-P2 on 0x21
    Light 2 (PTT):    P3-P5 on 0x21
    Light 3 (Speaker): P6-P7 on 0x21 + P6 on 0x20 (divided LED)

    Any number of programs can each make their own RGBLeds: they share one state.
    """

    def __init__(self):
        """Initialize LED controller"""
        self._bus = None
        self._enabled = False
        self._private_state = (0x00, 0)  # only used if the shared file cannot be used
        self._warned_about_file = False
        self._last_error_log = 0.0

        try:
            self._bus = SMBus(I2C_BUS)
            self._enabled = True
            # Create the shared state if we are the first program since boot (that switches
            # every LED off: the chips power up with all pins high, i.e. all LEDs on).
            led, red3 = self._update(lambda led, red3: (led, red3))
            log(f"[LEDS] Initialized: 0x21=0x{led:02X}, light 3 red={red3}")
        except Exception as e:
            log(f"[LEDS] Failed to initialize: {e} - LEDs disabled")
            self._enabled = False

    # -- shared state ---------------------------------------------------------

    def _open_state(self):
        """Open the shared state file. Returns None if it cannot be used."""
        if fcntl is None:
            return None
        path = os.environ.get(STATE_PATH_ENV, DEFAULT_STATE_PATH)
        try:
            try:
                return os.open(path, os.O_RDWR)
            except FileNotFoundError:
                try:
                    fd = os.open(path, os.O_RDWR | os.O_CREAT | os.O_EXCL, 0o666)
                except FileExistsError:  # another program made it a moment ago
                    return os.open(path, os.O_RDWR)
                try:
                    os.fchmod(fd, 0o666)  # the other programs may run as other users
                except OSError:
                    pass
                return fd
        except OSError as e:
            if not self._warned_about_file:
                self._warned_about_file = True
                log(f"[LEDS] Cannot use the shared LED state file {path}: {e} - keeping a private copy")
            return None

    @staticmethod
    def _read_state(fd):
        """(led_byte, red3) from the file, or None if it is empty or damaged (first start since boot)."""
        try:
            os.lseek(fd, 0, os.SEEK_SET)
            data = json.loads(os.read(fd, 200).decode("utf-8"))
            return int(data["led"]) & 0xFF, 1 if data["red3"] else 0
        except (ValueError, KeyError, TypeError, OSError):
            return None

    @staticmethod
    def _save_state(fd, led, red3):
        payload = json.dumps({"led": led, "red3": red3}).encode("utf-8")
        os.lseek(fd, 0, os.SEEK_SET)
        os.ftruncate(fd, 0)
        os.write(fd, payload)

    def _write_chips(self, led, red3, write_buttons):
        """Send the state to the chips. Errors are logged (rarely) and never raised."""
        try:
            self._bus.write_byte(LED_EXPANDER_ADDRESS, led)
            if write_buttons:
                self._bus.write_byte(BUTTON_EXPANDER_ADDRESS, BUTTONS_RELEASED | (red3 << RED3_PIN))
        except Exception as e:
            now = time.monotonic()
            if now - self._last_error_log >= ERROR_LOG_INTERVAL:
                self._last_error_log = now
                log(f"[LEDS] Write error: {e}")

    def _update(self, change, touches_buttons=False):
        """Apply change(led_byte, red3) -> (led_byte, red3) to the shared state and write the chips.

        Returns the new (led_byte, red3). The file lock also keeps the programs (and threads)
        from writing to the chips at the same moment.
        """
        fd = self._open_state()
        if fd is None:
            led, red3 = change(*self._private_state)
            self._private_state = (led, red3)
            self._write_chips(led, red3, write_buttons=True)
            return led, red3
        try:
            fcntl.flock(fd, fcntl.LOCK_EX)
            old = self._read_state(fd)
            fresh = old is None
            led, red3 = change(*(old if old is not None else (0x00, 0)))
            self._save_state(fd, led, red3)
            self._write_chips(led, red3, write_buttons=touches_buttons or fresh)
            return led, red3
        finally:
            os.close(fd)  # also drops the lock

    @staticmethod
    def _with_light(led, red3, light_num, color):
        b, g, r = color
        if light_num == 3:
            # Divided LED: B=P6(0x21), G=P7(0x21), R=P6(0x20)
            led = _with_bit(led, 6, b)
            led = _with_bit(led, 7, g)
            return led, 1 if r else 0
        pins = LIGHT1_PINS if light_num == 1 else LIGHT2_PINS
        for pin, on in zip(pins, color):
            led = _with_bit(led, pin, on)
        return led, red3

    # -- public API -----------------------------------------------------------

    def set_light(self, light_num: int, color: tuple):
        """
        Set LED 1, 2, or 3 to a color.

        Args:
            light_num: 1 (health), 2 (ptt), or 3 (speaker)
            color: BGR tuple from Colors class, e.g. Colors.GREEN
        """
        if not self._enabled:
            return
        self._update(
            lambda led, red3: self._with_light(led, red3, light_num, color),
            touches_buttons=(light_num == 3),
        )

    def off(self, light_num: int):
        """Turn off specific LED"""
        self.set_light(light_num, Colors.OFF)

    def off_all(self):
        """Turn off all 3 LEDs"""
        if not self._enabled:
            return
        self._update(lambda led, red3: (0x00, 0), touches_buttons=True)

    def close(self):
        """Clean up - turn off LEDs and close bus"""
        self.off_all()
        if self._bus:
            try:
                self._bus.close()
            except Exception:
                pass
