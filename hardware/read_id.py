import RPi.GPIO as GPIO
from mfrc522 import SimpleMFRC522
import time

reader = SimpleMFRC522()

try:
    while True:
        print("Hold a tag near the reader...")
        
        # CHANGED: We are only asking for the ID, not the text data
        id = reader.read_id()
        
        print(f"Success! ID: {id}")
        time.sleep(1)

except KeyboardInterrupt:
    print("\nQuitting...")

finally:
    GPIO.cleanup()