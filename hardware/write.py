import RPi.GPIO as GPIO
from mfrc522 import SimpleMFRC522
import time

reader = SimpleMFRC522()

print("=========================================")
print("🟢 BATCH RFID WRITER (READ-FIRST MODE)")
print("🛑 Press Ctrl+C in this terminal to quit.")
print("=========================================")

try:
    while True:
        print("\n" + "="*41)
        print("📡 1. Place a card on the reader to start...")
        
        # --- PHASE 1: ROBUST READ ---
        current_text = None
        card_id = None
        
        # Loop endlessly until a card is successfully read
        while True:
            try:
                card_id, raw_text = reader.read()
                current_text = raw_text.strip() if raw_text else ""
                
                print(f"✅ Card detected! (ID: {card_id})")
                if current_text:
                    print(f"📄 Current data on card: '{current_text}'")
                else:
                    print("✨ Card is currently empty.")
                
                # Break out of the read loop since we succeeded
                break 
                
            except Exception:
                # If the scanner glitches, ignore the error and try reading again instantly
                time.sleep(0.1)
                continue 

        # --- PHASE 2: GET USER INPUT ---
        print("\n⌨️  2. KEEP THE CARD ON THE READER.")
        text_to_write = input("Enter flower name to write (or press Enter to skip): ")
        
        # If you hit enter without typing, skip to the next card
        if not text_to_write.strip():
            print("⏭️ Skipping this card. Please remove it and get the next one.")
            time.sleep(2)
            continue
            
        # --- PHASE 3: ROBUST WRITE & VERIFY ---
        print(f"\n✍️  3. Writing '{text_to_write}' to card...")
        success = False
        
        while not success:
            try:
                # Attempt the write
                reader.write(text_to_write)
                time.sleep(0.2) # Brief pause so the chip can process
                
                # Immediately try to read it back to verify
                _, verify_text = reader.read()
                
                if verify_text and verify_text.strip() == text_to_write.strip():
                    print(f"🎉 SUCCESS! Data verified: '{verify_text.strip()}'")
                    print("👉 You can remove this card now. Get ready for the next one.")
                    success = True
                else:
                    print("⚠️ Verification failed. Retrying... Keep card still.")
                    time.sleep(0.5)
                    
            except Exception:
                # If it loses connection during write/read, catch it and try again
                print("⚠️ Scanner glitch during write. Retrying... Keep card still.")
                time.sleep(0.5)
                
        # Give you a brief moment to remove the card before the main loop restarts
        time.sleep(1.5)

except KeyboardInterrupt:
    print("\n\n🛑 Batch writing stopped. Quitting safely...")

finally:
    # Always clean up GPIO pins to prevent hardware locks on the next run
    GPIO.cleanup()