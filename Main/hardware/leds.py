"""
APA102 LED wrapper - DISABLED (as requested)
All LED functions are no-ops
"""

from utils.logger import log


class LEDs:
    """APA102 LED strip wrapper - DISABLED"""
    
    def __init__(self, num_leds: int = 3):
        """Initialize LED strip (disabled)"""
        pass
    
    def set_color(self, r: int, g: int, b: int, brightness: int = 31):
        """Set all LEDs to a color (disabled)"""
        pass
    
    def set_led(self, index: int, r: int, g: int, b: int, brightness: int = 31):
        """Set a specific LED to a color (disabled)"""
        pass
    
    def blink(self, r: int, g: int, b: int, times: int = 3, interval: float = 0.2):
        """Blink all LEDs (disabled)"""
        pass
    
    def pulse(self, r: int, g: int, b: int, duration: float = 1.0):
        """Pulse LEDs (disabled)"""
        pass
    
    def off(self):
        """Turn off all LEDs (disabled)"""
        pass
    
    def close(self):
        """Clean up LED resources (disabled)"""
        pass
