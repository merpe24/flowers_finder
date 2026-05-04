import RPi.GPIO as GPIO
import time

GREEN_LED = 17

GPIO.setmode(GPIO.BCM)

GPIO.setup(GREEN_LED, GPIO.OUT)

GPIO.output(GREEN_LED, GPIO.HIGH)
time.sleep(1)

GPIO.cleanup()
