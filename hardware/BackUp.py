import cv2
from picamera2 import Picamera2
import time
import threading
# Import your specific RFID library here
import RPi.GPIO as GPIO
from mfrc522 import SimpleMFRC522 #allows us to read the cards

# ==========================================
# 1. INITIALIZE HARDWARE
# ==========================================

#Declaring LED pins
GREEN_LED = 17 
RED_LED = 27
BUZZER = 22

GPIO.setmode(GPIO.BCM)
GPIO.setup(GREEN_LED, GPIO.OUT)
GPIO.setup(RED_LED, GPIO.OUT)
 
# Ensure LEDs start OFF
GPIO.output(GREEN_LED, GPIO.LOW)
GPIO.output(RED_LED, GPIO.LOW)
GPIO.setup(BUZZER, GPIO.OUT)
GPIO.output(BUZZER, GPIO.LOW) 
# Setup RFID
def buzz(duration=0.2):
    GPIO.output(BUZZER, GPIO.HIGH)
    time.sleep(duration)
    GPIO.output(BUZZER, GPIO.LOW)

def success_sound():
    # happy double beep
    buzz(0.2)
    time.sleep(0.1)
    buzz(0.2)

def error_sound():
    # longer sad buzz
    buzz(0.5)

def timeout_sound():
    # fast triple beep
    for _ in range(3):
        buzz(0.2)
        time.sleep(0.1)
reader = SimpleMFRC522()
def rfid_loop():
    global latest_card_text
    while True:
        try:
            card_id, card_text = reader.read()
            clean_text = card_text.replace('\x00', '').strip().lower()
            
            if clean_text:
                latest_card_text = clean_text
                print(f"\n🎯 SELECTED FLOWER: {clean_text.upper()}")
        except Exception:
            continue


# Setup Camera
picam2 = Picamera2()
config = picam2.create_preview_configuration({"size": (640, 480)})
picam2.configure(config)
picam2.start()

# Setup QR Detector
detector = cv2.QRCodeDetector()
latest_card_text = None

print("=========================================")
print("🌸 WELCOME TO FLOWER FINDER!!! 🌸")
print("=========================================")

rfid_thread = threading.Thread(target=rfid_loop, daemon=True)
rfid_thread.start()

try:
    # ------------------------------------------
    # OUTER LOOP: Waiting for an RFID Card
    # ------------------------------------------
    while True:
        print("\n[STANDBY] Waiting for RFID scan...")

        if not latest_card_tex:
            time.sleep(0.1)
            continue
        target_flower=latest_card_text
        latest_card_text=None
        
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
                timeout_sound()
                print("Try again!")
                GPIO.output(RED_LED,GPIO.HIGH)
                time.sleep(1.5)
                GPIO.output(RED_LED,GPIO.LOW)
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
            gray_img = cv2.cvtColor(img, cv2.COLOR_RGB2GRAY)

            # Look for QR
            data, bbox, _ = detector.detectAndDecode(gray_img)
            
            if bbox is not None and data:
                scanned_flower = data.strip().lower()
                
                # Check for a match
                if scanned_flower == target_flower:
                    print(f"✅NOICE, you found the {target_flower.upper()}!")
                    success_sound()
                    flower_found = True
                    latest_card_text = None
                    GPIO.output(GREEN_LED,GPIO.HIGH)
                    time.sleep(2) 
                    GPIO.output(GREEN_LED,GPIO.LOW)
                
                else:
                    print(f"❌ Wrong flower. That is a {scanned_flower.upper()}. Keep looking!")
                    error_sound()
                    # TODO: Work with led to (Red led? buzzer noise?)
                    GPIO.output(RED_LED,GPIO.HIGH)
                    time.sleep(1.5)
                    GPIO.output(RED_LED,GPIO.LOW)

except KeyboardInterrupt:
    print("\n🛑 BYE BYEEEE...")

finally:
    # Clean up everything
    GPIO.cleanup()
    picam2.stop()