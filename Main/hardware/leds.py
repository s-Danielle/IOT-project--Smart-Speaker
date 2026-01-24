"""
RGB LED control via PCF8574 I2C expander at 0x21
Light 1 (P0-P2): Device Health - controlled by health_monitor.py
Light 2 (P3-P5): Player State - controlled by Main via ui/lights.py
"""

from smbus2 import SMBus
from utils.logger import log

# I2C Configuration
I2C_BUS = 1
I2C_ADDRESS = 0x21

# Pin mappings (accent-high: set bit = LED ON)
LIGHT1_PINS = (0, 1, 2)  # P0=R, P1=G, P2=B (Health LED)
LIGHT2_PINS = (3, 4, 5)  # P3=R, P4=G, P5=B (Player LED)


class Colors:
    """RGB color tuples (R, G, B) as booleans"""
    OFF =     (False, False, False)
    RED =     (True,  False, False)
    GREEN =   (False, True,  False)
    BLUE =    (False, False, True)
    YELLOW =  (True,  True,  False)
    CYAN =    (False, True,  True)
    MAGENTA = (True,  False, True)
    WHITE =   (True,  True,  True)


class RGBLeds:
    """
    Control 2 RGB LEDs via PCF8574 I2C expander.
    Each service controls its own LED - state is preserved for the other LED.
    """
    
    def __init__(self):
        """Initialize LED controller"""
        self._bus = None
        self._state = 0x00
        self._enabled = False
        
        try:
            self._bus = SMBus(I2C_BUS)
            # Read current state to preserve other LED's state
            try:
                self._state = self._bus.read_byte(I2C_ADDRESS)
            except:
                self._state = 0x00
            self._enabled = True
            log(f"[LEDS] Initialized PCF8574 at 0x{I2C_ADDRESS:02X}, state=0x{self._state:02X}")
        except Exception as e:
            log(f"[LEDS] Failed to initialize: {e} - LEDs disabled")
            self._enabled = False
    
    def set_light(self, light_num: int, color: tuple):
        """
        Set LED 1 or 2 to a color.
        
        Args:
            light_num: 1 (health) or 2 (player)
            color: RGB tuple from Colors class, e.g. Colors.GREEN
        """
        if not self._enabled:
            return
        
        pins = LIGHT1_PINS if light_num == 1 else LIGHT2_PINS
        
        for pin, on in zip(pins, color):
            if on:
                self._state |= (1 << pin)   # Set bit (LED ON)
            else:
                self._state &= ~(1 << pin)  # Clear bit (LED OFF)
        
        try:
            self._bus.write_byte(I2C_ADDRESS, self._state)
        except Exception as e:
            log(f"[LEDS] Write error: {e}")
    
    def off(self, light_num: int):
        """Turn off specific LED"""
        self.set_light(light_num, Colors.OFF)
    
    def off_all(self):
        """Turn off both LEDs"""
        if not self._enabled:
            return
        self._state = 0x00
        try:
            self._bus.write_byte(I2C_ADDRESS, self._state)
        except Exception as e:
            log(f"[LEDS] Write error: {e}")
    
    def close(self):
        """Clean up - turn off LEDs and close bus"""
        self.off_all()
        if self._bus:
            try:
                self._bus.close()
            except:
                pass
