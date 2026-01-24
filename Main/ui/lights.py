"""
Player LED feedback (Light 2) via PCF8574
Implements the show_* interface called by UIController
"""

import threading
import time
from hardware.leds import RGBLeds, Colors
from utils.logger import log


class Lights:
    """
    High-level LED state management for player feedback.
    Controls Light 2 (P3-P5) on PCF8574.
    
    This class implements the interface already called by UIController:
    - show_idle(), show_chip_loaded(), show_playing(), show_paused()
    - show_recording(), show_success(), show_error(), show_volume()
    """
    
    LIGHT = 2  # Player uses Light 2
    
    def __init__(self, leds=None):
        """Initialize lights controller"""
        self._leds = None
        self._enabled = False
        self._flash_thread = None
        
        try:
            self._leds = leds or RGBLeds()
            self._enabled = True
            log("[LIGHTS] Player LED initialized (Light 2)")
        except Exception as e:
            log(f"[LIGHTS] Failed to initialize: {e} - LEDs disabled")
            self._enabled = False
    
    # =========================================================================
    # SOLID STATES
    # =========================================================================
    
    def show_idle(self):
        """Chip cleared - LED off"""
        if self._enabled:
            self._leds.off(self.LIGHT)
    
    def show_chip_loaded(self):
        """Chip scanned/loaded - blue flash then off"""
        if self._enabled:
            self._flash(Colors.BLUE, duration=0.2)
    
    def show_playing(self):
        """Playing - green solid"""
        if self._enabled:
            self._leds.set_light(self.LIGHT, Colors.GREEN)
    
    def show_paused(self):
        """Paused - yellow solid"""
        if self._enabled:
            self._leds.set_light(self.LIGHT, Colors.YELLOW)
    
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
        """Volume change - white brief flash"""
        if self._enabled:
            self._flash(Colors.WHITE, duration=0.1)
    
    def off(self):
        """Turn off player LED"""
        if self._enabled:
            self._leds.off(self.LIGHT)
    
    # =========================================================================
    # FLASH HELPERS (non-blocking)
    # =========================================================================
    
    def _flash(self, color: tuple, duration: float = 0.2):
        """Single flash then off (non-blocking)"""
        def do_flash():
            self._leds.set_light(self.LIGHT, color)
            time.sleep(duration)
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
