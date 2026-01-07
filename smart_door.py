import cv2
import numpy as np
from picamera2 import Picamera2
import face_recognition
import os
import requests
import time
import threading

# --- 1. הגדרות טלגרם וזיהוי ---
TELEGRAM_TOKEN = "8505473880:AAEqXQ_H_VRR1iZXI-rMeNzvSQoftgjGhy8"
CHAT_IDS = ["7125165791", "6484314043"] 

# סף דיוק מחמיר (הפחתנו ל-0.42 כדי למנוע זיהויי שווא של אסף/לורן)
TOLERANCE = 0.42 

def send_msg_worker(chat_id, text):
    """פונקציה שרצה ברקע ומטפלת בשגיאות רשת בשקט"""
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage?chat_id={chat_id}&text={text}"
    try:
        # שליחה עם timeout של 10 שניות למקרה של אינטרנט איטי
        requests.get(url, timeout=10)
    except requests.exceptions.RequestException:
        # במקום להדפיס שגיאה ארוכה, מדפיסים רק שורה אחת קטנה
        print(f"⚠️ שגיאת תקשורת: לא ניתן לשלוח הודעה ל-{chat_id} (בדוק חיבור אינטרנט)")

def send_telegram_to_all(text):
    """שולח את ההודעה לכל המכשירים ב-Threads נפרדים"""
    for chat_id in CHAT_IDS:
        # פתיחת תהליכון חדש לכל שליחה
        thread = threading.Thread(target=send_msg_worker, args=(chat_id, text))
        thread.start()

# --- 2. טעינת מסד הנתונים של הפנים המוכרים ---
known_face_encodings = []
known_face_names = []
path = "known_people"

print("טוען פנים מוכרות מהתיקייה...")
if not os.path.exists(path):
    os.makedirs(path)

for filename in os.listdir(path):
    if filename.endswith((".jpg", ".png", ".jpeg")):
        image = face_recognition.load_image_file(f"{path}/{filename}")
        encodings = face_recognition.face_encodings(image)
        if encodings:
            known_face_encodings.append(encodings[0])
            known_face_names.append(os.path.splitext(filename)[0])

# --- 3. אתחול המצלמה (BGR888 עבור Raspberry Pi 5) ---
picam2 = Picamera2()
config = picam2.create_video_configuration()
config['main']['size'] = (640, 480)
config['main']['format'] = 'BGR888'
picam2.configure(config)
picam2.start()

# משתנים לניהול זמנים
last_notified_time = {}
unknown_counter = 0

print("המערכת פעילה! מחפשת פנים... (לסגירה לחצו 'q' בחלון הווידאו)")

try:
    while True:
        # לכידת פריים
        frame_bgr = picam2.capture_array()
        
        # המרה ל-RGB עבור face_recognition
        frame_rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
        
        # הקטנה פי 4 לשיפור ביצועים (FPS גבוה יותר)
        small_frame = cv2.resize(frame_rgb, (0, 0), fx=0.25, fy=0.25)
        
        # חיפוש פנים בפריים
        face_locations = face_recognition.face_locations(small_frame)
        
        if not face_locations:
            unknown_counter = 0
            cv2.imshow('Smart Doorbell - Live', frame_bgr)
            if cv2.waitKey(1) & 0xFF == ord('q'): break
            continue

        face_encodings = face_recognition.face_encodings(small_frame, face_locations)

        for face_encoding in face_encodings:
            name = "Unknown"
            best_dist = 1.0

            if len(known_face_encodings) > 0:
                # חישוב המרחקים
                face_distances = face_recognition.face_distance(known_face_encodings, face_encoding)
                best_match_index = np.argmin(face_distances)
                best_dist = face_distances[best_match_index]
                
                if best_dist <= TOLERANCE:
                    name = known_face_names[best_match_index]

            now = time.time()
            
            # לוגיקת הודעות חכמה ושקטה בטרמינל
            if name == "Unknown":
                unknown_counter += 1
                # שולח הודעה רק אם זוהה Unknown ב-3 פריימים רצופים (סינון רעשים)
                if unknown_counter >= 3 and (now - last_notified_time.get("Unknown", 0) > 30):
                    print(f">>> [אירוע] אדם לא מוכר זוהה (מרחק: {best_dist:.4f})")
                    send_telegram_to_all("⚠️ אדם לא מוכר נמצא בדלת!")
                    last_notified_time["Unknown"] = now
            else:
                unknown_counter = 0
                # שליחה פעם בדקה לאדם מוכר
                if now - last_notified_time.get(name, 0) > 60:
                    print(f">>> [אירוע] {name} זוהה/תה בדלת (מרחק: {best_dist:.4f})")
                    send_telegram_to_all(f"✅ {name} נמצא/ת בדלת")
                    last_notified_time[name] = now

        # הצגת התמונה
        cv2.imshow('Smart Doorbell - Live', frame_bgr)
        if cv2.waitKey(1) & 0xFF == ord('q'): break

finally:
    picam2.stop()
    cv2.destroyAllWindows()
    print("המערכת נסגרה.")
