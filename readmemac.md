📋 QR Attendance — README (macOS)

This README explains everything needed to run, test, and host the QR Attendance app (single-file Flask app) locally on macOS.


---

CONTENTS

1. Requirements


2. Files in repo


3. Quick start (run locally)


4. Environment variables (what each does)


5. Install dependencies (exact commands)


6. Run the app


7. Test flow (teacher + student)


8. Expose to internet (ngrok)


9. Deploying (suggested hosts)


10. Git / GitHub steps


11. Security & production notes


12. Troubleshooting


13. Useful commands summary




---

1) REQUIREMENTS

macOS (Intel or Apple Silicon M1/M2/M3)

Python 3.8+ (3.10+ recommended)

pip

Terminal (zsh)

Git (optional but recommended)


Check Python:

python3 --version

Install Python (if missing):

brew install python


---

2) FILES IN REPO

app.py — main Flask single-file app

.gitignore

README.md

requirements.txt (optional)

attendance.db (created automatically)



---

3) QUICK START (FASTEST WAY)

Open Terminal in the project folder and run one by one:

pip3 install --user Flask itsdangerous "qrcode[pil]" pillow pandas openpyxl

export SECRET_KEY="change_me"
export QR_SECRET="change_qr_secret"
export ADMIN_PASSWORD="admin123"
export QR_TTL_SECONDS="600"
export TEACHER_PIN="1234"

python3 app.py

Open:

Student page → http://127.0.0.1:5000

Teacher page → http://127.0.0.1:5000/admin/login



---

4) ENVIRONMENT VARIABLES (EXPLAINED)

SECRET_KEY → Flask session security key

QR_SECRET → Secret used to sign QR tokens

ADMIN_PASSWORD → Admin / teacher login password

TEACHER_PIN → PIN students must enter

QR_TTL_SECONDS → QR validity time (seconds)

BASE_URL (optional) → Public base URL (used with ngrok)


> macOS export VAR=value is temporary for that Terminal session.




---

5) INSTALL DEPENDENCIES (DETAILED)

Recommended (no venv required):

pip3 install --user Flask itsdangerous "qrcode[pil]" pillow pandas openpyxl

If pip mismatch:

python3 -m pip install --user Flask itsdangerous "qrcode[pil]" pillow pandas openpyxl

Generate requirements file:

python3 -m pip freeze > requirements.txt


---

6) RUN THE APP

export SECRET_KEY="change_me"
export QR_SECRET="change_qr_secret"
export ADMIN_PASSWORD="admin123"
export QR_TTL_SECONDS="600"
export TEACHER_PIN="1234"
export BASE_URL="http://127.0.0.1:5000"

python3 app.py

Stop server:

CTRL + C


---

7) TEST FLOW

Teacher

Open /admin/login

Login using ADMIN_PASSWORD

Generate QR/token

Share QR or link

View / export attendance


Student

Open root page or scan QR

Enter name, roll, teacher PIN

Submit attendance



---

8) EXPOSE TO INTERNET (ngrok)

brew install ngrok
ngrok config add-authtoken YOUR_TOKEN
ngrok http 5000

Set base URL:

export BASE_URL="https://abcd1234.ngrok.io"
python3 app.py


---

9) DEPLOYING

Supported:

Render

Railway

Fly.io

VPS + gunicorn


Docker example:

FROM python:3.12-slim
WORKDIR /app
COPY . .
RUN pip install Flask itsdangerous "qrcode[pil]" pillow pandas openpyxl
CMD ["python","app.py"]


---

10) GIT / GITHUB

git init
git add .
git commit -m "initial"
git branch -M main
git remote add origin https://github.com/YOUR_USER/REPO.git
git push -u origin main


---

11) SECURITY NOTES

Never hard-code secrets

Use HTTPS in production

QR tokens are time-limited

Device lock is not foolproof



---

12) TROUBLESHOOTING

ModuleNotFoundError

python3 -m pip install <package>

Token expired

Regenerate QR

Increase QR_TTL_SECONDS


ngrok not reachable

Ensure BASE_URL set before QR generation



---

13) USEFUL COMMANDS SUMMARY

pip3 install --user Flask itsdangerous "qrcode[pil]" pillow pandas openpyxl

export SECRET_KEY="change_me"
export QR_SECRET="change_qr_secret"
export ADMIN_PASSWORD="admin123"
export QR_TTL_SECONDS="600"
export TEACHER_PIN="1234"
export BASE_URL="http://127.0.0.1:5000"

python3 app.py


---

✅ FINAL CONFIRMATION

✔ Your existing Flask QR Attendance app runs on macOS without any code changes.
✔ Only command syntax changes (python3, export) are needed.

If you want:

ultra-short README (1-page),

school-project explanation,

macOS app bundling,

or public hosting guide,


just tell me.
