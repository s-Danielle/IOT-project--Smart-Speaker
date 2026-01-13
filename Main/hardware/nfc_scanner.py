"""
PN532 NFC reader (non-blocking read_uid)
"""

from typing import Optional
import time


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
    log_error("NFC hardware libraries not available - NFC scanning will not work")


class NFCScanner:
    """PN532 NFC reader wrapper"""
    
    def __init__(self):
        """Initialize NFC reader"""
        self._pn532 = None
        self._last_uid: Optional[str] = None
        self._last_error_log_time = 0.0
        self._error_log_interval = 5.0  # Only log errors every 5 seconds
        
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
            log_error("NFC Scanner not available - hardware libraries missing")
    
    def read_uid(self) -> Optional[str]:
        """
        Non-blocking read of NFC chip UID. 
        Returns UID string if chip present, None otherwise.
        Errors are expected when no chip is present, so we rate-limit error logging.
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
            # Rate-limit error logging to avoid spam when no chip is present
            # Most errors are expected (no chip, I/O errors, communication issues)
            error_msg = str(e)
            
            # Suppress common expected errors completely
            expected_errors = [
                "Input/output error",
                "Response frame preamble does not contain 0x00FF",
                "Did not receive expected ACK from PN532",
                "Timeout waiting for",
            ]
            
            is_expected = any(expected in error_msg for expected in expected_errors)
            
            if not is_expected:
                # Only log unexpected errors, and rate-limit them
                current_time = time.time()
                if current_time - self._last_error_log_time >= self._error_log_interval:
                    log_error(f"NFC read error: {e}")
                    self._last_error_log_time = current_time
            
            return None
    
    def close(self):
        """Clean up NFC reader resources"""
        log_nfc("NFC Scanner closed")
        self._pn532 = None
