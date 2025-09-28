from flask import Flask, render_template, Response, jsonify, session, redirect, url_for
from detection import gen_frames, get_status
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.image import MIMEImage
from email.mime.base import MIMEBase
from email import encoders
from email.mime.text import MIMEText
import datetime
import os
from functools import wraps
import traceback

# ✅ DB + Auth
from db import init_db, get_db_connection
from auth import auth

app = Flask(__name__)
app.secret_key = "supersecretkey"   # 🔑 change later to env variable
app.register_blueprint(auth)

EMAIL_RECIPIENTS = ["20240802193@dypiu.ac.in", "darshantannu5@gmail.com"]
FROM_EMAIL = "darshantannu9@gmail.com"
APP_PASSWORD = "wilj hlcr mlmd ybtf"   # ⚠️ Gmail app password (16 chars, no spaces)

# ---------------- Email Alert ----------------
def send_email_alert(snapshot_path=None, video_path=None, behavior="Abnormal", location="Unknown", user=None):
    subject = "🚨 Dog Abnormal Behavior Detected"
    user_info = "Unknown"
    if user:
        user_info = f'{user.get("name")} ({user.get("email")}, {user.get("phone")})'

    body = f"""⚠️ Abnormal behavior detected.

Behavior: {behavior}
Location: {location}
User: {user_info}
See attachments below.
"""

    msg = MIMEMultipart()
    msg["From"] = FROM_EMAIL
    msg["To"] = ", ".join(EMAIL_RECIPIENTS)
    msg["Subject"] = subject
    msg.attach(MIMEText(body, "plain"))

    if snapshot_path and os.path.exists(snapshot_path):
        try:
            with open(snapshot_path, "rb") as f:
                img = MIMEImage(f.read())
                img.add_header("Content-Disposition", "attachment", filename=os.path.basename(snapshot_path))
                msg.attach(img)
        except Exception as e:
            print("❌ Could not attach snapshot:", e)

    if video_path and os.path.exists(video_path):
        try:
            with open(video_path, "rb") as f:
                part = MIMEBase('application', 'octet-stream')
                part.set_payload(f.read())
                encoders.encode_base64(part)
                part.add_header('Content-Disposition', f'attachment; filename={os.path.basename(video_path)}')
                msg.attach(part)
        except Exception as e:
            print("❌ Could not attach video:", e)

    password = APP_PASSWORD.strip()

    try:
        # Try SSL first
        server = smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=15)
        server.login(FROM_EMAIL, password)
        server.sendmail(FROM_EMAIL, EMAIL_RECIPIENTS, msg.as_string())
        server.quit()
        print("✅ Email sent (SSL).")
        return True
    except Exception as e_ssl:
        print("⚠️ SMTP_SSL failed, trying STARTTLS. Error:", e_ssl)
        try:
            server = smtplib.SMTP("smtp.gmail.com", 587, timeout=15)
            server.ehlo()
            server.starttls()
            server.login(FROM_EMAIL, password)
            server.sendmail(FROM_EMAIL, EMAIL_RECIPIENTS, msg.as_string())
            server.quit()
            print("✅ Email sent (STARTTLS).")
            return True
        except Exception as e:
            print("❌ Email failed:", e)
            traceback.print_exc()
            return False

# ---------------- Auth Helpers ----------------
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if "user_id" not in session:
            return redirect(url_for("auth.login"))
        return f(*args, **kwargs)
    return decorated_function

def get_current_user():
    """Fetch current logged-in user details from DB"""
    if "user_id" not in session:
        return None
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT id, name, email, phone FROM users WHERE id=?", (session["user_id"],))
    user = cur.fetchone()
    conn.close()
    if user:
        return {"id": user[0], "name": user[1], "email": user[2], "phone": user[3]}
    return None

# ---------------- Flask Routes ----------------
@app.route("/")
def home():
    if "user_id" in session:
        return redirect(url_for("dashboard"))
    return redirect(url_for("auth.login"))

@app.route("/dashboard")
@login_required
def dashboard():
    return render_template("index.html", user_name=session.get("user_name"))

@app.route("/video_feed")
@login_required
def video_feed():
    user = get_current_user()

    def alert_callback(snapshot_path=None, video_path=None, behavior="Abnormal", location="Unknown", user=user):
        try:
            conn = get_db_connection()
            cur = conn.cursor()
            user_id = user.get("id") if user else None
            cur.execute("""
                INSERT INTO alerts (user_id, snapshot_path, clip_path, behavior, timestamp)
                VALUES (?, ?, ?, ?, ?)
            """, (user_id, snapshot_path, video_path, behavior,
                  datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
            conn.commit()
            conn.close()
        except Exception as e:
            print("❌ DB insert failed:", e)
            traceback.print_exc()

        try:
            send_email_alert(snapshot_path, video_path, behavior, location, user)
        except Exception as e:
            print("❌ Email sending failed:", e)
            traceback.print_exc()

    return Response(gen_frames(alert_callback=alert_callback),
                    mimetype="multipart/x-mixed-replace; boundary=frame")

@app.route("/status")
@login_required
def status():
    detection_status = get_status()

    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM alerts")
    alerts_count = cur.fetchone()[0]
    conn.close()

    # ✅ only abnormal detections + behavior info
    return jsonify({
        "status": detection_status.get("status"),
        "abnormal_detections": detection_status.get("abnormal_detections"),
        "alerts_count": alerts_count,
        "last_behavior": detection_status.get("last_behavior"),
        "geo_tag": detection_status.get("geo_tag"),
        "datetime": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    })

@app.route("/alerts")
@login_required
def alerts():
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT a.id, a.timestamp, a.snapshot_path, a.clip_path, a.behavior,
               u.name, u.email, u.phone
        FROM alerts a
        JOIN users u ON a.user_id = u.id
        ORDER BY a.id DESC
    """)
    rows = cur.fetchall()
    conn.close()

    alerts = []
    for r in rows:
        alerts.append({
            "id": r[0],
            "time": r[1],
            "snapshot": r[2],
            "clip": r[3],
            "behavior": r[4],
            "user_name": r[5],
            "user_email": r[6],
            "user_phone": r[7]
        })
    return jsonify(alerts)

# ---------------- Main ----------------
if __name__ == "__main__":
    init_db()   # ✅ Create DB tables if not exist
    app.run(debug=True)






