"""
Speaker LED feedback (Light 3 - Divided LED) via PCF8574
Implements the show_* interface called by UIController

Light 3 is split across two expanders:
- Blue: P6 on 0x21
- Green: P7 on 0x21
- Red: P6 on 0x20
"""

import threading
import time
from hardware.leds import RGBLeds, Colors
from utils.logger import log


class Lights:
    """
    High-level LED state management for speaker/player feedback.
    Controls Light 3 (Divided LED) on PCF8574.
    
    This class implements the interface already called by UIController:
    - show_idle(), show_chip_loaded(), show_playing(), show_paused()
    - show_recording(), show_success(), show_error(), show_volume()
    
    Color scheme (R/G/B only):
    - GREEN: Playing
    - BLUE: Idle/Pause
    - RED: Recording
    - RED blinking: Error
    """
    
    LIGHT = 3  # Speaker uses Light 3 (divided LED)
    
    def __init__(self, leds=None):
        """Initialize lights controller"""
        self._leds = None
        self._enabled = False
        self._flash_thread = None
        
        try:
            self._leds = leds or RGBLeds()
            self._enabled = True
            log("[LIGHTS] Speaker LED initialized (Light 3 - Divided)")
        except Exception as e:
            log(f"[LIGHTS] Failed to initialize: {e} - LEDs disabled")
            self._enabled = False
    
    # =========================================================================
    # SOLID STATES
    # =========================================================================
    
    def show_idle(self):
        """Chip cleared / Idle - blue solid"""
        if self._enabled:
            self._leds.set_light(self.LIGHT, Colors.BLUE)
    
    def show_chip_loaded(self):
        """Chip scanned/loaded - green flash then blue (idle)"""
        if self._enabled:
            self._flash(Colors.GREEN, duration=0.2, return_to=Colors.BLUE)
    
    def show_playing(self):
        """Playing - green solid"""
        if self._enabled:
            self._leds.set_light(self.LIGHT, Colors.GREEN)
    
    def show_paused(self):
        """Paused - blue solid"""
        if self._enabled:
            self._leds.set_light(self.LIGHT, Colors.BLUE)
    
    def show_recording(self):
        """Recording - red solid"""
        if self._enabled:
            self._leds.set_light(self.LIGHT, Colors.RED)
    
    # =========================================================================
    # FLASH PATTERNS
    # =========================================================================
    
    def show_success(self):
        """Success (recording saved) - green flash"""
        if self._enabled:
            self._flash(Colors.GREEN, duration=0.5)
    
    def show_error(self):
        """Error or blocked action - red triple flash"""
        if self._enabled:
            self._multi_flash(Colors.RED, times=3, on_time=0.1, off_time=0.1)
    
    def show_volume(self, volume: int):
        """Volume change - blue brief flash"""
        if self._enabled:
            self._flash(Colors.BLUE, duration=0.1)
    
    def off(self):
        """Turn off speaker LED"""
        if self._enabled:
            self._leds.off(self.LIGHT)
    
    # =========================================================================
    # FLASH HELPERS (non-blocking)
    # =========================================================================
    
    def _flash(self, color: tuple, duration: float = 0.2, return_to: tuple = None):
        """Single flash then off or return to color (non-blocking)"""
        def do_flash():
            self._leds.set_light(self.LIGHT, color)
            time.sleep(duration)
            if return_to:
                self._leds.set_light(self.LIGHT, return_to)
            else:
                self._leds.off(self.LIGHT)
        
        # Run in background thread so it doesn't block
        thread = threading.Thread(target=do_flash, daemon=True)
        thread.start()
    
    def _multi_flash(self, color: tuple, times: int = 3, on_time: float = 0.1, off_time: float = 0.1):
        """Multiple flashes (non-blocking)"""
        def do_multi():
            for i in range(times):
                self._leds.set_light(self.LIGHT, color)
                time.sleep(on_time)
                self._leds.off(self.LIGHT)
                if i < times - 1:
                    time.sleep(off_time)
        
        thread = threading.Thread(target=do_multi, daemon=True)
        thread.start()
