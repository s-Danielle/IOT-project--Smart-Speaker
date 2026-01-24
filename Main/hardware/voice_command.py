"""
Voice command processor for PTT (Push-to-Talk) feature.
Handles recording, transcription, and command parsing.
Uses Google Speech API (requires internet).

Supported commands (must start with "hi speaker" or "hey speaker"):
- "hi speaker play" -> play
- "hi speaker pause" -> pause  
- "hi speaker stop" -> stop
- "hi speaker clear" -> clear
"""

import subprocess
import tempfile
import os
import time
import signal
from typing import Optional

from config.settings import (
    PTT_ENABLED,
    PTT_LISTEN_DURATION,
    PTT_WAKE_PHRASE,
    RECORDING_DEVICE,
)
from hardware.speech_recognition_wrapper import SpeechRecognitionWrapper
from utils.logger import log


# Max recording duration to prevent endless recording
MAX_RECORD_DURATION = 10.0  # seconds


class VoiceCommand:
    """
    Voice command processor with wake phrase detection.
    
    Supports two modes:
    1. Fixed duration: listen_and_parse(duration) - records for set time
    2. Hold-to-talk: start_recording() / stop_and_parse() - records while button held
    """
    
    # Supported commands after wake phrase
    COMMANDS = {"play", "pause", "stop", "clear"}
    
    def __init__(self):
        """Initialize voice command processor."""
        self._enabled = PTT_ENABLED
        self._duration = PTT_LISTEN_DURATION
        self._wake_phrase = PTT_WAKE_PHRASE.lower()
        
        self._speech = SpeechRecognitionWrapper()
        
        # For hold-to-talk mode
        self._recording_process = None
        self._recording_file = None
        self._recording_start_time = None
        
        log(f"[VOICE] Initialized (wake phrase: '{self._wake_phrase}')")
    
    def start_recording(self) -> bool:
        """
        Start recording audio (for hold-to-talk mode).
        Call stop_and_parse() when done to get the command.
        
        Returns:
            True if recording started, False on error
        """
        if not self._enabled:
            log("[VOICE] PTT is disabled")
            return False
        
        if self._recording_process is not None:
            log("[VOICE] Already recording")
            return False
        
        # Create temp file for recording
        with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as f:
            self._recording_file = f.name
        
        try:
            # Build arecord command (no duration limit, we'll stop it manually)
            cmd = [
                'arecord',
                '-f', 'S16_LE',
                '-r', '16000',
                '-c', '1',
                '-q',
                self._recording_file
            ]
            
            if RECORDING_DEVICE and RECORDING_DEVICE.strip():
                cmd.insert(1, '-D')
                cmd.insert(2, RECORDING_DEVICE)
            
            # Start recording in background
            self._recording_process = subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE
            )
            self._recording_start_time = time.time()
            
            log("[VOICE] Recording started (hold button, release when done)")
            return True
            
        except Exception as e:
            log(f"[VOICE] Failed to start recording: {e}")
            self._cleanup_recording()
            return False
    
    def stop_and_parse(self) -> Optional[str]:
        """
        Stop recording and parse the command (for hold-to-talk mode).
        
        Returns:
            Command string ("play", "pause", "stop", "clear") or None
        """
        if self._recording_process is None:
            log("[VOICE] Not recording")
            return None
        
        # Calculate recording duration
        duration = time.time() - self._recording_start_time if self._recording_start_time else 0
        log(f"[VOICE] Stopping recording (duration: {duration:.1f}s)")
        
        # Stop the recording process
        try:
            self._recording_process.terminate()
            self._recording_process.wait(timeout=2)
        except:
            try:
                self._recording_process.kill()
                self._recording_process.wait()
            except:
                pass
        
        self._recording_process = None
        
        # Check minimum duration
        if duration < 0.5:
            log("[VOICE] Recording too short (< 0.5s)")
            self._cleanup_recording()
            return None
        
        # Read the recorded audio
        try:
            with open(self._recording_file, 'rb') as f:
                wav_data = f.read()
            
            if len(wav_data) <= 44:
                log("[VOICE] Recording file too small")
                self._cleanup_recording()
                return None
            
            audio_data = wav_data[44:]  # Skip WAV header
            
        except Exception as e:
            log(f"[VOICE] Failed to read recording: {e}")
            self._cleanup_recording()
            return None
        finally:
            self._cleanup_recording()
        
        # Transcribe
        log("[VOICE] Transcribing via Google Speech API...")
        text = self._speech.transcribe(audio_data, sample_rate=16000)
        
        if text is None:
            log("[VOICE] Transcription failed")
            return None
        
        # Parse command
        command = self._parse_command(text)
        
        if command:
            log(f"[VOICE] Command recognized: {command}")
        else:
            log(f"[VOICE] No valid command in: '{text}'")
        
        return command
    
    def is_recording(self) -> bool:
        """Check if currently recording."""
        return self._recording_process is not None
    
    def cancel_recording(self):
        """Cancel current recording without processing."""
        if self._recording_process is not None:
            try:
                self._recording_process.terminate()
                self._recording_process.wait(timeout=1)
            except:
                try:
                    self._recording_process.kill()
                except:
                    pass
            self._recording_process = None
            log("[VOICE] Recording cancelled")
        self._cleanup_recording()
    
    def _cleanup_recording(self):
        """Clean up recording temp file."""
        if self._recording_file:
            try:
                os.unlink(self._recording_file)
            except:
                pass
            self._recording_file = None
        self._recording_start_time = None
    
    def listen_and_parse(self, duration: Optional[float] = None) -> Optional[str]:
        """
        Record audio for fixed duration, transcribe, and parse for command.
        (Original mode - kept for compatibility)
        
        Args:
            duration: Recording duration in seconds (default from settings)
            
        Returns:
            Command string ("play", "pause", "stop", "clear") or None
        """
        if not self._enabled:
            log("[VOICE] PTT is disabled")
            return None
        
        duration = duration or self._duration
        
        # Step 1: Record audio
        log(f"[VOICE] Listening for {duration}s...")
        audio_data = self._record_audio(duration)
        
        if audio_data is None:
            log("[VOICE] Recording failed")
            return None
        
        # Step 2: Transcribe (uses Google Speech API - needs internet)
        log("[VOICE] Transcribing via Google Speech API...")
        text = self._speech.transcribe(audio_data, sample_rate=16000)
        
        if text is None:
            log("[VOICE] Transcription failed")
            return None
        
        # Step 3: Parse command
        command = self._parse_command(text)
        
        if command:
            log(f"[VOICE] Command recognized: {command}")
        else:
            log(f"[VOICE] No valid command in: '{text}'")
        
        return command
    
    def _record_audio(self, duration: float) -> Optional[bytes]:
        """
        Record audio using arecord.
        
        Args:
            duration: Recording duration in seconds
            
        Returns:
            Raw PCM audio bytes (16-bit signed, mono, 16kHz) or None
        """
        # Create temp file for recording
        with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as f:
            temp_path = f.name
        
        try:
            # Build arecord command
            # -f S16_LE: 16-bit signed little-endian
            # -r 16000: 16kHz sample rate (good for speech)
            # -c 1: mono
            # -d N: duration in seconds
            cmd = [
                'arecord',
                '-f', 'S16_LE',
                '-r', '16000',
                '-c', '1',
                '-d', str(int(duration)),
                '-q',  # quiet mode
                temp_path
            ]
            
            # Add device if specified
            if RECORDING_DEVICE and RECORDING_DEVICE.strip():
                cmd.insert(1, '-D')
                cmd.insert(2, RECORDING_DEVICE)
            
            # Run arecord
            result = subprocess.run(
                cmd,
                capture_output=True,
                timeout=duration + 5  # Extra time for overhead
            )
            
            if result.returncode != 0:
                stderr = result.stderr.decode() if result.stderr else "Unknown error"
                log(f"[VOICE] arecord failed: {stderr}")
                return None
            
            # Read raw PCM data (skip WAV header - 44 bytes)
            with open(temp_path, 'rb') as f:
                wav_data = f.read()
                # WAV header is 44 bytes, rest is PCM data
                if len(wav_data) > 44:
                    return wav_data[44:]
                else:
                    log("[VOICE] Recording too short")
                    return None
                    
        except subprocess.TimeoutExpired:
            log("[VOICE] Recording timed out")
            return None
        except FileNotFoundError:
            log("[VOICE] arecord not found - install alsa-utils")
            return None
        except Exception as e:
            log(f"[VOICE] Recording error: {e}")
            return None
        finally:
            # Clean up temp file
            try:
                os.unlink(temp_path)
            except:
                pass
    
    def _parse_command(self, text: str) -> Optional[str]:
        """
        Parse transcribed text for wake phrase and command.
        
        Args:
            text: Transcribed text (already lowercase)
            
        Returns:
            Command string or None if not recognized
        """
        if not text:
            return None
        
        text = text.lower().strip()
        
        # Accept variations of wake phrase (ordered by priority - longer matches first)
        # "hi speaker" / "hey speaker" preferred, but "hi" / "hey" alone also work
        wake_phrases = ["hi speaker", "hey speaker", "hi ", "hey "]
        
        remainder = None
        for phrase in wake_phrases:
            if text.startswith(phrase):
                remainder = text[len(phrase):].strip()
                break
        
        if remainder is None:
            log(f"[VOICE] No wake phrase found")
            return None
        
        # Check for each command
        for cmd in self.COMMANDS:
            if remainder.startswith(cmd):
                return cmd
        
        # Wake phrase present but no valid command
        log(f"[VOICE] Wake phrase found but unknown command: '{remainder}'")
        return None
    
    def is_available(self) -> bool:
        """Check if voice commands are available."""
        return self._enabled and self._speech.is_available()
