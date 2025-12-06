import board
import busio
from adafruit_pn532.i2c import PN532_I2C
import time

i2c = busio.I2C(board.SCL, board.SDA)
pn532 = PN532_I2C(i2c, address=0x24)
pn532.SAM_configuration()

print("Tap an NFC card...")

while True:
    uid = pn532.read_passive_target(timeout=0.5)
    if uid is not None:
        print("Card detected! UID:", [hex(i) for i in uid])
    else:
        print("No card detected")
        time.sleep(1)
