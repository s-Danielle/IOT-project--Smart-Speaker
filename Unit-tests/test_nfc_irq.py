#!/usr/bin/env python3
"""Verify that the PN532 can read an NFC tag using IRQ on GPIO 13. Run on the Pi."""

import sys
import time

import board
import busio
from adafruit_pn532.i2c import PN532_I2C
from digitalio import DigitalInOut

PN532_ADDR = 0x24
IRQ_PIN = DigitalInOut(board.D13)
TIMEOUT = 30

i2c = busio.I2C(board.SCL, board.SDA)
pn532 = PN532_I2C(i2c, address=PN532_ADDR, irq=IRQ_PIN, debug=False)
pn532.SAM_configuration()

fw = pn532.firmware_version
print(f"PN532 firmware: {fw}")

print(f"Waiting up to {TIMEOUT}s for an NFC tag (IRQ on GPIO 13)...")
deadline = time.monotonic() + TIMEOUT

while time.monotonic() < deadline:
    uid = pn532.read_passive_target(timeout=0.5)
    if uid is not None:
        print(f"PASS: Read tag UID = {uid.hex(':')}")
        sys.exit(0)

print("FAIL: No NFC tag detected within timeout")
sys.exit(1)
