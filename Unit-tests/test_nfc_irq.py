#!/usr/bin/env python3
"""Verify PN532 IRQ is wired to GPIO 13. Run on the Pi."""

import sys
import time

import board
import busio
from adafruit_pn532.i2c import PN532_I2C
from digitalio import DigitalInOut

PN532_ADDR = 0x24
IRQ_GPIO = 13
TIMEOUT = 30

irq = DigitalInOut(getattr(board, f"D{IRQ_GPIO}"))
i2c = busio.I2C(board.SCL, board.SDA)
pn532 = PN532_I2C(i2c, address=PN532_ADDR, irq=irq, debug=False)
pn532.SAM_configuration()

print(f"Hold an NFC chip on the reader (GPIO {IRQ_GPIO} IRQ)...")
deadline = time.monotonic() + TIMEOUT

while time.monotonic() < deadline:
    if not irq.value:  # active low
        print("PASS: IRQ received")
        sys.exit(0)
    pn532.listen_for_passive_target(timeout=0.2)

print("FAIL: No IRQ within timeout — check wiring to GPIO 13")
sys.exit(1)
