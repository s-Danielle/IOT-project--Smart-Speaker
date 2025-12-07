"""
Play WAVs (chip-loaded beep, error beep…)
"""

import os
import sys
import time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import paths
from utils.logger import log_sound, log_error

# Try to import audio playback library
try:
    import subprocess
    HAS_APLAY = True
except:
    HAS_APLAY = False


class Sounds:
    """WAV sound playback for UI feedback"""
    
    def __init__(self, sounds_dir: str = None, cooldown: float = 0.1):
        """Initialize sound player
        
        Args:
            sounds_dir: Directory containing sound files
            cooldown: Minimum time between sounds (seconds)
        """
        self._sounds_dir = sounds_dir or paths.SOUNDS_DIR
        self._cooldown = cooldown
        self._last_sound_time = 0.0
        self._current_process = None  # Track current aplay process
        log_sound(f"Sounds initialized (dir: {self._sounds_dir}, cooldown: {cooldown}s)")
    
    def _play_file(self, filepath: str, name: str):
        """Play a WAV file (stops any currently playing sound)"""
        current_time = time.time()
        
        # Check cooldown
        if current_time - self._last_sound_time < self._cooldown:
            log_sound(f"[SKIPPED] {name} (cooldown)")
            return
        
        # Stop any currently playing sound
        if self._current_process is not None:
            try:
                self._current_process.terminate()
                self._current_process.wait(timeout=0.1)
            except:
                try:
                    self._current_process.kill()
                except:
                    pass
            self._current_process = None
            log_sound(f"[STOPPED] Previous sound to play: {name}")
        
        log_sound(f"🔊 Playing: {name}")
        
        if not os.path.exists(filepath):
            log_error(f"Sound file not found: {filepath}")
            return
        
        try:
            # Use aplay for WAV playback (non-blocking)
            self._current_process = subprocess.Popen(
                ["aplay", "-q", filepath],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
            self._last_sound_time = current_time
        except FileNotFoundError:
            log_sound(f"[SIMULATION] Would play: {name}")
            self._last_sound_time = current_time
        except Exception as e:
            log_error(f"Failed to play sound: {e}")
    
    def play(self, sound_name: str):
        """Play a sound by filename"""
        filepath = os.path.join(self._sounds_dir, sound_name)
        self._play_file(filepath, sound_name)
    
    def play_chip_loaded(self):
        """Play chip loaded beep"""
        self._play_file(paths.SOUND_CHIP_LOADED, "CHIP LOADED")
    
    def play_play(self):
        """Play start playback chime"""
        self._play_file(paths.SOUND_PLAY, "PLAY")
    
    def play_pause(self):
        """Play pause click"""
        self._play_file(paths.SOUND_PAUSE, "PAUSE")
    
    def play_stop(self):
        """Play stop tone"""
        self._play_file(paths.SOUND_STOP, "STOP")
    
    def play_error(self):
        """Play error beep"""
        self._play_file(paths.SOUND_ERROR, "ERROR")
    
    def play_record_start(self):
        """Play record start beep"""
        self._play_file(paths.SOUND_RECORD_START, "RECORD START")
    
    def play_record_saved(self):
        """Play record saved chime"""
        self._play_file(paths.SOUND_RECORD_SAVED, "RECORD SAVED")
    
    def play_record_canceled(self):
        """Play record canceled tone"""
        self._play_file(paths.SOUND_RECORD_CANCELED, "RECORD CANCELED")
    
    def play_blocked(self):
        """Play blocked action beep"""
        self._play_file(paths.SOUND_BLOCKED, "BLOCKED")
    
    def play_reset(self):
        """Play reset tone (longer stop for clear chip)"""
        self._play_file(paths.SOUND_RESET, "RESET")
    
    def play_swipe(self):
        """Play soft no-action click (same chip scanned)"""
        self._play_file(paths.SOUND_SWIPE, "SWIPE (no action)")
    
    def stop(self):
        """Stop any currently playing sound"""
        if self._current_process is not None:
            try:
                self._current_process.terminate()
                self._current_process.wait(timeout=0.1)
            except:
                try:
                    self._current_process.kill()
                except:
                    pass
            self._current_process = None
            log_sound("[STOPPED] Current sound")
