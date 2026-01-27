"""
RGB LED control via PCF8574 I2C expanders

Light 1 (P0-P2 on 0x21): Health LED - controlled by health_monitor.py
Light 2 (P3-P5 on 0x21): PTT LED - controlled by controller.py
Light 3 (Divided LED):   Speaker LED - controlled by ui/lights.py
    - P6 on 0x21 = Blue
    - P7 on 0x21 = Green
    - P6 on 0x20 = Red
"""

from smbus2 import SMBus
from utils.logger import log

# I2C Configuration
I2C_BUS = 1
LED_EXPANDER_ADDRESS = 0x21    # Main LED expander
BUTTON_EXPANDER_ADDRESS = 0x20  # Button expander (has divided LED red pin)

# Pin mappings - all LEDs are B, G, R order (active-high: set bit = LED ON)
LIGHT1_PINS = (0, 1, 2)  # P0=B, P1=G, P2=R (Health LED)
LIGHT2_PINS = (3, 4, 5)  # P3=B, P4=G, P5=R (PTT LED)
# Light 3 is divided: P6=B, P7=G on 0x21, P6=R on 0x20


class Colors:
    """RGB color tuples (B, G, R) as booleans - matches pin order"""
    OFF =    (False, False, False)
    BLUE =   (True,  False, False)
    GREEN =  (False, True,  False)
    RED =    (False, False, True)
    YELLOW = (False, True,  True)   # Green + Red = Yellow


class RGBLeds:
    """
    Control 3 RGB LEDs via PCF8574 I2C expanders.
    
    Light 1 (Health): P0-P2 on 0x21
    Light 2 (PTT):    P3-P5 on 0x21
    Light 3 (Speaker): P6-P7 on 0x21 + P6 on 0x20 (divided LED)
    
    Each service controls its own LED - state is preserved for other LEDs.
    """
    
    def __init__(self):
        """Initialize LED controller"""
        self._bus = None
        self._led_state = 0x00      # State for 0x21 (LED expander)
        self._button_state = 0x3F   # State for 0x20 (keep P0-P5 high for buttons)
        self._enabled = False
        
        try:
            self._bus = SMBus(I2C_BUS)
            # Read current states to preserve other LED states
            try:
                self._led_state = self._bus.read_byte(LED_EXPANDER_ADDRESS)
            except:
                self._led_state = 0x00
            try:
                self._button_state = self._bus.read_byte(BUTTON_EXPANDER_ADDRESS)
            except:
                self._button_state = 0x3F  # P0-P5 high for button inputs
            self._enabled = True
            log(f"[LEDS] Initialized: 0x21=0x{self._led_state:02X}, 0x20=0x{self._button_state:02X}")
        except Exception as e:
            log(f"[LEDS] Failed to initialize: {e} - LEDs disabled")
            self._enabled = False
    
    def set_light(self, light_num: int, color: tuple):
        """
        Set LED 1, 2, or 3 to a color.
        
        Args:
            light_num: 1 (health), 2 (ptt), or 3 (speaker)
            color: BGR tuple from Colors class, e.g. Colors.GREEN
        """
        if not self._enabled:
            return
        
        if light_num == 3:
            # Divided LED: B=P6(0x21), G=P7(0x21), R=P6(0x20)
            b, g, r = color
            
            # Blue and Green on LED expander (0x21)
            if b:
                self._led_state |= (1 << 6)
            else:
                self._led_state &= ~(1 << 6)
            if g:
                self._led_state |= (1 << 7)
            else:
                self._led_state &= ~(1 << 7)
            
            # Red on Button expander (0x20) - P6
            if r:
                self._button_state |= (1 << 6)
            else:
                self._button_state &= ~(1 << 6)
            
            try:
                self._bus.write_byte(LED_EXPANDER_ADDRESS, self._led_state)
                self._bus.write_byte(BUTTON_EXPANDER_ADDRESS, self._button_state)
            except Exception as e:
                log(f"[LEDS] Write error (light 3): {e}")
        else:
            # Light 1 or 2 - all pins on LED expander (0x21)
            pins = LIGHT1_PINS if light_num == 1 else LIGHT2_PINS
            
            for pin, on in zip(pins, color):
                if on:
                    self._led_state |= (1 << pin)
                else:
                    self._led_state &= ~(1 << pin)
            
            try:
                self._bus.write_byte(LED_EXPANDER_ADDRESS, self._led_state)
            except Exception as e:
                log(f"[LEDS] Write error: {e}")
    
    def off(self, light_num: int):
        """Turn off specific LED"""
        self.set_light(light_num, Colors.OFF)
    
    def off_all(self):
        """Turn off all 3 LEDs"""
        if not self._enabled:
            return
        # Clear Light 1, 2, 3 pins on LED expander (P0-P7)
        self._led_state = 0x00
        # Clear Light 3 red pin on Button expander (P6), keep P0-P5 high for buttons
        self._button_state = 0x3F
        try:
            self._bus.write_byte(LED_EXPANDER_ADDRESS, self._led_state)
            self._bus.write_byte(BUTTON_EXPANDER_ADDRESS, self._button_state)
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
