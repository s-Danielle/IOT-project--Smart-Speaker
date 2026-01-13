"""
Central paths for sound files, recordings, tags.json
"""

import os

# Base directory (Main folder)
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Configuration files
TAGS_JSON = os.path.join(BASE_DIR, "config", "tags.json")

# Assets
ASSETS_DIR = os.path.join(BASE_DIR, "assets")
SOUNDS_DIR = os.path.join(ASSETS_DIR, "sounds")

# Recordings output - unified with uploads under local_files
RECORDINGS_DIR = os.path.join(BASE_DIR, "local_files", "recordings")

# Sound file paths (mapped to actual wav files)
SOUND_CHIP_LOADED = os.path.join(SOUNDS_DIR, "loaded_success.wav")
SOUND_PLAY = os.path.join(SOUNDS_DIR, "play.wav")
SOUND_PAUSE = os.path.join(SOUNDS_DIR, "pause.wav")
SOUND_STOP = os.path.join(SOUNDS_DIR, "stop.wav")
SOUND_ERROR = os.path.join(SOUNDS_DIR, "failed.wav")
SOUND_RECORD_START = os.path.join(SOUNDS_DIR, "countdown.wav")
SOUND_RECORD_SAVED = os.path.join(SOUNDS_DIR, "saves_success.wav")
SOUND_RECORD_CANCELED = os.path.join(SOUNDS_DIR, "reset.wav")
SOUND_BLOCKED = os.path.join(SOUNDS_DIR, "blocked.wav")
SOUND_RESET = os.path.join(SOUNDS_DIR, "reset.wav")
SOUND_SWIPE = os.path.join(SOUNDS_DIR, "swipe.wav")

