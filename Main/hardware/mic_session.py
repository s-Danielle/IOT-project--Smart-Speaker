"""
Exclusive mic ownership: one arecord at a time, media silenced while held.
"""

import threading
from typing import Callable, Optional

from utils.logger import log_event


class MicSession:
    """Lock around capture. Acquiring pauses Mopidy; releasing may resume it.

    PTT and voice-memo recording both spawn `arecord`. Whichever acquires
    first owns the mic; the other gets False and must not start capture.
    Media is paused (not stopped) so a later restore keeps the track
    position. Feedback WAVs share the card via dmix, so they are stopped
    too — otherwise they bleed into the recording.
    """

    def __init__(self, audio_player, silence_feedback: Optional[Callable[[], None]] = None):
        self._audio = audio_player
        self._silence_feedback = silence_feedback
        self._lock = threading.Lock()
        self._owner: Optional[str] = None
        self._paused_media = False

    def acquire(self, owner: str) -> bool:
        """Claim the mic and silence output. Returns False if already held."""
        with self._lock:
            if self._owner is not None:
                log_event(f"[MIC] Busy (held by {self._owner}, refused {owner})")
                return False

            self._owner = owner
            if self._silence_feedback is not None:
                self._silence_feedback()

            if self._audio.is_playing(force_refresh=True):
                log_event(f"[MIC] Acquired by {owner} (pausing media)")
                self._audio.pause()
                self._paused_media = True
            else:
                log_event(f"[MIC] Acquired by {owner}")
                self._paused_media = False
            return True

    def release(self, restore: bool = True) -> None:
        """Drop the claim. Resume media only if this session paused it."""
        with self._lock:
            if self._owner is None:
                return

            owner = self._owner
            should_resume = self._paused_media and restore
            self._owner = None
            self._paused_media = False

            if should_resume:
                log_event(f"[MIC] Released by {owner} (restoring media)")
                self._audio.resume()
            else:
                log_event(f"[MIC] Released by {owner}")

    def is_held(self) -> bool:
        with self._lock:
            return self._owner is not None

    @property
    def owner(self) -> Optional[str]:
        with self._lock:
            return self._owner
