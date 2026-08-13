"""
Card playback volume via the ALSA mixer (not Mopidy).
"""

import alsaaudio

from config.settings import (
    ALSA_CARD,
    ALSA_VOLUME_CONTROL,
    VOLUME_DEFAULT,
    VOLUME_STEP,
)
from utils.logger import log_audio, log_error


class Mixer:
    """0-100 volume on the card's PCM control."""

    def __init__(self):
        self._mixer = None
        try:
            self._mixer = alsaaudio.Mixer(ALSA_VOLUME_CONTROL, cardindex=ALSA_CARD)
            log_audio(
                f"Mixer initialized ({ALSA_VOLUME_CONTROL} on card {ALSA_CARD}, "
                f"volume {self._read_volume()})"
            )
        except alsaaudio.ALSAAudioError as e:
            log_error(
                f"Cannot open ALSA mixer '{ALSA_VOLUME_CONTROL}' on card {ALSA_CARD}: {e}"
            )

    def _read_volume(self) -> int:
        volumes = self._mixer.getvolume()
        if not volumes:
            return VOLUME_DEFAULT
        return min(int(v) for v in volumes)

    def get_volume(self) -> int:
        """Current volume (0-100). Returns VOLUME_DEFAULT if the mixer is unavailable."""
        if self._mixer is None:
            return VOLUME_DEFAULT
        try:
            return self._read_volume()
        except alsaaudio.ALSAAudioError as e:
            log_error(f"Failed to read volume: {e}")
            return VOLUME_DEFAULT

    def set_volume(self, volume: int) -> bool:
        """Set volume (0-100) on all channels. Returns True if successful."""
        volume = max(0, min(100, volume))
        if self._mixer is None:
            log_error(f"Cannot set volume to {volume}: mixer not available")
            return False
        try:
            self._mixer.setvolume(volume)
            log_audio(f"Volume set to {volume}")
            return True
        except alsaaudio.ALSAAudioError as e:
            log_error(f"Failed to set volume to {volume}: {e}")
            return False

    def volume_up(self) -> int:
        """Increase volume by VOLUME_STEP. Returns the new level."""
        new_volume = min(100, self.get_volume() + VOLUME_STEP)
        self.set_volume(new_volume)
        return new_volume

    def volume_down(self) -> int:
        """Decrease volume by VOLUME_STEP. Returns the new level."""
        new_volume = max(0, self.get_volume() - VOLUME_STEP)
        self.set_volume(new_volume)
        return new_volume
