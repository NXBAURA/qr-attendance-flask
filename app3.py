# app.py - Teacher-controlled QR attendance with Teacher PIN required for student submit
from flask import Flask, request, session, redirect, url_for, render_template_string, make_response
import os, io, base64, sqlite3, hashlib
from itsdangerous import URLSafeTimedSerializer, SignatureExpired, BadSignature
from datetime import datetime
import qrcode, pandas as pd

# --------- CONFIG ----------
SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret-key")
QR_SECRET = os.environ.get("QR_SECRET", "qr-secret")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "admin123")
# Teacher PIN for student submission (set this env var before running)
TEACHER_PIN = os.environ.get("TEACHER_PIN", "0000")
QR_TTL_SECONDS = int(os.environ.get("QR_TTL_SECONDS", "600"))
BASE_URL = os.environ.get("BASE_URL", "http://127.0.0.1:5000")
DATABASE = os.path.join(os.path.dirname(__file__), "attendance.db")

app = Flask(__name__)
app.secret_key = SECRET_KEY
serializer = URLSafeTimedSerializer(QR_SECRET)

# --------- DB ----------
def init_db():
    conn = sqlite3.connect(DATABASE)
    c = conn.cursor()
    c.execute("""
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
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS tokens (
            token TEXT PRIMARY KEY,
            slot TEXT,
            created_at TEXT
        )
    """)
    conn.commit()
    conn.close()

def get_setting(key):
    conn = sqlite3.connect(DATABASE)
    c = conn.cursor()
    c.execute("SELECT value FROM settings WHERE key=?", (key,))
    row = c.fetchone()
    conn.close()
    return row[0] if row else None

def set_setting(key, value):
    conn = sqlite3.connect(DATABASE)
    c = conn.cursor()
    c.execute("INSERT INTO settings (key,value) VALUES (?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, value))
    conn.commit()
    conn.close()

def clear_setting(key):
    conn = sqlite3.connect(DATABASE)
    c = conn.cursor()
    c.execute("DELETE FROM settings WHERE key=?", (key,))
    conn.commit()
    conn.close()

def store_token(token, slot):
    conn = sqlite3.connect(DATABASE)
    c = conn.cursor()
    c.execute("INSERT OR REPLACE INTO tokens (token,slot,created_at) VALUES (?,?,?)", (token, slot, datetime.utcnow().isoformat()))
    conn.commit()
    conn.close()

def get_token_for_slot(slot):
    conn = sqlite3.connect(DATABASE)
    c = conn.cursor()
    c.execute("SELECT token, created_at FROM tokens WHERE slot=?", (slot,))
    row = c.fetchone()
    conn.close()
    return row if row else None

def delete_token(token):
    conn = sqlite3.connect(DATABASE)
    c = conn.cursor()
    c.execute("DELETE FROM tokens WHERE token=?", (token,))
    conn.commit()
    conn.close()

def insert_record(name, roll, slot, device_cid, ip, ua):
    conn = sqlite3.connect(DATABASE)
    c = conn.cursor()
    c.execute("INSERT INTO attendance (student_name, roll, slot, timestamp, device_cid, ip, user_agent) VALUES (?,?,?,?,?,?,?)",
              (name, roll, slot, datetime.utcnow().isoformat(), device_cid, ip, ua))
    conn.commit()
    conn.close()

def query_records(slot=None, admin_view=False):
    conn = sqlite3.connect(DATABASE)
    c = conn.cursor()
    if admin_view:
        if slot:
            c.execute("SELECT id, student_name, roll, slot, timestamp FROM attendance WHERE slot=? ORDER BY timestamp DESC", (slot,))
        else:
            c.execute("SELECT id, student_name, roll, slot, timestamp FROM attendance ORDER BY timestamp DESC")
        rows = c.fetchall()
        cols = ["id","student_name","roll","slot","timestamp"]
    else:
        if slot:
            c.execute("SELECT id, student_name, roll, slot, timestamp, device_cid, ip, user_agent FROM attendance WHERE slot=? ORDER BY timestamp DESC", (slot,))
        else:
            c.execute("SELECT id, student_name, roll, slot, timestamp, device_cid, ip, user_agent FROM attendance ORDER BY timestamp DESC")
        rows = c.fetchall()
        cols = ["id","student_name","roll","slot","timestamp","device_cid","ip","user_agent"]
    conn.close()
    return pd.DataFrame(rows, columns=cols) if rows else pd.DataFrame(columns=cols)

def clear_records(all_records=False, slot=None):
    conn = sqlite3.connect(DATABASE)
    c = conn.cursor()
    if all_records:
        c.execute("DELETE FROM attendance")
    elif slot:
        c.execute("DELETE FROM attendance WHERE slot=?", (slot,))
    conn.commit()
    conn.close()

# --------- UTIL ----------
def make_device_cid(req):
    ua = req.headers.get("User-Agent", "")
    ip = req.remote_addr or ""
    return hashlib.sha256(f"{ip}|{ua}".encode()).hexdigest()

def make_token(slot):
    return serializer.dumps({"slot": slot})

def decode_token(token):
    return serializer.loads(token, max_age=QR_TTL_SECONDS)

# --------- TEMPLATES ----------
BASE_HTML = """
<!doctype html><html lang='en'><head><meta charset='utf-8'/><meta name='viewport' content='width=device-width,initial-scale=1'/>
<link href='https://cdn.jsdelivr.net/npm/bootstrap@5.3.2/dist/css/bootstrap.min.css' rel='stylesheet'/>
<style>body{background:#0f1724;color:#e6eef8} .card{background:#0b1320;border:none} .qr-img{max-width:230px;background:#fff;padding:8px;border-radius:8px} a{color:#7dd3fc}</style>
</head><body>
<div class='container py-4'>
  <div class='d-flex justify-content-between mb-3'>
    <h3>QR Attendance</h3>
    <div>
      <a href='/' class='btn btn-sm btn-outline-light'>Student</a>
      <a href='/admin/login' class='btn btn-sm btn-outline-light ms-2'>Teacher</a>
    </div>
  </div>
  {{content | safe}}
</div></body></html>
"""

STUDENT_HTML = """
<div class='card p-3'>
  <h5>Current Active Slot</h5>
  {% if active_slot %}
    <p><b>{{active_slot}}</b></p>
    {% if token_link %}
      <p><a href='{{token_link}}' target='_blank' class='btn btn-sm btn-primary'>Open Attendance</a></p>
      <p class='small-muted'>Students must enter Teacher PIN when submitting.</p>
    {% else %}
      <p class='text-secondary'>Teacher has activated slot but not generated the link yet.</p>
    {% endif %}
  {% else %}
    <p class='text-secondary'>No active slot right now. Wait for your teacher to start attendance.</p>
  {% endif %}
</div>
"""

ADMIN_LOGIN_HTML = """
<div class='card p-4 col-md-5 mx-auto'>
  <h4>Teacher login</h4>
  {% if error %}<div class='alert alert-danger'>{{error}}</div>{% endif %}
  <form method='post'><input class='form-control' name='password' placeholder='Password' required><button class='btn btn-primary w-100 mt-3'>Login</button></form>
</div>
"""

ADMIN_DASH_HTML = """
<div class='card p-3'>
  <h4>Teacher Panel</h4>
  <form method='post' action='/admin/activate' class='d-flex gap-2'>
    <input name='slot' class='form-control' placeholder='Enter slot name e.g. classA' value='{{active_slot or ""}}' required>
    <button class='btn btn-success'>Activate</button>
    <button formaction='/admin/deactivate' formmethod='post' class='btn btn-outline-light ms-2'>Deactivate</button>
  </form>

  <hr>
  <h6>Generate QR / Link for active slot</h6>
  {% if active_slot %}
    <form method='post' action='/admin/generate' class='d-flex gap-2'>
      <button class='btn btn-primary'>Generate QR & Link</button>
    </form>
    {% if token_info %}
      <div class='mt-3 d-flex gap-3'>
        <img src='data:image/png;base64,{{token_info.qr_b64}}' class='qr-img' />
        <div>
          <p><b>Slot:</b> {{active_slot}}</p>
          <p><a href='{{token_info.link}}' target='_blank'>Open student link</a></p>
          <p><button class='btn btn-sm btn-outline-light' onclick='navigator.clipboard.writeText("{{token_info.link}}")'>Copy link</button></p>
          <p class='small-muted'>Generated at: {{token_info.created_at}}</p>
        </div>
      </div>
    {% endif %}
  {% else %}
    <p class='text-secondary'>No active slot — activate first.</p>
  {% endif %}

  <hr>
  <h6>Records / Export / Clear</h6>
  <p>
    <a href='/admin/view' class='btn btn-sm btn-outline-light'>View records</a>
    <a href='/admin/export' class='btn btn-sm btn-outline-light ms-2'>Export (Excel)</a>
  </p>
  <form method='post' action='/admin/clear' class='d-flex gap-2 mt-2'>
    <input name='slot' class='form-control form-control-sm' placeholder='(optional) slot to clear'>
    <button name='action' value='clear_slot' class='btn btn-sm btn-warning'>Clear Slot</button>
    <button name='action' value='clear_all' class='btn btn-sm btn-danger ms-2'>Clear All</button>
  </form>
  <p class='small-muted mt-2'>Clearing is permanent.</p>
</div>
"""

SUBMIT_HTML = """
<div class='card p-3 col-md-6 mx-auto'>
  <h4>Submit attendance — {{slot}}</h4>
  {% if error %}<div class='alert alert-danger'>{{error}}</div>{% endif %}
  <form method='post'>
    <label>Name</label><input class='form-control' name='student_name' required>
    <label class='mt-2'>Roll</label><input class='form-control' name='roll' required>
    <label class='mt-2'>Teacher PIN</label><input class='form-control' name='teacher_pin' required>
    <input type='hidden' name='token' value='{{token}}'>
    <button class='btn btn-success mt-3'>Submit</button>
  </form>
</div>
"""

VIEW_HTML = """
<div class='card p-3'>
  <h4>Attendance Records</h4>
  <div class='table-responsive small mt-3'>{{table | safe}}</div>
  <a href='/admin' class='btn btn-sm btn-outline-light mt-3'>Back</a>
</div>
"""

# --------- RENDER HELP -----------
def page(html, **ctx):
    inner = render_template_string(html, **ctx)
    return render_template_string(BASE_HTML, content=inner)

# --------- ROUTES ----------
@app.route("/")
def student_index():
    active = get_setting("active_slot")
    token_row = get_token_for_slot(active) if active else None
    token_info = None
    if token_row:
        token_str, created_at = token_row
        link = f"{BASE_URL}/submit?token={token_str}"
        token_info = {"link": link}
    return page(STUDENT_HTML, active_slot=active, token_link=(token_info["link"] if token_info else None), ttl=QR_TTL_SECONDS)

@app.route("/admin/login", methods=["GET","POST"])
def admin_login():
    if request.method == "GET":
        return page(ADMIN_LOGIN_HTML, error=None)
    pwd = request.form.get("password","")
    if pwd == ADMIN_PASSWORD:
        session["admin"] = True
        return redirect(url_for("admin"))
    return page(ADMIN_LOGIN_HTML, error="Wrong password")

@app.route("/admin")
def admin():
    if not session.get("admin"):
        return redirect(url_for("admin_login"))
    active = get_setting("active_slot")
    token_row = get_token_for_slot(active) if active else None
    token_info = None
    if token_row:
        token_str, created_at = token_row
        link = f"{BASE_URL}/submit?token={token_str}"
        buf = io.BytesIO(); qrcode.make(link).save(buf, format="PNG")
        qr_b64 = base64.b64encode(buf.getvalue()).decode("ascii")
        token_info = {"link": link, "qr_b64": qr_b64, "created_at": created_at}
    return page(ADMIN_DASH_HTML, active_slot=active, token_info=token_info)

@app.route("/admin/activate", methods=["POST"])
def admin_activate():
    if not session.get("admin"):
        return redirect(url_for("admin_login"))
    slot = request.form.get("slot","").strip()
    if slot:
        set_setting("active_slot", slot)
    return redirect(url_for("admin"))

@app.route("/admin/deactivate", methods=["POST"])
def admin_deactivate():
    if not session.get("admin"):
        return redirect(url_for("admin_login"))
    clear_setting("active_slot")
    return redirect(url_for("admin"))

@app.route("/admin/generate", methods=["POST"])
def admin_generate():
    if not session.get("admin"):
        return redirect(url_for("admin_login"))
    active = get_setting("active_slot")
    if not active:
        return page(ADMIN_DASH_HTML, active_slot=None, token_info=None)
    token = make_token(active)
    store_token(token, active)
    return redirect(url_for("admin"))

@app.route("/submit", methods=["GET","POST"])
def submit():
    token = request.args.get("token") or request.form.get("token")
    if not token:
        return "Missing token", 400
    try:
        data = decode_token(token)
    except SignatureExpired:
        return "Token expired", 400
    except BadSignature:
        return "Invalid token", 400
    slot = data.get("slot")
    # ensure teacher actually generated this token
    token_row = get_token_for_slot(slot)
    if not token_row or token_row[0] != token:
        return "This attendance link is not active. Ask your teacher.", 403
    if request.method == "GET":
        return page(SUBMIT_HTML, slot=slot, error=None, token=token)
    # POST -> require teacher PIN
    student_name = request.form.get("student_name","").strip()
    roll = request.form.get("roll","").strip()
    teacher_pin = request.form.get("teacher_pin","").strip()
    if teacher_pin != TEACHER_PIN:
        return page(SUBMIT_HTML, slot=slot, error="Incorrect Teacher PIN", token=token)
    device_cid = make_device_cid(request)
    df = query_records(slot=slot)
    if not df.empty and not df[df["device_cid"] == device_cid].empty:
        return "Attendance already recorded from this device for this slot.", 400
    insert_record(student_name, roll, slot, device_cid, request.remote_addr or "", request.headers.get("User-Agent",""))
    return f"Attendance recorded for {student_name} (roll {roll}) for slot {slot}."

@app.route("/admin/view")
def admin_view():
    if not session.get("admin"):
        return redirect(url_for("admin_login"))
    df = query_records(admin_view=True)
    table = df.to_html(index=False, classes="table table-dark table-sm")
    return page(VIEW_HTML, table=table)

@app.route("/admin/export")
def admin_export():
    if not session.get("admin"):
        return redirect(url_for("admin_login"))
    df = query_records()  # full export
    buf = io.BytesIO(); df.to_excel(buf, index=False); buf.seek(0)
    resp = make_response(buf.read())
    resp.headers["Content-Type"] = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    resp.headers["Content-Disposition"] = "attachment; filename=attendance.xlsx"
    return resp

@app.route("/admin/clear", methods=["POST"])
def admin_clear():
    if not session.get("admin"):
        return redirect(url_for("admin_login"))
    action = request.form.get("action")
    slot = request.form.get("slot","").strip()
    if action == "clear_all":
        clear_records(all_records=True)
    elif action == "clear_slot" and slot:
        clear_records(slot=slot)
    return redirect(url_for("admin_view"))

# --------- START ----------
if __name__ == "__main__":
    init_db()
    app.run(debug=True)
