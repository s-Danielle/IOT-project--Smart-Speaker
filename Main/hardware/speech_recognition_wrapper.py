"""
Speech-to-text wrapper using Google Cloud Speech API (free tier).
Used for PTT voice commands on Raspberry Pi Zero.
Requires internet connection.
"""

import os
import tempfile
import wave
from typing import Optional
from utils.logger import log


class SpeechRecognitionWrapper:
    """
    Speech-to-text using Google's free speech recognition API.
    
    Features:
    - No API key required (uses free tier)
    - Works on any architecture (Pi Zero included)
    - Requires internet connection
    """
    
    def __init__(self):
        """Initialize speech recognition wrapper."""
        self._recognizer = None
        log("[SPEECH] Google Speech Recognition wrapper initialized")
    
    def _ensure_recognizer(self) -> bool:
        """
        Lazy load recognizer on first use.
        
        Returns:
            True if recognizer is ready, False otherwise
        """
        if self._recognizer is not None:
            return True
        
        try:
            import speech_recognition as sr
            self._recognizer = sr.Recognizer()
            log("[SPEECH] Recognizer ready")
            return True
        except ImportError:
            log("[SPEECH] Error: SpeechRecognition not installed")
            log("[SPEECH] Install with: pip install SpeechRecognition")
            return False
        except Exception as e:
            log(f"[SPEECH] Error initializing: {e}")
            return False
    
    def transcribe(self, audio_data: bytes, sample_rate: int = 16000) -> Optional[str]:
        """
        Transcribe audio bytes to text using Google Speech API.
        
        Args:
            audio_data: Raw PCM audio bytes (16-bit signed, mono)
            sample_rate: Audio sample rate
            
        Returns:
            Transcribed text (lowercase) or None on error
        """
        if not self._ensure_recognizer():
            return None
        
        try:
            import speech_recognition as sr
            
            # Create a temporary WAV file from raw audio data
            with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as f:
                temp_path = f.name
            
            try:
                # Write WAV file
                with wave.open(temp_path, 'wb') as wf:
                    wf.setnchannels(1)  # Mono
                    wf.setsampwidth(2)  # 16-bit
                    wf.setframerate(sample_rate)
                    wf.writeframes(audio_data)
                
                # Load audio file
                with sr.AudioFile(temp_path) as source:
                    audio = self._recognizer.record(source)
                
                # Transcribe using Google (free, no API key needed)
                text = self._recognizer.recognize_google(audio).lower().strip()
                
                if text:
                    log(f"[SPEECH] Transcribed: '{text}'")
                else:
                    log("[SPEECH] No speech detected")
                
                return text
                
            finally:
                # Clean up temp file
                try:
                    os.unlink(temp_path)
                except:
                    pass
                    
        except Exception as e:
            # Handle specific speech recognition errors
            error_name = type(e).__name__
            if error_name == 'UnknownValueError':
                log("[SPEECH] Could not understand audio")
            elif error_name == 'RequestError':
                log(f"[SPEECH] API error (need internet): {e}")
            else:
                log(f"[SPEECH] Transcription error: {e}")
            return None
    
    def is_available(self) -> bool:
        """Check if speech recognition is available."""
        try:
            import speech_recognition
            return True
        except ImportError:
            return False
