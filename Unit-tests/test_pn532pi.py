#!/usr/bin/env python3
"""
Unit test for the PN532 NFC reader using the pn532pi library
instead of the Adafruit CircuitPython library.

Install:  pip install pn532pi
Hardware: PN532 connected via I2C on bus 1
"""

import sys
import time
import binascii

from pn532pi import Pn532I2c, Pn532, pn532

PN532_I2C_BUS = 1
TAG_READ_TIMEOUT = 30  # seconds to wait for a tag


def test_init():
    """Initialize the PN532 over I2C and verify communication."""
    print("=== Test: PN532 Initialization ===")

    i2c = Pn532I2c(PN532_I2C_BUS)
    nfc = Pn532(i2c)
    nfc.begin()

    versiondata = nfc.getFirmwareVersion()
    if not versiondata:
        print("FAIL: Could not communicate with PN532 — no firmware version returned")
        return None

    ic = (versiondata >> 24) & 0xFF
    ver = (versiondata >> 16) & 0xFF
    rev = (versiondata >> 8) & 0xFF
    print(f"PASS: Found chip PN5{ic:#x}, firmware {ver}.{rev}")

    nfc.setPassiveActivationRetries(0xFF)
    nfc.SAMConfig()
    print("PASS: SAM configured successfully")
    return nfc


def test_read_tag(nfc):
    """Wait for an ISO14443A tag and read its UID."""
    print(f"\n=== Test: Read NFC Tag (timeout {TAG_READ_TIMEOUT}s) ===")
    print("Place an NFC tag on the reader...")

    deadline = time.monotonic() + TAG_READ_TIMEOUT

    while time.monotonic() < deadline:
        success, uid = nfc.readPassiveTargetID(pn532.PN532_MIFARE_ISO14443A_106KBPS)
        if success:
            uid_hex = binascii.hexlify(uid).decode("ascii").upper()
            print(f"PASS: Read tag UID = {uid_hex} (length: {len(uid)} bytes)")
            return uid_hex
        time.sleep(0.25)

    print("FAIL: No NFC tag detected within timeout")
    return None


def main():
    nfc = test_init()
    if nfc is None:
        print("\nRESULT: FAIL — could not initialize PN532")
        sys.exit(1)

    uid = test_read_tag(nfc)
    if uid is None:
        print("\nRESULT: FAIL — no tag read")
        sys.exit(1)

    print(f"\nRESULT: ALL PASSED (tag UID: {uid})")
    sys.exit(0)


if __name__ == "__main__":
    main()
