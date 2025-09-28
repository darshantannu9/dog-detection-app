import cv2
import numpy as np
from ultralytics import YOLO
from collections import deque, Counter
import time
import requests
import threading
import os
import traceback

# Load YOLO model
yolo = YOLO("yolov8n.pt")

# ---------------- Globals ----------------
prev_center = None
prev_area = None
motion_history = deque(maxlen=100)
status_history = deque(maxlen=30)

current_status = "Normal"
last_behavior = "Normal"
current_location = "Unknown"

# Counter for abnormal detections only
abnormal_count = 0   

# Alert / recording variables
last_alert_time = 0
cooldown = 60   # seconds

alpha = 0.5
motion_smooth = 0.0

# Directories
os.makedirs("snapshots", exist_ok=True)
os.makedirs("clips", exist_ok=True)

# ---------------- Geo-location updater ----------------
def fetch_location_once():
    try:
        res = requests.get("https://ipinfo.io/json", timeout=3)
        data = res.json()
        loc = data.get("loc", "")
        city = data.get("city", "Unknown")
        region = data.get("region", "Unknown")
        country = data.get("country", "Unknown")
        return f"{loc} ({city}, {region}, {country})"
    except Exception:
        return "Unknown"

def location_updater(interval=30):
    global current_location
    while True:
        try:
            current_location = fetch_location_once()
        except Exception:
            pass
        time.sleep(interval)

threading.Thread(target=location_updater, args=(30,), daemon=True).start()

# ---------------- Detection helpers ----------------
def detect_abnormal(motion_history):
    if len(motion_history) < 20:
        return "Normal"
    recent = list(motion_history)[-20:]
    avg = np.mean(recent)
    std = np.std(recent)
    if (avg > 20 and std < 5) or (avg < 1.5) or (std > 20):
        return "Abnormal"
    return "Normal"

def get_cam_index():
    for i in range(5):
        cap = cv2.VideoCapture(i)
        if cap.isOpened():
            cap.release()
            print(f"✅ Using webcam at index {i}")
            return i
    print("❌ No camera found")
    return -1

# ---------------- Background Alert Worker ----------------
def handle_alert(frame_buffer, fps, alert_callback, location_snapshot=None):
    try:
        now = int(time.time())
        snapshot_path = f"snapshots/snapshot_{now}.jpg"
        clip_path = f"clips/clip_{now}.mp4"

        if frame_buffer:
            cv2.imwrite(snapshot_path, frame_buffer[-1])

        if frame_buffer:
            h, w, _ = frame_buffer[0].shape
            fourcc = cv2.VideoWriter_fourcc(*'mp4v')
            writer = cv2.VideoWriter(clip_path, fourcc, fps, (w, h))
            for f in frame_buffer:
                writer.write(f)
            writer.release()

        if alert_callback:
            alert_callback(snapshot_path=snapshot_path, video_path=clip_path,
                           behavior="Abnormal", location=location_snapshot)

        print("✅ Alert handled in background")
    except Exception as e:
        print("❌ Exception in handle_alert:", e)
        traceback.print_exc()

# ---------------- Frame Generator ----------------
def gen_frames(alert_callback=None):
    global prev_center, prev_area, motion_history, status_history
    global current_status, last_behavior, abnormal_count
    global last_alert_time, motion_smooth, alpha, current_location

    cam_index = get_cam_index()
    if cam_index == -1:
        return

    cap = cv2.VideoCapture(cam_index)
    if not cap.isOpened():
        print("❌ Could not open camera")
        return

    fps = cap.get(cv2.CAP_PROP_FPS)
    if fps <= 0 or fps is None:
        fps = 20

    buffer_seconds = 5
    max_buffer = max(1, int(fps * buffer_seconds))
    frame_buffer = deque(maxlen=max_buffer)

    while True:
        success, frame = cap.read()
        if not success:
            break

        frame_buffer.append(frame.copy())
        results = yolo(frame, verbose=False)[0]
        dog_box = None

        for box, cls in zip(results.boxes.xyxy, results.boxes.cls):
            if int(cls) == 16:  # Dog
                x1, y1, x2, y2 = map(int, box)
                dog_box = (x1, y1, x2, y2)
                break

        if dog_box:
            x1, y1, x2, y2 = dog_box
            cx, cy = (x1 + x2)//2, (y1 + y2)//2
            center = (cx, cy)
            area = (x2 - x1)*(y2 - y1)

            if prev_center is not None and prev_area is not None:
                motion = np.linalg.norm(np.array(center)-np.array(prev_center))
                area_change = abs(area-prev_area)/max(prev_area,1)
                motion = motion + (area_change*50)
                motion_smooth = alpha * motion_smooth + (1-alpha) * motion
                motion_history.append(motion_smooth)

            prev_center, prev_area = center, area

            status = detect_abnormal(motion_history)
            status_history.append(status)
            current_status = Counter(status_history).most_common(1)[0][0]
            last_behavior = current_status

            loc_snapshot = current_location

            # Draw
            color = (0,255,0) if current_status=="Normal" else (0,0,255)
            cv2.rectangle(frame, (x1,y1), (x2,y2), color, 2)
            cv2.putText(frame, f"Status: {current_status}", (x1, y1-10),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)
            cv2.putText(frame, f"Loc: {loc_snapshot}", (x1, y2+20),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255,255,0), 1)

            now = time.time()
            if current_status == "Abnormal" and now - last_alert_time > cooldown:
                last_alert_time = now
                abnormal_count += 1   # ✅ count abnormal only
                buffer_copy = list(frame_buffer)
                threading.Thread(
                    target=handle_alert,
                    args=(buffer_copy, int(fps), alert_callback, loc_snapshot),
                    daemon=True
                ).start()

        # Encode for streaming
        ret, buffer = cv2.imencode('.jpg', frame)
        frame_bytes = buffer.tobytes()
        yield (b'--frame\r\n'
               b'Content-Type: image/jpeg\r\n\r\n'+frame_bytes+b'\r\n')

    cap.release()
    cv2.destroyAllWindows()

# ---------------- Status API ----------------
def get_status():
    return {
        "status": current_status,
        "abnormal_detections": abnormal_count,   # ✅ only abnormal sent
        "last_behavior": last_behavior,
        "geo_tag": current_location
    }


