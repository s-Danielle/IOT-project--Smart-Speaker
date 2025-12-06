import board
import busio
from adafruit_pn532.i2c import PN532_I2C

# Create I2C object on Pi I2C bus 1
i2c = busio.I2C(board.SCL, board.SDA)

# Your device address:
PN532_ADDR = 0x24

pn532 = PN532_I2C(i2c, address=PN532_ADDR, debug=False)

# Wake up and configure SAM (required)
pn532.SAM_configuration()

fw = pn532.firmware_version
print("Found PN532 with firmware version:", fw)

