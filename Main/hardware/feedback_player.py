"""
Play a WAV through ALSA without touching the Mopidy tracklist.
"""

import os
import shutil
import signal
import subprocess
import threading
from typing import Optional

from config.settings import FEEDBACK_PCM
from utils.logger import log_audio, log_error


class FeedbackPlayer:
    """aplay-backed playback of UI feedback WAVs on a dedicated PCM."""

    def __init__(self, pcm: str = None):
        self._pcm = pcm or FEEDBACK_PCM
        self._lock = threading.Lock()
        self._process: Optional[subprocess.Popen] = None
        self._aplay = shutil.which("aplay")
        if self._aplay is None:
            log_error("aplay not found in PATH; UI feedback sounds disabled")
            log_error("On Raspberry Pi, install with: sudo apt-get install alsa-utils")
        else:
            log_audio(f"Feedback player initialized (PCM: {self._pcm})")

    def play(self, path: str):
        """Start playing a WAV, replacing any still-running feedback sound."""
        if self._aplay is None:
            log_error(f"Cannot play {path}: aplay not available")
            return

        if not os.path.exists(path):
            log_error(f"Sound file not found: {path}")
            return

        with self._lock:
            self._stop_locked()
            try:
                self._process = subprocess.Popen(
                    [self._aplay, "-q", "-D", self._pcm, path],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.PIPE,
                )
            except OSError as e:
                log_error(f"Failed to start aplay: {e}")
                self._process = None

    def stop(self):
        """Stop the current feedback sound, if any."""
        with self._lock:
            self._stop_locked()

    def close(self):
        """Tear down the player."""
        self.stop()

    def _stop_locked(self):
        proc = self._process
        self._process = None
        if proc is None:
            return

        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=0.2)
            except subprocess.TimeoutExpired:
                proc.kill()
                try:
                    proc.wait(timeout=0.2)
                except subprocess.TimeoutExpired:
                    log_error("aplay did not exit after SIGKILL")
                    return

        stderr = b""
        if proc.stderr is not None:
            try:
                stderr = proc.stderr.read()
            except OSError:
                pass
        if proc.returncode not in (0, None, -signal.SIGTERM, -signal.SIGKILL):
            err = stderr.decode(errors="replace").strip()
            log_error(f"aplay exited {proc.returncode}: {err or 'no stderr'}")
