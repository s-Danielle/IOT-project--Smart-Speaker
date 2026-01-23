"""
Constants: timings, I2C addresses, etc.
"""

# Timing constants (in seconds)
LOOP_INTERVAL = 0.05  # 50ms main loop interval
RECORD_HOLD_DURATION = 3.0  # Hold duration to arm recording
CLEAR_CHIP_HOLD_DURATION = 3.0  # Hold duration to clear chip
PLAY_LATEST_HOLD_DURATION = 2.0  # Hold duration on Play/Pause to play latest recording

# Playback monitoring (handles variable Spotify loading times)
MAX_WAIT_FOR_PLAYBACK = 15.0  # Max seconds to wait for Mopidy to confirm playback started
MIN_PLAYBACK_DURATION = 2.0   # Min seconds of confirmed playback before considering "finished"

# I2C addresses
PCF8574_ADDRESS = 0x20  # Button expander address
PN532_I2C_ADDRESS = 0x24  # NFC reader address

# Button bit positions on PCF8574 (active-low)
BUTTON_PLAY_PAUSE_BIT = 0  # P0
BUTTON_RECORD_BIT = 1       # P1
BUTTON_STOP_BIT = 2         # P2
BUTTON_VOLUME_UP_BIT = 3    # P3 (Button 4)
BUTTON_VOLUME_DOWN_BIT = 4  # P4 (Button 5)

# Volume settings
VOLUME_STEP = 10  # Volume change per button press (0-100 scale)
VOLUME_DEFAULT = 50  # Default volume level

# Audio settings
SAMPLE_RATE = 44100
CHANNELS = 1
AUDIO_FORMAT = "S16_LE"

# HTTP Server settings (local API server)
SERVER_HOST = "localhost"
SERVER_PORT = 8080

# Mopidy settings
MOPIDY_HOST = "localhost"
MOPIDY_PORT = 6680  # HTTP JSON-RPC port (deprecated, kept for backward compatibility)
MPD_PORT = 6600  # MPD protocol port (used by python-mpd2)
STATUS_POLL_INTERVAL = 0.5  # Minimum seconds between Mopidy status polls (caching optimization)

# NFC settings
NFC_TIMEOUT = 0.05# Short timeout for non-blocking reads

# Recording settings
# Leave empty to use default ALSA device (recommended)
# Or specify device like "plughw:0,0" or "hw:0,0"
# List available devices with: arecord -l
RECORDING_DEVICE = ""  # Empty = use default device (matches RecordShortAudio.sh)
