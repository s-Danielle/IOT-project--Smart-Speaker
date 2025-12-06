from smbus2 import SMBus
import time

bus = SMBus(1)
ADDR = 0x20  # PCF8574

while True:
    value = bus.read_byte(ADDR)
    p0 = value & 0b00000001  # read bit 0

    if p0 == 0:
        print("Button pressed!")
    else:
        print("Button not pressed")

    time.sleep(0.2)
