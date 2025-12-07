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
    
    def start(self, chip_name: str = "unknown") -> bool:
        """Start recording to file. Returns True if recording started successfully."""
        if self._recording:
            log_error("Already recording!")
            return False
        
        # Generate filename with timestamp and chip name
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_name = "".join(c for c in chip_name if c.isalnum() or c in "._-")
        filename = f"recording_{safe_name}_{timestamp}.wav"
        self._current_file = os.path.join(RECORDINGS_DIR, filename)
        
        log_recording(f"🎙️  Starting recording: {filename}")
        
        # Check if arecord is available
        try:
            subprocess.run(["which", "arecord"], check=True, capture_output=True)
        except (FileNotFoundError, subprocess.CalledProcessError):
            log_error("arecord command not found in PATH")
            log_error("On Raspberry Pi, install with: sudo apt-get install alsa-utils")
            # Create placeholder file for simulation
            try:
                wav_header = b'RIFF' + (0).to_bytes(4, 'little') + b'WAVE' + b'fmt ' + (16).to_bytes(4, 'little') + \
                            (1).to_bytes(2, 'little') + (CHANNELS).to_bytes(2, 'little') + \
                            (SAMPLE_RATE).to_bytes(4, 'little') + \
                            (SAMPLE_RATE * CHANNELS * 2).to_bytes(4, 'little') + \
                            (CHANNELS * 2).to_bytes(2, 'little') + (16).to_bytes(2, 'little') + \
                            b'data' + (0).to_bytes(4, 'little')
                with open(self._current_file, 'wb') as f:
                    f.write(wav_header)
                log_recording(f"[SIMULATION] Created placeholder file: {self._current_file}")
                self._recording = True
                return True
            except Exception as e:
                log_error(f"[SIMULATION] Failed to create placeholder file: {e}")
                return False
        
        try:
            # Start arecord process
            log_recording(f"Starting arecord with device: {RECORDING_DEVICE}")
            self._process = subprocess.Popen([
                "arecord",
                "-D", RECORDING_DEVICE,
                "-f", AUDIO_FORMAT,
                "-r", str(SAMPLE_RATE),
                "-c", str(CHANNELS),
                self._current_file
            ], stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
            
            # Check if process started successfully
            time.sleep(0.1)  # Brief wait to check if process crashed immediately
            if self._process.poll() is not None:
                # Process exited immediately - likely an error
                stderr_output = self._process.stderr.read().decode() if self._process.stderr else "Unknown error"
                log_error(f"arecord process exited immediately: {stderr_output}")
                log_error(f"Check recording device: {RECORDING_DEVICE}")
                log_error("List available devices with: arecord -l")
                self._process = None
                return False
            
            self._recording = True
            log_success(f"Recording started: {self._current_file}")
            return True
        except FileNotFoundError:
            log_error("arecord executable not found")
            log_error("On Raspberry Pi, install with: sudo apt-get install alsa-utils")
            return False
        except Exception as e:
            log_error(f"Failed to start recording: {e}")
            self._current_file = None
            self._recording = False
            return False
    
    def stop(self) -> Optional[str]:
        """Stop recording and return file path"""
        if not self._recording:
            log_error("Not currently recording!")
            return None
        
        log_recording("⏹️  Stopping recording")
        
        if self._process:
            # Send SIGTERM to arecord to stop recording gracefully
            self._process.terminate()
            try:
                self._process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                log_error("arecord did not stop gracefully, killing process")
                self._process.kill()
                self._process.wait()
            
            # Check for errors
            if self._process.stderr:
                stderr_output = self._process.stderr.read().decode()
                if stderr_output:
                    log_error(f"arecord stderr: {stderr_output}")
            
            self._process = None
        
        self._recording = False
        saved_file = self._current_file
        self._current_file = None
        
        if saved_file:
            if os.path.exists(saved_file):
                size = os.path.getsize(saved_file)
                if size > 0:
                    log_success(f"Recording saved: {saved_file} ({size} bytes)")
                else:
                    log_error(f"Recording file is empty: {saved_file}")
            else:
                log_error(f"Recording file not found: {saved_file}")
                log_error("Check if arecord has write permissions to recordings directory")
        else:
            log_error("No file path saved - recording may not have started properly")
        
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
