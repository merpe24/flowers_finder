import cv2
from picamera2 import Picamera2
import time

# Initialize the native Raspberry Pi camera system
picam2 = Picamera2()

# Configure the camera resolution
config = picam2.create_preview_configuration({"size": (640, 480)})
picam2.configure(config)

# Start the camera stream
picam2.start()

# QR code detection Method
detector = cv2.QRCodeDetector()

print("=========================================")
print("🟢 Camera Active in HEADLESS Mode")
print("📡 Waiting for QR Code...")
print("🛑 Press Ctrl+C in this terminal to quit.")
print("=========================================")

try:
    # Infinite loop to keep searching for data
    while True:
        
        # Grab a frame directly as an array from the Pi camera hardware
        try:
            img = picam2.capture_array()
        except Exception as e:
            continue
        
        if img is None:
            continue
        
        # Read the QR code and decode the data 
        data, bbox, _ = detector.detectAndDecode(img)
        
        # If data is found, print it
        if bbox is not None and data:
            print(f"\n✅ SUCCESS! Scanned Data: {data}")
            
            # Future RFID or LED triggers go here
            if data == 'red':
                pass 
            if data == 'green':
                pass 
            
            # Pause for a second so it doesn't spam the terminal with the same scan 30 times
            time.sleep(1)
            print("📡 Waiting for next QR Code...")

except KeyboardInterrupt:
    # This catches the Ctrl+C command to safely exit
    print("\n🛑 Quitting scanner...")

finally:
    # Safely shut down the camera
    picam2.stop()
