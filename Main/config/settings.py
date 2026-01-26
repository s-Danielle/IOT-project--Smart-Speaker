"""
Constants: timings, I2C addresses, etc.
"""

# Timing constants (in seconds)
LOOP_INTERVAL = 0.05  # 50ms main loop interval
RECORD_HOLD_DURATION = 5.0  # Hold duration to arm recording
CLEAR_CHIP_HOLD_DURATION = 3.0  # Hold duration to clear chip
PLAY_LATEST_HOLD_DURATION = 2.0  # Hold duration on Play/Pause to play latest recording

# Long press actions (Health Monitor)
LONG_PRESS_REBOOT_DURATION = 5.0  # Hold Volume Up for 5s to reboot
LONG_PRESS_RESTART_SERVICES_DURATION = 5.0  # Hold Volume Down for 5s to restart services

# Playback monitoring (handles variable Spotify loading times)
MAX_WAIT_FOR_PLAYBACK = 60.0  # Max seconds to wait for Mopidy to confirm playback started
MIN_PLAYBACK_DURATION = 2.0   # Min seconds of confirmed playback before considering "finished"

# I2C addresses
PCF8574_ADDRESS = 0x20  # Button expander address
PCF8574_RGB_ADDRESS = 0x21  # RGB LED expander address
PN532_I2C_ADDRESS = 0x24  # NFC reader address

# RGB LED pin mappings (B, G, R order - not R, G, B!)
# Light 1 (Health):  P0=B, P1=G, P2=R on 0x21
# Light 2 (PTT):     P3=B, P4=G, P5=R on 0x21
# Light 3 (Speaker): P6=B, P7=G on 0x21, P6=R on 0x20 (divided LED)
RGB_LIGHT1_PINS = (0, 1, 2)  # Health LED
RGB_LIGHT2_PINS = (3, 4, 5)  # PTT LED

# Button bit positions on PCF8574 (active-low)
BUTTON_PLAY_PAUSE_BIT = 0  # P0
BUTTON_RECORD_BIT = 1       # P1
BUTTON_STOP_BIT = 2         # P2
BUTTON_VOLUME_UP_BIT = 3    # P3 (Button 4)
BUTTON_VOLUME_DOWN_BIT = 4  # P4 (Button 5)
BUTTON_PTT_BIT = 5          # P5 (Button 6) - Push-to-Talk voice commands

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
MAX_RECORDING_DURATION = 300.0  # Maximum recording duration in seconds (5 minutes)
MIN_DISK_SPACE_MB = 100  # Minimum free disk space in MB before allowing recording

# PTT (Push-to-Talk) Voice Command settings
PTT_ENABLED = True                          # Enable/disable PTT feature
PTT_LISTEN_DURATION = 5.0                   # Seconds to listen for voice command
PTT_WAKE_PHRASE = "hi speaker"              # Must say this before command
# Note: Uses Google Speech API (requires internet connection)
