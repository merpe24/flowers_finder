import cv2
import time

# Initialize the USB Webcam (0 is usually the default built-in or first plugged-in camera)
cap = cv2.VideoCapture(0)

# Optional: Set resolution (matches your previous 640x480 setting)
cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)

# QR code detection Method
detector = cv2.QRCodeDetector()

print("=========================================")
print("🟢 USB Webcam Active in HEADLESS Mode")
print("📡 Waiting for QR Code...")
print("🛑 Press Ctrl+C in this terminal to quit.")
print("=========================================")

try:
    # Infinite loop to keep searching for data
    while True:
        
        # Grab a frame from the USB webcam
        ret, img = cap.read()
        
        # If the frame didn't grab properly, try again
        if not ret or img is None:
            time.sleep(0.1)
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
            
            # Pause for a second so it doesn't spam the terminal
            time.sleep(1)
            print("📡 Waiting for next QR Code...")

except KeyboardInterrupt:
    # This catches the Ctrl+C command to safely exit
    print("\n🛑 Quitting scanner...")

finally:
    # Safely shut down the camera
    cap.release()