"""
PN532 NFC reader (non-blocking read_uid)
"""

import time
from typing import Optional

from config.settings import PN532_I2C_ADDRESS, NFC_TIMEOUT
from utils.logger import log_nfc, log_error
from utils.hardware_health import HardwareHealthManager

# Hardware imports - will fail gracefully on non-Pi systems
try:
    import board
    import busio
    from adafruit_pn532.i2c import PN532_I2C
    HAS_HARDWARE = True
except ImportError:
    HAS_HARDWARE = False
    log_error("NFC hardware libraries not available - NFC scanning will not work")


# A reader that is not there (a loose wire, say) must not stop the speaker from starting:
# the buttons, the app and the music all work without it. We keep trying in the background.
NFC_INIT_RETRY_DELAY = 5  # seconds between attempts to connect to a missing reader
NFC_MISSING_LOG_INTERVAL = 60  # seconds between "still no reader" log lines


class NFCScanner:
    """PN532 NFC reader wrapper"""

    def __init__(self):
        """Try once to connect to the NFC reader. Never blocks and never fails if it is missing."""
        self._pn532 = None
        self._last_uid: Optional[str] = None
        self._attempts = 0
        self._last_attempt = float("-inf")
        self._last_missing_log = float("-inf")

        # Register with health manager for error throttling
        self._health = HardwareHealthManager.get_instance().register(
            "nfc",
            expected_errors=[
                "Input/output error",
                "Response frame preamble does not contain 0x00FF",
                "Did not receive expected ACK from PN532",
                "Timeout waiting for",
            ],
            log_interval=5.0,
            failure_threshold=50  # NFC has more transient errors, higher threshold
        )

        if not HAS_HARDWARE:
            log_error("NFC hardware libraries not available - NFC stays off")
            return

        # One try now. The service thread keeps trying (see read_uid) if the reader is not there.
        self._try_connect()

    def _try_connect(self):
        """One attempt to connect to the reader. Rate-limited, quick, never raises."""
        if self._pn532 is not None:
            return
        now = time.monotonic()
        if now - self._last_attempt < NFC_INIT_RETRY_DELAY:
            return
        self._last_attempt = now
        self._attempts += 1

        try:
            i2c = busio.I2C(board.SCL, board.SDA)
            pn532 = PN532_I2C(i2c, address=PN532_I2C_ADDRESS, debug=False)
            pn532.SAM_configuration()
            fw = pn532.firmware_version
        except Exception as e:
            self._pn532 = None
            if now - self._last_missing_log >= NFC_MISSING_LOG_INTERVAL:
                self._last_missing_log = now
                log_error(
                    f"NFC reader not available (attempt {self._attempts}): {e} - "
                    f"the speaker keeps running and retries every {NFC_INIT_RETRY_DELAY}s"
                )
            return

        self._pn532 = pn532
        log_nfc(f"PN532 initialized successfully, firmware: {fw} (attempt {self._attempts})")

    def read_uid(self) -> Optional[str]:
        """
        Non-blocking read of NFC chip UID.
        Returns UID string if chip present, None otherwise.
        Errors are expected when no chip is present, so we use health manager
        for rate-limited, filtered error logging.
        """
        if self._pn532 is None:
            # No reader right now. Try to connect (rate-limited), and pause as long as a
            # normal read would, so the NFC thread does not spin.
            if HAS_HARDWARE:
                self._try_connect()
            time.sleep(NFC_TIMEOUT)
            return None

        try:
            uid = self._pn532.read_passive_target(timeout=NFC_TIMEOUT)
            if uid is not None:
                # Convert to uppercase hex string (e.g., "9903EEB9")
                uid_str = ''.join(f'{b:02X}' for b in uid)
                self._health.report_success()
                return uid_str
            return None
        except Exception as e:
            # Use health manager for rate-limited, filtered error logging
            if self._health.report_error(e):
                log_error(f"NFC read error: {e}")

            # Check for persistent failure - try to reinitialize
            if self._health.is_failed():
                log_error("NFC reader failed - attempting to reinitialize...")
                self._pn532 = None
                self._health.reset()  # Reset health tracking for fresh start
                self._last_attempt = float("-inf")  # try again right away
                self._try_connect()

            return None

    def close(self):
        """Clean up NFC reader resources"""
        log_nfc("NFC Scanner closed")
        self._pn532 = None
