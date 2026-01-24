"""
Vosk speech-to-text wrapper with lazy loading and CPU optimization.
Used for PTT voice commands.
"""

import json
import os
from typing import Optional
from utils.logger import log


class VoskWrapper:
    """
    Thin wrapper around Vosk for speech-to-text.
    
    Features:
    - Lazy model loading (only loads on first use)
    - CPU optimization via disabled logging
    - Simple transcription interface
    """
    
    def __init__(self, model_path: str):
        """
        Initialize wrapper with model path.
        Model is NOT loaded until first transcription.
        
        Args:
            model_path: Path to Vosk model directory
        """
        self._model = None
        self._model_path = model_path
        self._initialized = False
        
        # Suppress Vosk logging immediately (before any model load)
        try:
            from vosk import SetLogLevel
            SetLogLevel(-1)  # -1 = no logging, saves CPU
        except ImportError:
            log("[VOSK] Warning: vosk not installed")
    
    def _ensure_model(self) -> bool:
        """
        Lazy load model on first use.
        
        Returns:
            True if model is ready, False otherwise
        """
        if self._model is not None:
            return True
        
        if not os.path.exists(self._model_path):
            log(f"[VOSK] Model not found at: {self._model_path}")
            log("[VOSK] Run: scripts/download-vosk-model.sh")
            return False
        
        try:
            from vosk import Model
            log(f"[VOSK] Loading model from: {self._model_path}")
            self._model = Model(self._model_path)
            log("[VOSK] Model loaded successfully")
            return True
        except ImportError:
            log("[VOSK] Error: vosk package not installed")
            log("[VOSK] Install with: pip install vosk")
            return False
        except Exception as e:
            log(f"[VOSK] Error loading model: {e}")
            return False
    
    def transcribe(self, audio_data: bytes, sample_rate: int = 16000) -> Optional[str]:
        """
        Transcribe audio bytes to text.
        
        Args:
            audio_data: Raw PCM audio bytes (16-bit signed, mono)
            sample_rate: Audio sample rate (default 16000 for Vosk)
            
        Returns:
            Transcribed text (lowercase) or None on error
        """
        if not self._ensure_model():
            return None
        
        try:
            from vosk import KaldiRecognizer
            
            rec = KaldiRecognizer(self._model, sample_rate)
            
            # Process audio in chunks for better performance
            chunk_size = 4000
            for i in range(0, len(audio_data), chunk_size):
                chunk = audio_data[i:i + chunk_size]
                rec.AcceptWaveform(chunk)
            
            # Get final result
            result = json.loads(rec.FinalResult())
            text = result.get("text", "").lower().strip()
            
            if text:
                log(f"[VOSK] Transcribed: '{text}'")
            else:
                log("[VOSK] No speech detected")
            
            return text
            
        except Exception as e:
            log(f"[VOSK] Transcription error: {e}")
            return None
    
    def is_available(self) -> bool:
        """Check if Vosk is installed and model exists."""
        try:
            import vosk
            return os.path.exists(self._model_path)
        except ImportError:
            return False
