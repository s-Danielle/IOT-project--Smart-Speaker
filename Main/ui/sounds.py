"""
Play WAVs (chip-loaded beep, error beep…)
"""

import os
import sys
import time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import paths
from utils.logger import log_sound, log_error

import subprocess


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
                # Check if process is still running
                if self._current_process.poll() is None:
                    # Process is still running, terminate it
                    self._current_process.terminate()
                    try:
                        self._current_process.wait(timeout=0.2)  # Longer timeout
                    except subprocess.TimeoutExpired:
                        # Force kill if terminate didn't work
                        self._current_process.kill()
                        self._current_process.wait()
                else:
                    # Process already finished, check for errors
                    if self._current_process.stderr:
                        try:
                            stderr_output = self._current_process.stderr.read().decode()
                            if stderr_output:
                                log_error(f"Previous aplay had errors: {stderr_output}")
                        except:
                            pass
            except Exception as e:
                log_error(f"Error stopping previous sound: {e}")
            finally:
                self._current_process = None
                log_sound(f"[STOPPED] Previous sound to play: {name}")
                # Small delay to let ALSA release the device
                time.sleep(0.05)
        
        log_sound(f"🔊 Playing: {name}")
        
        if not os.path.exists(filepath):
            log_error(f"Sound file not found: {filepath}")
            return
        
        try:
            # Use aplay for WAV playback (non-blocking)
            # Use -D default to avoid device conflicts, and capture stderr
            self._current_process = subprocess.Popen(
                ["aplay", "-q", filepath],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE
            )
            self._last_sound_time = current_time
            
            # Check if process started successfully (after brief delay)
            time.sleep(0.1)  # Longer wait to check if process crashed
            if self._current_process.poll() is not None:
                # Process exited immediately - likely an error
                stderr_output = ""
                if self._current_process.stderr:
                    try:
                        stderr_output = self._current_process.stderr.read().decode().strip()
                    except:
                        stderr_output = "Could not read stderr"
                
                if stderr_output:
                    log_error(f"aplay failed: {stderr_output}")
                    # If it's a permission/device lock error, suggest solutions
                    if "Permission denied" in stderr_output or "unable to create IPC" in stderr_output:
                        log_error("Audio device may be locked by another process (arecord/Mopidy)")
                        log_error("Try: sudo usermod -a -G audio $USER (then logout/login)")
                        log_error("Or check: lsof | grep snd")
                else:
                    log_error(f"aplay process exited immediately (exit code: {self._current_process.returncode})")
                log_error(f"Sound file: {filepath}")
                self._current_process = None
                return  # Don't continue if playback failed
        except FileNotFoundError:
            log_error(f"aplay executable not found - cannot play sound: {name}")
            log_error("On Raspberry Pi, install with: sudo apt-get install alsa-utils")
        except Exception as e:
            log_error(f"Failed to play sound: {e}")
            self._current_process = None
    
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
                # Check if process is still running
                if self._current_process.poll() is None:
                    # Process is still running, terminate it
                    self._current_process.terminate()
                    try:
                        self._current_process.wait(timeout=0.1)
                    except subprocess.TimeoutExpired:
                        # Force kill if terminate didn't work
                        self._current_process.kill()
                        self._current_process.wait()
            except Exception as e:
                log_error(f"Error stopping sound: {e}")
            finally:
                self._current_process = None
                log_sound("[STOPPED] Current sound")
