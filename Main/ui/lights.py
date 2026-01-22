"""
High-level LED states - DISABLED (as requested)
All light functions are no-ops
"""


class Lights:
    """High-level LED state management - DISABLED"""
    
    def __init__(self, leds=None):
        pass
    
    def show_idle(self):
        pass
    
    def show_chip_loaded(self):
        pass
    
    def show_playing(self):
        pass
    
    def show_paused(self):
        pass
    
    def show_recording(self):
        pass
    
    def show_error(self):
        pass
    
    def show_success(self):
        pass
    
    def show_volume(self, volume: int):
        """Show volume level feedback (0-100)"""
        pass
    
    def off(self):
        pass
