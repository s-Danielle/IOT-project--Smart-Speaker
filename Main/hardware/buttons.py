"""
PCF8574 or GPIO wrapper, returns raw states
Buttons are active-low.
"""

import time
from dataclasses import dataclass
from enum import Enum, auto
from typing import Dict


from config.settings import (
    PCF8574_ADDRESS, 
    BUTTON_PLAY_PAUSE_BIT, 
    BUTTON_RECORD_BIT, 
    BUTTON_STOP_BIT,
    BUTTON_VOLUME_UP_BIT,
    BUTTON_VOLUME_DOWN_BIT,
    BUTTON_PTT_BIT,
)
from utils.logger import log_button, log_error
from utils.hardware_health import HardwareHealthManager

# Hardware imports
try:
    from smbus2 import SMBus
    HAS_HARDWARE = True
except ImportError:
    HAS_HARDWARE = False
    log_error("SMBus library not available - button input will not work")


class ButtonID(Enum):
    """Button identifiers"""
    PLAY_PAUSE = auto()
    RECORD = auto()
    STOP = auto()
    VOLUME_UP = auto()
    VOLUME_DOWN = auto()
    PTT = auto()  # Push-to-Talk for voice commands


@dataclass
class ButtonState:
    """Current button state with timing info"""
    is_pressed: bool = False
    press_start_time: float = 0.0
    was_pressed: bool = False  # Previous state for edge detection


class Buttons:
    """Button reader wrapper (PCF8574)"""
    
    # Map button ID to bit position
    BUTTON_BITS = {
        ButtonID.PLAY_PAUSE: BUTTON_PLAY_PAUSE_BIT,
        ButtonID.RECORD: BUTTON_RECORD_BIT,
        ButtonID.STOP: BUTTON_STOP_BIT,
        ButtonID.VOLUME_UP: BUTTON_VOLUME_UP_BIT,
        ButtonID.VOLUME_DOWN: BUTTON_VOLUME_DOWN_BIT,
        ButtonID.PTT: BUTTON_PTT_BIT,
    }
    
    def __init__(self):
        """Initialize button reader"""
        self._bus = None
        self._states: Dict[ButtonID, ButtonState] = {
            btn: ButtonState() for btn in ButtonID
        }
        
        # Register with health manager for error throttling
        self._health = HardwareHealthManager.get_instance().register(
            "buttons",
            expected_errors=["Input/output error", "Remote I/O error"],
            log_interval=3.0,
            failure_threshold=20
        )
        
        if HAS_HARDWARE:
            try:
                self._bus = SMBus(1)
                log_button("PCF8574 buttons initialized")
            except Exception as e:
                log_error(f"Failed to initialize buttons: {e}")
                self._bus = None
        else:
            log_error("Buttons not available - hardware libraries missing")
    
    def _read_raw(self) -> int:
        """Read raw byte from PCF8574"""
        if self._bus is None:
            return 0xFF  # All buttons released (active-low)
        try:
            result = self._bus.read_byte(PCF8574_ADDRESS)
            self._health.report_success()
            return result
        except Exception as e:
            # Track errors silently (no logging to avoid flooding)
            # Health monitor will handle recovery via LED feedback + service restart
            self._health.report_error(e)
            return 0xFF
    
    def update(self):
        """Update button states - call this every loop iteration"""
        raw = self._read_raw()
        current_time = time.time()
        
        for button, bit in self.BUTTON_BITS.items():
            state = self._states[button]
            # Active-low: 0 = pressed, 1 = released
            is_pressed = (raw & (1 << bit)) == 0
            
            # Save previous state
            state.was_pressed = state.is_pressed
            state.is_pressed = is_pressed
            
            # Track press start time
            if is_pressed and not state.was_pressed:
                state.press_start_time = current_time
                log_button(f"{button.name} pressed")
            elif not is_pressed and state.was_pressed:
                duration = current_time - state.press_start_time
                log_button(f"{button.name} released (held {duration:.2f}s)")
    
    def is_pressed(self, button: ButtonID) -> bool:
        """Check if button is currently pressed"""
        return self._states[button].is_pressed
    
    def just_pressed(self, button: ButtonID) -> bool:
        """Check if button was just pressed (rising edge)"""
        state = self._states[button]
        return state.is_pressed and not state.was_pressed
    
    def just_released(self, button: ButtonID) -> bool:
        """Check if button was just released (falling edge)"""
        state = self._states[button]
        return not state.is_pressed and state.was_pressed
    
    def hold_duration(self, button: ButtonID) -> float:
        """Get how long button has been held (0 if not pressed)"""
        state = self._states[button]
        if state.is_pressed:
            return time.time() - state.press_start_time
        return 0.0
    
    def get_release_duration(self, button: ButtonID) -> float:
        """Get how long button was held when released (only valid on release frame)"""
        state = self._states[button]
        if self.just_released(button):
            return time.time() - state.press_start_time
        return 0.0
    
    def close(self):
        """Clean up button reader resources"""
        if self._bus:
            self._bus.close()
        log_button("Buttons closed")
