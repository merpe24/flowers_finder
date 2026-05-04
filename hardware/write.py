import RPi.GPIO as GPIO
from mfrc522 import SimpleMFRC522
import time

reader = SimpleMFRC522()

try:
    text = input('Enter the flower name to save to this card (e.g., rose): ')    
    success = False
    
    while not success:
        print("\nAttempting to write...")
        reader.write(text)
        
        time.sleep(0.5) 
        
        print("Verifying data...")
        id, written_text = reader.read()
        
        if written_text and written_text.strip() == text.strip():
            print(f"✅ Success! Verified data on card: {written_text.strip()}")
            success = True
        else:
            print("❌ Auth Error or Write Failed. Keep holding the card still...")
            time.sleep(1.5)

except KeyboardInterrupt:
    print("\nQuitting...")

finally:
    GPIO.cleanup()