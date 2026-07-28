# Maji Power Flask Backend

A simplified two-file Flask backend focused on the **Billing & Collections Officer**.

## Structure

```text
maji_power_flask_revamp/
├── app.py          # Flask routes, authentication and role protection
├── service.py      # SQLite queries and billing/payment business rules
├── utilities.db    # Your supplied database
└── requirements.txt
```

## Setup on macOS

```bash
cd maji_power_flask_revamp
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -r requirements.txt
python3 app.py
```

The server runs at `http://127.0.0.1:5000`.

## Demo login

Billing officer:

```json
{
  "phone": "+254700000003",
  "password": "Billing123!"
}
```

Admin:

```json
{
  "phone": "+254700000005",
  "password": "Admin123!"
}
```

Login command:

```bash
curl -X POST http://127.0.0.1:5000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"phone":"+254700000003","password":"Billing123!"}'
```

Copy the returned `access_token`, then use it in protected requests:

```bash
curl http://127.0.0.1:5000/api/officer/dashboard \
  -H "Authorization: Bearer YOUR_TOKEN"
```

## Main Billing Officer endpoints

- `GET /api/officer/dashboard`
- `GET /api/officer/accounts`
- `POST /api/officer/billing/preview`
- `POST /api/officer/billing/preview-bulk`
- `POST /api/officer/bills`
- `POST /api/officer/bills/bulk`
- `GET /api/officer/bills`
- `GET /api/officer/bills/<id>`
- `POST /api/officer/bills/process-overdue`
- `POST /api/officer/notifications`
- `GET /api/officer/payments`
- `GET /api/officer/payments/<id>`
- `PATCH /api/officer/payments/<id>/status`
- `GET /api/officer/reports/daily-collections`
- `GET /api/officer/reports/overdue`
- `GET /api/officer/reports/revenue`
- `GET /api/officer/audit-log`

`app.py` automatically adds password and session support to the existing database when it starts.
