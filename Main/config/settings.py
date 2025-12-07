"""
Constants: timings, I2C addresses, etc.
"""

# Timing constants (in seconds)
LOOP_INTERVAL = 0.05  # 50ms main loop interval
RECORD_HOLD_DURATION = 3.0  # Hold duration to arm recording
CLEAR_CHIP_HOLD_DURATION = 3.0  # Hold duration to clear chip
PLAY_LATEST_HOLD_DURATION = 2.0  # Hold duration on Play/Pause to play latest recording

# I2C addresses
PCF8574_ADDRESS = 0x27  # Button expander address
PN532_I2C_ADDRESS = 0x24  # NFC reader address

# Button bit positions on PCF8574 (active-low)
BUTTON_PLAY_PAUSE_BIT = 0  # P0
BUTTON_RECORD_BIT = 1       # P1
BUTTON_STOP_BIT = 2         # P2

# Audio settings
SAMPLE_RATE = 44100
CHANNELS = 1
AUDIO_FORMAT = "S16_LE"

# Mopidy settings
MOPIDY_HOST = "localhost"
MOPIDY_PORT = 6680

# NFC settings
NFC_TIMEOUT = 0.1  # Short timeout for non-blocking reads

# Recording settings
RECORDING_DEVICE = "plughw:0,0"  # ALSA device for recording
