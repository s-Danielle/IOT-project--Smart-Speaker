"""
PN532 NFC reader (non-blocking read_uid)
"""

from typing import Optional
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config.settings import PN532_I2C_ADDRESS, NFC_TIMEOUT
from utils.logger import log_nfc, log_error

# Hardware imports - will fail gracefully on non-Pi systems
try:
    import board
    import busio
    from adafruit_pn532.i2c import PN532_I2C
    HAS_HARDWARE = True
except ImportError:
    HAS_HARDWARE = False
    log_error("NFC hardware libraries not available - running in simulation mode")


class NFCScanner:
    """PN532 NFC reader wrapper"""
    
    def __init__(self):
        """Initialize NFC reader"""
        self._pn532 = None
        self._last_uid: Optional[str] = None
        
        if HAS_HARDWARE:
            try:
                i2c = busio.I2C(board.SCL, board.SDA)
                self._pn532 = PN532_I2C(i2c, address=PN532_I2C_ADDRESS, debug=False)
                self._pn532.SAM_configuration()
                fw = self._pn532.firmware_version
                log_nfc(f"PN532 initialized, firmware: {fw}")
            except Exception as e:
                log_error(f"Failed to initialize NFC reader: {e}")
                self._pn532 = None
        else:
            log_nfc("NFC Scanner running in simulation mode")
    
    def read_uid(self) -> Optional[str]:
        """
        Non-blocking read of NFC chip UID. 
        Returns UID string if chip present, None otherwise.
        """
        if self._pn532 is None:
            return None
        
        try:
            uid = self._pn532.read_passive_target(timeout=NFC_TIMEOUT)
            if uid is not None:
                # Convert to string representation matching tags.json format
                uid_str = str(bytearray(uid))
                return uid_str
            return None
        except Exception as e:
            log_error(f"NFC read error: {e}")
            return None
    
    def close(self):
        """Clean up NFC reader resources"""
        log_nfc("NFC Scanner closed")
        self._pn532 = None
