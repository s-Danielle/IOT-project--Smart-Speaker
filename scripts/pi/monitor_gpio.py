#!/usr/bin/env python3
import RPi.GPIO as GPIO
import time

GPIO.setmode(GPIO.BCM)
GPIO.setup(12, GPIO.IN)
GPIO.setup(13, GPIO.IN)

try:
    while True:
        p12 = GPIO.input(12)
        p13 = GPIO.input(13)
        print(f"GPIO12: {p12}  GPIO13: {p13}")
        time.sleep(0.1)
except KeyboardInterrupt:
    pass
finally:
    GPIO.cleanup()
