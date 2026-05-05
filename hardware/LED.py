import RPi.GPIO as GPIO
import time

GREEN_LED = 17
RED_LED = 27
BUZZER = 22

GPIO.setmode(GPIO.BCM)

GPIO.setup(GREEN_LED, GPIO.OUT)
GPIO.setup(RED_LED, GPIO.OUT)
GPIO.setup(BUZZER, GPIO.OUT)


try:
    while True:
        GPIO.output(GREEN_LED, GPIO.HIGH)
        GPIO.output(RED_LED, GPIO.HIGH)
        GPIO.output(BUZZER, GPIO.HIGH)
        time.sleep(1)

        GPIO.output(GREEN_LED, GPIO.LOW)
        GPIO.output(RED_LED, GPIO.LOW)
        GPIO.output(BUZZER, GPIO.LOW)
        time.sleep(1)

except KeyboardInterrupt:
    print("\nQuitting...")
    
finally:
    GPIO.cleanup()
