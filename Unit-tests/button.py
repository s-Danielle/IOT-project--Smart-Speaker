import RPi.GPIO as GPIO
import time

BUTTON = 17

GPIO.setmode(GPIO.BCM)
GPIO.setup(BUTTON, GPIO.IN)

was_on = False
print("press the button!")
i = 0
while True:
    state = GPIO.input(BUTTON)
    if not state:
        print("the button was pressed. good bye.")
        break
    elif i > 40:
        print("i aint got all day. good bye")
        break

    time.sleep(0.25)
    i = i + 1
