import cv2
from picamera2 import Picamera2
import time
# Import your specific RFID library here
import RPi.GPIO as GPIO
from mfrc522 import SimpleMFRC522 

# ==========================================
# 1. INITIALIZE HARDWARE
# ==========================================

# Setup RFID
reader = SimpleMFRC522()

# Setup Camera
picam2 = Picamera2()
config = picam2.create_preview_configuration({"size": (640, 480)})
picam2.configure(config)
picam2.start()

# Setup QR Detector
detector = cv2.QRCodeDetector()

print("=========================================")
print("🌸 WELCOME TO FLOWER FINDER!!! 🌸")
print("=========================================")

try:
    # ------------------------------------------
    # OUTER LOOP: Waiting for an RFID Card
    # ------------------------------------------
    while True:
        print("\n[STANDBY] Please insert an RFID card to select a flower...")
        
        # RFID read
        card_id, card_text = reader.read()

        if not card_text:
            print(" READ ERROR: Please try again")
            time.sleep(1)
            continue
        
        #Clear bytes and strip
        target_flower = card_text.replace('\x00', '').strip().lower()

        if not target_flower:
            print(" READ ERROR: Card is blank or missed. Try again.")
            time.sleep(1)
            continue	
        
        print(f"\n🎯 SELECTED FLOWER: {target_flower.upper()}")
        print(" YOU HAVE 60 SECONDS. GO GO GO!!!")
        print("📷 Point the camera at QR codes to find the match...")
        
        
        time.sleep(1)

        # ------------------------------------------
        # INNER LOOP: Find the QR Code
        # ------------------------------------------
        flower_found = False

        time_limit = 60
        start_time = time.time()
        
        while not flower_found:
            # Check the clock
            time_left = time_limit - (time.time() - start_time)
            
            if time_left <= 0:
                print(f"\n GAME OVER! You ran out of time looking for the {target_flower.upper()}.")
                print("Try again!")
                time.sleep(3)
                break
      
            if int(time_left) % 5 == 0 and int(time_left) != 0:
                print(f"Time left: {int(time_left)} secondes...", end='\r')

            # Grab a frame
            try:
                img = picam2.capture_array()
            except Exception:
                continue
            
            if img is None:
                continue
            
            # Look for QR
            data, bbox, _ = detector.detectAndDecode(img)
            
            if bbox is not None and data:
                scanned_flower = data.strip().lower()
                
                # Check for a match
                if scanned_flower == target_flower:
                    print(f"✅NOICE, you found the {target_flower.upper()}!")
                    # TODO: Communicate with led or buzzer (Green led if success?)
                    
                    flower_found = True 
                    time.sleep(2) 
                
                else:
                    print(f"❌ Wrong flower. That is a {scanned_flower.upper()}. Keep looking!")
                    # TODO: Work with led to (Red led? buzzer noise?)
                    
                    
                    time.sleep(1.5)

except KeyboardInterrupt:
    print("\n🛑 BYE BYEEEE...")

finally:
    # Clean up everything
    GPIO.cleanup()
    picam2.stop()
