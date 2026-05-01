import RPi.GPIO as GPIO
from mfrc522 import SimpleMFRC522

reader = SimpleMFRC522()

# HIJACK THE LIBRARY: Move away from the broken Sector 8
# We will use Sector 3 (Block 12, Trailer 15)
reader.BLOCK_ADDR = 12
reader.TRAILER_BLOCK = 15

try:
    text = input('New data: ')
    print("Now place your tag flat and DO NOT MOVE IT for 3 seconds...")
    reader.write(text)
    print("Successfully Written to the new sector!")
finally:
    GPIO.cleanup()
