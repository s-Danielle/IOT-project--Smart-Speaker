"""
Start/stop/cancel recordings (arecord)
"""

import subprocess
import os
import time
from typing import Optional
from datetime import datetime
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config.paths import RECORDINGS_DIR
from config.settings import SAMPLE_RATE, CHANNELS, AUDIO_FORMAT, RECORDING_DEVICE
from utils.logger import log_recording, log_error, log_success


class Recorder:
    """Audio recorder using arecord"""
    
    def __init__(self):
        """Initialize recorder"""
        self._process: Optional[subprocess.Popen] = None
        self._current_file: Optional[str] = None
        self._recording = False
        
        # Ensure recordings directory exists
        os.makedirs(RECORDINGS_DIR, exist_ok=True)
        log_recording(f"Recorder initialized (output dir: {RECORDINGS_DIR})")
    
    def start(self, chip_name: str = "unknown"):
        """Start recording to file"""
        if self._recording:
            log_error("Already recording!")
            return
        
        # Generate filename with timestamp and chip name
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_name = "".join(c for c in chip_name if c.isalnum() or c in "._-")
        filename = f"recording_{safe_name}_{timestamp}.wav"
        self._current_file = os.path.join(RECORDINGS_DIR, filename)
        
        log_recording(f"🎙️  Starting recording: {filename}")
        
        try:
            # Start arecord process
            self._process = subprocess.Popen([
                "arecord",
                "-D", RECORDING_DEVICE,
                "-f", AUDIO_FORMAT,
                "-r", str(SAMPLE_RATE),
                "-c", str(CHANNELS),
                self._current_file
            ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            self._recording = True
            log_success(f"Recording started: {self._current_file}")
        except FileNotFoundError:
            log_error("arecord not found - running in simulation mode")
            self._recording = True  # Simulate recording
            log_recording("[SIMULATION] Recording started")
        except Exception as e:
            log_error(f"Failed to start recording: {e}")
            self._current_file = None
    
    def stop(self) -> Optional[str]:
        """Stop recording and return file path"""
        if not self._recording:
            log_error("Not currently recording!")
            return None
        
        log_recording("⏹️  Stopping recording")
        
        if self._process:
            self._process.terminate()
            try:
                self._process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                self._process.kill()
            self._process = None
        
        self._recording = False
        saved_file = self._current_file
        self._current_file = None
        
        if saved_file and os.path.exists(saved_file):
            size = os.path.getsize(saved_file)
            log_success(f"Recording saved: {saved_file} ({size} bytes)")
        else:
            log_recording("[SIMULATION] Recording saved")
        
        return saved_file
    
    def cancel(self):
        """Cancel recording (delete file)"""
        if not self._recording:
            return
        
        log_recording("❌ Canceling recording")
        
        if self._process:
            self._process.terminate()
            try:
                self._process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                self._process.kill()
            self._process = None
        
        # Delete the file
        if self._current_file and os.path.exists(self._current_file):
            try:
                os.remove(self._current_file)
                log_recording(f"Deleted canceled recording: {self._current_file}")
            except Exception as e:
                log_error(f"Failed to delete recording: {e}")
        
        self._recording = False
        self._current_file = None
        log_success("Recording canceled")
    
    def is_recording(self) -> bool:
        """Check if currently recording"""
        return self._recording
    
    def close(self):
        """Clean up recorder resources"""
        if self._recording:
            self.cancel()
        log_recording("Recorder closed")
