import cv2 # used for image processing and displaying the video window.
import numpy as np # mathematical operations on the image arrays.
from picamera2 import Picamera2 # official library for Raspberry Pi 5 camera control.
import face_recognition # AI library that handles face detection and comparison.
import os # interacting with the operating system, specifically for reading files from your folders.
import requests # Handles the HTTP requests sent to the Telegram API.
import time # "cooldown" periods between notifications.
import threading # Allows the program to run concurrent tasks, ensuring the camera feed doesn't freeze while sending messages.
# we started to use threading because of the low quaility interenet connection
# Telegram
TELEGRAM_TOKEN = "8505473880:AAEqXQ_H_VRR1iZXI-rMeNzvSQoftgjGhy8" #telegeram bot api
CHAT_IDS = ["7125165791", "6484314043"] # chats id 

# Sets the threshold for face similarity lower values make the system more "strict". 
TOLERANCE = 0.42 

# A function designed to run in the background to handle the actual network request.
def send_msg_worker(chat_id, text):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage?chat_id={chat_id}&text={text}"
    try:
        # Sends the message; the timeout prevents the thread from waiting forever if the internet is slow.
        requests.get(url, timeout=10)
    except requests.exceptions.RequestException:
        print(f" NETWORK CONNECTION FAILED, can't connect to -{chat_id} ")

def send_telegram_to_all(text): # uses thread for each chat to send message at the same time
    for chat_id in CHAT_IDS:
        # create new thread
        thread = threading.Thread(target=send_msg_worker, args=(chat_id, text))
        thread.start()

# load familiar faces
known_face_encodings = [] # vectors of the known faces 
known_face_names = [] 
path = "known_people"
print("loading known faces...")
if not os.path.exists(path):# if you don't find the folder create one.
    os.makedirs(path)
for filename in os.listdir(path): # go over each photo in folder
    if filename.endswith((".jpg", ".png", ".jpeg")): # if the file is a photo
        image = face_recognition.load_image_file(f"{path}/{filename}") # load the photo as numpy array for the vectors
        encodings = face_recognition.face_encodings(image) # save the vectors from above 
        if encodings: # if everything above works and we saved array for the photo
            # Store the first detected face vector from the current image into the master database.
            # 0 spot because we create imagie each run of the for loop
            known_face_encodings.append(encodings[0])
            # Extract the filename without the extension and use it as the person's label/name.
            known_face_names.append(os.path.splitext(filename)[0])

# Initialize the Picamera2 library for Raspberry Pi 5
picam2 = Picamera2() 
# Create a configuration template that we can modify
config = picam2.create_video_configuration() 
config['main']['size'] = (640, 480) # frame resolution
config['main']['format'] = 'BGR888' # pixel color blue-green-red
picam2.configure(config) # pass the modified config to the camera driver
picam2.start() # power the camera sensor

# Initialize dictionary to track the last notification timestamp for each person
last_notified_time = {}
unknown_counter = 0 # counter unknow detections to prevent false alarms
print("Searching for faces... (Press 'q' in the video window to exit)")

try:
    while True:
        # Capture the raw image from the camera
        frame_bgr = picam2.capture_array()
        # convert the colors to RGB because of the face recognition library
        frame_rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
        # Downscale the image to 25% to optimize processing speed
        small_frame = cv2.resize(frame_rgb, (0, 0), fx=0.25, fy=0.25)
        # search for faces in the image given
        face_locations = face_recognition.face_locations(small_frame)
        # If no faces are detected, reset counters and skip further analysis
        if not face_locations:
            unknown_counter = 0
            cv2.imshow('Smart Doorbell - Live', frame_bgr)
            if cv2.waitKey(1) & 0xFF == ord('q'): break
            continue
        # Generate encodings for all faces found in the current frame  
        face_encodings = face_recognition.face_encodings(small_frame, face_locations)
        for face_encoding in face_encodings:
            name = "Unknown"  # Default to Unknown until a match is confirmed
            best_dist = 1.0
            # Only attempt matching if the database is not empty
            if len(known_face_encodings) > 0:
                # Calculate the distance to all known face vectors 
                face_distances = face_recognition.face_distance(known_face_encodings, face_encoding)
                best_match_index = np.argmin(face_distances)
                best_dist = face_distances[best_match_index]
                # If the distance is within our capability, assign the name
                if best_dist <= TOLERANCE:
                    name = known_face_names[best_match_index]  

            now = time.time() # Get current timestamp for notification management
            # לוגיקת הודעות חכמה ושקטה בטרמינל
            if name == "Unknown":
                unknown_counter += 1
                # שולח הודעה רק אם זוהה Unknown ב-3 פריימים רצופים (סינון רעשים)
                if unknown_counter >= 3 and (now - last_notified_time.get("Unknown", 0) > 30):
                    print(f">>> [אירוע] אדם לא מוכר זוהה (מרחק: {best_dist:.4f})")
                    send_telegram_to_all("Unknown Person Outside")
                    last_notified_time["Unknown"] = now
            else:
                unknown_counter = 0
                # שליחה פעם בדקה לאדם מוכר
                if now - last_notified_time.get(name, 0) > 60:
                    print(f">>> [אירוע] {name} זוהה/תה בדלת (מרחק: {best_dist:.4f})")
                    send_telegram_to_all(f"{name} Is םutside The Door")
                    last_notified_time[name] = now

        # הצגת התמונה
        cv2.imshow('Smart Doorbell - Live', frame_bgr)
        if cv2.waitKey(1) & 0xFF == ord('q'): break

finally:
    picam2.stop()
    cv2.destroyAllWindows()
    print("המערכת נסגרה.")
