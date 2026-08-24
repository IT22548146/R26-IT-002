"""
routes/plant.py
Plant Manager portal endpoints:
  - View assigned orders
  - Submit daily production logs (runs C3 automatically)
  - Mark bulk orders as Ready (emails Buyer + Admin)
  - Notifications inbox
"""

import os
import json
from datetime import datetime, timedelta
from flask import Blueprint, request, jsonify, g, current_app
from database.db import get_db
from middleware.auth_middleware import require_role
from services.email_service import (
    send_critical_risk_alert,
    send_order_ready_to_buyer,
    send_order_ready_to_admin,
)
from services.notification_service import create_notification

plant_bp = Blueprint("plant", __name__)

ADMIN_EMAIL = os.environ.get("ADMIN_EMAIL", "admin@fabricflow.com")

PRODUCTION_STAGES = ["Pending", "Cutting", "Embroidery", "Sewing", "Packing", "Shipping", "Delivery"]


def _get_admin():
    db = get_db()
    return db.execute("SELECT id, email FROM users WHERE role='Admin' LIMIT 1").fetchone()


# ── Assigned Orders ───────────────────────────────────────────────────────

@plant_bp.route("/orders", methods=["GET"])
@require_role("PlantManager")
def list_assigned_orders():
    """Bulk orders assigned to my plant."""
    db    = get_db()
    plant_id = g.plant_id

    # Lazy auto-completion: once an approved order's production window has
    # elapsed (plant_approved_at + total production days), mark it Completed.
    _auto_complete_elapsed_orders(db, plant_id)

    orders = db.execute(
        """SELECT bo.id, bo.style_number, bo.bulk_order_quantity, bo.style_priority,
                  bo.approved_date, bo.buyer_required_date, bo.status, bo.production_stage,
                  bo.assigned_at, bo.plant_approved_at, bo.ready_at, bo.created_at,
                  bo.c2_result_json,
                  opa.allocated_qty, opa.allocation_type,
                  u.full_name AS buyer_name
           FROM bulk_orders bo
           JOIN order_plant_allocations opa ON opa.bulk_order_id = bo.id
           JOIN users u ON bo.buyer_id = u.id
           WHERE opa.plant_id = ?
           ORDER BY bo.created_at DESC""",
        (plant_id,),
    ).fetchall()
    result = []
    for o in orders:
        row = dict(o)
        prod_days = None
        if row.get("c2_result_json"):
            try:
                prod_days = json.loads(row["c2_result_json"]).get("production_days", {}).get("total_production_days")
            except Exception:
                prod_days = None
        row["total_production_days"] = prod_days
        row["expected_completion_date"] = _expected_completion(row.get("plant_approved_at"), prod_days)
        del row["c2_result_json"]
        result.append(row)
    return jsonify(result), 200


def _expected_completion(plant_approved_at, prod_days):
    """Return YYYY-MM-DD when an approved order should finish, or None."""
    if not plant_approved_at or not prod_days:
        return None
    try:
        start = datetime.strptime(str(plant_approved_at)[:10], "%Y-%m-%d")
        return (start + timedelta(days=int(round(float(prod_days))))).strftime("%Y-%m-%d")
    except Exception:
        return None


def _auto_complete_elapsed_orders(db, plant_id):
    """Mark approved Processing orders Completed once their production window has passed."""
    rows = db.execute(
        """SELECT bo.id, bo.plant_approved_at, bo.c2_result_json
           FROM bulk_orders bo
           JOIN order_plant_allocations opa ON opa.bulk_order_id = bo.id
           WHERE opa.plant_id = ? AND bo.status = 'Processing'
                 AND bo.plant_approved_at IS NOT NULL""",
        (plant_id,),
    ).fetchall()
    today = datetime.utcnow().date()
    changed = False
    for r in rows:
        prod_days = None
        if r["c2_result_json"]:
            try:
                prod_days = json.loads(r["c2_result_json"]).get("production_days", {}).get("total_production_days")
            except Exception:
                prod_days = None
        exp = _expected_completion(r["plant_approved_at"], prod_days)
        if exp and datetime.strptime(exp, "%Y-%m-%d").date() <= today:
            db.execute("UPDATE bulk_orders SET status='Completed', ready_at=? WHERE id=?",
                       (datetime.utcnow(), r["id"]))
            changed = True
    if changed:
        db.commit()


@plant_bp.route("/sample-orders", methods=["GET"])
@require_role("PlantManager")
def list_assigned_sample_orders():
    """Sample orders assigned to my plant."""
    db = get_db()
    plant_id = g.plant_id
    orders = db.execute(
        """SELECT so.*, u.full_name AS buyer_name
           FROM sample_orders so
           JOIN users u ON so.buyer_id = u.id
           WHERE so.assigned_plant_id = ?
           ORDER BY so.created_at DESC""",
        (plant_id,),
    ).fetchall()
    return jsonify([dict(o) for o in orders]), 200


@plant_bp.route("/sample-orders/<int:order_id>/ready", methods=["POST"])
@require_role("PlantManager")
def mark_sample_order_ready(order_id):
    """Mark an assigned sample order as completed/ready."""
    db = get_db()
    plant_id = g.plant_id

    order = db.execute(
        "SELECT * FROM sample_orders WHERE id = ? AND assigned_plant_id = ?",
        (order_id, plant_id)
    ).fetchone()

    if not order:
        return jsonify({"error": "Sample Order not found or not assigned to your plant"}), 404

    if order["status"] == "Completed":
        return jsonify({"error": "Already marked as completed"}), 400

    db.execute(
        "UPDATE sample_orders SET status='Completed' WHERE id=?",
        (order_id,)
    )
    db.commit()

    # Notify admin and buyer
    plant = db.execute("SELECT name FROM plants WHERE id=?", (plant_id,)).fetchone()
    buyer = db.execute("SELECT id, email, full_name FROM users WHERE id=?", (order["buyer_id"],)).fetchone()
    admin = _get_admin()

    plant_name_str = plant["name"] if plant else plant_id

    if buyer:
        send_order_ready_to_buyer(
            buyer["email"], buyer["full_name"],
            order["style_number"], order_id, plant_name_str
        )
        create_notification(
            buyer["id"],
            f"Sample Order Ready — {order['style_number']}",
            f"Your sample order #{order_id} has been completed by {plant_name_str}.",
            notif_type="success", related_order_type="sample_order", related_order_id=order_id,
        )

    if admin:
        send_order_ready_to_admin(
            admin["email"], plant_name_str,
            order["style_number"], order_id
        )
        create_notification(
            admin["id"],
            f"Sample Order Ready — {order['style_number']}",
            f"{plant_name_str} has marked sample order #{order_id} as completed.",
            notif_type="info", related_order_type="sample_order", related_order_id=order_id,
        )

    return jsonify({"message": "Sample order marked as completed!"}), 200

@plant_bp.route("/orders/<int:order_id>", methods=["GET"])
@require_role("PlantManager")
def get_assigned_order(order_id):
    """Full detail of an assigned bulk order including C2 result."""
    db       = get_db()
    plant_id = g.plant_id
    order = db.execute(
        """SELECT bo.* FROM bulk_orders bo
           JOIN order_plant_allocations opa ON opa.bulk_order_id = bo.id
           WHERE bo.id = ? AND opa.plant_id = ?""",
        (order_id, plant_id),
    ).fetchone()
    if not order:
        return jsonify({"error": "Order not found or not assigned to your plant"}), 404
    row = dict(order)
    if row.get("c2_result_json"):
        row["c2_result"] = json.loads(row["c2_result_json"])
        del row["c2_result_json"]
    return jsonify(row), 200


# ── Daily Logs ────────────────────────────────────────────────────────────

@plant_bp.route("/orders/<int:order_id>/log", methods=["POST"])
@require_role("PlantManager")
def submit_daily_log(order_id):
    """
    Plant Manager submits today's production log.
    Required: plant_daily_output, daily_damage_qty, max_daily_damage_qty,
              machine_breakdown_count, worker_shortage_count,
              cumulative_completed_qty
    Component 3 runs automatically and the risk result is saved.
    If severity=Critical, emails Admin + Plant Manager.
    """
    data = request.get_json(force=True, silent=True) or {}
    required = ["plant_daily_output", "cumulative_completed_qty"]
    missing  = [f for f in required if data.get(f) is None]
    if missing:
        return jsonify({"error": f"Missing fields: {missing}"}), 400

    db       = get_db()
    plant_id = g.plant_id

    # Verify order is assigned to this plant
    order = db.execute(
        """SELECT bo.* FROM bulk_orders bo
           JOIN order_plant_allocations opa ON opa.bulk_order_id = bo.id
           WHERE bo.id = ? AND opa.plant_id = ?""",
        (order_id, plant_id),
    ).fetchone()
    if not order:
        return jsonify({"error": "Order not found or not assigned to your plant"}), 404
    if order["status"] != "Processing":
        return jsonify({"error": f"Cannot log for order in status: {order['status']}"}), 400

    # Auto-derive working_day_no
    working_day_no = (
        db.execute(
            "SELECT COUNT(*) AS cnt FROM daily_logs WHERE bulk_order_id=? AND plant_id=?",
            (order_id, plant_id),
        ).fetchone()["cnt"]
        + 1
    )

    # Log date: defaults to today, but the plant manager can pick another date so a
    # missed day can still be entered. Future dates are rejected.
    today = datetime.utcnow().date().isoformat()
    log_date = str(data.get("log_date") or today)[:10]
    try:
        parsed = datetime.strptime(log_date, "%Y-%m-%d").date()
    except ValueError:
        return jsonify({"error": "log_date must be YYYY-MM-DD."}), 400
    if parsed > datetime.utcnow().date():
        return jsonify({"error": "Cannot log production for a future date."}), 400
    today = log_date
    full_qty   = order["bulk_order_quantity"]
    commitment = order["daily_commitment"]

    # Total working days from C2 result
    c2_data          = json.loads(order["c2_result_json"]) if order["c2_result_json"] else {}
    total_work_days  = int(c2_data.get("production_days", {}).get("total_production_days", 30))
    remaining_qty    = max(0, full_qty - int(data["cumulative_completed_qty"]))

    # Build C3 payload
    c3_payload = {
        "bulk_order_id":           str(order_id),
        "style_id":                order["style_number"],
        "buyer_name":              "N/A",
        "allocated_bulk_plant":    plant_id,
        "plant_location":          "N/A",
        "full_order_qty":          full_qty,
        # These are DATE columns, so the app connection (PARSE_DECLTYPES) hands back
        # datetime.date objects. Flask would serialise those as HTTP-date strings
        # ("Sun, 27 Dec 2026 ..."), which Component 3 cannot parse - so send ISO text.
        "bulk_order_approved_date": str(order["approved_date"])[:10],
        "buyer_required_date":     str(order["buyer_required_date"])[:10],
        "total_working_days":      total_work_days,
        "cutting_days":            int(c2_data.get("production_days", {}).get("cutting_days", 10)),
        "sewing_days":             int(c2_data.get("production_days", {}).get("sewing_days", 10)),
        "daily_commitment":        commitment,
        "production_date":         today,
        "working_day_no":          working_day_no,
        "plant_daily_output":      int(data["plant_daily_output"]),
        "daily_damage_qty":        int(data.get("daily_damage_qty", 0)),
        "max_daily_damage_qty":    int(data.get("max_daily_damage_qty", 20)),
        "machine_breakdown_count": int(data.get("machine_breakdown_count", 0)),
        "worker_shortage_count":   int(data.get("worker_shortage_count", 0)),
        "cumulative_completed_qty": int(data["cumulative_completed_qty"]),
    }

    with current_app.test_client() as client:
        resp = client.post(
            "/api/component3/predict",
            json=c3_payload,
            headers={"Content-Type": "application/json"},
        )
        c3_result = resp.get_json()

    # Save log
    db.execute(
        """INSERT OR REPLACE INTO daily_logs
           (bulk_order_id, plant_id, log_date, working_day_no, plant_daily_output,
            daily_damage_qty, max_daily_damage_qty, machine_breakdown_count,
            worker_shortage_count, cumulative_completed_qty, c3_result_json, submitted_by)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            order_id, plant_id, today, working_day_no,
            int(data["plant_daily_output"]),
            int(data.get("daily_damage_qty", 0)),
            int(data.get("max_daily_damage_qty", 20)),
            int(data.get("machine_breakdown_count", 0)),
            int(data.get("worker_shortage_count", 0)),
            int(data["cumulative_completed_qty"]),
            json.dumps(c3_result),
            g.user_id,
        ),
    )

    # Logging keeps the order in Processing (assignment already set it there).
    db.commit()

    # ── Critical risk alert ───────────────────────────────────────────────
    # C3 nests these under "risk_detection" — reading them at the top level
    # silently returned "" and the alert never fired.
    _risk       = c3_result.get("risk_detection") or {}
    severity    = _risk.get("severity") or ""
    risk_type   = _risk.get("risk_type", "Unknown")
    recom       = _risk.get("recommendation", "")

    if severity == "Critical":
        admin = _get_admin()
        plant = db.execute("SELECT name FROM plants WHERE id=?", (plant_id,)).fetchone()
        pm    = db.execute("SELECT email FROM users WHERE id=?", (g.user_id,)).fetchone()

        send_critical_risk_alert(
            admin["email"] if admin else ADMIN_EMAIL,
            pm["email"] if pm else "",
            plant["name"] if plant else plant_id,
            order["style_number"],
            order_id, risk_type, recom,
        )
        if admin:
            create_notification(
                admin["id"],
                f"⚠️ Critical Risk — Order #{order_id}",
                f"Critical risk '{risk_type}' detected at {plant['name'] if plant else plant_id}. {recom}",
                notif_type="critical",
                related_order_type="bulk_order", related_order_id=order_id,
            )
        create_notification(
            g.user_id,
            f"⚠️ Critical Risk Detected — Order #{order_id}",
            f"Risk type: {risk_type}. Recommended action: {recom}",
            notif_type="critical",
            related_order_type="bulk_order", related_order_id=order_id,
        )

    return jsonify({
        "message":       "Daily log submitted",
        "order_id":      order_id,
        "working_day_no": working_day_no,
        "c3_result":     c3_result,
    }), 201


@plant_bp.route("/orders/<int:order_id>/logs", methods=["GET"])
@require_role("PlantManager")
def get_order_logs(order_id):
    """All daily logs for a specific bulk order."""
    db       = get_db()
    plant_id = g.plant_id
    logs = db.execute(
        "SELECT * FROM daily_logs WHERE bulk_order_id=? AND plant_id=? ORDER BY log_date",
        (order_id, plant_id),
    ).fetchall()
    result = []
    for l in logs:
        row = dict(l)
        if row.get("c3_result_json"):
            row["c3_result"] = json.loads(row["c3_result_json"])
            del row["c3_result_json"]
        result.append(row)
    return jsonify(result), 200


# ── Plant approval of an assignment ────────────────────────────────────────

@plant_bp.route("/orders/<int:order_id>/approve", methods=["POST"])
@require_role("PlantManager")
def approve_assignment(order_id):
    """
    Plant Manager accepts an assigned order. The production-day countdown (which
    drives auto-completion) starts from this approval.
    """
    db = get_db()
    plant_id = g.plant_id
    order = db.execute(
        """SELECT bo.* FROM bulk_orders bo
           JOIN order_plant_allocations opa ON opa.bulk_order_id = bo.id
           WHERE bo.id = ? AND opa.plant_id = ?""",
        (order_id, plant_id),
    ).fetchone()
    if not order:
        return jsonify({"error": "Order not found or not assigned to your plant"}), 404
    if order["status"] != "Processing":
        return jsonify({"error": f"Only Processing orders can be approved. Current: {order['status']}"}), 400
    if order["plant_approved_at"]:
        return jsonify({"error": "Order already approved."}), 400

    db.execute("UPDATE bulk_orders SET plant_approved_at=? WHERE id=?", (datetime.utcnow(), order_id))
    db.commit()

    admin = _get_admin()
    if admin:
        create_notification(
            admin["id"],
            f"Plant Accepted Order — {order['style_number']}",
            f"The assigned plant has accepted bulk order #{order_id} and started production.",
            notif_type="success", related_order_type="bulk_order", related_order_id=order_id,
        )
    return jsonify({"message": "Assignment approved", "order_id": order_id}), 200


# ── Production stage updates ────────────────────────────────────────────────

@plant_bp.route("/orders/<int:order_id>/stage", methods=["POST"])
@require_role("PlantManager")
def update_bulk_stage(order_id):
    """Plant advances the production stage of a bulk order assigned to it."""
    data = request.get_json(force=True, silent=True) or {}
    stage = data.get("stage")
    if stage not in PRODUCTION_STAGES:
        return jsonify({"error": f"Invalid stage. Allowed: {PRODUCTION_STAGES}"}), 400

    db = get_db()
    order = db.execute(
        """SELECT bo.id, bo.style_number, bo.buyer_id FROM bulk_orders bo
           JOIN order_plant_allocations opa ON opa.bulk_order_id = bo.id
           WHERE bo.id = ? AND opa.plant_id = ?""",
        (order_id, g.plant_id),
    ).fetchone()
    if not order:
        return jsonify({"error": "Order not found or not assigned to your plant"}), 404

    db.execute("UPDATE bulk_orders SET production_stage=? WHERE id=?", (stage, order_id))
    db.commit()
    create_notification(
        order["buyer_id"],
        f"Production Update — {order['style_number']}",
        f"Your bulk order #{order_id} is now at the '{stage}' stage.",
        notif_type="info", related_order_type="bulk_order", related_order_id=order_id,
    )
    return jsonify({"message": "Stage updated", "production_stage": stage}), 200


@plant_bp.route("/sample-orders/<int:order_id>/stage", methods=["POST"])
@require_role("PlantManager")
def update_sample_stage(order_id):
    """Plant advances the production stage of a sample order assigned to it."""
    data = request.get_json(force=True, silent=True) or {}
    stage = data.get("stage")
    if stage not in PRODUCTION_STAGES:
        return jsonify({"error": f"Invalid stage. Allowed: {PRODUCTION_STAGES}"}), 400

    db = get_db()
    order = db.execute(
        "SELECT id, style_number, buyer_id FROM sample_orders WHERE id=? AND assigned_plant_id=?",
        (order_id, g.plant_id),
    ).fetchone()
    if not order:
        return jsonify({"error": "Order not found or not assigned to your plant"}), 404

    db.execute("UPDATE sample_orders SET production_stage=? WHERE id=?", (stage, order_id))
    db.commit()
    create_notification(
        order["buyer_id"],
        f"Sample Update — {order['style_number']}",
        f"Your sample order #{order_id} is now at the '{stage}' stage.",
        notif_type="info", related_order_type="sample_order", related_order_id=order_id,
    )
    return jsonify({"message": "Stage updated", "production_stage": stage}), 200


# ── Mark Ready ────────────────────────────────────────────────────────────

@plant_bp.route("/orders/<int:order_id>/ready", methods=["POST"])
@require_role("PlantManager")
def mark_order_ready(order_id):
    """
    Plant Manager marks the bulk order as production-complete.
    Triggers email + notification to BOTH the Buyer AND Admin.
    """
    db       = get_db()
    plant_id = g.plant_id

    order = db.execute(
        """SELECT bo.* FROM bulk_orders bo
           JOIN order_plant_allocations opa ON opa.bulk_order_id = bo.id
           WHERE bo.id = ? AND opa.plant_id = ?""",
        (order_id, plant_id),
    ).fetchone()
    if not order:
        return jsonify({"error": "Order not found or not assigned to your plant"}), 404
    if order["status"] != "Processing":
        return jsonify({"error": f"Order must be Processing to mark complete. Current: {order['status']}"}), 400
    if not order["plant_approved_at"]:
        return jsonify({"error": "Approve the assignment before marking it complete."}), 400

    now = datetime.utcnow()
    db.execute(
        "UPDATE bulk_orders SET status='Completed', ready_at=? WHERE id=?",
        (now, order_id),
    )
    db.commit()

    plant = db.execute("SELECT name FROM plants WHERE id=?", (plant_id,)).fetchone()
    buyer = db.execute(
        "SELECT id, email, full_name FROM users WHERE id=?", (order["buyer_id"],)
    ).fetchone()
    admin = _get_admin()

    # Email + notification to Buyer
    if buyer:
        send_order_ready_to_buyer(
            buyer["email"], buyer["full_name"],
            order["style_number"], order_id,
            plant["name"] if plant else plant_id,
        )
        create_notification(
            buyer["id"],
            f"Order Ready — {order['style_number']}",
            f"Your bulk order #{order_id} is ready for shipment from {plant['name'] if plant else plant_id}.",
            notif_type="success",
            related_order_type="bulk_order", related_order_id=order_id,
        )

    # Email + notification to Admin
    if admin:
        send_order_ready_to_admin(
            admin["email"],
            plant["name"] if plant else plant_id,
            order["style_number"], order_id,
        )
        create_notification(
            admin["id"],
            f"Order Ready — Confirm Shipment — {order['style_number']}",
            f"{plant['name'] if plant else plant_id} has marked order #{order_id} as ready. Confirm shipment.",
            notif_type="info",
            related_order_type="bulk_order", related_order_id=order_id,
        )

    return jsonify({
        "message":  "Order marked as Ready",
        "order_id": order_id,
        "ready_at": now.isoformat(),
    }), 200


# ── Notifications ─────────────────────────────────────────────────────────

@plant_bp.route("/notifications", methods=["GET"])
@require_role("PlantManager")
def get_notifications():
    """Plant Manager notification inbox."""
    db = get_db()
    notifs = db.execute(
        "SELECT * FROM notifications WHERE user_id=? ORDER BY created_at DESC LIMIT 50",
        (g.user_id,),
    ).fetchall()
    return jsonify([dict(n) for n in notifs]), 200


@plant_bp.route("/notifications/<int:notif_id>/read", methods=["POST"])
@require_role("PlantManager")
def mark_notification_read(notif_id):
    db = get_db()
    db.execute(
        "UPDATE notifications SET is_read=1 WHERE id=? AND user_id=?",
        (notif_id, g.user_id),
    )
    db.commit()
    return jsonify({"message": "Marked as read"}), 200
