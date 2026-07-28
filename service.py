"""Business and database services for the Maji Power billing backend."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta
from typing import Any

DB_NAME = "utilities.db"
OFFICER_ROLES = {"billing_officer", "admin"}
PAYMENT_STATUSES = {"initiated", "pending", "confirmed", "failed", "cancelled"}
BILL_STATUSES = {"draft", "issued", "paid", "partially_paid", "overdue"}


class ServiceError(Exception):
    def __init__(self, message: str, status_code: int = 400, details: Any = None):
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.details = details


def get_connection(db_path: str = DB_NAME) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def row_to_dict(row: sqlite3.Row | None) -> dict | None:
    return dict(row) if row is not None else None


def rows_to_dicts(rows) -> list[dict]:
    return [dict(row) for row in rows]


def log_action(conn, user_id: int | None, action: str, target: str, detail: str | None = None) -> None:
    conn.execute(
        "INSERT INTO audit_log (user_id, action, target, detail) VALUES (?, ?, ?, ?)",
        (user_id, action, target, detail),
    )


def get_user(conn, user_id: int) -> dict:
    row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    if not row:
        raise ServiceError("User not found.", 401)
    return dict(row)


def dashboard(conn) -> dict:
    readings = conn.execute(
        "SELECT COUNT(*) AS total FROM meter_readings"
    ).fetchone()["total"]
    bills_to_generate = conn.execute(
        """
        SELECT COUNT(*) AS total
        FROM utility_accounts ua
        WHERE EXISTS (
            SELECT 1 FROM meter_readings mr
            WHERE mr.utility_account_id = ua.id
        )
        AND NOT EXISTS (
            SELECT 1 FROM bills b
            WHERE b.utility_account_id = ua.id
              AND b.billing_period = strftime('%Y-%m', 'now')
        )
        """
    ).fetchone()["total"]
    overdue = conn.execute(
        "SELECT COUNT(*) AS total FROM bills WHERE status = 'overdue'"
    ).fetchone()["total"]
    outstanding = conn.execute(
        """
        SELECT COALESCE(SUM(
            b.total_due - COALESCE((
                SELECT SUM(p.amount) FROM payments p
                WHERE p.bill_id = b.id AND p.status = 'confirmed'
            ), 0)
        ), 0) AS total
        FROM bills b
        WHERE b.status IN ('issued', 'partially_paid', 'overdue')
        """
    ).fetchone()["total"]
    confirmed_today = conn.execute(
        """
        SELECT COALESCE(SUM(amount), 0) AS total
        FROM payments
        WHERE status = 'confirmed' AND DATE(paid_at) = DATE('now')
        """
    ).fetchone()["total"]
    return {
        "readings_received": readings,
        "bills_to_generate": bills_to_generate,
        "overdue_accounts": overdue,
        "outstanding_balance": round(float(outstanding or 0), 2),
        "collections_today": round(float(confirmed_today or 0), 2),
    }


def list_accounts(conn, service_type: str | None = None, search: str | None = None) -> dict:
    sql = """
        SELECT ua.*, u.name AS customer_name, u.phone AS customer_phone,
               (SELECT mr.current_reading FROM meter_readings mr
                WHERE mr.utility_account_id = ua.id
                ORDER BY mr.reading_date DESC, mr.id DESC LIMIT 1) AS latest_reading
        FROM utility_accounts ua
        JOIN users u ON u.id = ua.customer_id
        WHERE 1=1
    """
    params: list[Any] = []
    if service_type:
        if service_type not in {"water", "electricity"}:
            raise ServiceError("service_type must be water or electricity.")
        sql += " AND ua.service_type = ?"
        params.append(service_type)
    if search:
        sql += " AND (ua.account_number LIKE ? OR ua.meter_number LIKE ? OR u.name LIKE ?)"
        value = f"%{search}%"
        params.extend([value, value, value])
    sql += " ORDER BY ua.account_number"
    items = rows_to_dicts(conn.execute(sql, params).fetchall())
    return {"items": items, "count": len(items)}


def _validate_period(period: str) -> str:
    try:
        datetime.strptime(period, "%Y-%m")
    except (TypeError, ValueError):
        raise ServiceError("billing_period must use YYYY-MM format.")
    return period


def _validate_date(value: str, field: str) -> str:
    try:
        datetime.strptime(value, "%Y-%m-%d")
    except (TypeError, ValueError):
        raise ServiceError(f"{field} must use YYYY-MM-DD format.")
    return value


def _active_tariff(conn, service_type: str) -> dict:
    row = conn.execute(
        """
        SELECT * FROM tariffs
        WHERE service_type = ?
          AND active_from <= DATE('now')
          AND (active_to IS NULL OR active_to >= DATE('now'))
        ORDER BY active_from DESC, id DESC
        LIMIT 1
        """,
        (service_type,),
    ).fetchone()
    if row:
        return dict(row)
    defaults = {
        "water": {"price_per_unit": 50.0, "fixed_charge": 200.0, "tax_rate": 0.04, "overdue_penalty_flat": 100.0},
        "electricity": {"price_per_unit": 20.0, "fixed_charge": 150.0, "tax_rate": 0.05, "overdue_penalty_flat": 150.0},
    }
    return {"service_type": service_type, **defaults[service_type]}


def _confirmed_paid(conn, bill_id: int) -> float:
    row = conn.execute(
        "SELECT COALESCE(SUM(amount), 0) AS total FROM payments WHERE bill_id = ? AND status='confirmed'",
        (bill_id,),
    ).fetchone()
    return float(row["total"] or 0)


def bill_preview(conn, account_id: int, billing_period: str, due_date: str) -> dict:
    _validate_period(billing_period)
    _validate_date(due_date, "due_date")
    account = conn.execute(
        """
        SELECT ua.*, u.name AS customer_name
        FROM utility_accounts ua JOIN users u ON u.id = ua.customer_id
        WHERE ua.id = ?
        """,
        (account_id,),
    ).fetchone()
    if not account:
        raise ServiceError("Utility account not found.", 404)
    account = dict(account)

    duplicate = conn.execute(
        "SELECT id FROM bills WHERE utility_account_id=? AND billing_period=?",
        (account_id, billing_period),
    ).fetchone()
    reading = conn.execute(
        """
        SELECT * FROM meter_readings
        WHERE utility_account_id = ?
        ORDER BY reading_date DESC, id DESC LIMIT 1
        """,
        (account_id,),
    ).fetchone()
    if not reading:
        return {**account, "can_generate": False, "exception": "Missing meter reading."}
    reading = dict(reading)
    consumption = float(reading["consumption"])
    if consumption < 0:
        return {**account, "can_generate": False, "exception": "Negative consumption reading."}

    tariff = _active_tariff(conn, account["service_type"])
    previous_balance_row = conn.execute(
        """
        SELECT COALESCE(SUM(
            total_due - COALESCE((SELECT SUM(p.amount) FROM payments p
                                  WHERE p.bill_id=b.id AND p.status='confirmed'),0)
        ),0) AS balance
        FROM bills b
        WHERE utility_account_id=? AND status IN ('issued','partially_paid','overdue')
        """,
        (account_id,),
    ).fetchone()
    previous_balance = max(float(previous_balance_row["balance"] or 0), 0)
    consumption_charge = round(consumption * float(tariff["price_per_unit"]), 2)
    fixed_charge = round(float(tariff["fixed_charge"]), 2)
    tax_amount = round((consumption_charge + fixed_charge) * float(tariff["tax_rate"]), 2)
    total_due = round(previous_balance + consumption_charge + fixed_charge + tax_amount, 2)
    warning = None
    if consumption > 0 and consumption >= max(float(reading["previous_reading"]) * 0.5, 100):
        warning = "High-consumption reading: review before generation."
    return {
        "account_id": account_id,
        "account_number": account["account_number"],
        "meter_number": account["meter_number"],
        "customer_name": account["customer_name"],
        "service_type": account["service_type"],
        "meter_reading_id": reading["id"],
        "previous_reading": reading["previous_reading"],
        "current_reading": reading["current_reading"],
        "consumption": consumption,
        "billing_period": billing_period,
        "previous_balance": round(previous_balance, 2),
        "price_per_unit": float(tariff["price_per_unit"]),
        "consumption_charge": consumption_charge,
        "fixed_charge": fixed_charge,
        "tax_amount": tax_amount,
        "penalty_amount": 0.0,
        "total_due": total_due,
        "due_date": due_date,
        "warning": warning,
        "can_generate": duplicate is None,
        "exception": "Bill already exists for this period." if duplicate else None,
    }


def bulk_preview(conn, billing_period: str, due_date: str, service_type: str | None = None) -> dict:
    _validate_period(billing_period)
    _validate_date(due_date, "due_date")
    accounts = list_accounts(conn, service_type=service_type)["items"]
    items = [bill_preview(conn, int(a["id"]), billing_period, due_date) for a in accounts]
    return {
        "billing_period": billing_period,
        "due_date": due_date,
        "items": items,
        "ready_to_generate": sum(1 for item in items if item["can_generate"]),
        "exceptions": [item for item in items if not item["can_generate"] or item.get("warning")],
    }


def _insert_bill(conn, preview: dict, user_id: int) -> int:
    cur = conn.execute(
        """
        INSERT INTO bills (
            utility_account_id, meter_reading_id, billing_period, previous_balance,
            consumption_charge, fixed_charge, tax_amount, penalty_amount, total_due,
            status, due_date, created_by_user_id
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'issued', ?, ?)
        """,
        (
            preview["account_id"], preview["meter_reading_id"], preview["billing_period"],
            preview["previous_balance"], preview["consumption_charge"], preview["fixed_charge"],
            preview["tax_amount"], preview["penalty_amount"], preview["total_due"],
            preview["due_date"], user_id,
        ),
    )
    bill_id = int(cur.lastrowid)
    log_action(conn, user_id, "bill_generated", f"bill:{bill_id}", f"Issued {preview['billing_period']} bill for {preview['account_number']}")
    return bill_id


def generate_bill(conn, user_id: int, account_id: int, billing_period: str, due_date: str) -> dict:
    preview = bill_preview(conn, account_id, billing_period, due_date)
    if not preview["can_generate"]:
        raise ServiceError(preview.get("exception") or "Bill cannot be generated.", 409, preview)
    bill_id = _insert_bill(conn, preview, user_id)
    conn.commit()
    return get_bill(conn, bill_id)


def generate_bulk(conn, user_id: int, billing_period: str, due_date: str, service_type: str | None = None) -> dict:
    preview = bulk_preview(conn, billing_period, due_date, service_type)
    generated, skipped = [], []
    for item in preview["items"]:
        if item["can_generate"]:
            generated.append(_insert_bill(conn, item, user_id))
        else:
            skipped.append({"account_id": item["account_id"], "reason": item.get("exception")})
    conn.commit()
    return {"message": "Billing run completed.", "generated_bill_ids": generated, "generated_count": len(generated), "skipped": skipped}


def list_bills(conn, status: str | None = None, billing_period: str | None = None, account: str | None = None) -> dict:
    sql = """
        SELECT b.*, ua.account_number, ua.meter_number, ua.service_type,
               u.name AS customer_name,
               COALESCE((SELECT SUM(p.amount) FROM payments p
                         WHERE p.bill_id=b.id AND p.status='confirmed'),0) AS paid_amount
        FROM bills b
        JOIN utility_accounts ua ON ua.id=b.utility_account_id
        JOIN users u ON u.id=ua.customer_id
        WHERE 1=1
    """
    params: list[Any] = []
    if status:
        if status not in BILL_STATUSES:
            raise ServiceError("Invalid bill status.")
        sql += " AND b.status=?"; params.append(status)
    if billing_period:
        _validate_period(billing_period); sql += " AND b.billing_period=?"; params.append(billing_period)
    if account:
        sql += " AND (ua.account_number LIKE ? OR ua.meter_number LIKE ?)"
        params.extend([f"%{account}%", f"%{account}%"])
    sql += " ORDER BY b.created_at DESC, b.id DESC"
    items = rows_to_dicts(conn.execute(sql, params).fetchall())
    for item in items:
        item["balance"] = round(float(item["total_due"]) - float(item["paid_amount"] or 0), 2)
    return {"items": items, "count": len(items)}


def get_bill(conn, bill_id: int) -> dict:
    row = conn.execute(
        """
        SELECT b.*, ua.account_number, ua.meter_number, ua.service_type, ua.address,
               u.name AS customer_name, u.phone AS customer_phone,
               mr.previous_reading, mr.current_reading, mr.consumption
        FROM bills b
        JOIN utility_accounts ua ON ua.id=b.utility_account_id
        JOIN users u ON u.id=ua.customer_id
        LEFT JOIN meter_readings mr ON mr.id=b.meter_reading_id
        WHERE b.id=?
        """,
        (bill_id,),
    ).fetchone()
    if not row:
        raise ServiceError("Bill not found.", 404)
    result = dict(row)
    result["payments"] = rows_to_dicts(conn.execute("SELECT * FROM payments WHERE bill_id=? ORDER BY id DESC", (bill_id,)).fetchall())
    result["paid_amount"] = _confirmed_paid(conn, bill_id)
    result["balance"] = round(float(result["total_due"]) - result["paid_amount"], 2)
    return result


def process_overdue(conn, user_id: int, apply_penalty: bool = True) -> dict:
    rows = conn.execute(
        "SELECT * FROM bills WHERE status IN ('issued','partially_paid') AND DATE(due_date) < DATE('now')"
    ).fetchall()
    updated = []
    for row in rows:
        bill = dict(row)
        penalty = float(bill["penalty_amount"] or 0)
        if apply_penalty and penalty == 0:
            service_type = conn.execute("SELECT service_type FROM utility_accounts WHERE id=?", (bill["utility_account_id"],)).fetchone()["service_type"]
            penalty = float(_active_tariff(conn, service_type)["overdue_penalty_flat"])
        new_total = round(float(bill["total_due"]) - float(bill["penalty_amount"] or 0) + penalty, 2)
        conn.execute("UPDATE bills SET status='overdue', penalty_amount=?, total_due=? WHERE id=?", (penalty, new_total, bill["id"]))
        log_action(conn, user_id, "bill_marked_overdue", f"bill:{bill['id']}", f"Penalty applied: {penalty}")
        updated.append(bill["id"])
    conn.commit()
    return {"updated_bill_ids": updated, "count": len(updated)}


def queue_bill_notifications(conn, user_id: int, bill_ids: list[int] | None = None) -> dict:
    if bill_ids:
        placeholders = ",".join("?" for _ in bill_ids)
        rows = conn.execute(
            f"""SELECT b.id, b.total_due, b.due_date, ua.customer_id, ua.account_number
                FROM bills b JOIN utility_accounts ua ON ua.id=b.utility_account_id
                WHERE b.status IN ('issued','overdue') AND b.id IN ({placeholders})""",
            bill_ids,
        ).fetchall()
    else:
        rows = conn.execute(
            """SELECT b.id, b.total_due, b.due_date, ua.customer_id, ua.account_number
               FROM bills b JOIN utility_accounts ua ON ua.id=b.utility_account_id
               WHERE b.status IN ('issued','overdue')"""
        ).fetchall()
    queued = []
    for row in rows:
        message = f"Maji Power bill for {row['account_number']}: KES {row['total_due']:.2f}, due {row['due_date']}."
        cur = conn.execute(
            "INSERT INTO notification_queue (user_id,bill_id,channel,message,status) VALUES (?,?, 'sms', ?, 'queued')",
            (row["customer_id"], row["id"], message),
        )
        queued.append(cur.lastrowid)
    log_action(conn, user_id, "notifications_queued", "notification_queue", f"Queued {len(queued)} bill notifications")
    conn.commit()
    return {"queued_count": len(queued), "notification_ids": queued}


def list_payments(conn, status: str | None = None, method: str | None = None, account: str | None = None, billing_period: str | None = None) -> dict:
    sql = """
        SELECT p.*, b.billing_period, b.total_due, b.status AS bill_status,
               ua.account_number, ua.meter_number, u.name AS customer_name
        FROM payments p
        JOIN bills b ON b.id=p.bill_id
        JOIN utility_accounts ua ON ua.id=b.utility_account_id
        JOIN users u ON u.id=ua.customer_id
        WHERE 1=1
    """
    params: list[Any] = []
    if status:
        if status not in PAYMENT_STATUSES: raise ServiceError("Invalid payment status.")
        sql += " AND p.status=?"; params.append(status)
    if method:
        if method not in {"mobile_money","card","bank"}: raise ServiceError("Invalid payment method.")
        sql += " AND p.payment_method=?"; params.append(method)
    if account:
        sql += " AND (ua.account_number LIKE ? OR ua.meter_number LIKE ?)"; params.extend([f"%{account}%",f"%{account}%"])
    if billing_period:
        _validate_period(billing_period); sql += " AND b.billing_period=?"; params.append(billing_period)
    sql += " ORDER BY p.created_at DESC, p.id DESC"
    items = rows_to_dicts(conn.execute(sql, params).fetchall())
    return {"items": items, "count": len(items)}


def get_payment(conn, payment_id: int) -> dict:
    row = conn.execute(
        """SELECT p.*, b.billing_period, b.total_due, ua.account_number, u.name AS customer_name
           FROM payments p JOIN bills b ON b.id=p.bill_id
           JOIN utility_accounts ua ON ua.id=b.utility_account_id
           JOIN users u ON u.id=ua.customer_id WHERE p.id=?""",
        (payment_id,),
    ).fetchone()
    if not row: raise ServiceError("Payment not found.", 404)
    result = dict(row)
    result["timeline"] = rows_to_dicts(conn.execute("SELECT * FROM payment_status_events WHERE payment_id=? ORDER BY id", (payment_id,)).fetchall())
    result["receipt"] = row_to_dict(conn.execute("SELECT * FROM receipts WHERE payment_id=?", (payment_id,)).fetchone())
    return result


def create_payment(conn, bill_id: int, amount: float, method: str, provider_reference: str | None = None) -> dict:
    if amount <= 0: raise ServiceError("amount must be greater than zero.")
    if method not in {"mobile_money","card","bank"}: raise ServiceError("Invalid payment method.")
    get_bill(conn, bill_id)
    cur = conn.execute(
        "INSERT INTO payments (bill_id,amount,payment_method,status,provider_reference) VALUES (?,?,?,'pending',?)",
        (bill_id, amount, method, provider_reference),
    )
    pid = int(cur.lastrowid)
    conn.execute("INSERT INTO payment_status_events (payment_id,status,detail) VALUES (?, 'pending', 'Payment submitted')", (pid,))
    conn.commit()
    return get_payment(conn, pid)


def update_payment_status(conn, user_id: int, payment_id: int, status: str, provider_reference: str | None = None) -> dict:
    if status not in {"confirmed", "failed", "cancelled", "pending"}:
        raise ServiceError("Status must be confirmed, failed, cancelled, or pending.")
    payment = get_payment(conn, payment_id)
    paid_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S") if status == "confirmed" else None
    receipt_id = payment.get("receipt_id")
    if status == "confirmed" and not receipt_id:
        receipt_id = f"RCPT-{datetime.now():%Y%m%d}-{payment_id:05d}"
    conn.execute(
        "UPDATE payments SET status=?, provider_reference=COALESCE(?,provider_reference), receipt_id=?, paid_at=? WHERE id=?",
        (status, provider_reference, receipt_id, paid_at, payment_id),
    )
    conn.execute("INSERT INTO payment_status_events (payment_id,status,detail) VALUES (?,?,?)", (payment_id, status, f"Updated by user {user_id}"))
    if status == "confirmed":
        existing = conn.execute("SELECT id FROM receipts WHERE payment_id=?", (payment_id,)).fetchone()
        if not existing:
            conn.execute(
                "INSERT INTO receipts (receipt_number,payment_id,bill_id,amount,provider_reference) VALUES (?,?,?,?,?)",
                (receipt_id, payment_id, payment["bill_id"], payment["amount"], provider_reference or payment.get("provider_reference")),
            )
        bill = get_bill(conn, payment["bill_id"])
        paid = _confirmed_paid(conn, payment["bill_id"])
        new_status = "paid" if paid >= float(bill["total_due"]) else "partially_paid"
        conn.execute("UPDATE bills SET status=? WHERE id=?", (new_status, payment["bill_id"]))
    log_action(conn, user_id, f"payment_{status}", f"payment:{payment_id}", f"Bill {payment['bill_id']}")
    conn.commit()
    return get_payment(conn, payment_id)


def manual_link_payment(conn, admin_id: int, payment_id: int, bill_id: int) -> dict:
    get_payment(conn, payment_id); get_bill(conn, bill_id)
    conn.execute("UPDATE payments SET bill_id=? WHERE id=?", (bill_id, payment_id))
    log_action(conn, admin_id, "payment_manually_linked", f"payment:{payment_id}", f"Linked to bill {bill_id}")
    conn.commit()
    return get_payment(conn, payment_id)


def report_daily_collections(conn, date_from: str | None = None, date_to: str | None = None) -> dict:
    sql = """SELECT DATE(paid_at) AS payment_date, COUNT(*) AS number_of_payments,
                    ROUND(SUM(amount),2) AS total_collected
             FROM payments WHERE status='confirmed'"""
    params = []
    if date_from: _validate_date(date_from,"date_from"); sql += " AND DATE(paid_at)>=?"; params.append(date_from)
    if date_to: _validate_date(date_to,"date_to"); sql += " AND DATE(paid_at)<=?"; params.append(date_to)
    sql += " GROUP BY DATE(paid_at) ORDER BY payment_date DESC"
    return {"items": rows_to_dicts(conn.execute(sql, params).fetchall())}


def report_overdue(conn) -> dict:
    items = rows_to_dicts(conn.execute(
        """SELECT b.id AS bill_id, u.name AS customer_name, u.phone, ua.account_number,
                  ua.service_type, b.total_due, b.due_date,
                  ROUND(b.total_due-COALESCE((SELECT SUM(p.amount) FROM payments p WHERE p.bill_id=b.id AND p.status='confirmed'),0),2) AS balance
           FROM bills b JOIN utility_accounts ua ON ua.id=b.utility_account_id
           JOIN users u ON u.id=ua.customer_id WHERE b.status='overdue' ORDER BY b.due_date"""
    ).fetchall())
    return {"items": items, "count": len(items)}


def report_revenue(conn) -> dict:
    items = rows_to_dicts(conn.execute(
        """SELECT ua.service_type, COUNT(p.id) AS payment_count, ROUND(COALESCE(SUM(p.amount),0),2) AS revenue
           FROM utility_accounts ua LEFT JOIN bills b ON b.utility_account_id=ua.id
           LEFT JOIN payments p ON p.bill_id=b.id AND p.status='confirmed'
           GROUP BY ua.service_type ORDER BY ua.service_type"""
    ).fetchall())
    return {"items": items}


def audit_logs(conn, limit: int = 100) -> dict:
    rows = conn.execute(
        """SELECT al.*, u.name AS user_name, u.role AS user_role
           FROM audit_log al LEFT JOIN users u ON u.id=al.user_id
           ORDER BY al.id DESC LIMIT ?""", (max(1,min(limit,500)),)
    ).fetchall()
    return {"items": rows_to_dicts(rows)}
