import RPi.GPIO as GPIO
from mfrc522 import SimpleMFRC522
import time

reader = SimpleMFRC522()

print("=========================================")
print("🟢 BATCH RFID WRITER (OVERWRITE SAFE)")
print("🛑 Press Ctrl+C in this terminal to quit.")
print("=========================================")

try:
    while True:
        print("\n-----------------------------------------")
        text = input('🌺 Enter the flower name to save (e.g., rose): ')    
        
        if not text.strip():
            print("⚠️ Input was empty. Please enter a valid name.")
            continue
            
        print("📡 Place your card near the reader to check it...")
        
        # --- 1. THE CHECK PHASE ---
        try:
            # This will wait until a card is placed
            id, current_text = reader.read()
            
            # If the card has data (ignoring empty spaces)
            if current_text and current_text.strip():
                print(f"\n⚠️ WARNING: This card is NOT empty!")
                print(f"It currently contains: '{current_text.strip()}'")
                
                # Ask for permission to overwrite
                overwrite = input("Do you want to overwrite it? (y/n): ")
                if overwrite.lower() != 'y':
                    print("⏭️ Skipping this card. Please remove it and get a new one.")
                    time.sleep(1.5)
                    continue # Skips back to asking for a flower name
            else:
                print("✨ Card is empty. Proceeding to write...")
                
        except Exception as e:
            print(f"⚠️ Error reading card: {e}. Let's try again.")
            time.sleep(1)
            continue
            
        # --- 2. THE WRITE PHASE ---
        success = False
        print("\n📡 Keep the card on the reader to write...")
        
        while not success:
            try:
                reader.write(text)
                time.sleep(0.5)     
                
                print("Verifying data...")
                id, written_text = reader.read()
                
                if written_text and written_text.strip() == text.strip():
                    print(f"✅ SUCCESS! ID: {id} | Data: '{written_text.strip()}'")
                    print("👉 You can remove this card. Ready for the next one!")
                    success = True
                else:
                    print("❌ Auth Error or Write Failed. Keep holding the card still...")
                    time.sleep(1.5)
                    
            except Exception as e:
                print(f"⚠️ Error during write: {e}. Adjust the card and trying again...")
                time.sleep(1)

except KeyboardInterrupt:
    print("\n\n🛑 Batch writing stopped. Quitting safely...")

finally:
    GPIO.cleanup()