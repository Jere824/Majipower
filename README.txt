MAJI POWER DATABASE AUTHENTICATION UPDATE

Files
-----
app.py
    Updated Flask API. Login retrieves the phone number, password_hash,
    role, and active status directly from the users table in utilities.db.

utilities.db
    Updated copy of the submitted SQLite database. All five sample users now
    have secure PBKDF2 password hashes. Plain-text passwords are not stored.

Place app.py and utilities.db beside your existing service.py.

Temporary demonstration credentials
-----------------------------------
Customer:
  +254700000001 / Alice123!
  +254700000002 / Brian123!

Billing Officer:
  +254700000003 / Billing123!

Meter Reader:
  +254700000004 / Meter123!

Administrator:
  +254700000005 / Admin123!

Run
---
source .venv/bin/activate
python3 app.py

Login example
-------------
curl -X POST http://127.0.0.1:5000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"phone":"+254700000003","password":"Billing123!"}'

Important
---------
These are temporary development passwords. Change them before deployment.