import spidev
from mfrc522 import SimpleMFRC522
import time

reader = SimpleMFRC522()

try:
    print("Hold a tag near the reader...")
    id, text = reader.read()
    print(f"ID: {id}")
    print(f"Text: {text}")
finally:
    pass

