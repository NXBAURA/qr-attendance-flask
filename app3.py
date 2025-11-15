"""
QR Attendance - Single-file Flask app
Features implemented:
- Generate time-limited QR tokens (10 minute TTL) for attendance slots using itsdangerous
- QR images served inline (PNG -> base64)
- Device-locking via hashed device fingerprint (IP + User-Agent)
- Teacher-controlled PIN required for submissions
- Admin login to view and export attendance (password-protected)
- SQLite storage (no external DB required)

How to use:
1. Save this file as `app.py` in an empty folder.
2. Create a virtualenv and install requirements:
   python -m venv venv
   venv\Scripts\activate (Windows) or source venv/bin/activate (mac/linux)
   pip install Flask itsdangerous qrcode[pil] pillow pandas openpyxl

3. Set environment variables (or edit defaults below in code):
   export SECRET_KEY="a-very-secret-key"
   export QR_SECRET="another-secret-for-qrs"
   export ADMIN_PASSWORD="choose_admin_pwd"
   export TEACHER_PIN="choose_teacher_pin"

4. Run:
   python app.py
   Open http://127.0.0.1:5000

Notes & limitations:
- Device-locking is implemented using a hash of IP+User-Agent; it's not bulletproof (NAT, mobile networks, dynamic IPs).
- When hosting on a public domain, use HTTPS and a proper reverse proxy (nginx) for security.
- TTL is 600 seconds (10 minutes) by default but can be changed.

"""

from flask import Flask, request, session, redirect, url_for, render_template_string, send_file, abort, make_response
import os
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired
import qrcode
import io
import base64
import sqlite3
from datetime import datetime
import hashlib
import pandas as pd

# Configuration (can be overridden with environment variables)
SECRET_KEY = os.environ.get('SECRET_KEY', 'dev-secret-key')
QR_SECRET = os.environ.get('QR_SECRET', 'qr-secret')
ADMIN_PASSWORD = os.environ.get('ADMIN_PASSWORD', 'admin123')
TEACHER_PIN = os.environ.get('TEACHER_PIN', '0000')
QR_TTL_SECONDS = int(os.environ.get('QR_TTL_SECONDS', '600'))  # 10 minutes
DATABASE = os.path.join(os.path.dirname(__file__), 'attendance.db')
BASE_URL = os.environ.get('BASE_URL', 'http://127.0.0.1:5000')

app = Flask(__name__)
app.secret_key = SECRET_KEY
serializer = URLSafeTimedSerializer(QR_SECRET)

# --- DB helpers ---
def init_db():
    conn = sqlite3.connect(DATABASE)
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS attendance (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_name TEXT,
            roll TEXT,
            slot TEXT,
            timestamp TEXT,
            device_cid TEXT,
            ip TEXT,
            user_agent TEXT
        )
    ''')
    conn.commit()
    conn.close()

def insert_record(student_name, roll, slot, device_cid, ip, user_agent):
    conn = sqlite3.connect(DATABASE)
    c = conn.cursor()
    c.execute('INSERT INTO attendance (student_name, roll, slot, timestamp, device_cid, ip, user_agent) VALUES (?,?,?,?,?,?,?)',
              (student_name, roll, slot, datetime.utcnow().isoformat(), device_cid, ip, user_agent))
    conn.commit()
    conn.close()

def query_records(slot=None):
    conn = sqlite3.connect(DATABASE)
    c = conn.cursor()
    if slot:
        c.execute('SELECT id, student_name, roll, slot, timestamp, device_cid, ip, user_agent FROM attendance WHERE slot=? ORDER BY timestamp DESC', (slot,))
    else:
        c.execute('SELECT id, student_name, roll, slot, timestamp, device_cid, ip, user_agent FROM attendance ORDER BY timestamp DESC')
    rows = c.fetchall()
    conn.close()
    cols = ['id','student_name','roll','slot','timestamp','device_cid','ip','user_agent']
    df = pd.DataFrame(rows, columns=cols)
    return df

# --- Utility ---
def make_device_cid(req: request):
    ua = req.headers.get('User-Agent','')
    ip = req.remote_addr or ''
    raw = f"{ip}|{ua}"
    return hashlib.sha256(raw.encode('utf-8')).hexdigest()

# --- QR Token ---
def create_token(slot_id: str):
    payload = {'slot': slot_id}
    token = serializer.dumps(payload)
    return token

def decode_token(token: str, max_age: int = QR_TTL_SECONDS):
    try:
        data = serializer.loads(token, max_age=max_age)
        return data
    except SignatureExpired:
        raise
    except BadSignature:
        raise

# --- Routes ---

# Simple index with generate form and admin link
INDEX_HTML = """
<h2>QR Attendance - Local Server</h2>
<p>Generate a temporary QR for a slot (10 minute TTL).</p>
<form action="/generate" method="post">
  Slot name: <input name="slot" value="classA" required>
  <button type="submit">Generate QR</button>
</form>
<p><a href="/admin/login">Admin login</a> — view & download records.</p>
"""

@app.route('/')
def index():
    return render_template_string(INDEX_HTML)

GENERATE_HTML = """
<h3>QR for slot: {{slot}}</h3>
<p>Expires in {{ttl}} seconds.</p>
<div>
  <img src="data:image/png;base64,{{qr_b64}}" alt="qr">
</div>
<p>Direct link: <a href="{{link}}">{{link}}</a></p>
<p><a href="/">Back</a></p>
"""

@app.route('/generate', methods=['POST'])
def generate():
    slot = request.form.get('slot','')
    token = create_token(slot)
    link = f"{BASE_URL}/submit?token={token}"
    # generate QR image for link
    img = qrcode.make(link)
    buf = io.BytesIO()
    img.save(buf, format='PNG')
    b64 = base64.b64encode(buf.getvalue()).decode('ascii')
    return render_template_string(GENERATE_HTML, slot=slot, ttl=QR_TTL_SECONDS, qr_b64=b64, link=link)

SUBMIT_HTML = """
<h3>Attendance - Slot: {{slot}}</h3>
{% if error %}<p style='color:red;'>{{error}}</p>{% endif %}
<form method="post">
  Student name: <input name="student_name" required><br>
  Roll / ID: <input name="roll" required><br>
  Teacher PIN (required to submit): <input name="teacher_pin" required><br>
  <button type="submit">Submit Attendance</button>
</form>
<p>Note: device fingerprint is recorded to prevent duplicate submissions.</p>
"""

@app.route('/submit', methods=['GET','POST'])
def submit():
    token = request.args.get('token') or request.form.get('token')
    if not token:
        return 'Missing token', 400
    try:
        data = decode_token(token)
    except SignatureExpired:
        return 'Token expired (QR TTL passed).', 400
    except Exception:
        return 'Invalid token.', 400
    slot = data.get('slot')
    if request.method == 'GET':
        return render_template_string(SUBMIT_HTML, slot=slot, error=None)
    # POST: handle attendance
    student_name = request.form.get('student_name','').strip()
    roll = request.form.get('roll','').strip()
    teacher_pin = request.form.get('teacher_pin','').strip()
    if teacher_pin != TEACHER_PIN:
        return render_template_string(SUBMIT_HTML, slot=slot, error='Incorrect teacher PIN')
    device_cid = make_device_cid(request)
    # check duplicate for same slot and device within the day
    df = query_records(slot=slot)
    if not df.empty:
        # check if device_cid already exists for this slot in last 24 hours
        existing = df[df['device_cid'] == device_cid]
        if not existing.empty:
            return 'Attendance already recorded from this device for this slot.', 400
    insert_record(student_name, roll, slot, device_cid, request.remote_addr or '', request.headers.get('User-Agent',''))
    return f"Attendance recorded for {student_name} (roll {roll}) for slot {slot}."

# --- Admin ---
LOGIN_HTML = """
<h3>Admin Login</h3>
{% if error %}<p style='color:red;'>{{error}}</p>{% endif %}
<form method="post">
  Password: <input type="password" name="password" required>
  <button type="submit">Login</button>
</form>
"""

ADMIN_HTML = """
<h3>Admin Dashboard</h3>
<p><a href="/admin/export">Download all records (Excel)</a></p>
<form method="get" action="/admin/view">
  Filter by slot: <input name="slot"><button type="submit">View</button>
</form>
<p><a href="/">Back to generator</a></p>
"""

@app.route('/admin/login', methods=['GET','POST'])
def admin_login():
    if request.method == 'GET':
        return render_template_string(LOGIN_HTML, error=None)
    pwd = request.form.get('password','')
    if pwd == ADMIN_PASSWORD:
        session['admin'] = True
        return redirect(url_for('admin_dashboard'))
    return render_template_string(LOGIN_HTML, error='Wrong password')

@app.route('/admin')
def admin_dashboard():
    if not session.get('admin'):
        return redirect(url_for('admin_login'))
    return render_template_string(ADMIN_HTML)

@app.route('/admin/view')
def admin_view():
    if not session.get('admin'):
        return redirect(url_for('admin_login'))
    slot = request.args.get('slot')
    df = query_records(slot=slot if slot else None)
    html = df.to_html(index=False)
    return f"<h3>Records</h3>{html}<p><a href=\"/admin\">Back</a></p>"

@app.route('/admin/export')
def admin_export():
    if not session.get('admin'):
        return redirect(url_for('admin_login'))
    df = query_records()
    buf = io.BytesIO()
    df.to_excel(buf, index=False)
    buf.seek(0)
    resp = make_response(buf.read())
    resp.headers['Content-Type'] = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    resp.headers['Content-Disposition'] = 'attachment; filename=attendance.xlsx'
    return resp

# --- Startup ---
if __name__ == '__main__':
    init_db()
    app.run(debug=True)
