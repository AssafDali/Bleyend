import cv2
import numpy as np
from picamera2 import Picamera2
import face_recognition
import os
import requests
import time

# --- 1. הגדרות טלגרם מעודכנות ---
TELEGRAM_TOKEN = "8505473880:AAEqXQ_H_VRR1iZXI-rMeNzvSQoftgjGhy8"
# כאן הוספתי את שני ה-IDs שברשותכם
CHAT_IDS = ["7125165791", "6484314043"] 

TOLERANCE = 0.45 # סף דיוק מחמיר למניעת זיהויי שווא

def send_telegram_to_all(text):
    """פונקציה ששולחת הודעה לכל המכשירים המוגדרים ברשימה"""
    for chat_id in CHAT_IDS:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage?chat_id={chat_id}&text={text}"
        try:
            # הוספת timeout למקרה שאחד המכשירים לא זמין
            requests.get(url, timeout=5)
            print(f"הודעה נשלחה בהצלחה ל-ID: {chat_id}")
        except Exception as e:
            print(f"שגיאה בשליחה ל-{chat_id}: {e}")

# --- 2. טעינת פנים מוכרות ---
known_encodings = []
known_names = []
path = "known_people"

print("טוען תמונות מהתיקייה...")
for filename in os.listdir(path):
    if filename.endswith((".jpg", ".png", ".jpeg")):
        image = face_recognition.load_image_file(f"{path}/{filename}")
        encodings = face_recognition.face_encodings(image)
        if encodings:
            known_encodings.append(encodings[0])
            known_names.append(os.path.splitext(filename)[0])

# --- 3. אתחול המצלמה (BGR888 לצבעים טבעיים ב-Pi 5) ---
picam2 = Picamera2()
config = picam2.create_video_configuration()
config['main']['size'] = (640, 480)
config['main']['format'] = 'BGR888'
picam2.configure(config)
picam2.start()

last_notified_time = {}



print("המערכת פעילה! שולחת התראות לשני המכשירים.")

try:
    while True:
        frame_bgr = picam2.capture_array()
        frame_rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
        small_frame = cv2.resize(frame_rgb, (0, 0), fx=0.25, fy=0.25)
        
        face_locations = face_recognition.face_locations(small_frame)
        
        if not face_locations:
            cv2.imshow('Smart Doorbell - Live', frame_bgr)
            if cv2.waitKey(1) & 0xFF == ord('q'): break
            continue

        face_encodings = face_recognition.face_encodings(small_frame, face_locations)

        for face_encoding in face_encodings:
            matches = face_recognition.compare_faces(known_encodings, face_encoding, tolerance=TOLERANCE)
            name = "Unknown"

            if len(known_encodings) > 0:
                face_distances = face_recognition.face_distance(known_encodings, face_encoding)
                best_match_index = np.argmin(face_distances)
                if matches[best_match_index]:
                    name = known_names[best_match_index]

            now = time.time()
            last_time = last_notified_time.get(name, 0)
            
            # לוגיקת השהייה של דקה לכל אדם בנפרד
            if now - last_time > 60:
                msg = f"זיהיתי את {name} בדלת" if name != "Unknown" else "אדם לא מוכר בדלת"
                send_telegram_to_all(msg)
                last_notified_time[name] = now

        cv2.imshow('Smart Doorbell - Live', frame_bgr)
        if cv2.waitKey(1) & 0xFF == ord('q'):
            break

finally:
    picam2.stop()
    cv2.destroyAllWindows()
