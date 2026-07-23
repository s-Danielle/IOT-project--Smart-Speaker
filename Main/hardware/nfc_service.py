"""
NFCService: dedicated background thread that owns the PN532 and publishes
the latest UID for the main loop to query.

The service thread is the ONLY place that touches the NFC hardware. This keeps
all I2C access to the reader on a single thread and creates one seam
(`_run_loop`) where polling can later be swapped for IRQ-driven reads without
changing the controller.
"""

import threading
from typing import Optional

from hardware.nfc_scanner import NFCScanner
from utils.logger import log_nfc, log_error


class NFCService:
    """Owns an NFCScanner and continuously updates the current UID in a thread."""

    def __init__(self, scanner: Optional[NFCScanner] = None):
        # Constructing the scanner here preserves NFCScanner's init-with-retry
        # behavior. Only the service thread will use it after start().
        self._scanner = scanner if scanner is not None else NFCScanner()
        self._uid: Optional[str] = None
        self._lock = threading.Lock()
        self._thread: Optional[threading.Thread] = None
        self._running = False

    def start(self):
        """Start the background reader thread."""
        if self._thread is not None:
            return  # Already started
        self._running = True
        self._thread = threading.Thread(
            target=self._run_loop, name="nfc-service", daemon=True
        )
        self._thread.start()
        log_nfc("NFC service thread started")

    def _run_loop(self):
        """Continuously read the PN532 and cache the latest UID.

        read_uid() blocks up to NFC_TIMEOUT when no card is present, which sets
        the effective poll cadence - no extra sleep is needed here.
        """
        while self._running:
            try:
                uid = self._scanner.read_uid()
                with self._lock:
                    self._uid = uid
            except Exception as e:
                # The reader thread must never die - log and keep going.
                log_error(f"NFC service loop error: {e}")

    def get_current_uid(self) -> Optional[str]:
        """Return the most recently read UID (or None). Non-blocking."""
        with self._lock:
            return self._uid

    def close(self):
        """Stop the reader thread and release the scanner."""
        self._running = False
        if self._thread is not None:
            self._thread.join(timeout=2.0)
            self._thread = None
        self._scanner.close()
        log_nfc("NFC service closed")
