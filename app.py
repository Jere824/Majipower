"""Maji Power Flask API focused on Billing & Collections Officer operations."""

from __future__ import annotations

import os
import secrets
import sqlite3
from datetime import datetime, timedelta
from functools import wraps

from flask import Flask, g, jsonify, request
from werkzeug.security import check_password_hash, generate_password_hash

import service

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.environ.get("MAJI_DB_PATH", os.path.join(BASE_DIR, "utilities.db"))
TOKEN_HOURS = 1

app = Flask(__name__)
app.config["JSON_SORT_KEYS"] = False


def db():
    if "db" not in g:
        g.db = service.get_connection(DB_PATH)
    return g.db


@app.teardown_appcontext
def close_db(_error=None):
    connection = g.pop("db", None)
    if connection is not None:
        connection.close()


def migrate_auth():
    conn = service.get_connection(DB_PATH)
    columns = {row["name"] for row in conn.execute("PRAGMA table_info(users)")}
    if "password_hash" not in columns:
        conn.execute("ALTER TABLE users ADD COLUMN password_hash TEXT")
    if "is_active" not in columns:
        conn.execute("ALTER TABLE users ADD COLUMN is_active INTEGER NOT NULL DEFAULT 1")
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS auth_sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL REFERENCES users(id),
            token TEXT NOT NULL UNIQUE,
            expires_at TEXT NOT NULL,
            revoked_at TEXT,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        )
        """
    )
    demo_passwords = {
        "+254700000003": "Billing123!",
        "+254700000005": "Admin123!",
    }
    for phone, password in demo_passwords.items():
        conn.execute(
            "UPDATE users SET password_hash=COALESCE(password_hash, ?) WHERE phone=?",
            (generate_password_hash(password, method="pbkdf2:sha256:600000"), phone),
        )
    conn.commit()
    conn.close()


def body_json():
    data = request.get_json(silent=True)
    if data is None:
        raise service.ServiceError("Request body must contain valid JSON.")
    return data


def bearer_token():
    header = request.headers.get("Authorization", "")
    if not header.startswith("Bearer "):
        raise service.ServiceError("Missing Authorization: Bearer <token> header.", 401)
    return header[7:].strip()


def authenticated_user():
    token = bearer_token()
    row = db().execute(
        """
        SELECT u.*, s.token, s.expires_at
        FROM auth_sessions s JOIN users u ON u.id=s.user_id
        WHERE s.token=? AND s.revoked_at IS NULL AND s.expires_at > datetime('now')
        """,
        (token,),
    ).fetchone()
    if not row:
        raise service.ServiceError("Invalid or expired login token.", 401)
    user = dict(row)
    if not user.get("is_active", 1):
        raise service.ServiceError("This user account is disabled.", 403)
    return user


def roles_allowed(*roles):
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            user = authenticated_user()
            if user["role"] not in roles:
                raise service.ServiceError(
                    f"Access denied. Required role: {', '.join(roles)}. Current role: {user['role']}.",
                    403,
                )
            g.current_user = user
            return func(*args, **kwargs)
        return wrapper
    return decorator


@app.errorhandler(service.ServiceError)
def handle_service_error(error):
    payload = {"error": error.message}
    if error.details is not None:
        payload["details"] = error.details
    return jsonify(payload), error.status_code


@app.errorhandler(sqlite3.IntegrityError)
def handle_integrity_error(error):
    return jsonify({"error": "Database constraint failed.", "details": str(error)}), 409


@app.errorhandler(Exception)
def handle_unexpected_error(error):
    app.logger.exception("Unhandled error")
    return jsonify({"error": "Internal server error.", "details": str(error) if app.debug else None}), 500


@app.get("/health")
def health():
    return jsonify({"status": "ok", "service": "Maji Power Billing API"})


@app.post("/api/auth/login")
def login():
    data = body_json()
    phone = str(data.get("phone", "")).strip()
    password = str(data.get("password", ""))
    if not phone or not password:
        raise service.ServiceError("phone and password are required.")
    user = db().execute("SELECT * FROM users WHERE phone=?", (phone,)).fetchone()

    print(f"User: {user}")  
    if not user or not user["password_hash"] or not check_password_hash(user["password_hash"], password):
        raise service.ServiceError("Invalid phone number or password.", 401)

    
    if not check_password_hash(user["password_hash"], password):
        raise service.ServiceError("wrong password.", 401)
    
    if not user["is_active"]:
        raise service.ServiceError("This user account is disabled.", 403)
    token = secrets.token_urlsafe(32)
    expires = (datetime.now() + timedelta(hours=TOKEN_HOURS)).strftime("%Y-%m-%d %H:%M:%S")
    db().execute("INSERT INTO auth_sessions (user_id,token,expires_at) VALUES (?,?,?)", (user["id"], token, expires))
    service.log_action(db(), user["id"], "login", f"user:{user['id']}", "Successful login")
    db().commit()
    return jsonify({
        "access_token": token,
        "token_type": "Bearer",
        "expires_at": expires,
      
        "user": {"id": user["id"], "name": user["name"], "phone": user["phone"], "role": user["role"]},
    })


@app.post("/api/auth/logout")
@roles_allowed("customer", "meter_reader", "billing_officer", "admin")
def logout():
    db().execute("UPDATE auth_sessions SET revoked_at=datetime('now') WHERE token=?", (bearer_token(),))
    service.log_action(db(), g.current_user["id"], "logout", f"user:{g.current_user['id']}")
    db().commit()
    return jsonify({"message": "Logged out successfully."})


@app.get("/api/auth/me")
@roles_allowed("customer", "meter_reader", "billing_officer", "admin")
def me():
    user = g.current_user
    return jsonify({"id": user["id"], "name": user["name"], "phone": user["phone"], "role": user["role"]})


# Billing & Collections Officer dashboard and account review
@app.get("/api/officer/dashboard")
@roles_allowed("billing_officer", "admin")
def officer_dashboard():
    return jsonify(service.dashboard(db()))


@app.get("/api/officer/accounts")
@roles_allowed("billing_officer", "admin")
def accounts():
    return jsonify(service.list_accounts(db(), request.args.get("service_type"), request.args.get("search")))


# Billing run: preview exceptions first, then generate one or many bills
@app.post("/api/officer/billing/preview")
@roles_allowed("billing_officer", "admin")
def preview_one():
    data = body_json()
    return jsonify(service.bill_preview(db(), int(data["account_id"]), data["billing_period"], data["due_date"]))


@app.post("/api/officer/billing/preview-bulk")
@roles_allowed("billing_officer", "admin")
def preview_bulk():
    data = body_json()
    return jsonify(service.bulk_preview(db(), data["billing_period"], data["due_date"], data.get("service_type")))


@app.post("/api/officer/bills")
@roles_allowed("billing_officer", "admin")
def create_bill():
    data = body_json()
    result = service.generate_bill(db(), g.current_user["id"], int(data["account_id"]), data["billing_period"], data["due_date"])
    return jsonify(result), 201


@app.post("/api/officer/bills/bulk")
@roles_allowed("billing_officer", "admin")
def create_bulk_bills():
    data = body_json()
    result = service.generate_bulk(db(), g.current_user["id"], data["billing_period"], data["due_date"], data.get("service_type"))
    return jsonify(result), 201


@app.get("/api/officer/bills")
@roles_allowed("billing_officer", "admin")
def bills():
    return jsonify(service.list_bills(db(), request.args.get("status"), request.args.get("billing_period"), request.args.get("account")))


@app.get("/api/officer/bills/<int:bill_id>")
@roles_allowed("billing_officer", "admin")
def bill_details(bill_id):
    return jsonify(service.get_bill(db(), bill_id))


@app.post("/api/officer/bills/process-overdue")
@roles_allowed("billing_officer", "admin")
def overdue():
    data = request.get_json(silent=True) or {}
    return jsonify(service.process_overdue(db(), g.current_user["id"], bool(data.get("apply_penalty", True))))


@app.post("/api/officer/notifications")
@roles_allowed("billing_officer", "admin")
def notifications():
    data = request.get_json(silent=True) or {}
    return jsonify(service.queue_bill_notifications(db(), g.current_user["id"], data.get("bill_ids")))


# Payments and reconciliation
@app.get("/api/officer/payments")
@roles_allowed("billing_officer", "admin")
def payments():
    return jsonify(service.list_payments(db(), request.args.get("status"), request.args.get("method"), request.args.get("account"), request.args.get("billing_period")))


@app.get("/api/officer/payments/<int:payment_id>")
@roles_allowed("billing_officer", "admin")
def payment_details(payment_id):
    return jsonify(service.get_payment(db(), payment_id))


@app.post("/api/payments")
@roles_allowed("customer", "billing_officer", "admin")
def submit_payment():
    data = body_json()
    result = service.create_payment(db(), int(data["bill_id"]), float(data["amount"]), data["payment_method"], data.get("provider_reference"))
    return jsonify(result), 201


@app.patch("/api/officer/payments/<int:payment_id>/status")
@roles_allowed("billing_officer", "admin")
def reconcile_payment(payment_id):
    data = body_json()
    return jsonify(service.update_payment_status(db(), g.current_user["id"], payment_id, data["status"], data.get("provider_reference")))


@app.patch("/api/admin/payments/<int:payment_id>/link")
@roles_allowed("admin")
def link_payment(payment_id):
    data = body_json()
    return jsonify(service.manual_link_payment(db(), g.current_user["id"], payment_id, int(data["bill_id"])))


# Officer reports and traceability
@app.get("/api/officer/reports/daily-collections")
@roles_allowed("billing_officer", "admin")
def daily_collections():
    return jsonify(service.report_daily_collections(db(), request.args.get("date_from"), request.args.get("date_to")))


@app.get("/api/officer/reports/overdue")
@roles_allowed("billing_officer", "admin")
def overdue_report():
    return jsonify(service.report_overdue(db()))


@app.get("/api/officer/reports/revenue")
@roles_allowed("billing_officer", "admin")
def revenue_report():
    return jsonify(service.report_revenue(db()))


@app.get("/api/officer/audit-log")
@roles_allowed("billing_officer", "admin")
def audit_log():
    return jsonify(service.audit_logs(db(), int(request.args.get("limit", 100))))


if __name__ == "__main__":
    migrate_auth()
    app.run(host="127.0.0.1", port=int(os.environ.get("PORT", "5000")), debug=True)