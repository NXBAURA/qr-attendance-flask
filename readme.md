QR Attendance — README

This README explains everything someone needs to do to run, test, and host the QR Attendance app (single-file Flask app).
It assumes Windows 11 + PowerShell, but sections show notes for Linux/mac where helpful.

---
CONTENTS
1. Requirements
2. Files in repo
3. Quick start (run locally)
4. Environment variables (what each does)
5. Install dependencies (detailed commands)
6. Run the app (exact commands)
7. Test flow (teacher + student steps)
8. Expose to internet (ngrok quick test)
9. Deploying (suggested hosts)
10. Git / GitHub steps (how to push)
11. Security & production notes
12. Troubleshooting (common errors + fixes)
13. Useful commands summary

---
1) REQUIREMENTS
- Python 3.8+ installed and on PATH (3.10/3.11/3.12 recommended)
- pip available
- Git (optional, but recommended)
- PowerShell (Windows) or terminal (mac/linux)

2) FILES IN REPO (what to expect)
- app.py (main Flask single-file app)
- .gitignore
- README.txt (this file)
- requirements.txt (optional: pip freeze output)
- attendance.db (created automatically on first run)

3) QUICK START (the shortest path)
Open PowerShell in the project folder and run these commands one-by-one:

pip install --user Flask itsdangerous "qrcode[pil]" pillow pandas openpyxl
$env:SECRET_KEY="change_me"
$env:QR_SECRET="change_qr_secret"
$env:ADMIN_PASSWORD="admin123"
$env:QR_TTL_SECONDS="600"
$env:TEACHER_PIN="1234"
python app.py

Open browser: http://127.0.0.1:5000 (student page)
Open teacher page: http://127.0.0.1:5000/admin/login

4) ENVIRONMENT VARIABLES (explain)
- SECRET_KEY: Flask secret key (session cookies). Set a random string in production.
- QR_SECRET: secret used to sign QR tokens (itsdangerous). Change in production.
- ADMIN_PASSWORD: teacher/admin login password for admin panel.
- TEACHER_PIN: PIN students must enter when submitting attendance.
- QR_TTL_SECONDS: token validity in seconds (default 600 = 10 minutes).
- BASE_URL (optional): public base URL used when generating links (set when using ngrok or public domain). Default: http://127.0.0.1:5000

NOTE: Setting these via PowerShell as $env:VAR=... is temporary for that terminal session. To persist, set system/user environment variables in Windows Settings or use a .env loader.

5) INSTALL DEPENDENCIES (detailed)
Recommended: use per-user install so you don't need venv (as requested):

PowerShell (one-line per command):
pip install --user Flask itsdangerous "qrcode[pil]" pillow pandas openpyxl

If pip points to a different Python, run:
python -m pip install --user Flask itsdangerous "qrcode[pil]" pillow pandas openpyxl

Optionally generate requirements.txt:
python -m pip freeze > requirements.txt

6) RUN THE APP (exact commands)
1. In PowerShell set environment variables (example):
$env:SECRET_KEY="change_me"
$env:QR_SECRET="change_qr_secret"
$env:ADMIN_PASSWORD="admin123"
$env:QR_TTL_SECONDS="600"
$env:TEACHER_PIN="1234"
$env:BASE_URL="http://127.0.0.1:5000"

2. Run:
python app.py

Stop server: Ctrl+C in the terminal.

7) TEST FLOW (teacher + student)
Teacher:
- Open http://127.0.0.1:5000/admin/login
- Login using ADMIN_PASSWORD
- Activate a slot (e.g. type "classA"), then click Generate to produce a token+QR
- Share the generated link or QR with students (copy link button exists)
- Optionally view/export records and clear records (slot or all)

Students:
- Open http://127.0.0.1:5000 (student landing page)
- If teacher activated and generated a token, student will see "Open Attendance" link
- Click link or scan QR, fill name, roll, and enter Teacher PIN (set by teacher)
- Submit. Device-based duplicate prevention prevents the same device from submitting twice for the same slot.

8) EXPOSE TO INTERNET (ngrok quick test)
1. Download ngrok (https://ngrok.com) and authenticate it (ngrok authtoken ...).
2. Run in separate terminal:
ngrok http 5000
3. Copy the HTTPS URL ngrok provides (e.g. https://abcd1234.ngrok.io)
4. Set BASE_URL in your PowerShell before running app:
$env:BASE_URL="https://abcd1234.ngrok.io"
5. Run python app.py — generate QR and test from mobile.

Note: ngrok free URLs change every session unless you have a paid plan.

9) DEPLOYING (options)
- Use Render, Railway, Heroku, Fly or a VPS. Requirements:
  - Serve via WSGI (gunicorn) and behind HTTPS. Use environment variables in host.
  - For Docker: add a Dockerfile and use a reverse proxy (nginx) for production.

Simple Dockerfile example (starter):
FROM python:3.12-slim
WORKDIR /app
COPY . /app
RUN pip install --no-cache-dir Flask itsdangerous "qrcode[pil]" pillow pandas openpyxl
ENV FLASK_ENV=production
ENV PYTHONUNBUFFERED=1
CMD ["python","app.py"]

10) GIT / GITHUB (push steps)
1. git init
2. git add .
3. git commit -m "initial"
4. Create a new GitHub repo on github.com (do NOT initialize with README)
5. git remote add origin https://github.com/YOUR_USER/REPO.git
6. git branch -M main
7. git push -u origin main

11) SECURITY & PRODUCTION NOTES
- Never keep secrets in code. Use real environment variables or secret management.
- Use HTTPS in production. Do not expose the app without HTTPS.
- The device-lock (IP+User-Agent hash) is a convenience, not bulletproof. NATs, shared networks may cause false duplicates.
- Tokens are signed and time-limited; keep QR_SECRET private.
- Admin password and teacher PIN should be strong and changed regularly.

12) TROUBLESHOOTING (common errors)
- "TemplateAssertionError: block 'content' defined twice": make sure you are running the single-file app provided (it uses {{content | safe}}) and not a mix of templates.
- "ModuleNotFoundError": ensure you installed packages with pip for the same Python interpreter. Use python -m pip install ... to be safe.
- Token expired: tokens are TTL-limited (QR_TTL_SECONDS). Regenerate QR or increase TTL for longer windows.
- ngrok: if mobile can't reach localhost, ensure ngrok running and BASE_URL set to ngrok URL before generating QR.
- Database locked: stop the app, delete attendance.db (only for tests), restart app.

13) USEFUL COMMANDS SUMMARY (copy-paste)
# Install
pip install --user Flask itsdangerous "qrcode[pil]" pillow pandas openpyxl

# Set env vars (PowerShell)
$env:SECRET_KEY="change_me"
$env:QR_SECRET="change_qr_secret"
$env:ADMIN_PASSWORD="admin123"
$env:QR_TTL_SECONDS="600"
$env:TEACHER_PIN="1234"
$env:BASE_URL="http://127.0.0.1:5000"

# Run
python app.py

# Git (one-time)
git init
git add .
git commit -m "initial"
git remote add origin https://github.com/YOUR_USERNAME/REPO.git
git branch -M main
git push -u origin main

---
If you want, I can also:
- create README.md (markdown) with badges and screenshots,
- add Dockerfile and docker-compose,
- add a small GUI confirmation modal for "Clear All" in admin,
- create a one-click script to set env vars permanently on Windows.

Tell me which extras you want and I’ll add them. Cheers.

