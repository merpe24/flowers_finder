import RPi.GPIO as GPIO
from mfrc522 import SimpleMFRC522
import time

reader = SimpleMFRC522()

try:
    success = False
    print("Hold a tag near the reader...")

    while not success:
        
        id, text = reader.read()
        
        if text and text.strip():
            print(f"Success! ID: {id}")
            print(f"Data Written: {text.strip()}")
            
            success = True

        else:
            print("Error read. Try again")
            time.sleep(1)
        

except KeyboardInterrupt:
    print("\nQuitting...")

finally:
    GPIO.cleanup()