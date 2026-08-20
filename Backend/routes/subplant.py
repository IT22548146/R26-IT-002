"""
routes/subplant.py
Local Sub Plant Portal (Part B) — the API behind the separate sub-plant app.

Every endpoint is scoped to the signed-in sub plant (g.plant_id), so one plant
can never read or write another plant's customers, orders, gatepasses or money.

Modules:
  /subplant/me                     the plant profile behind the token
  /subplant/customers              customer register (doc s12)
  /subplant/orders                 new order register (doc s13)
  /subplant/gatepasses             gatepass management (doc s14)
  /subplant/invoices               invoices + payments (doc s15-18)
  /subplant/dashboard              portal home KPIs
  /subplant/performance            this plant's own Component 4 result

Gatepasses are the integration point (doc s19): saving one refreshes that day's
row in plant_daily_logs, which is exactly what the Component 4 aggregation in
services/plant_analytics_service.py already consumes. No sync job required.
"""
from datetime import date, datetime

from flask import Blueprint, request, jsonify, g

from database.db import get_db
from middleware.auth_middleware import require_role

subplant_bp = Blueprint("subplant", __name__)


# ── helpers ───────────────────────────────────────────────────────────────

def _plant_id():
    """The sub plant tied to the signed-in user."""
    return g.plant_id


def _own(row_plant_id):
    return row_plant_id == _plant_id()


def _num(value, default=0.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _int(value, default=0):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _valid_date(value):
    try:
        datetime.strptime(str(value)[:10], "%Y-%m-%d")
        return True
    except (TypeError, ValueError):
        return False


def _refresh_daily_log(plant_id, log_date):
    """
    Roll all gatepasses for one plant-day into plant_daily_logs — the table the
    Component 4 monthly aggregation reads. Machines/staff fall back to the
    plant's registered totals since sub plants report output, not floor detail.
    """
    db = get_db()
    row = db.execute(
        """SELECT COALESCE(SUM(good_qty),0) AS good,
                  COALESCE(SUM(damage_qty),0) AS dmg,
                  COUNT(*) AS n
           FROM sub_plant_gatepasses WHERE plant_id=? AND gatepass_date=?""",
        (plant_id, log_date),
    ).fetchone()

    plant = db.execute("SELECT total_machines, employee_count FROM plants WHERE id=?",
                       (plant_id,)).fetchone()
    machines = (plant["total_machines"] if plant else None) or 10
    staff = (plant["employee_count"] if plant else None) or 30

    if not row or row["n"] == 0:
        # No gatepasses left for that day — drop the derived log row.
        db.execute("DELETE FROM plant_daily_logs WHERE plant_id=? AND log_date=?",
                   (plant_id, log_date))
        db.commit()
        return

    db.execute(
        """INSERT OR REPLACE INTO plant_daily_logs
           (plant_id, log_date, machines_total, machines_active, employees_present,
            machine_breakdown_count, worker_shortage_count, total_output,
            total_damage_qty, urgent_orders_handled, notes, submitted_by)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
        (plant_id, log_date, machines, machines, staff, 0, 0,
         row["good"] + row["dmg"], row["dmg"], 0, "from gatepass", g.user_id),
    )
    db.commit()


# ── profile ───────────────────────────────────────────────────────────────

@subplant_bp.route("/me", methods=["GET"])
@require_role("SubPlant")
def me():
    db = get_db()
    p = db.execute("SELECT * FROM plants WHERE id=?", (_plant_id(),)).fetchone()
    u = db.execute("SELECT id, full_name, email FROM users WHERE id=?", (g.user_id,)).fetchone()
    return jsonify({"plant": dict(p) if p else None, "user": dict(u) if u else None}), 200


# ── Customer Register (doc s12) ───────────────────────────────────────────

@subplant_bp.route("/customers", methods=["GET"])
@require_role("SubPlant")
def list_customers():
    db = get_db()
    rows = db.execute(
        """SELECT c.*,
                  (SELECT COUNT(*) FROM sub_plant_orders o WHERE o.customer_id=c.id) AS order_count,
                  (SELECT COALESCE(SUM(i.total_price - i.paid_amount),0)
                     FROM sub_plant_invoices i WHERE i.customer_id=c.id) AS balance
           FROM sub_plant_customers c
           WHERE c.plant_id=? ORDER BY c.created_at DESC""",
        (_plant_id(),),
    ).fetchall()
    return jsonify([dict(r) for r in rows]), 200


@subplant_bp.route("/customers", methods=["POST"])
@require_role("SubPlant")
def create_customer():
    data = request.get_json(force=True, silent=True) or {}
    name = (data.get("customer_name") or "").strip()
    if not name:
        return jsonify({"error": "Customer name is required."}), 400

    db = get_db()
    db.execute(
        """INSERT INTO sub_plant_customers
           (plant_id, customer_code, customer_name, customer_type, contact_no,
            location, registered_date, is_active)
           VALUES (?,?,?,?,?,?,?,?)""",
        (_plant_id(), (data.get("customer_code") or "").strip() or None, name,
         (data.get("customer_type") or "").strip() or None,
         (data.get("contact_no") or "").strip() or None,
         (data.get("location") or "").strip() or None,
         (data.get("registered_date") or date.today().isoformat())[:10],
         1 if data.get("is_active", True) else 0),
    )
    db.commit()
    new_id = db.execute("SELECT last_insert_rowid() AS id").fetchone()["id"]
    return jsonify({"message": "Customer registered", "id": new_id}), 201


@subplant_bp.route("/customers/<int:cid>", methods=["PUT"])
@require_role("SubPlant")
def update_customer(cid):
    data = request.get_json(force=True, silent=True) or {}
    db = get_db()
    row = db.execute("SELECT plant_id FROM sub_plant_customers WHERE id=?", (cid,)).fetchone()
    if not row or not _own(row["plant_id"]):
        return jsonify({"error": "Customer not found"}), 404

    fields, values = [], []
    for key in ("customer_code", "customer_name", "customer_type", "contact_no", "location"):
        if key in data:
            fields.append("%s=?" % key)
            values.append((data.get(key) or "").strip() or None)
    if "is_active" in data:
        fields.append("is_active=?")
        values.append(1 if data.get("is_active") else 0)
    if not fields:
        return jsonify({"error": "Nothing to update."}), 400
    values.append(cid)
    db.execute("UPDATE sub_plant_customers SET %s WHERE id=?" % ", ".join(fields), values)
    db.commit()
    return jsonify({"message": "Customer updated"}), 200


@subplant_bp.route("/customers/<int:cid>", methods=["DELETE"])
@require_role("SubPlant")
def delete_customer(cid):
    db = get_db()
    row = db.execute("SELECT plant_id FROM sub_plant_customers WHERE id=?", (cid,)).fetchone()
    if not row or not _own(row["plant_id"]):
        return jsonify({"error": "Customer not found"}), 404
    used = db.execute("SELECT COUNT(*) c FROM sub_plant_orders WHERE customer_id=?", (cid,)).fetchone()["c"]
    if used:
        return jsonify({"error": "This customer has orders — deactivate instead of deleting."}), 400
    db.execute("DELETE FROM sub_plant_customers WHERE id=?", (cid,))
    db.commit()
    return jsonify({"message": "Customer deleted"}), 200


@subplant_bp.route("/customers/stats", methods=["GET"])
@require_role("SubPlant")
def customer_stats():
    """Customer dashboard figures (doc s12)."""
    db = get_db()
    pid = _plant_id()
    total = db.execute("SELECT COUNT(*) c FROM sub_plant_customers WHERE plant_id=?", (pid,)).fetchone()["c"]
    active = db.execute("SELECT COUNT(*) c FROM sub_plant_customers WHERE plant_id=? AND is_active=1", (pid,)).fetchone()["c"]
    this_month = date.today().strftime("%Y-%m")
    new_this_month = db.execute(
        "SELECT COUNT(*) c FROM sub_plant_customers WHERE plant_id=? AND substr(registered_date,1,7)=?",
        (pid, this_month)).fetchone()["c"]
    pending_pay = db.execute(
        """SELECT COUNT(DISTINCT customer_id) c FROM sub_plant_invoices
           WHERE plant_id=? AND payment_status IN ('Pending','Partial','Overdue')""",
        (pid,)).fetchone()["c"]
    by_type = db.execute(
        """SELECT COALESCE(customer_type,'Unspecified') AS name, COUNT(*) AS value
           FROM sub_plant_customers WHERE plant_id=? GROUP BY customer_type""",
        (pid,)).fetchall()
    over_time = db.execute(
        """SELECT substr(registered_date,1,7) AS month, COUNT(*) AS count
           FROM sub_plant_customers WHERE plant_id=? AND registered_date IS NOT NULL
           GROUP BY month ORDER BY month""",
        (pid,)).fetchall()
    return jsonify({
        "total_customers": total, "active_customers": active,
        "new_this_month": new_this_month, "pending_payment_customers": pending_pay,
        "by_type": [dict(r) for r in by_type],
        "over_time": [dict(r) for r in over_time],
    }), 200


# ── New Order Register (doc s13) ──────────────────────────────────────────

@subplant_bp.route("/orders", methods=["GET"])
@require_role("SubPlant")
def list_orders():
    db = get_db()
    rows = db.execute(
        """SELECT o.*, c.customer_name,
                  (SELECT COALESCE(SUM(g.good_qty),0) FROM sub_plant_gatepasses g
                    WHERE g.order_id=o.id) AS dispatched_qty
           FROM sub_plant_orders o
           LEFT JOIN sub_plant_customers c ON c.id=o.customer_id
           WHERE o.plant_id=? ORDER BY o.created_at DESC""",
        (_plant_id(),),
    ).fetchall()
    return jsonify([dict(r) for r in rows]), 200


@subplant_bp.route("/orders", methods=["POST"])
@require_role("SubPlant")
def create_order():
    data = request.get_json(force=True, silent=True) or {}
    order_number = (data.get("order_number") or "").strip()
    qty = _int(data.get("order_quantity"))
    if not order_number:
        return jsonify({"error": "Order number is required."}), 400
    if qty <= 0:
        return jsonify({"error": "Order quantity must be greater than zero."}), 400
    for f in ("planned_start", "planned_finish"):
        if data.get(f) and not _valid_date(data[f]):
            return jsonify({"error": "%s must be YYYY-MM-DD." % f}), 400
    if data.get("planned_start") and data.get("planned_finish") \
            and str(data["planned_finish"])[:10] < str(data["planned_start"])[:10]:
        return jsonify({"error": "Planned finish cannot be before planned start."}), 400

    status = data.get("status") or "Draft"
    if status not in ("Draft", "Confirmed", "In Progress", "Completed", "Cancelled"):
        return jsonify({"error": "Invalid status."}), 400

    db = get_db()
    db.execute(
        """INSERT INTO sub_plant_orders
           (plant_id, order_number, customer_id, order_date, order_quantity,
            planned_start, planned_finish, status, notes)
           VALUES (?,?,?,?,?,?,?,?,?)""",
        (_plant_id(), order_number, data.get("customer_id") or None,
         (data.get("order_date") or date.today().isoformat())[:10], qty,
         (data.get("planned_start") or None), (data.get("planned_finish") or None),
         status, (data.get("notes") or "").strip() or None),
    )
    db.commit()
    new_id = db.execute("SELECT last_insert_rowid() AS id").fetchone()["id"]
    return jsonify({"message": "Order registered", "id": new_id}), 201


@subplant_bp.route("/orders/<int:oid>", methods=["PUT"])
@require_role("SubPlant")
def update_order(oid):
    data = request.get_json(force=True, silent=True) or {}
    db = get_db()
    row = db.execute("SELECT plant_id FROM sub_plant_orders WHERE id=?", (oid,)).fetchone()
    if not row or not _own(row["plant_id"]):
        return jsonify({"error": "Order not found"}), 404

    fields, values = [], []
    if "status" in data:
        if data["status"] not in ("Draft", "Confirmed", "In Progress", "Completed", "Cancelled"):
            return jsonify({"error": "Invalid status."}), 400
        fields.append("status=?"); values.append(data["status"])
        if data["status"] == "Completed":
            fields.append("actual_finish=?")
            values.append((data.get("actual_finish") or date.today().isoformat())[:10])
    if "order_quantity" in data:
        q = _int(data["order_quantity"])
        if q <= 0:
            return jsonify({"error": "Order quantity must be greater than zero."}), 400
        fields.append("order_quantity=?"); values.append(q)
    for key in ("planned_start", "planned_finish", "notes", "customer_id"):
        if key in data:
            fields.append("%s=?" % key); values.append(data[key] or None)
    if not fields:
        return jsonify({"error": "Nothing to update."}), 400
    values.append(oid)
    db.execute("UPDATE sub_plant_orders SET %s WHERE id=?" % ", ".join(fields), values)
    db.commit()
    return jsonify({"message": "Order updated"}), 200


@subplant_bp.route("/orders/<int:oid>", methods=["DELETE"])
@require_role("SubPlant")
def delete_order(oid):
    db = get_db()
    row = db.execute("SELECT plant_id FROM sub_plant_orders WHERE id=?", (oid,)).fetchone()
    if not row or not _own(row["plant_id"]):
        return jsonify({"error": "Order not found"}), 404
    db.execute("DELETE FROM sub_plant_orders WHERE id=?", (oid,))
    db.commit()
    return jsonify({"message": "Order deleted"}), 200


@subplant_bp.route("/orders/stats", methods=["GET"])
@require_role("SubPlant")
def order_stats():
    """Order register dashboard (doc s13)."""
    db = get_db()
    pid = _plant_id()
    this_month = date.today().strftime("%Y-%m")
    orders_month = db.execute(
        "SELECT COUNT(*) c, COALESCE(SUM(order_quantity),0) q FROM sub_plant_orders "
        "WHERE plant_id=? AND substr(order_date,1,7)=?", (pid, this_month)).fetchone()
    completed = db.execute(
        """SELECT COUNT(*) total,
                  SUM(CASE WHEN actual_finish IS NOT NULL AND planned_finish IS NOT NULL
                            AND actual_finish <= planned_finish THEN 1 ELSE 0 END) on_time
           FROM sub_plant_orders WHERE plant_id=? AND status='Completed'""",
        (pid,)).fetchone()
    on_time_rate = round((completed["on_time"] or 0) / completed["total"], 4) if completed["total"] else None
    avg_commit = db.execute(
        """SELECT AVG(daily) d FROM (
             SELECT order_quantity * 1.0 /
                    MAX(1, (julianday(planned_finish) - julianday(planned_start))) AS daily
             FROM sub_plant_orders
             WHERE plant_id=? AND planned_start IS NOT NULL AND planned_finish IS NOT NULL)""",
        (pid,)).fetchone()["d"]
    by_status = db.execute(
        "SELECT status AS name, COUNT(*) AS value FROM sub_plant_orders WHERE plant_id=? GROUP BY status",
        (pid,)).fetchall()
    trend = db.execute(
        """SELECT substr(order_date,1,7) AS month, COALESCE(SUM(order_quantity),0) AS qty,
                  COUNT(*) AS orders
           FROM sub_plant_orders WHERE plant_id=? AND order_date IS NOT NULL
           GROUP BY month ORDER BY month""",
        (pid,)).fetchall()
    return jsonify({
        "orders_this_month": orders_month["c"],
        "planned_quantity": orders_month["q"],
        "avg_daily_commitment": round(avg_commit, 1) if avg_commit else None,
        "on_time_rate": on_time_rate,
        "by_status": [dict(r) for r in by_status],
        "trend": [dict(r) for r in trend],
    }), 200


# ── Gatepass (doc s14) — feeds Component 4 (doc s19) ──────────────────────

@subplant_bp.route("/gatepasses", methods=["GET"])
@require_role("SubPlant")
def list_gatepasses():
    db = get_db()
    rows = db.execute(
        """SELECT g.*, c.customer_name, o.order_number,
                  (g.good_qty + g.damage_qty) AS total_qty
           FROM sub_plant_gatepasses g
           LEFT JOIN sub_plant_customers c ON c.id=g.customer_id
           LEFT JOIN sub_plant_orders o ON o.id=g.order_id
           WHERE g.plant_id=? ORDER BY g.gatepass_date DESC, g.id DESC""",
        (_plant_id(),),
    ).fetchall()
    return jsonify([dict(r) for r in rows]), 200


@subplant_bp.route("/gatepasses", methods=["POST"])
@require_role("SubPlant")
def create_gatepass():
    data = request.get_json(force=True, silent=True) or {}
    number = (data.get("gatepass_number") or "").strip()
    gp_date = (data.get("gatepass_date") or date.today().isoformat())[:10]
    good = _int(data.get("good_qty"))
    dmg = _int(data.get("damage_qty"))
    if not number:
        return jsonify({"error": "Gatepass number is required."}), 400
    if not _valid_date(gp_date):
        return jsonify({"error": "Gatepass date must be YYYY-MM-DD."}), 400
    if good < 0 or dmg < 0:
        return jsonify({"error": "Quantities cannot be negative."}), 400
    if good + dmg == 0:
        return jsonify({"error": "Enter at least one good or damaged piece."}), 400
    status = data.get("dispatch_status") or "Pending"
    if status not in ("Pending", "Dispatched", "Received"):
        return jsonify({"error": "Invalid dispatch status."}), 400

    db = get_db()
    db.execute(
        """INSERT INTO sub_plant_gatepasses
           (plant_id, gatepass_number, gatepass_date, order_id, customer_id,
            style_number, description, good_qty, damage_qty, dispatch_status)
           VALUES (?,?,?,?,?,?,?,?,?,?)""",
        (_plant_id(), number, gp_date, data.get("order_id") or None,
         data.get("customer_id") or None,
         (data.get("style_number") or "").strip() or None,
         (data.get("description") or "").strip() or None,
         good, dmg, status),
    )
    db.commit()
    # Push this day's production into Component 4's source table.
    _refresh_daily_log(_plant_id(), gp_date)
    new_id = db.execute("SELECT last_insert_rowid() AS id").fetchone()["id"]
    return jsonify({"message": "Gatepass recorded", "id": new_id,
                    "daily_log_updated": gp_date}), 201


@subplant_bp.route("/gatepasses/<int:gid>", methods=["DELETE"])
@require_role("SubPlant")
def delete_gatepass(gid):
    db = get_db()
    row = db.execute("SELECT plant_id, gatepass_date FROM sub_plant_gatepasses WHERE id=?", (gid,)).fetchone()
    if not row or not _own(row["plant_id"]):
        return jsonify({"error": "Gatepass not found"}), 404
    gp_date = str(row["gatepass_date"])[:10]
    db.execute("DELETE FROM sub_plant_gatepasses WHERE id=?", (gid,))
    db.commit()
    _refresh_daily_log(_plant_id(), gp_date)
    return jsonify({"message": "Gatepass deleted"}), 200


# ── Invoices + payments (doc s15-18) ──────────────────────────────────────

def _recalc_invoice_status(db, invoice_id):
    inv = db.execute("SELECT * FROM sub_plant_invoices WHERE id=?", (invoice_id,)).fetchone()
    if not inv:
        return
    paid = db.execute(
        "SELECT COALESCE(SUM(amount),0) p FROM sub_plant_payments WHERE invoice_id=?",
        (invoice_id,)).fetchone()["p"]
    total = inv["total_price"] or 0
    if paid <= 0:
        status = "Pending"
    elif paid + 0.01 >= total:
        status = "Paid"
    else:
        status = "Partial"
    if status != "Paid" and inv["due_date"] and str(inv["due_date"])[:10] < date.today().isoformat():
        status = "Overdue"
    db.execute("UPDATE sub_plant_invoices SET paid_amount=?, payment_status=? WHERE id=?",
               (paid, status, invoice_id))
    db.commit()


@subplant_bp.route("/invoices", methods=["GET"])
@require_role("SubPlant")
def list_invoices():
    db = get_db()
    rows = db.execute(
        """SELECT i.*, c.customer_name, (i.total_price - i.paid_amount) AS balance
           FROM sub_plant_invoices i
           LEFT JOIN sub_plant_customers c ON c.id=i.customer_id
           WHERE i.plant_id=? ORDER BY i.invoice_date DESC, i.id DESC""",
        (_plant_id(),),
    ).fetchall()
    return jsonify([dict(r) for r in rows]), 200


@subplant_bp.route("/invoices", methods=["POST"])
@require_role("SubPlant")
def create_invoice():
    data = request.get_json(force=True, silent=True) or {}
    number = (data.get("invoice_number") or "").strip()
    if not number:
        return jsonify({"error": "Invoice number is required."}), 400
    amount = _num(data.get("amount"))
    discount = _num(data.get("discount"))
    if amount <= 0:
        return jsonify({"error": "Amount must be greater than zero."}), 400
    if discount < 0 or discount > amount:
        return jsonify({"error": "Discount must be between 0 and the amount."}), 400
    total = round(amount - discount, 2)
    inv_date = (data.get("invoice_date") or date.today().isoformat())[:10]
    if not _valid_date(inv_date):
        return jsonify({"error": "Invoice date must be YYYY-MM-DD."}), 400

    db = get_db()
    db.execute(
        """INSERT INTO sub_plant_invoices
           (plant_id, invoice_number, invoice_date, customer_id, description,
            amount, discount, total_price, paid_amount, due_date, payment_status)
           VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
        (_plant_id(), number, inv_date, data.get("customer_id") or None,
         (data.get("description") or "").strip() or None,
         amount, discount, total, 0, data.get("due_date") or None, "Pending"),
    )
    db.commit()
    new_id = db.execute("SELECT last_insert_rowid() AS id").fetchone()["id"]
    return jsonify({"message": "Invoice created", "id": new_id, "total_price": total}), 201


@subplant_bp.route("/invoices/<int:iid>/payments", methods=["POST"])
@require_role("SubPlant")
def add_payment(iid):
    data = request.get_json(force=True, silent=True) or {}
    db = get_db()
    inv = db.execute("SELECT plant_id, total_price, paid_amount FROM sub_plant_invoices WHERE id=?",
                     (iid,)).fetchone()
    if not inv or not _own(inv["plant_id"]):
        return jsonify({"error": "Invoice not found"}), 404
    amount = _num(data.get("amount"))
    if amount <= 0:
        return jsonify({"error": "Payment amount must be greater than zero."}), 400
    outstanding = (inv["total_price"] or 0) - (inv["paid_amount"] or 0)
    if amount > outstanding + 0.01:
        return jsonify({"error": "Payment exceeds the outstanding balance of %.2f." % outstanding}), 400

    db.execute(
        """INSERT INTO sub_plant_payments (invoice_id, payment_date, amount, method, note)
           VALUES (?,?,?,?,?)""",
        (iid, (data.get("payment_date") or date.today().isoformat())[:10], amount,
         (data.get("method") or "").strip() or None, (data.get("note") or "").strip() or None),
    )
    db.commit()
    _recalc_invoice_status(db, iid)
    return jsonify({"message": "Payment recorded"}), 201


@subplant_bp.route("/invoices/<int:iid>", methods=["GET"])
@require_role("SubPlant")
def get_invoice(iid):
    db = get_db()
    inv = db.execute(
        """SELECT i.*, c.customer_name, c.location, c.contact_no
           FROM sub_plant_invoices i
           LEFT JOIN sub_plant_customers c ON c.id=i.customer_id
           WHERE i.id=?""", (iid,)).fetchone()
    if not inv or not _own(inv["plant_id"]):
        return jsonify({"error": "Invoice not found"}), 404
    pays = db.execute("SELECT * FROM sub_plant_payments WHERE invoice_id=? ORDER BY payment_date",
                      (iid,)).fetchall()
    return jsonify({"invoice": dict(inv), "payments": [dict(p) for p in pays]}), 200


@subplant_bp.route("/invoices/stats", methods=["GET"])
@require_role("SubPlant")
def invoice_stats():
    """Financial dashboard + payment status analysis (doc s16, s17)."""
    db = get_db()
    pid = _plant_id()
    this_month = date.today().strftime("%Y-%m")
    this_year = date.today().strftime("%Y")

    monthly = db.execute(
        "SELECT COALESCE(SUM(total_price),0) t FROM sub_plant_invoices "
        "WHERE plant_id=? AND substr(invoice_date,1,7)=?", (pid, this_month)).fetchone()["t"]
    yearly = db.execute(
        "SELECT COALESCE(SUM(total_price),0) t FROM sub_plant_invoices "
        "WHERE plant_id=? AND substr(invoice_date,1,4)=?", (pid, this_year)).fetchone()["t"]
    paid = db.execute("SELECT COALESCE(SUM(paid_amount),0) t FROM sub_plant_invoices WHERE plant_id=?",
                      (pid,)).fetchone()["t"]
    billed = db.execute("SELECT COALESCE(SUM(total_price),0) t FROM sub_plant_invoices WHERE plant_id=?",
                        (pid,)).fetchone()["t"]
    by_status = db.execute(
        "SELECT payment_status AS name, COUNT(*) AS value, COALESCE(SUM(total_price),0) AS amount "
        "FROM sub_plant_invoices WHERE plant_id=? GROUP BY payment_status", (pid,)).fetchall()
    income_trend = db.execute(
        """SELECT substr(invoice_date,1,7) AS month,
                  COALESCE(SUM(total_price),0) AS billed,
                  COALESCE(SUM(paid_amount),0) AS collected
           FROM sub_plant_invoices WHERE plant_id=? AND invoice_date IS NOT NULL
           GROUP BY month ORDER BY month""", (pid,)).fetchall()
    return jsonify({
        "monthly_income": round(monthly, 2),
        "yearly_income": round(yearly, 2),
        "paid_amount": round(paid, 2),
        "pending_amount": round(billed - paid, 2),
        "total_billed": round(billed, 2),
        "by_status": [dict(r) for r in by_status],
        "income_trend": [dict(r) for r in income_trend],
    }), 200


# ── Portal dashboard + own performance ────────────────────────────────────

@subplant_bp.route("/dashboard", methods=["GET"])
@require_role("SubPlant")
def dashboard():
    db = get_db()
    pid = _plant_id()
    this_month = date.today().strftime("%Y-%m")
    customers = db.execute("SELECT COUNT(*) c FROM sub_plant_customers WHERE plant_id=?", (pid,)).fetchone()["c"]
    open_orders = db.execute(
        "SELECT COUNT(*) c FROM sub_plant_orders WHERE plant_id=? AND status IN ('Confirmed','In Progress')",
        (pid,)).fetchone()["c"]
    out = db.execute(
        """SELECT COALESCE(SUM(good_qty),0) good, COALESCE(SUM(damage_qty),0) dmg
           FROM sub_plant_gatepasses WHERE plant_id=? AND substr(gatepass_date,1,7)=?""",
        (pid, this_month)).fetchone()
    total = (out["good"] or 0) + (out["dmg"] or 0)
    pending_money = db.execute(
        "SELECT COALESCE(SUM(total_price - paid_amount),0) t FROM sub_plant_invoices WHERE plant_id=?",
        (pid,)).fetchone()["t"]
    return jsonify({
        "month": this_month,
        "total_customers": customers,
        "open_orders": open_orders,
        "output_this_month": total,
        "damage_rate": round(((out["dmg"] or 0) / total * 100), 2) if total else 0.0,
        "pending_payment": round(pending_money, 2),
    }), 200


@subplant_bp.route("/performance/analyze", methods=["POST"])
@require_role("SubPlant")
def analyze_own_performance():
    """
    Run Component 4 for THIS plant only, for one month.

    The plant id is taken from the token, never from the request body, so a sub
    plant can only ever score itself. The model is deterministic over the month's
    gatepasses, so re-running cannot inflate a score - it simply recomputes from
    the records already entered.
    Body: { month: 'YYYY-MM' }  (defaults to the current month)
    """
    from services.plant_analytics_service import analyze_plant_month

    data = request.get_json(force=True, silent=True) or {}
    month_year = (data.get("month") or "").strip() or date.today().strftime("%Y-%m")
    try:
        datetime.strptime(month_year + "-01", "%Y-%m-%d")
    except ValueError:
        return jsonify({"error": "month must be YYYY-MM."}), 400
    if month_year > date.today().strftime("%Y-%m"):
        return jsonify({"error": "Cannot analyse a future month."}), 400

    res = analyze_plant_month(_plant_id(), month_year)
    if "error" in res:
        return jsonify(res), 400
    return jsonify({
        "message": "Performance updated",
        "month_year": month_year,
        "performance_score": res.get("performance_score"),
        "star_rating_num": res.get("star_rating_num"),
        "metrics": res.get("metrics"),
        "warnings": (res.get("c4_result") or {}).get("warnings", []),
    }), 200


@subplant_bp.route("/performance/months", methods=["GET"])
@require_role("SubPlant")
def own_performance_months():
    """Months this plant has production records for (newest first)."""
    db = get_db()
    rows = db.execute(
        """SELECT DISTINCT substr(log_date,1,7) AS m FROM plant_daily_logs
           WHERE plant_id=? ORDER BY m DESC LIMIT 24""", (_plant_id(),),
    ).fetchall()
    return jsonify({"months": [r["m"] for r in rows],
                    "current": date.today().strftime("%Y-%m")}), 200


@subplant_bp.route("/performance", methods=["GET"])
@require_role("SubPlant")
def own_performance():
    """This plant's own Component 4 history — the same scoring the mother company sees."""
    db = get_db()
    rows = db.execute(
        """SELECT month_year, performance_score, star_rating_num, efficiency,
                  utilization, damage_rate, delay_ratio, daily_commitment, total_workload
           FROM plant_performance WHERE plant_id=? ORDER BY month_year""",
        (_plant_id(),),
    ).fetchall()
    return jsonify({"trend": [dict(r) for r in rows]}), 200
