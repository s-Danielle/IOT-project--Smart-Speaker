"""
Sound+light combined events (on_play(), etc.)
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ui.sounds import Sounds
from ui.lights import Lights
from utils.logger import log_event


class UIController:
    """Unified UI feedback controller combining sounds and lights"""
    
    def __init__(self, sounds: Sounds = None, lights: Lights = None):
        """Initialize UI controller"""
        self._sounds = sounds or Sounds()
        self._lights = lights or Lights()
        log_event("UI Controller initialized")
    
    def on_chip_loaded(self):
        """Feedback when chip is loaded"""
        log_event("📀 CHIP LOADED")
        self._sounds.play_chip_loaded()
        self._lights.show_chip_loaded()
    
    def on_same_chip_scanned(self):
        """Feedback when same chip is scanned (no effect)"""
        log_event("📀 Same chip scanned (no action)")
        self._sounds.play_swipe()
    
    def on_play(self):
        """Feedback when playback starts/resumes"""
        log_event("▶️  PLAY")
        self._lights.show_playing()
    
    def on_pause(self):
        """Feedback when playback pauses"""
        log_event("⏸️  PAUSE")
        self._lights.show_paused()
    
    def on_stop(self):
        """Feedback when playback stops"""
        log_event("⏹️  STOP")
        self._sounds.play_stop()
        self._lights.show_chip_loaded()
    
    def on_clear_chip(self):
        """Feedback when chip is cleared (reset)"""
        log_event("🔄 CLEAR CHIP (Reset)")
        self._sounds.play_reset()
        self._lights.show_idle()
    
    def on_record_start(self):
        """Feedback when recording starts"""
        log_event("🎙️  RECORDING STARTED")
        self._sounds.play_record_start()
        self._lights.show_recording()
    
    def on_record_saved(self):
        """Feedback when recording is saved"""
        log_event("💾 RECORDING SAVED")
        self._sounds.play_record_saved()
        self._lights.show_success()
    
    def on_record_canceled(self):
        """Feedback when recording is canceled"""
        log_event("❌ RECORDING CANCELED")
        self._sounds.play_record_canceled()
        self._lights.show_chip_loaded()
    
    def on_blocked_action(self):
        """Feedback when action is blocked"""
        log_event("🚫 ACTION BLOCKED")
        self._sounds.play_blocked()
        self._lights.show_error()
    
    def on_error(self):
        """Feedback for errors"""
        log_event("❌ ERROR")
        self._sounds.play_error()
        self._lights.show_error()
    
    def on_volume_change(self, volume: int):
        """Feedback when volume changes
        
        Note: We don't play a sound here because that would interrupt music playback.
        Volume control works while music is playing via Mopidy's mixer API.
        """
        log_event(f"🔊 VOLUME: {volume}")
        self._lights.show_volume(volume)