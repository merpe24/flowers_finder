import RPi.GPIO as GPIO
from mfrc522 import SimpleMFRC522

reader = SimpleMFRC522()

# Tell the reader to look in the new sector!
reader.BLOCK_ADDR = 12
reader.TRAILER_BLOCK = 15

try:
    print("Place your tag to read...")
    id, text = reader.read()
    print("The Card ID is:", id)
    print("The Text inside is:", text)
finally:
    GPIO.cleanup()
