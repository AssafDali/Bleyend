import cv2
import numpy as np
from picamera2 import Picamera2
import face_recognition
import os
import requests
import time
import threading


# Group Members: Assaf Dali, Loren Kricheli
# Course: Robotics for Computer Science, HIT

# Telegram API Setup - Used to send real-time alerts to the user 
TELEGRAM_TOKEN = "8505473880:AAEqXQ_H_VRR1iZXI-rMeNzvSQoftgjGhy8"
CHAT_IDS = ["7125165791", "6484314043"] 

# Face recognition sensitivity - Lower values are more "strict"
TOLERANCE = 0.42 

def send_msg_worker(chat_id, text):
    """
    Background worker to handle HTTP requests to Telegram.
    Using a timeout prevents the main thread from hanging during network delays.
    """
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage?chat_id={chat_id}&text={text}"
    try:
        requests.get(url, timeout=10)
    except requests.exceptions.RequestException:
        print(f"Network Error: Could not reach chat ID {chat_id}")

def send_telegram_to_all(text):
    """
    Spawns a new thread for each recipient.
    This ensures the camera feed remains smooth while messages are being sent.
    """
    for chat_id in CHAT_IDS:
        thread = threading.Thread(target=send_msg_worker, args=(chat_id, text))
        thread.start()

#Loading Database of Known Faces
known_face_encodings = []
known_face_names = [] 
path = "known_people"

if not os.path.exists(path):
    os.makedirs(path)

print("Loading authorized face database...")
for filename in os.listdir(path):
    if filename.endswith((".jpg", ".png", ".jpeg")):
        # Load image and convert it into a 128-dimension face encoding (vector)
        image = face_recognition.load_image_file(f"{path}/{filename}")
        encodings = face_recognition.face_encodings(image)
        if encodings:
            known_face_encodings.append(encodings[0])
            known_face_names.append(os.path.splitext(filename)[0])

#Camera Hardware Initialization (Raspberry Pi 5)
picam2 = Picamera2() 
config = picam2.create_video_configuration() 
config['main']['size'] = (640, 480) # Resolution balance between clarity and speed
config['main']['format'] = 'BGR888' 
picam2.configure(config)
picam2.start()

#State Management variables
last_notified_time = {} # Manages "cooldown" periods to prevent notification spam
unknown_counter = 0     # Filters noise to confirm a stranger is actually present

print("System Active. Monitoring for faces... (Press 'q' to exit)")

try:
    while True:
        # Capture raw frame from the Pi camera
        frame_bgr = picam2.capture_array()
        
        # Convert BGR (OpenCV default) to RGB (Required by face_recognition library)
        frame_rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
        
        # Resize frame to 25% to significantly boost processing performance (FPS)
        small_frame = cv2.resize(frame_rgb, (0, 0), fx=0.25, fy=0.25)
        
        # Detect face locations and generate encodings for the current frame
        face_locations = face_recognition.face_locations(small_frame)
        
        if not face_locations:
            unknown_counter = 0 # Reset stranger counter if no one is visible
            cv2.imshow('Smart Doorbell - Live', frame_bgr)
            if cv2.waitKey(1) & 0xFF == ord('q'): break
            continue

        face_encodings = face_recognition.face_encodings(small_frame, face_locations)
        
        for face_encoding in face_encodings:
            name = "Unknown"
            best_dist = 1.0
            
            if len(known_face_encodings) > 0:
                # Calculate the Euclidean distance to find the closest match
                face_distances = face_recognition.face_distance(known_face_encodings, face_encoding)
                best_match_index = np.argmin(face_distances)
                
                if face_distances[best_match_index] <= TOLERANCE:
                    name = known_face_names[best_match_index]
                    best_dist = face_distances[best_match_index]

            now = time.time()
            
            # Notification Logic
            if name == "Unknown":
                unknown_counter += 1
                # Alert for strangers only after 3 consecutive frames (to avoid false positives)
                if unknown_counter >= 3 and (now - last_notified_time.get("Unknown", 0) > 30):
                    print(f">>> EVENT: Stranger detected (Distance: {best_dist:.4f})")
                    send_telegram_to_all("An unknown person is at the door.")
                    last_notified_time["Unknown"] = now
            else:
                unknown_counter = 0
                # Notify for known individuals (60-second cooldown per person)
                if now - last_notified_time.get(name, 0) > 60:
                    print(f">>> EVENT: {name} recognized (Distance: {best_dist:.4f})")
                    send_telegram_to_all(f"{name} is outside the door.")
                    last_notified_time[name] = now

        # Display the live feed for debugging/monitoring
        cv2.imshow('Smart Doorbell - Live', frame_bgr)
        if cv2.waitKey(1) & 0xFF == ord('q'): break

finally:
    # Safe shutdown: Release hardware resources and close windows
    picam2.stop()
    cv2.destroyAllWindows()
    print("System terminated successfully.")
