"""
Voice command processor for PTT (Push-to-Talk) feature.
Handles recording, transcription, and command parsing.
Uses Google Speech API (requires internet).

Supported commands (must start with "hi speaker"):
- "hi speaker play" -> play
- "hi speaker pause" -> pause  
- "hi speaker stop" -> stop
- "hi speaker clear" -> clear
"""

import subprocess
import tempfile
import os
from typing import Optional

from config.settings import (
    PTT_ENABLED,
    PTT_LISTEN_DURATION,
    PTT_WAKE_PHRASE,
    RECORDING_DEVICE,
)
from hardware.speech_recognition_wrapper import SpeechRecognitionWrapper
from utils.logger import log


class VoiceCommand:
    """
    Voice command processor with wake phrase detection.
    
    Flow:
    1. Record audio for fixed duration (2.5s)
    2. Transcribe using Google Speech API
    3. Parse for wake phrase + command
    4. Return command or None
    """
    
    # Supported commands after wake phrase
    COMMANDS = {"play", "pause", "stop", "clear"}
    
    def __init__(self):
        """Initialize voice command processor."""
        self._enabled = PTT_ENABLED
        self._duration = PTT_LISTEN_DURATION
        self._wake_phrase = PTT_WAKE_PHRASE.lower()
        
        self._speech = SpeechRecognitionWrapper()
        log(f"[VOICE] Initialized (wake phrase: '{self._wake_phrase}')")
    
    def listen_and_parse(self, duration: Optional[float] = None) -> Optional[str]:
        """
        Record audio, transcribe, and parse for command.
        
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
        
        # Must start with wake phrase
        if not text.startswith(self._wake_phrase):
            log(f"[VOICE] No wake phrase (expected '{self._wake_phrase}')")
            return None
        
        # Extract remainder after wake phrase
        remainder = text[len(self._wake_phrase):].strip()
        
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
