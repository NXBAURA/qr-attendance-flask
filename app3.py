# app.py - QR Attendance with cleaner admin view + clear-records feature
from flask import Flask, request, session, redirect, url_for, render_template_string, make_response
import os, io, base64, sqlite3, hashlib
from itsdangerous import URLSafeTimedSerializer, SignatureExpired, BadSignature
from datetime import datetime
import qrcode, pandas as pd

# --------------- CONFIG ----------------
SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret-key")
QR_SECRET = os.environ.get("QR_SECRET", "qr-secret")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "admin123")
TEACHER_PIN = os.environ.get("TEACHER_PIN", "0000")
QR_TTL_SECONDS = int(os.environ.get("QR_TTL_SECONDS", "600"))
BASE_URL = os.environ.get("BASE_URL", "http://127.0.0.1:5000")
DATABASE = os.path.join(os.path.dirname(__file__), "attendance.db")

app = Flask(__name__)
app.secret_key = SECRET_KEY
serializer = URLSafeTimedSerializer(QR_SECRET)

# --------------- DB --------------------
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
    conn.commit()
    conn.close()

def insert_record(name, roll, slot, device_cid, ip, ua):
    conn = sqlite3.connect(DATABASE)
    c = conn.cursor()
    c.execute(
        "INSERT INTO attendance (student_name, roll, slot, timestamp, device_cid, ip, user_agent) VALUES (?,?,?,?,?,?,?)",
        (name, roll, slot, datetime.utcnow().isoformat(), device_cid, ip, ua),
    )
    conn.commit()
    conn.close()

def query_records(slot=None, limit=None, admin_view=False):
    """
    admin_view=True will return only useful columns (id, student_name, roll, slot, timestamp)
    """
    conn = sqlite3.connect(DATABASE)
    c = conn.cursor()
    if admin_view:
        if slot:
            c.execute("SELECT id, student_name, roll, slot, timestamp FROM attendance WHERE slot=? ORDER BY timestamp DESC", (slot,))
        else:
            c.execute("SELECT id, student_name, roll, slot, timestamp FROM attendance ORDER BY timestamp DESC")
        rows = c.fetchall()
        conn.close()
        cols = ["id","student_name","roll","slot","timestamp"]
        df = pd.DataFrame(rows, columns=cols)
    else:
        if slot:
            c.execute("SELECT id, student_name, roll, slot, timestamp, device_cid, ip, user_agent FROM attendance WHERE slot=? ORDER BY timestamp DESC", (slot,))
        else:
            c.execute("SELECT id, student_name, roll, slot, timestamp, device_cid, ip, user_agent FROM attendance ORDER BY timestamp DESC")
        rows = c.fetchall()
        conn.close()
        cols = ["id","student_name","roll","slot","timestamp","device_cid","ip","user_agent"]
        df = pd.DataFrame(rows, columns=cols)
    if limit:
        return df.head(limit)
    return df

def clear_records(all_records=False, slot=None):
    conn = sqlite3.connect(DATABASE)
    c = conn.cursor()
    if all_records:
        c.execute("DELETE FROM attendance")
    elif slot:
        c.execute("DELETE FROM attendance WHERE slot=?", (slot,))
    conn.commit()
    conn.close()

# --------------- UTIL ------------------
def make_device_cid(req):
    ua = req.headers.get("User-Agent", "")
    ip = req.remote_addr or ""
    return hashlib.sha256(f"{ip}|{ua}".encode()).hexdigest()

def make_token(slot):
    return serializer.dumps({"slot": slot})

def decode_token(token):
    return serializer.loads(token, max_age=QR_TTL_SECONDS)

# --------------- TEMPLATES --------------
BASE_HTML = """
<!doctype html>
<html lang='en'><head>
<meta charset='utf-8'/><meta name='viewport' content='width=device-width,initial-scale=1'/>
<link href='https://cdn.jsdelivr.net/npm/bootstrap@5.3.2/dist/css/bootstrap.min.css' rel='stylesheet'/>
<style>body{background:#0f1724;color:#e6eef8} .card{background:#0b1320;border:none} .qr-img{max-width:230px;background:#fff;padding:8px;border-radius:8px} a{color:#7dd3fc}</style>
</head><body>
<div class='container py-4'>
  <div class='d-flex justify-content-between mb-3'>
    <h3>QR Attendance</h3>
    <div>
      <a href='/admin/login' class='btn btn-sm btn-outline-light'>Admin</a>
    </div>
  </div>
  {{content | safe}}
</div>
</body></html>
"""

INDEX_HTML = """
<div class='row'>
  <div class='col-lg-6'>
    <div class='card p-3'>
      <h5>Generate QR</h5>
      <p class='muted'>TTL: {{ttl}} seconds</p>
      <form method='post' action='/generate' class='d-flex gap-2'>
        <input class='form-control' name='slot' value='classA' required>
        <button class='btn btn-primary'>Generate</button>
      </form>

      {% if link %}
      <div class='mt-3 d-flex gap-3'>
        <img src='data:image/png;base64,{{qr_b64}}' class='qr-img'>
        <div>
          <p><b>Slot:</b> {{slot}}</p>
          <a href='{{link}}' target='_blank'>Open link</a><br>
          <button class='btn btn-sm btn-outline-light mt-2' onclick='navigator.clipboard.writeText("{{link}}")'>Copy Link</button>
        </div>
      </div>
      {% endif %}
    </div>
  </div>

  <div class='col-lg-6'>
    <div class='card p-3'>
      <h5>Recent</h5>
      {% if recent.empty %}
        <p class='text-secondary'>No records</p>
      {% else %}
        <div class='table-responsive small'>{{ recent.to_html(classes='table table-dark table-sm', index=False) | safe }}</div>
      {% endif %}
    </div>
  </div>
</div>
"""

SUBMIT_HTML = """
<div class='card p-3 col-md-6 mx-auto'>
  <h4>Submit — {{slot}}</h4>
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

LOGIN_HTML = """
<div class='card p-4 col-md-4 mx-auto'>
  <h4>Admin Login</h4>
  {% if error %}<div class='alert alert-danger'>{{error}}</div>{% endif %}
  <form method='post'>
    <input class='form-control' name='password' placeholder='Password' required>
    <button class='btn btn-primary w-100 mt-3'>Login</button>
  </form>
</div>
"""

ADMIN_HTML = """
<div class='card p-3'>
  <h4>Admin Panel</h4>
  <p class='mt-2'>
    <a href='/admin/view' class='btn btn-sm btn-outline-light'>View Records</a>
    <a href='/admin/export' class='btn btn-sm btn-outline-light ms-2'>Export Excel</a>
  </p>
  <hr>
  <h6>Clear records</h6>
  <form method='post' action='/admin/clear' class='d-flex gap-2 align-items-center mt-2'>
    <input name='slot' class='form-control form-control-sm' placeholder='(optional) slot name to clear only'>
    <button name='action' value='clear_slot' class='btn btn-sm btn-warning'>Clear Slot</button>
    <button name='action' value='clear_all' class='btn btn-sm btn-danger ms-2'>Clear All</button>
  </form>
  <p class='small-muted mt-2'>Clearing is permanent. Use carefully.</p>
</div>
"""

VIEW_HTML = """
<div class='card p-3'>
  <h4>Attendance Records</h4>
  <div class='table-responsive small mt-3'>{{table | safe}}</div>
  <a href='/admin' class='btn btn-sm btn-outline-light mt-3'>Back</a>
</div>
"""

ABOUT_HTML = "<div class='card p-3'><h4>About</h4><p>Tokens expire after {{ttl}} seconds.</p></div>"

# --------------- RENDER HELP --------------
def page(html, **ctx):
    inner = render_template_string(html, **ctx)
    return render_template_string(BASE_HTML, content=inner)

# --------------- ROUTES -------------------
@app.route("/")
def index():
    recent = query_records(limit=6, admin_view=True)
    return page(INDEX_HTML, ttl=QR_TTL_SECONDS, recent=recent, link=None, qr_b64=None, slot=None)

@app.route("/generate", methods=["POST"])
def generate():
    slot = request.form.get("slot","").strip()
    if not slot:
        return redirect(url_for("index"))
    token = make_token(slot)
    link = f"{BASE_URL}/submit?token={token}"
    img = qrcode.make(link)
    buf = io.BytesIO(); img.save(buf, format="PNG")
    qr_b64 = base64.b64encode(buf.getvalue()).decode("ascii")
    recent = query_records(limit=6, admin_view=True)
    return page(INDEX_HTML, ttl=QR_TTL_SECONDS, recent=recent, link=link, qr_b64=qr_b64, slot=slot)

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
    if request.method == "GET":
        return page(SUBMIT_HTML, slot=slot, error=None, token=token)
    name = request.form.get("student_name","").strip()
    roll = request.form.get("roll","").strip()
    pin = request.form.get("teacher_pin","").strip()
    if pin != TEACHER_PIN:
        return page(SUBMIT_HTML, slot=slot, error="Wrong Teacher PIN", token=token)
    device_cid = make_device_cid(request)
    df = query_records(slot=slot)
    if not df.empty and not df[df["device_cid"] == device_cid].empty:
        return "Already submitted from this device.", 400
    insert_record(name, roll, slot, device_cid, request.remote_addr or "", request.headers.get("User-Agent",""))
    return f"Attendance recorded for {name} (roll {roll})"

# ------- Admin -------
@app.route("/admin/login", methods=["GET","POST"])
def admin_login():
    if request.method == "GET":
        return page(LOGIN_HTML, error=None)
    pwd = request.form.get("password","")
    if pwd == ADMIN_PASSWORD:
        session["admin"] = True
        return redirect(url_for("admin"))
    return page(LOGIN_HTML, error="Wrong password")

@app.route("/admin")
def admin():
    if not session.get("admin"):
        return redirect(url_for("admin_login"))
    return page(ADMIN_HTML)

@app.route("/admin/view")
def admin_view():
    if not session.get("admin"):
        return redirect(url_for("admin_login"))
    df = query_records(admin_view=True)  # only useful columns
    table = df.to_html(index=False, classes="table table-dark table-sm")
    return page(VIEW_HTML, table=table)

@app.route("/admin/export")
def admin_export():
    if not session.get("admin"):
        return redirect(url_for("admin_login"))
    df = query_records()  # full export (includes device_cid/ip/user_agent)
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

@app.route("/about")
def about():
    return page(ABOUT_HTML, ttl=QR_TTL_SECONDS)

# --------------- START ------------------
if __name__ == "__main__":
    init_db()
    app.run(debug=True)
