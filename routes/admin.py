"""
routes/admin.py
Admin portal endpoints:
  - User management (approve/reject buyers)
  - Sample & bulk order management + assignment
  - Capacity overview
  - C4 production analysis trigger
  - Shipment confirmation
"""

import json
import math
import os
from datetime import datetime, timedelta

from flask import Blueprint, abort, current_app, g, jsonify, request, send_file

from database.db import get_db
from middleware.auth_middleware import require_role
from services.capacity_service import (
    calculate_assignment_daily_commitment,
    deduct_capacity,
    get_all_plants_window_capacity,
    get_available_capacity,
    months_between,
)
from services.email_service import (
    send_bulk_order_assigned_to_plant,
    send_buyer_approved,
    send_buyer_rejected,
    send_order_approved_to_buyer,
    send_sample_order_assigned_to_plant,
)
from services.notification_service import create_notification
from services.sample_planning_service import (
    confirm_order_reservation,
    get_current_plan,
    normalize_priority_ranks,
    plan_buyer_queue,
    reserve_plan_capacity,
)
from services.upload_service import resolve_upload_path

admin_bp = Blueprint("admin", __name__)

ADMIN_EMAIL = os.environ.get("ADMIN_EMAIL", "admin@fabricflow.com")

DEADLINE_MARGIN_DAYS = 5

PRODUCTION_STAGES = [
    "Pending",
    "Cutting",
    "Embroidery",
    "Sewing",
    "Packing",
    "Shipping",
    "Delivery",
]


def _update_stage(table: str, order_id: int, stage: str, order_type: str):
    """Shared helper: set an order's production_stage and notify the buyer."""
    if stage not in PRODUCTION_STAGES:
        return jsonify({"error": f"Invalid stage. Allowed: {PRODUCTION_STAGES}"}), 400
    db = get_db()
    order = db.execute(
        f"SELECT id, style_number, buyer_id FROM {table} WHERE id=?", (order_id,)
    ).fetchone()
    if not order:
        return jsonify({"error": "Order not found"}), 404
    db.execute(f"UPDATE {table} SET production_stage=? WHERE id=?", (stage, order_id))
    db.commit()
    create_notification(
        order["buyer_id"],
        f"Production Update — {order['style_number']}",
        f"Your order #{order_id} is now at the '{stage}' stage.",
        notif_type="info",
        related_order_type=order_type,
        related_order_id=order_id,
    )
    return jsonify({"message": "Stage updated", "production_stage": stage}), 200


# ── User Management ───────────────────────────────────────────────────────


@admin_bp.route("/users/pending", methods=["GET"])
@require_role("Admin")
def pending_users():
    """List all buyer accounts awaiting approval."""
    db = get_db()
    users = db.execute(
        """SELECT u.id, u.full_name, u.email, u.role, u.created_at, o.name AS org_name
           FROM users u JOIN organizations o ON u.org_id = o.id
           WHERE u.status = 'Pending' AND u.role = 'Buyer'
           ORDER BY u.created_at DESC"""
    ).fetchall()
    return jsonify([dict(u) for u in users]), 200


@admin_bp.route("/users", methods=["GET"])
@require_role("Admin")
def all_users():
    """List all users."""
    db = get_db()
    users = db.execute(
        """SELECT u.id, u.full_name, u.email, u.role, u.status, u.plant_id,
                  u.created_at, o.name AS org_name
           FROM users u JOIN organizations o ON u.org_id = o.id
           ORDER BY u.created_at DESC"""
    ).fetchall()
    return jsonify([dict(u) for u in users]), 200


@admin_bp.route("/users/<int:user_id>/approve", methods=["POST"])
@require_role("Admin")
def approve_user(user_id):
    """Approve a pending buyer account."""
    db = get_db()
    user = db.execute(
        "SELECT id, email, full_name, status FROM users WHERE id = ?", (user_id,)
    ).fetchone()
    if not user:
        return jsonify({"error": "User not found"}), 404
    if user["status"] != "Pending":
        return jsonify({"error": f"User is already {user['status']}"}), 400

    db.execute(
        "UPDATE users SET status='Approved', approved_by=?, approved_at=? WHERE id=?",
        (g.user_id, datetime.utcnow(), user_id),
    )
    db.commit()

    send_buyer_approved(user["email"], user["full_name"])
    create_notification(
        user_id,
        "Account Approved",
        "Your account has been approved. You can now log in and place orders.",
        notif_type="success",
    )
    return jsonify({"message": f"User {user['email']} approved"}), 200


@admin_bp.route("/users/<int:user_id>/reject", methods=["POST"])
@require_role("Admin")
def reject_user(user_id):
    """Reject a pending buyer account."""
    db = get_db()
    user = db.execute(
        "SELECT id, email, full_name, status FROM users WHERE id = ?", (user_id,)
    ).fetchone()
    if not user:
        return jsonify({"error": "User not found"}), 404

    db.execute(
        "UPDATE users SET status='Rejected', approved_by=?, approved_at=? WHERE id=?",
        (g.user_id, datetime.utcnow(), user_id),
    )
    db.commit()

    send_buyer_rejected(user["email"], user["full_name"])
    create_notification(
        user_id,
        "Account Not Approved",
        "Your account registration was not approved. Please contact us for details.",
        notif_type="warning",
    )
    return jsonify({"message": f"User {user['email']} rejected"}), 200


@admin_bp.route("/users/manager", methods=["POST"])
@require_role("Admin")
def create_manager():
    """
    Admin-only: create a Manager account — an admin-panel operator who can run
    order/style/capacity operations but NOT user management or the performance
    dashboard. The manager is Approved immediately and shares the creating
    admin's organisation.
    Body: { full_name, email, password }
    """
    from middleware.auth_middleware import hash_password

    data = request.get_json(force=True, silent=True) or {}
    full_name = (data.get("full_name") or "").strip()
    email = (data.get("email") or "").strip().lower()
    password = data.get("password") or ""

    if not full_name or not email or not password:
        return jsonify({"error": "full_name, email and password are required."}), 400
    if len(password) < 8:
        return jsonify({"error": "Password must be at least 8 characters."}), 400
    if "@" not in email:
        return jsonify({"error": "Enter a valid email address."}), 400

    db = get_db()
    if db.execute("SELECT id FROM users WHERE email=?", (email,)).fetchone():
        return jsonify({"error": "An account with this email already exists."}), 409

    admin = db.execute("SELECT org_id FROM users WHERE id=?", (g.user_id,)).fetchone()
    org_id = admin["org_id"] if admin else None
    if org_id is None:
        return jsonify({"error": "Could not resolve organisation for the new manager."}), 400

    db.execute(
        """INSERT INTO users(org_id, full_name, email, password_hash, role, status,
                             approved_by, approved_at)
           VALUES (?,?,?,?,?,?,?,?)""",
        (
            org_id,
            full_name,
            email,
            hash_password(password),
            "Manager",
            "Approved",
            g.user_id,
            datetime.utcnow(),
        ),
    )
    db.commit()
    new_id = db.execute("SELECT id FROM users WHERE email=?", (email,)).fetchone()["id"]
    return jsonify({"message": "Manager account created", "user_id": new_id}), 201


@admin_bp.route("/sub-plants", methods=["GET"])
@require_role("Admin", "Manager")
def list_sub_plants():
    """External local sub plants, with their portal login if one exists."""
    db = get_db()
    rows = db.execute(
        """SELECT p.*, u.email AS portal_email, u.full_name AS portal_user
           FROM plants p
           LEFT JOIN users u ON u.plant_id = p.id AND u.role = 'SubPlant'
           WHERE p.plant_type = 'SubPlant' ORDER BY p.name"""
    ).fetchall()
    return jsonify([dict(r) for r in rows]), 200


@admin_bp.route("/sub-plants", methods=["POST"])
@require_role("Admin")
def create_sub_plant():
    """
    Register an external local sub plant and its portal login.
    Body: { plant_id, name, location, total_machines, employee_count,
            contact_no, contact_email, full_name, email, password }
    """
    from middleware.auth_middleware import hash_password

    data = request.get_json(force=True, silent=True) or {}
    plant_id = (data.get("plant_id") or "").strip().upper()
    name = (data.get("name") or "").strip()
    email = (data.get("email") or "").strip().lower()
    password = data.get("password") or ""
    if not plant_id or not name:
        return jsonify({"error": "plant_id and name are required."}), 400
    if not email or len(password) < 8:
        return jsonify({"error": "A portal email and an 8+ character password are required."}), 400

    db = get_db()
    if db.execute("SELECT 1 FROM plants WHERE id=? OR name=?", (plant_id, name)).fetchone():
        return jsonify({"error": "A plant with that id or name already exists."}), 409
    if db.execute("SELECT 1 FROM users WHERE email=?", (email,)).fetchone():
        return jsonify({"error": "An account with this email already exists."}), 409

    admin = db.execute("SELECT org_id FROM users WHERE id=?", (g.user_id,)).fetchone()
    db.execute(
        """INSERT INTO plants(id, org_id, name, location, quality_rating,
                              historical_on_time_rate, historical_miss_rate,
                              utilization_min, utilization_max, total_machines,
                              employee_count, plant_type, contact_no, contact_email)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,'SubPlant',?,?)""",
        (
            plant_id,
            admin["org_id"] if admin else None,
            name,
            (data.get("location") or "").strip() or None,
            float(data.get("quality_rating") or 4.0),
            float(data.get("historical_on_time_rate") or 0.8),
            float(data.get("historical_miss_rate") or 0.2),
            33.33,
            100.0,
            int(data.get("total_machines") or 10),
            int(data.get("employee_count") or 30),
            (data.get("contact_no") or "").strip() or None,
            (data.get("contact_email") or "").strip() or None,
        ),
    )
    db.execute(
        """INSERT INTO users(org_id, full_name, email, password_hash, role, plant_id,
                             status, approved_by, approved_at)
           VALUES (?,?,?,?,?,?,?,?,?)""",
        (
            admin["org_id"] if admin else None,
            (data.get("full_name") or name).strip(),
            email,
            hash_password(password),
            "SubPlant",
            plant_id,
            "Approved",
            g.user_id,
            datetime.utcnow(),
        ),
    )
    db.commit()
    return jsonify(
        {"message": "Sub plant registered", "plant_id": plant_id, "portal_email": email}
    ), 201


# ── Sample Orders ─────────────────────────────────────────────────────────


@admin_bp.route("/orders/sample", methods=["GET"])
@require_role("Admin", "Manager")
def list_sample_orders():
    """All sample orders with buyer info."""
    db = get_db()
    orders = db.execute(
        """SELECT so.*, u.full_name AS buyer_name, u.email AS buyer_email,
                  p.name AS assigned_plant_name
           FROM sample_orders so
           JOIN users u ON so.buyer_id = u.id
           LEFT JOIN plants p ON so.assigned_plant_id = p.id
           ORDER BY CASE WHEN so.status='Pending' THEN 0 ELSE 1 END,
                    so.buyer_id, COALESCE(so.buyer_priority_rank, 999999),
                    so.created_at DESC"""
    ).fetchall()
    # Group captured email replies (order_type='sample') by order so the admin
    # can see the buyer's date-negotiation reply on each card.
    reply_rows = db.execute(
        """SELECT id, order_id, from_addr, subject, body, detected_action,
                  extension_days, applied, note, created_at
           FROM inbound_emails WHERE order_type='sample' ORDER BY created_at DESC"""
    ).fetchall()
    replies_by_order = {}
    for r in reply_rows:
        replies_by_order.setdefault(r["order_id"], []).append(dict(r))

    result = []
    for o in orders:
        row = dict(o)
        if row.get("c1_result_json"):
            row["c1_result"] = json.loads(row["c1_result_json"])
            del row["c1_result_json"]
        row["current_plan"] = get_current_plan(db, o["id"])
        row["replies"] = replies_by_order.get(o["id"], [])
        result.append(row)
    return jsonify(result), 200


@admin_bp.route("/orders/sample/<int:order_id>", methods=["GET"])
@require_role("Admin", "Manager")
def get_sample_order_admin(order_id):
    """One sample order with its full C1 result, plant, and captured email replies."""
    db = get_db()
    o = db.execute(
        """SELECT so.*, u.full_name AS buyer_name, u.email AS buyer_email,
                  p.name AS assigned_plant_name, p.location AS assigned_plant_location
           FROM sample_orders so
           JOIN users u ON so.buyer_id = u.id
           LEFT JOIN plants p ON so.assigned_plant_id = p.id
           WHERE so.id = ?""",
        (order_id,),
    ).fetchone()
    if not o:
        return jsonify({"error": "Sample order not found"}), 404

    row = dict(o)
    if row.get("c1_result_json"):
        try:
            row["c1_result"] = json.loads(row["c1_result_json"])
        except Exception:
            row["c1_result"] = None
        del row["c1_result_json"]

    replies = db.execute(
        """SELECT id, from_addr, subject, body, detected_action, extension_days,
                  applied, note, created_at
           FROM inbound_emails
           WHERE order_id=? AND order_type='sample'
           ORDER BY created_at DESC""",
        (order_id,),
    ).fetchall()
    row["replies"] = [dict(r) for r in replies]
    row["current_plan"] = get_current_plan(db, order_id)
    return jsonify(row), 200


@admin_bp.route("/orders/sample/<int:order_id>/pdf", methods=["GET"])
@require_role("Admin", "Manager")
def download_sample_pdf(order_id):
    """Admin downloads the buyer's uploaded style PDF for a sample order."""
    db = get_db()
    order = db.execute(
        "SELECT style_pdf_path, style_number FROM sample_orders WHERE id=?", (order_id,)
    ).fetchone()
    if not order:
        return jsonify({"error": "Sample order not found"}), 404
    if not order["style_pdf_path"]:
        return jsonify({"error": "No style PDF uploaded for this order"}), 404
    abs_path = resolve_upload_path(order["style_pdf_path"])
    if not abs_path:
        abort(404)
    return send_file(
        abs_path,
        mimetype="application/pdf",
        as_attachment=True,
        download_name=f"{order['style_number']}_style.pdf",
    )


@admin_bp.route("/orders/sample/<int:order_id>/generate-plan", methods=["POST"])
@require_role("Admin", "Manager")
def generate_sample_plan(order_id):
    """Regenerate queue-aware draft plans and return this order's proposal."""
    db = get_db()
    order = db.execute(
        "SELECT id, buyer_id, status FROM sample_orders WHERE id=?", (order_id,)
    ).fetchone()
    if not order:
        return jsonify({"error": "Sample order not found"}), 404
    if order["status"] != "Pending":
        return jsonify({"error": "Only pending sample orders can be planned"}), 400

    current_plan = get_current_plan(db, order_id)
    if current_plan and current_plan["plan_status"] in ("AwaitingBuyer", "BuyerApproved"):
        return jsonify(
            {"error": "This plan is already awaiting or has received buyer approval."}
        ), 409

    try:
        plan_buyer_queue(db, order["buyer_id"])
        db.commit()
    except ValueError as exc:
        db.rollback()
        return jsonify({"error": str(exc)}), 400
    return jsonify(
        {"message": "Sample plan generated", "plan": get_current_plan(db, order_id)}
    ), 200


@admin_bp.route("/orders/sample/<int:order_id>/propose-plan", methods=["POST"])
@require_role("Admin", "Manager")
def propose_sample_plan(order_id):
    """Send a delayed whole-order shipment proposal to the buyer for approval."""
    from services.email_service import _wrap_html, send_email

    data = request.get_json(force=True, silent=True) or {}
    message = (data.get("message") or "").strip() or None
    db = get_db()
    order = db.execute("SELECT * FROM sample_orders WHERE id=?", (order_id,)).fetchone()
    if not order:
        return jsonify({"error": "Sample order not found"}), 404
    if order["status"] != "Pending":
        return jsonify({"error": "Only pending sample orders can be proposed"}), 400

    plan = get_current_plan(db, order_id)
    if not plan:
        return jsonify({"error": "Generate a plan first"}), 400
    if plan["can_meet_original_date"]:
        return jsonify(
            {"error": "This plan meets the original date and does not need buyer approval"}
        ), 400

    buyer = db.execute(
        "SELECT id, email, full_name FROM users WHERE id=?", (order["buyer_id"],)
    ).fetchone()
    if not buyer:
        return jsonify({"error": "Buyer not found"}), 404

    higher_priority = db.execute(
        """SELECT id FROM sample_orders
           WHERE buyer_id=? AND status='Pending' AND priority_locked_at IS NULL
             AND buyer_priority_rank < ?
           ORDER BY buyer_priority_rank LIMIT 1""",
        (order["buyer_id"], order["buyer_priority_rank"] or 999999),
    ).fetchone()
    if higher_priority:
        return jsonify(
            {"error": f"Resolve higher-priority sample order #{higher_priority['id']} first."}
        ), 409

    now = datetime.utcnow()
    try:
        reservation = reserve_plan_capacity(db, order_id, plan)
    except ValueError as exc:
        db.rollback()
        return jsonify({"error": str(exc)}), 409
    db.execute(
        """UPDATE sample_order_plans
           SET plan_status='AwaitingBuyer', buyer_message=?, updated_at=? WHERE id=?""",
        (message, now, plan["id"]),
    )
    db.execute(
        """UPDATE sample_orders
           SET timeline_email_sent_at=?, proposed_shipment_date=?,
               customer_response=NULL, customer_message=NULL, customer_responded_at=NULL,
               priority_locked_at=COALESCE(priority_locked_at, ?)
           WHERE id=?""",
        (now, plan["planned_shipment_date"], now, order_id),
    )
    db.commit()

    subject = f"[Sample #{order_id}] Revised Shipment Plan"
    note = f"<p>{message}</p>" if message else ""
    html = _wrap_html(
        "Revised Sample Shipment Plan",
        f"<p>Dear {buyer['full_name']},</p>"
        f"<p>Your sample order <strong>#{order_id}</strong> for style "
        f"<strong>{order['style_number']}</strong> cannot be completed by "
        f"<strong>{plan['original_required_date']}</strong>.</p>"
        f"<p>The earliest achievable shipment is "
        f"<strong>{plan['planned_shipment_date']}</strong> from "
        f"<strong>{plan['recommended_plant_name']}</strong>.</p>{note}"
        "<p>Please approve or reject this proposal in the FabricFlow buyer portal.</p>",
    )
    send_email(buyer["email"], subject, html)
    create_notification(
        buyer["id"],
        f"Shipment approval needed — Sample #{order_id}",
        f"Please approve or reject the proposed shipment date "
        f"{plan['planned_shipment_date']}.",
        notif_type="warning",
        related_order_type="sample_order",
        related_order_id=order_id,
    )
    return jsonify(
        {
            "message": "Plan proposed to buyer",
            "plan": get_current_plan(db, order_id),
            "reservation": reservation,
        }
    ), 200


@admin_bp.route("/orders/sample/<int:order_id>/assign", methods=["POST"])
@require_role("Admin", "Manager")
def assign_sample_order(order_id):
    """
    Admin assigns a plant to a feasible sample order.
    Required body: { "plant_id": "PL01" }
    Deducts sample_qty from plant monthly capacity.
    """
    data = request.get_json(force=True, silent=True) or {}
    plant_id = data.get("plant_id")
    if not plant_id:
        return jsonify({"error": "plant_id is required"}), 400

    db = get_db()
    order = db.execute("SELECT * FROM sample_orders WHERE id = ?", (order_id,)).fetchone()
    if not order:
        return jsonify({"error": "Sample order not found"}), 404
    if order["status"] != "Pending":
        return jsonify({"error": f"Cannot assign order in status: {order['status']}"}), 400

    plan = get_current_plan(db, order_id)
    if order["feasibility"] == "Infeasible" and not plan:
        return jsonify(
            {"error": "Generate a capacity-aware plan before assigning this order."}
        ), 400
    if plan and not plan["can_meet_original_date"] and plan["plan_status"] != "BuyerApproved":
        return jsonify(
            {"error": "The buyer must approve the revised shipment date before assignment."}
        ), 400

    higher_priority = db.execute(
        """SELECT id, buyer_priority_rank FROM sample_orders
           WHERE buyer_id=? AND status='Pending' AND priority_locked_at IS NULL
             AND buyer_priority_rank < ?
           ORDER BY buyer_priority_rank LIMIT 1""",
        (order["buyer_id"], order["buyer_priority_rank"] or 999999),
    ).fetchone()
    if higher_priority:
        return jsonify(
            {
                "error": (
                    f"Sample order #{higher_priority['id']} has a higher buyer priority. "
                    "Assign it first or ask the buyer to reorder the queue."
                )
            }
        ), 400

    plant = db.execute(
        """SELECT * FROM plants WHERE (id=? OR name=?)
           AND (plant_type IS NULL OR plant_type='Registered')""",
        (plant_id, plant_id),
    ).fetchone()
    if not plant:
        return jsonify({"error": f"Plant {plant_id} not found"}), 404

    plant_id = plant["id"]  # Ensure we use the actual ID moving forward
    if plan and plant_id != plan["recommended_plant_id"]:
        return jsonify(
            {
                "error": (
                    f"The current plan recommends {plan['recommended_plant_name']}. "
                    "Regenerate the plan before choosing a different plant."
                )
            }
        ), 400

    now = datetime.utcnow()
    month_year = str(plan["estimated_start_date"] if plan else order["receive_date"])[:7]
    capacity = get_available_capacity(plant_id, month_year)
    held_for_other_orders = db.execute(
        """SELECT COALESCE(SUM(reserved_quantity), 0) AS quantity
           FROM sample_capacity_reservations
           WHERE plant_id=? AND capacity_month=? AND status='Tentative'
             AND sample_order_id!=?""",
        (plant_id, month_year, order_id),
    ).fetchone()["quantity"]
    effective_available = max(
        0, int(capacity["available_capacity"]) - int(held_for_other_orders or 0)
    )
    if effective_available < int(order["sample_qty"]):
        return jsonify(
            {"error": "Plant capacity changed. Regenerate the sample plan before assignment."}
        ), 409

    # Assigning to a plant moves the buyer-facing status to Processing.
    db.execute(
        """UPDATE plant_monthly_capacity
           SET used_capacity=used_capacity+?
           WHERE plant_id=? AND month_year=?""",
        (order["sample_qty"], plant_id, month_year),
    )
    db.execute(
        """UPDATE sample_orders
           SET status='Processing', assigned_plant_id=?, assigned_by=?, assigned_at=?,
               priority_locked_at=COALESCE(priority_locked_at, ?),
               production_stage=CASE WHEN production_stage='Pending' OR production_stage IS NULL
                                     THEN 'Cutting' ELSE production_stage END
           WHERE id=?""",
        (plant_id, g.user_id, now, now, order_id),
    )
    if plan:
        db.execute(
            """UPDATE sample_order_plans
               SET plan_status='Scheduled', updated_at=? WHERE id=?""",
            (now, plan["id"]),
        )
        confirm_order_reservation(db, order_id, plan["id"])
    normalize_priority_ranks(db, order["buyer_id"])
    try:
        plan_buyer_queue(db, order["buyer_id"])
    except ValueError as exc:
        current_app.logger.warning("Remaining sample queue could not be replanned: %s", exc)
    db.commit()

    # Notify plant manager
    pm = db.execute(
        "SELECT id, email, full_name FROM users WHERE role='PlantManager' AND plant_id=?",
        (plant_id,),
    ).fetchone()
    if pm:
        send_sample_order_assigned_to_plant(
            pm["email"],
            plant["name"],
            order["style_number"],
            order["sample_qty"],
            order_id,
        )
        create_notification(
            pm["id"],
            f"New Sample Order Assigned — {order['style_number']}",
            f"Sample order #{order_id} (Qty: {order['sample_qty']}) has been assigned to your plant.",
            notif_type="info",
            related_order_type="sample_order",
            related_order_id=order_id,
        )

    # Notify buyer
    buyer = db.execute(
        "SELECT id, email, full_name FROM users WHERE id = ?", (order["buyer_id"],)
    ).fetchone()
    if buyer:
        send_order_approved_to_buyer(
            buyer["email"], buyer["full_name"], order["style_number"], order_id
        )
        create_notification(
            buyer["id"],
            f"Sample Order Assigned — {order['style_number']}",
            f"Your sample order #{order_id} has been assigned to {plant['name']}.",
            notif_type="success",
            related_order_type="sample_order",
            related_order_id=order_id,
        )

    return jsonify(
        {
            "message": "Sample order assigned",
            "order_id": order_id,
            "plant_id": plant_id,
            "plant_name": plant["name"],
        }
    ), 200


@admin_bp.route("/orders/sample/<int:order_id>/request-date", methods=["POST"])
@require_role("Admin", "Manager")
def request_sample_new_date(order_id):
    """
    Email the buyer to request a new (later) receive date for a sample order that
    can't be met as scheduled. Moves the order into an 'awaiting customer'
    sub-state — status stays 'Pending', but timeline_email_sent_at is set and
    customer_response is cleared. The buyer replies by email and the inbox poller
    folds the reply back in (or the admin records it manually).
    Body: { proposed_date?: 'YYYY-MM-DD', message?: str }
    """
    from services.email_service import _wrap_html, send_email

    data = request.get_json(force=True, silent=True) or {}
    proposed_date = (data.get("proposed_date") or "").strip() or None
    extra_message = (data.get("message") or "").strip() or None

    if proposed_date:
        try:
            datetime.strptime(proposed_date, "%Y-%m-%d")
        except ValueError:
            return jsonify({"error": "proposed_date must be YYYY-MM-DD."}), 400

    db = get_db()
    order = db.execute("SELECT * FROM sample_orders WHERE id=?", (order_id,)).fetchone()
    if not order:
        return jsonify({"error": "Sample order not found"}), 404
    if order["status"] != "Pending":
        return jsonify(
            {"error": f"Cannot request a new date for an order in status: {order['status']}"}
        ), 400

    buyer = db.execute(
        "SELECT id, email, full_name FROM users WHERE id=?", (order["buyer_id"],)
    ).fetchone()
    if not buyer:
        return jsonify({"error": "Buyer not found"}), 404

    subject = "Sample Order — New Receive Date Needed"
    proposed_line = (
        f"<p>We propose a revised receive date of <strong>{proposed_date}</strong>.</p>"
        if proposed_date
        else "<p>Please reply with a revised receive date that works for you.</p>"
    )
    note_line = f"<p>{extra_message}</p>" if extra_message else ""
    html = _wrap_html(
        subject,
        f"<p>Dear {buyer['full_name']},</p>"
        f"<p>Regarding sample order <strong>#{order_id}</strong> (style {order['style_number']}), "
        f"the requested receive date of <strong>{order['receive_date']}</strong> cannot be met with "
        f"current capacity.</p>"
        f"{proposed_line}{note_line}"
        f"<p>Please <strong>reply to this email</strong> to let us know — for example, "
        f'"we agree" to accept, or tell us how many more days you need.</p>'
        f"<p>Best regards,<br/>FabricFlow International</p>",
    )
    send_email(buyer["email"], f"[Sample #{order_id}] {subject}", html)

    db.execute(
        """UPDATE sample_orders
           SET timeline_email_sent_at=?, proposed_receive_date=?, customer_response=NULL,
               customer_message=NULL, extension_days_requested=NULL, customer_responded_at=NULL
           WHERE id=?""",
        (datetime.utcnow(), proposed_date, order_id),
    )
    db.commit()
    create_notification(
        order["buyer_id"],
        f"Action needed — Sample Order #{order_id}",
        f"We've asked you to confirm a new receive date for style {order['style_number']}. "
        f"Please check your email and reply.",
        notif_type="info",
        related_order_type="sample_order",
        related_order_id=order_id,
    )
    return jsonify({"message": "Date-request email sent", "awaiting_customer": True}), 200


@admin_bp.route("/orders/sample/<int:order_id>/customer-response", methods=["POST"])
@require_role("Admin", "Manager")
def record_sample_customer_response(order_id):
    """
    Manually record the buyer's reply to the date-request email (for cases the
    inbox poller can't auto-apply, or when no mailbox is configured).
    Body: { response: 'Approved'|'Rejected', new_date?: 'YYYY-MM-DD',
            extension_days?: int, message?: str }
    """
    data = request.get_json(force=True, silent=True) or {}
    response = data.get("response")
    if response not in ("Approved", "Rejected"):
        return jsonify({"error": "response must be 'Approved' or 'Rejected'"}), 400

    new_date = (data.get("new_date") or "").strip() or None
    if new_date:
        try:
            datetime.strptime(new_date, "%Y-%m-%d")
        except ValueError:
            return jsonify({"error": "new_date must be YYYY-MM-DD."}), 400
    ext_days = data.get("extension_days")
    try:
        ext_days = int(ext_days) if ext_days not in (None, "") else None
    except (TypeError, ValueError):
        return jsonify({"error": "extension_days must be a whole number."}), 400
    message = (data.get("message") or "").strip() or None

    db = get_db()
    order = db.execute("SELECT id FROM sample_orders WHERE id=?", (order_id,)).fetchone()
    if not order:
        return jsonify({"error": "Sample order not found"}), 404

    db.execute(
        """UPDATE sample_orders
           SET customer_response=?, customer_message=?, extension_days_requested=?,
               proposed_receive_date=COALESCE(?, proposed_receive_date),
               customer_responded_at=?
           WHERE id=?""",
        (response, message, ext_days, new_date, datetime.utcnow(), order_id),
    )
    db.commit()
    return jsonify({"message": f"Recorded: {response}", "response": response}), 200


@admin_bp.route("/orders/sample/<int:order_id>/apply-new-date", methods=["POST"])
@require_role("Admin", "Manager")
def apply_sample_new_date(order_id):
    """
    Commit an agreed new receive date: update receive_date, re-run C1 feasibility,
    and clear the negotiation so the order is a clean 'Pending' again — assignable
    if it is now feasible.
    Body: { new_date?: 'YYYY-MM-DD' }  (falls back to proposed_receive_date on file)
    """
    from flask import current_app

    from components.component1 import ALL_BUYERS

    data = request.get_json(force=True, silent=True) or {}
    db = get_db()
    order = db.execute("SELECT * FROM sample_orders WHERE id=?", (order_id,)).fetchone()
    if not order:
        return jsonify({"error": "Sample order not found"}), 404

    # proposed_receive_date may come back as a datetime.date (PARSE_DECLTYPES),
    # so normalise to a string before validating.
    new_date = data.get("new_date") or order["proposed_receive_date"]
    if not new_date:
        return jsonify({"error": "No new date provided and none proposed on file."}), 400
    new_date = str(new_date).strip()
    try:
        datetime.strptime(new_date, "%Y-%m-%d")
    except ValueError:
        return jsonify({"error": "new_date must be YYYY-MM-DD."}), 400

    # Re-run C1 feasibility with the new receive date.
    buyer_org = db.execute(
        "SELECT o.name FROM users u JOIN organizations o ON u.org_id=o.id WHERE u.id=?",
        (order["buyer_id"],),
    ).fetchone()
    buyer_name = buyer_org["name"] if buyer_org else ALL_BUYERS[0]
    c1_buyer = buyer_name if buyer_name in ALL_BUYERS else ALL_BUYERS[0]
    with current_app.test_client() as client:
        resp = client.post(
            "/api/component1/predict",
            json={
                "buyer_name": c1_buyer,
                "style_id": order["artwork_number"] or order["style_number"],
                "sample_qty": order["sample_qty"],
                "receive_date": new_date,
                "buyer_required_date": order["buyer_required_date"],
            },
            headers={"Content-Type": "application/json"},
        )
        c1_result = resp.get_json()
    feasible = bool((c1_result or {}).get("planning_output", {}).get("feasible", False))
    feasibility = "Feasible" if feasible else "Infeasible"

    db.execute(
        """UPDATE sample_orders
           SET receive_date=?, feasibility=?, c1_result_json=?, status='Pending',
               timeline_email_sent_at=NULL, proposed_receive_date=NULL
           WHERE id=?""",
        (new_date, feasibility, json.dumps(c1_result), order_id),
    )
    db.commit()
    return jsonify(
        {
            "message": "New date applied",
            "receive_date": new_date,
            "feasibility": feasibility,
            "feasible": feasible,
        }
    ), 200


# ── Bulk Orders ───────────────────────────────────────────────────────────


@admin_bp.route("/orders/bulk", methods=["GET"])
@require_role("Admin", "Manager")
def list_bulk_orders():
    """All bulk orders with buyer info."""
    db = get_db()
    orders = db.execute(
        """SELECT bo.*, u.full_name AS buyer_name, u.email AS buyer_email
           FROM bulk_orders bo
           JOIN users u ON bo.buyer_id = u.id
           ORDER BY bo.created_at DESC"""
    ).fetchall()
    result = []
    for o in orders:
        row = dict(o)
        if row.get("c2_result_json"):
            row["c2_result"] = json.loads(row["c2_result_json"])
            del row["c2_result_json"]
        # Attach allocations
        allocs = db.execute(
            "SELECT opa.*, p.name AS plant_name FROM order_plant_allocations opa JOIN plants p ON opa.plant_id=p.id WHERE opa.bulk_order_id=?",
            (o["id"],),
        ).fetchall()
        row["allocations"] = [dict(a) for a in allocs]
        result.append(row)
    return jsonify(result), 200


@admin_bp.route("/orders/bulk/<int:order_id>", methods=["GET"])
@require_role("Admin", "Manager")
def get_bulk_order(order_id):
    """Fetch a single bulk order by ID."""
    db = get_db()
    o = db.execute(
        """SELECT bo.*, u.full_name AS buyer_name, u.email AS buyer_email
           FROM bulk_orders bo
           JOIN users u ON bo.buyer_id = u.id
           WHERE bo.id = ?""",
        (order_id,),
    ).fetchone()
    if not o:
        return jsonify({"error": "Order not found"}), 404

    row = dict(o)
    if row.get("c2_result_json"):
        row["c2_result"] = json.loads(row["c2_result_json"])
        del row["c2_result_json"]

    allocs = db.execute(
        "SELECT opa.*, p.name AS plant_name FROM order_plant_allocations opa JOIN plants p ON opa.plant_id=p.id WHERE opa.bulk_order_id=?",
        (order_id,),
    ).fetchall()
    row["allocations"] = [dict(a) for a in allocs]

    # Customer email replies captured for this order (newest first), so the
    # detail page can show the full back-and-forth, not just the latest status.
    replies = db.execute(
        """SELECT id, from_addr, subject, body, detected_action, extension_days,
                  applied, note, created_at
           FROM inbound_emails
           WHERE order_id=? AND (order_type='bulk' OR order_type IS NULL)
           ORDER BY created_at DESC""",
        (order_id,),
    ).fetchall()
    row["replies"] = [dict(r) for r in replies]
    return jsonify(row), 200


@admin_bp.route("/orders/bulk/<int:order_id>/stage", methods=["POST"])
@require_role("Admin", "Manager")
def update_bulk_stage_admin(order_id):
    """Admin sets a bulk order's production stage."""
    data = request.get_json(force=True, silent=True) or {}
    return _update_stage("bulk_orders", order_id, data.get("stage"), "bulk_order")


@admin_bp.route("/orders/sample/<int:order_id>/stage", methods=["POST"])
@require_role("Admin", "Manager")
def update_sample_stage_admin(order_id):
    """Admin sets a sample order's production stage."""
    data = request.get_json(force=True, silent=True) or {}
    return _update_stage("sample_orders", order_id, data.get("stage"), "sample_order")


@admin_bp.route("/orders/bulk/<int:order_id>/pdf", methods=["GET"])
@require_role("Admin", "Manager")
def download_bulk_pdf(order_id):
    """Admin downloads the buyer's uploaded style PDF for a bulk order."""
    db = get_db()
    order = db.execute(
        "SELECT style_pdf_path, style_number FROM bulk_orders WHERE id=?", (order_id,)
    ).fetchone()
    if not order:
        return jsonify({"error": "Bulk order not found"}), 404
    if not order["style_pdf_path"]:
        return jsonify({"error": "No style PDF uploaded for this order"}), 404
    abs_path = resolve_upload_path(order["style_pdf_path"])
    if not abs_path:
        abort(404)
    return send_file(
        abs_path,
        mimetype="application/pdf",
        as_attachment=True,
        download_name=f"{order['style_number']}_style.pdf",
    )


@admin_bp.route("/orders/bulk/<int:order_id>/assign", methods=["POST"])
@require_role("Admin", "Manager")
def assign_bulk_order(order_id):
    """
    Admin assigns plant(s) to a bulk order.
    Required body:
    {
        "allocations": [
            {"plant_id": "PL01", "allocation_type": "Primary", "allocated_qty": 8000},
            {"plant_id": "PL02", "allocation_type": "Secondary", "allocated_qty": 2360}
        ]
    }
    """
    data = request.get_json(force=True, silent=True) or {}
    allocations = data.get("allocations", [])
    if not allocations:
        return jsonify({"error": "allocations list is required"}), 400

    db = get_db()
    order = db.execute("SELECT * FROM bulk_orders WHERE id = ?", (order_id,)).fetchone()
    if not order:
        return jsonify({"error": "Bulk order not found"}), 404
    # Assignable while awaiting action: Pending, customer-approved (CustomerPending), or paused (Hold).
    if order["status"] not in ("Pending", "CustomerPending", "Hold"):
        return jsonify({"error": f"Cannot assign order in status: {order['status']}"}), 400

    # For a split, the per-plant quantities must add up to the whole order.
    try:
        total_alloc = sum(int(a.get("allocated_qty", 0)) for a in allocations)
    except (TypeError, ValueError):
        return jsonify({"error": "allocated_qty values must be whole numbers."}), 400
    if total_alloc != order["bulk_order_quantity"]:
        return jsonify(
            {
                "error": f"Allocated quantity ({total_alloc:,}) must equal the "
                f"order quantity ({order['bulk_order_quantity']:,})."
            }
        ), 400
    plant_ids = [a.get("plant_id") for a in allocations if a.get("plant_id")]
    if len(set(plant_ids)) != len(plant_ids):
        return jsonify({"error": "The same plant is listed more than once in the split."}), 400

    # Validate every allocation against capacity across the complete production
    # window before mutating the order.
    production_months = months_between(
        str(order["approved_date"])[:7], str(order["buyer_required_date"])[:7]
    )
    resolved_allocations = []
    for allocation in allocations:
        plant_row = db.execute(
            "SELECT id, name FROM plants WHERE id=? OR name=?",
            (allocation.get("plant_id"), allocation.get("plant_id")),
        ).fetchone()
        if not plant_row:
            return jsonify({"error": f"Plant {allocation.get('plant_id')} not found"}), 404
        available = 0
        for month in production_months:
            capacity = db.execute(
                """SELECT total_capacity, used_capacity
                   FROM plant_monthly_capacity
                   WHERE plant_id=? AND month_year=?""",
                (plant_row["id"], month),
            ).fetchone()
            available += capacity["total_capacity"] - capacity["used_capacity"] if capacity else 0
        requested = int(allocation.get("allocated_qty", 0))
        if requested > available:
            return jsonify(
                {
                    "error": (
                        f"{plant_row['name']} has only {available:,} units free between "
                        f"{production_months[0]} and {production_months[-1]}, but "
                        f"{requested:,} pcs were allocated. Reduce the amount, split "
                        "across more plants, or extend the timeline."
                    )
                }
            ), 400

        capacity_plan = calculate_assignment_daily_commitment(
            plant_row["id"],
            requested,
            order["approved_date"],
            order["buyer_required_date"],
            order["c2_result_json"],
            fallback_daily_commitment=order["daily_commitment"],
            db=db,
        )
        resolved_allocations.append(
            {
                "plant_id": plant_row["id"],
                "plant_name": plant_row["name"],
                "allocation_type": allocation.get("allocation_type", "Primary"),
                "allocated_qty": requested,
                "capacity_plan": capacity_plan,
            }
        )

    resolved_plant_ids = [item["plant_id"] for item in resolved_allocations]
    if len(set(resolved_plant_ids)) != len(resolved_plant_ids):
        return jsonify({"error": "The same plant is listed more than once in the split."}), 400

    now = datetime.utcnow()
    str(order["approved_date"])[:7]

    # Assigning a plant moves the order into Processing; the production-day
    # countdown starts from this assignment date (assigned_at).
    db.execute(
        """UPDATE bulk_orders
           SET status='Processing', assigned_by=?, assigned_at=?,
               production_stage=CASE WHEN production_stage='Pending' OR production_stage IS NULL
                                     THEN 'Cutting' ELSE production_stage END
           WHERE id=?""",
        (g.user_id, now, order_id),
    )

    notified_plants = set()
    saved_allocations = []
    for alloc in resolved_allocations:
        actual_plant_id = alloc["plant_id"]
        alloc_type = alloc["allocation_type"]
        allocated_qty = alloc["allocated_qty"]
        capacity_plan = alloc["capacity_plan"]
        allocation_daily_commitment = capacity_plan["daily_commitment"]

        db.execute(
            """INSERT INTO order_plant_allocations(
                   bulk_order_id, plant_id, allocation_type, allocated_qty,
                   daily_commitment, daily_capacity_snapshot
               ) VALUES (?,?,?,?,?,?)""",
            (
                order_id,
                actual_plant_id,
                alloc_type,
                allocated_qty,
                allocation_daily_commitment,
                capacity_plan["plant_daily_capacity"],
            ),
        )

        # Distribute capacity deduction across months based on daily commitment
        # (sqlite3.Row has no .get() — index access with an explicit guard)
        daily_commit = allocation_daily_commitment

        qty_remaining = allocated_qty
        try:
            dt_str = str(order["approved_date"])[:10]
            current_date = datetime.strptime(dt_str, "%Y-%m-%d")
        except Exception:
            current_date = datetime.utcnow()

        guard = 0
        while qty_remaining > 0 and guard < 36:
            guard += 1
            current_month_str = current_date.strftime("%Y-%m")
            monthly_allowance = min(qty_remaining, daily_commit * 25)  # 25 working days

            deduction = deduct_capacity(actual_plant_id, current_month_str, monthly_allowance)
            qty_remaining -= deduction.get("deducted", monthly_allowance)

            # Only the year/month matter for capacity allocation. Reset the day
            # before advancing so dates on the 29th, 30th, or 31st cannot create
            # an invalid date when the next month is shorter (for example,
            # August 30 -> February 30 after repeated advances).
            if current_date.month == 12:
                current_date = current_date.replace(year=current_date.year + 1, month=1, day=1)
            else:
                current_date = current_date.replace(month=current_date.month + 1, day=1)

        if qty_remaining > 0:
            current_app.logger.warning(
                "Order %s: %s pcs could not be placed against %s capacity within 36 months",
                order_id,
                qty_remaining,
                actual_plant_id,
            )

        if actual_plant_id not in notified_plants:
            plant = db.execute("SELECT * FROM plants WHERE id = ?", (actual_plant_id,)).fetchone()
            pm = db.execute(
                "SELECT id, email FROM users WHERE role='PlantManager' AND plant_id=?",
                (actual_plant_id,),
            ).fetchone()
            if pm and plant:
                send_bulk_order_assigned_to_plant(
                    pm["email"],
                    plant["name"],
                    order["style_number"],
                    order["bulk_order_quantity"],
                    order_id,
                )
                create_notification(
                    pm["id"],
                    f"Bulk Order Assigned — {order['style_number']}",
                    f"Bulk order #{order_id} (Qty: {allocated_qty:,}) has been assigned to your plant.",
                    notif_type="info",
                    related_order_type="bulk_order",
                    related_order_id=order_id,
                )
            notified_plants.add(actual_plant_id)

        saved_allocations.append(
            {
                "plant_id": actual_plant_id,
                "plant_name": alloc["plant_name"],
                "allocation_type": alloc_type,
                "allocated_qty": allocated_qty,
                **capacity_plan,
            }
        )

    db.commit()

    # Notify buyer
    buyer = db.execute(
        "SELECT id, email, full_name FROM users WHERE id = ?", (order["buyer_id"],)
    ).fetchone()
    if buyer:
        send_order_approved_to_buyer(
            buyer["email"], buyer["full_name"], order["style_number"], order_id
        )
        create_notification(
            buyer["id"],
            f"Bulk Order Assigned — {order['style_number']}",
            f"Your bulk order #{order_id} has been assigned to production.",
            notif_type="success",
            related_order_type="bulk_order",
            related_order_id=order_id,
        )

    return jsonify(
        {
            "message": "Bulk order assigned",
            "order_id": order_id,
            "allocations": saved_allocations,
        }
    ), 200


@admin_bp.route("/orders/bulk/<int:order_id>/reevaluate", methods=["POST"])
@require_role("Admin", "Manager")
def reevaluate_bulk_order(order_id):
    """
    Re-run Component 2 for a still-unassigned bulk order using the CURRENT live
    plant capacity, so the plant ranking / can_handle_solo / deadline / split
    strategy reflect capacity consumed by orders assigned since submission.
    Only valid before assignment (Pending / CustomerPending / Hold).
    Returns a before/after summary of the recommendation.
    """
    from flask import current_app

    from components.component2 import KNOWN_BUYERS

    db = get_db()
    order = db.execute("SELECT * FROM bulk_orders WHERE id=?", (order_id,)).fetchone()
    if not order:
        return jsonify({"error": "Bulk order not found"}), 404
    if order["status"] not in ("Pending", "CustomerPending", "Hold"):
        return jsonify(
            {"error": f"Only un-assigned orders can be re-evaluated (status: {order['status']})."}
        ), 400

    # Snapshot the current recommendation for a before/after diff.
    try:
        prev = json.loads(order["c2_result_json"]) if order["c2_result_json"] else {}
    except Exception:
        prev = {}

    org = db.execute(
        "SELECT o.name FROM users u JOIN organizations o ON u.org_id=o.id WHERE u.id=?",
        (order["buyer_id"],),
    ).fetchone()
    c2_buyer = org["name"] if org and org["name"] in KNOWN_BUYERS else KNOWN_BUYERS[0]
    month_year = str(order["approved_date"])[:7]
    monthly_cap = get_all_plants_window_capacity(month_year, str(order["buyer_required_date"])[:7])
    sample_plant = max(monthly_cap, key=monthly_cap.get) if monthly_cap else None

    c2_payload = {
        "buyer_name": c2_buyer,
        "style_id": order["style_number"],
        "bulk_order_quantity": order["bulk_order_quantity"],
        "daily_commitment": order["daily_commitment"],
        "style_priority": order["style_priority"],
        "design_width": float(order["design_width"] or 0),
        "design_length": float(order["design_length"] or 0),
        "color_count": int(order["color_count"] or 0),
        "stitch_count": int(order["stitch_count"] or 0),
        "sample_plant": sample_plant,
        "sp_cap_util_pct": 85.0,
        "bulk_order_approved_date": str(order["approved_date"]),
        "buyer_required_date": str(order["buyer_required_date"]),
        "damage_pct": float(order["damage_pct"] or 0.0),
        "shipment_days": int(order["shipment_days"] or 18),
        "monthly_capacity": monthly_cap,
    }
    with current_app.test_client() as client:
        resp = client.post(
            "/api/component2/predict", json=c2_payload, headers={"Content-Type": "application/json"}
        )
        c2_result = resp.get_json()

    if not c2_result or "error" in c2_result:
        return jsonify(
            {
                "error": (c2_result or {}).get("error", "Re-evaluation failed."),
                "detail": "Component 2 could not produce a result for the current inputs.",
            }
        ), 502

    db.execute(
        "UPDATE bulk_orders SET c2_result_json=? WHERE id=?", (json.dumps(c2_result), order_id)
    )
    db.commit()

    def _summ(res):
        res = res or {}
        return {
            "top_plant": (res.get("plant_recommendation") or {}).get("top_plant"),
            "deadline_match": (res.get("deadline") or {}).get("deadline_match"),
            "allocation_type": (res.get("allocation") or {}).get("allocation_type"),
        }

    return jsonify(
        {
            "message": "Re-evaluated with current capacity",
            "before": _summ(prev),
            "after": _summ(c2_result),
        }
    ), 200


@admin_bp.route("/orders/bulk/<int:order_id>/confirm-shipment", methods=["POST"])
@require_role("Admin", "Manager")
def confirm_shipment(order_id):
    """Admin confirms the order has been shipped."""
    db = get_db()
    order = db.execute("SELECT * FROM bulk_orders WHERE id = ?", (order_id,)).fetchone()
    if not order:
        return jsonify({"error": "Bulk order not found"}), 404
    if order["status"] != "Completed":
        return jsonify({"error": "Order must be Completed before confirming shipment"}), 400

    db.execute(
        "UPDATE bulk_orders SET status='Shipped', shipped_at=? WHERE id=?",
        (datetime.utcnow(), order_id),
    )
    db.commit()

    buyer = db.execute(
        "SELECT email, full_name FROM users WHERE id = ?", (order["buyer_id"],)
    ).fetchone()
    if buyer:
        from services.email_service import send_order_shipped_to_buyer

        send_order_shipped_to_buyer(
            buyer["email"],
            buyer["full_name"],
            order["style_number"],
            order_id,
        )
        create_notification(
            order["buyer_id"],
            f"Order Shipped — {order['style_number']}",
            f"Your bulk order #{order_id} has been confirmed as shipped.",
            notif_type="success",
            related_order_type="bulk_order",
            related_order_id=order_id,
        )

    return jsonify({"message": "Shipment confirmed", "order_id": order_id}), 200


# ── Bulk workflow: timeline email → customer response → hold ────────────────


@admin_bp.route("/orders/bulk/<int:order_id>/timeline-email", methods=["POST"])
@require_role("Admin", "Manager")
def send_bulk_timeline_email(order_id):
    """
    Send the completion-timeline email to the buyer and move the order to
    CustomerPending (awaiting the buyer's reply).
    Body: {
      decision: 'can_complete' | 'cannot_complete',
      given_days: int, needed_days: int, gap_days: int (extra if can, more if cannot)
    }
    """
    from services.email_service import _wrap_html, send_email

    data = request.get_json(force=True, silent=True) or {}
    decision = data.get("decision")
    if decision not in ("can_complete", "cannot_complete"):
        return jsonify({"error": "decision must be 'can_complete' or 'cannot_complete'"}), 400
    try:
        given = int(data.get("given_days"))
        needed = int(data.get("needed_days"))
        gap = int(data.get("gap_days"))
    except (TypeError, ValueError):
        return jsonify({"error": "given_days, needed_days and gap_days must be numbers."}), 400

    db = get_db()
    order = db.execute("SELECT * FROM bulk_orders WHERE id=?", (order_id,)).fetchone()
    if not order:
        return jsonify({"error": "Bulk order not found"}), 404
    if order["status"] not in ("Pending", "CustomerPending", "Hold"):
        return jsonify({"error": f"Cannot send timeline email in status: {order['status']}"}), 400

    buyer = db.execute(
        "SELECT email, full_name FROM users WHERE id=?", (order["buyer_id"],)
    ).fetchone()
    if not buyer:
        return jsonify({"error": "Buyer not found"}), 404

    if decision == "can_complete":
        subject = "Order Completion Within Timeline"
        body_txt = (
            f"We acknowledge the timeline of {given} days provided for this order. "
            f"Our team confirms that we can complete the work within the given schedule "
            f"(we estimate {needed} days, leaving {gap} day(s) to spare), and we are ready "
            f"to proceed with the order."
        )
    else:
        subject = "Order Cannot Be Completed Within Timeline"
        body_txt = (
            f"We acknowledge the timeline of {given} days provided for this order. "
            f"Our team requires {needed} days to complete the work, which exceeds the given "
            f"schedule. If you are able to extend the timeline by {gap} day(s), we will be "
            f"able to take on the order and deliver it successfully."
        )

    # The buyer can respond from their portal — that reply flows straight back
    # into the system (no email inbox to watch).
    html = _wrap_html(
        subject,
        f"<p>Dear {buyer['full_name']},</p><p>{body_txt}</p>"
        f"<p>Please log in to your FabricFlow account and open Bulk Orders to respond — "
        f"you can <strong>approve</strong> the order or <strong>request more time</strong>.</p>"
        f"<p>Best regards,<br/>FabricFlow International</p>",
    )
    send_email(buyer["email"], f"[Order #{order_id}] {subject}", html)

    proposed_date = None
    if decision == "cannot_complete" and gap > 0:
        try:
            current_required = datetime.strptime(
                str(order["buyer_required_date"])[:10], "%Y-%m-%d"
            ).date()
            approved = datetime.strptime(str(order["approved_date"])[:10], "%Y-%m-%d").date()

            lead_needed = None
            try:
                if order["c2_result_json"]:
                    lead_needed = (
                        json.loads(order["c2_result_json"])
                        .get("production_days", {})
                        .get("total_lead_days")
                    )
            except (TypeError, ValueError):
                lead_needed = None

            candidate_dates = [current_required + timedelta(days=gap)]
            if lead_needed:
                candidate_dates.append(
                    approved
                    + timedelta(days=int(math.ceil(float(lead_needed))) + DEADLINE_MARGIN_DAYS)
                )
            proposed_date = max(candidate_dates).isoformat()
        except (TypeError, ValueError):
            proposed_date = None

    db.execute(
        """UPDATE bulk_orders
           SET status='CustomerPending', timeline_email_sent_at=?, customer_response=NULL,
               timeline_decision=?, timeline_given_days=?, timeline_needed_days=?,
               timeline_gap_days=?, proposed_required_date=?
           WHERE id=?""",
        (
            datetime.utcnow(),
            decision,
            given,
            needed,
            gap,
            proposed_date,
            order_id,
        ),
    )
    db.commit()
    create_notification(
        order["buyer_id"],
        f"Action needed — Bulk Order #{order_id}",
        (
            f"We need {gap} more day(s) for style {order['style_number']}"
            + (f" — proposed new date {proposed_date}." if proposed_date else ".")
            + " Please review and respond."
        )
        if decision == "cannot_complete"
        else (
            f"We can complete style {order['style_number']} within your schedule. Please confirm."
        ),
        notif_type="info",
        related_order_type="bulk_order",
        related_order_id=order_id,
    )
    return jsonify({"message": "Timeline email sent", "status": "CustomerPending"}), 200


@admin_bp.route("/orders/bulk/<int:order_id>/customer-response", methods=["POST"])
@require_role("Admin", "Manager")
def record_customer_response(order_id):
    """
    Record the buyer's reply to the timeline email.
    Body: { response: 'Approved' | 'Rejected' }
    Approved -> stays CustomerPending, ready for plant assignment.
    Rejected -> moves to Hold.
    """
    data = request.get_json(force=True, silent=True) or {}
    response = data.get("response")
    if response not in ("Approved", "Rejected"):
        return jsonify({"error": "response must be 'Approved' or 'Rejected'"}), 400

    db = get_db()
    order = db.execute("SELECT * FROM bulk_orders WHERE id=?", (order_id,)).fetchone()
    if not order:
        return jsonify({"error": "Bulk order not found"}), 404
    if order["status"] != "CustomerPending":
        return jsonify({"error": "Order is not awaiting a customer response."}), 400

    new_status = "CustomerPending" if response == "Approved" else "Hold"
    applied_date = None
    if response == "Approved" and order["proposed_required_date"]:
        applied_date = str(order["proposed_required_date"])[:10]

    db.execute(
        """UPDATE bulk_orders
           SET customer_response=?, status=?, customer_responded_at=?,
               buyer_required_date=COALESCE(?, buyer_required_date),
               proposed_required_date=CASE WHEN ? IS NULL
                                           THEN proposed_required_date ELSE NULL END
           WHERE id=?""",
        (
            response,
            new_status,
            datetime.utcnow(),
            applied_date,
            applied_date,
            order_id,
        ),
    )
    db.commit()
    return jsonify(
        {
            "message": f"Customer response recorded: {response}",
            "status": new_status,
            "assignable": response == "Approved",
            "buyer_required_date": applied_date,
        }
    ), 200


@admin_bp.route("/orders/bulk/<int:order_id>/apply-extension", methods=["POST"])
@require_role("Admin", "Manager")
def apply_bulk_extension(order_id):
    """Accept a requested extension, update the date, and re-run Component 2."""
    from components.component2 import KNOWN_BUYERS

    data = request.get_json(force=True, silent=True) or {}
    db = get_db()
    order = db.execute("SELECT * FROM bulk_orders WHERE id=?", (order_id,)).fetchone()
    if not order:
        return jsonify({"error": "Bulk order not found"}), 404
    if order["status"] in ("Completed", "Shipped"):
        return jsonify({"error": f"Cannot change the date of a {order['status']} order."}), 400

    current_required = datetime.strptime(str(order["buyer_required_date"])[:10], "%Y-%m-%d").date()
    new_date_raw = (data.get("new_date") or "").strip()
    if new_date_raw:
        try:
            new_required = datetime.strptime(new_date_raw[:10], "%Y-%m-%d").date()
        except ValueError:
            return jsonify({"error": "new_date must be YYYY-MM-DD."}), 400
    else:
        days = data.get("extension_days")
        if days in (None, ""):
            days = order["extension_days_requested"]
        try:
            days = int(days)
        except (TypeError, ValueError):
            return jsonify({"error": "Provide extension_days or new_date."}), 400
        if days <= 0:
            return jsonify({"error": "Extension days must be greater than zero."}), 400
        new_required = current_required + timedelta(days=days)

    if new_required <= current_required:
        return jsonify({"error": "The new required date must be later than the current one."}), 400

    org = db.execute(
        """SELECT o.name FROM users u JOIN organizations o ON u.org_id=o.id
           WHERE u.id=?""",
        (order["buyer_id"],),
    ).fetchone()
    c2_buyer = org["name"] if org and org["name"] in KNOWN_BUYERS else KNOWN_BUYERS[0]
    start_month = str(order["approved_date"])[:7]
    monthly_capacity = get_all_plants_window_capacity(start_month, new_required.strftime("%Y-%m"))
    sample_plant = max(monthly_capacity, key=monthly_capacity.get) if monthly_capacity else None

    with current_app.test_client() as client:
        response = client.post(
            "/api/component2/predict",
            json={
                "buyer_name": c2_buyer,
                "style_id": order["style_number"],
                "bulk_order_quantity": order["bulk_order_quantity"],
                "daily_commitment": order["daily_commitment"],
                "style_priority": order["style_priority"],
                "design_width": float(order["design_width"] or 0),
                "design_length": float(order["design_length"] or 0),
                "color_count": int(order["color_count"] or 0),
                "stitch_count": int(order["stitch_count"] or 0),
                "sample_plant": sample_plant,
                "sp_cap_util_pct": 85.0,
                "bulk_order_approved_date": str(order["approved_date"])[:10],
                "buyer_required_date": new_required.isoformat(),
                "damage_pct": float(order["damage_pct"] or 0.0),
                "shipment_days": int(order["shipment_days"] or 18),
                "monthly_capacity": monthly_capacity,
            },
            headers={"Content-Type": "application/json"},
        )
        c2_result = response.get_json()

    c2_ok = bool(c2_result) and "error" not in c2_result
    db.execute(
        """UPDATE bulk_orders
           SET buyer_required_date=?, status='Pending', customer_response=NULL,
               extension_days_requested=NULL, customer_message=NULL,
               timeline_email_sent_at=NULL, customer_responded_at=NULL,
               c2_result_json=COALESCE(?, c2_result_json)
           WHERE id=?""",
        (
            new_required.isoformat(),
            json.dumps(c2_result) if c2_ok else None,
            order_id,
        ),
    )
    db.commit()

    create_notification(
        order["buyer_id"],
        f"Date Updated - Bulk Order #{order_id}",
        f"The required date for style {order['style_number']} is now {new_required.isoformat()}.",
        notif_type="success",
        related_order_type="bulk_order",
        related_order_id=order_id,
    )
    return jsonify(
        {
            "message": "Required date updated",
            "buyer_required_date": new_required.isoformat(),
            "previous_required_date": current_required.isoformat(),
            "deadline_match": (
                (c2_result.get("deadline") or {}).get("deadline_match") if c2_ok else None
            ),
            "status": "Pending",
        }
    ), 200


@admin_bp.route("/orders/bulk/<int:order_id>/hold", methods=["POST"])
@require_role("Admin", "Manager")
def toggle_bulk_hold(order_id):
    """Put an order On Hold, or release it back to Pending. Body: { hold: bool }."""
    data = request.get_json(force=True, silent=True) or {}
    hold = bool(data.get("hold", True))

    db = get_db()
    order = db.execute("SELECT status FROM bulk_orders WHERE id=?", (order_id,)).fetchone()
    if not order:
        return jsonify({"error": "Bulk order not found"}), 404

    if hold:
        if order["status"] in ("Shipped", "Completed"):
            return jsonify({"error": f"Cannot hold an order in status: {order['status']}"}), 400
        db.execute("UPDATE bulk_orders SET status='Hold' WHERE id=?", (order_id,))
    else:
        if order["status"] != "Hold":
            return jsonify({"error": "Order is not on hold."}), 400
        db.execute("UPDATE bulk_orders SET status='Pending' WHERE id=?", (order_id,))
    db.commit()
    return jsonify({"message": "Hold updated", "status": "Hold" if hold else "Pending"}), 200


@admin_bp.route("/orders/bulk/<int:order_id>/analysis", methods=["GET"])
@require_role("Admin", "Manager")
def bulk_order_analysis(order_id):
    """Run Component 4 on one bulk-order allocation's saved C3 daily logs."""
    db = get_db()
    order = db.execute("SELECT * FROM bulk_orders WHERE id = ?", (order_id,)).fetchone()
    if not order:
        return jsonify({"error": "Bulk order not found"}), 404

    requested_plant_id = (request.args.get("plant_id") or "").strip()
    allocation = db.execute(
        """SELECT opa.plant_id, opa.allocated_qty, opa.allocation_type,
                  p.name AS plant_name, p.location AS plant_location,
                  u.full_name AS buyer_name
           FROM order_plant_allocations opa
           JOIN plants p ON p.id = opa.plant_id
           JOIN bulk_orders bo ON bo.id = opa.bulk_order_id
           JOIN users u ON u.id = bo.buyer_id
           WHERE opa.id = (
               SELECT MAX(opa2.id)
               FROM order_plant_allocations opa2
               WHERE opa2.bulk_order_id = ?
                 AND (? = '' OR opa2.plant_id = ?)
           )""",
        (order_id, requested_plant_id, requested_plant_id),
    ).fetchone()
    if not allocation:
        return jsonify({"error": "No matching plant allocation found for this order"}), 404
    plant_id = allocation["plant_id"]

    logs = db.execute(
        """SELECT * FROM daily_logs
           WHERE bulk_order_id = ? AND plant_id = ?
           ORDER BY log_date, working_day_no""",
        (order_id, plant_id),
    ).fetchall()
    if not logs:
        return jsonify({"error": "No Component 3 daily logs found for this order and plant"}), 404

    # Aggregate values from logs for C4
    total_days = len(logs)
    machine_breakdown_days = sum(1 for log in logs if log["machine_breakdown_count"] > 0)
    worker_shortage_days = sum(1 for log in logs if log["worker_shortage_count"] > 0)
    avg_daily_output = sum(log["plant_daily_output"] for log in logs) / total_days
    total_damage = sum(log["daily_damage_qty"] or 0 for log in logs)
    total_output = sum(log["plant_daily_output"] for log in logs)
    damage_rate = round((total_damage / max(total_output, 1)) * 100, 2)
    # C3 nests severity under "risk_detection" — the old top-level lookup always
    # returned None, so this count was permanently 0.
    risk_count_c3 = 0
    critical_risk_days = 0
    recovery_required_days = 0
    for log in logs:
        if not log["c3_result_json"]:
            continue
        try:
            c3_result = json.loads(log["c3_result_json"])
        except (TypeError, json.JSONDecodeError):
            continue
        risk_detection = c3_result.get("risk_detection") or {}
        if risk_detection.get("risk_status") == "Risk":
            risk_count_c3 += 1
        if risk_detection.get("severity") == "Critical":
            critical_risk_days += 1
        recovery = c3_result.get("recovery_plan") or {}
        if recovery.get("status") == "recovery_required":
            recovery_required_days += 1

    plant = db.execute("SELECT * FROM plants WHERE id = ?", (plant_id,)).fetchone()
    allocated_quantity = int(allocation["allocated_qty"] or order["bulk_order_quantity"])

    try:
        c2_result = json.loads(order["c2_result_json"] or "{}")
    except (TypeError, json.JSONDecodeError):
        c2_result = {}
    planned_completion_days = max(
        1,
        int(
            round(
                float(
                    (c2_result.get("production_days") or {}).get(
                        "total_production_days", total_days
                    )
                )
            )
        ),
    )

    c4_payload = {
        "plant_name": plant["name"],
        "order_quantity": allocated_quantity,
        "planned_completion_days": planned_completion_days,
        "actual_completion_days": total_days,
        "machine_count": plant["total_machines"],
        "active_machine_count": plant["total_machines"],
        "employee_count": plant["employee_count"],
        "daily_output_avg": round(avg_daily_output, 1),
        "total_workload": allocated_quantity,
        "urgent_style_flag": "Yes" if order["style_priority"] == "High" else "No",
        "urgent_handled_count": min(risk_count_c3, 6),
        "risk_count_from_component3": risk_count_c3,
        "machine_breakdown_days": machine_breakdown_days,
        "worker_shortage_days": worker_shortage_days,
        "damage_rate": damage_rate,
    }

    # Call Component 4 internally
    from flask import current_app

    with current_app.test_client() as client:
        resp = client.post(
            "/api/component4/predict",
            json=c4_payload,
            headers={"Content-Type": "application/json"},
        )
        c4_result = resp.get_json()

    if resp.status_code >= 400 or not isinstance(c4_result, dict):
        return jsonify(
            {
                "error": (c4_result or {}).get(
                    "error", "Component 4 analysis could not be completed"
                ),
                "details": (c4_result or {}).get("details", []),
            }
        ), 502

    # Persist the C4 result onto the latest daily log so performance history is stored.
    db.execute(
        "UPDATE daily_logs SET c4_result_json=? WHERE id=?",
        (json.dumps(c4_result), logs[-1]["id"]),
    )
    db.commit()

    return jsonify(
        {
            "order_id": order_id,
            "style_number": order["style_number"],
            "buyer_name": allocation["buyer_name"],
            "plant_id": plant_id,
            "plant_name": allocation["plant_name"],
            "plant_location": allocation["plant_location"],
            "allocated_quantity": allocated_quantity,
            "logs_analysed": total_days,
            "risk_events_c3": risk_count_c3,
            "critical_risk_days": critical_risk_days,
            "recovery_required_days": recovery_required_days,
            "component4_result": c4_result,
        }
    ), 200


@admin_bp.route("/performance", methods=["GET"])
@require_role("Admin")
def performance_list():
    """
    Garment-wise performance module (Component 4): completed/shipped bulk orders
    that have production logs, with any previously-computed C4 result attached.
    """
    db = get_db()
    orders = db.execute(
        """WITH latest_allocations AS (
               SELECT opa.*
               FROM order_plant_allocations opa
               JOIN (
                   SELECT bulk_order_id, plant_id, MAX(id) AS allocation_id
                   FROM order_plant_allocations
                   GROUP BY bulk_order_id, plant_id
               ) latest ON latest.allocation_id = opa.id
           )
           SELECT bo.id, bo.style_number, bo.bulk_order_quantity, bo.status,
                  bo.buyer_required_date, bo.ready_at, bo.shipped_at,
                  u.full_name AS buyer_name,
                  opa.plant_id, opa.allocated_qty, opa.allocation_type,
                  (SELECT COUNT(*) FROM daily_logs dl
                   WHERE dl.bulk_order_id = bo.id
                     AND dl.plant_id = opa.plant_id) AS log_count,
                  p.name AS plant_name, p.location AS plant_location
           FROM bulk_orders bo
           JOIN users u ON bo.buyer_id = u.id
           JOIN latest_allocations opa ON opa.bulk_order_id = bo.id
           JOIN plants p ON p.id = opa.plant_id
           WHERE bo.status IN ('Completed','Shipped')
           ORDER BY bo.ready_at DESC, bo.id DESC, opa.plant_id"""
    ).fetchall()

    result = []
    for o in orders:
        row = dict(o)
        # Attach the most recent stored C4 result, if any.
        latest = db.execute(
            """SELECT c4_result_json FROM daily_logs
               WHERE bulk_order_id=? AND plant_id=?
                 AND c4_result_json IS NOT NULL
               ORDER BY id DESC LIMIT 1""",
            (o["id"], o["plant_id"]),
        ).fetchone()
        row["c4_result"] = json.loads(latest["c4_result_json"]) if latest else None
        result.append(row)
    return jsonify(result), 200


# ── Capacity & Plants ─────────────────────────────────────────────────────


@admin_bp.route("/capacity", methods=["GET"])
@require_role("Admin", "Manager")
def capacity_overview():
    """Current capacity for a given month, excluding external sub-plants."""
    month_year = request.args.get("month", datetime.utcnow().strftime("%Y-%m"))
    db = get_db()
    plants = db.execute(
        """SELECT id, name, location FROM plants
           WHERE plant_type IS NULL OR plant_type='Registered'"""
    ).fetchall()
    result = []
    for p in plants:
        cap = db.execute(
            "SELECT total_capacity, used_capacity FROM plant_monthly_capacity WHERE plant_id=? AND month_year=?",
            (p["id"], month_year),
        ).fetchone()
        result.append(
            {
                "plant_id": p["id"],
                "plant_name": p["name"],
                "location": p["location"],
                "month_year": month_year,
                "total_capacity": cap["total_capacity"] if cap else None,
                "used_capacity": cap["used_capacity"] if cap else 0,
                "available_capacity": (cap["total_capacity"] - cap["used_capacity"])
                if cap
                else None,
            }
        )
    return jsonify(result), 200


@admin_bp.route("/plants", methods=["GET"])
@require_role("Admin", "Manager")
def list_plants():
    """All registered plants with their static KPIs (excludes external sub plants)."""
    db = get_db()
    plants = db.execute(
        "SELECT * FROM plants WHERE plant_type IS NULL OR plant_type='Registered'"
    ).fetchall()
    return jsonify([dict(p) for p in plants]), 200


@admin_bp.route("/plants/<plant_id>/logs", methods=["GET"])
@require_role("Admin", "Manager")
def plant_logs(plant_id):
    """All daily logs for a specific plant."""
    db = get_db()
    logs = db.execute(
        "SELECT * FROM daily_logs WHERE plant_id = ? ORDER BY log_date DESC LIMIT 100",
        (plant_id,),
    ).fetchall()
    result = []
    for log in logs:
        row = dict(log)
        if row.get("c3_result_json"):
            row["c3_result"] = json.loads(row["c3_result_json"])
            del row["c3_result_json"]
        result.append(row)
    return jsonify(result), 200


# ── Contact Us inbox ───────────────────────────────────────────────────────


@admin_bp.route("/inbound-email/poll", methods=["POST"])
@require_role("Admin", "Manager")
def poll_inbound_email():
    """Manually check the mailbox now for customer email replies."""
    from services.inbound_email_service import poll_inbox

    result = poll_inbox()
    status = 200 if not result.get("error") else 502
    return jsonify(result), status


@admin_bp.route("/inbound-email", methods=["GET"])
@require_role("Admin", "Manager")
def list_inbound_email():
    """Recent inbound customer email replies — bulk + sample, matched and unmatched."""
    db = get_db()
    rows = db.execute(
        """SELECT ie.*,
                  COALESCE(bo.style_number, so.style_number) AS style_number
           FROM inbound_emails ie
           LEFT JOIN bulk_orders   bo ON ie.order_type = 'bulk'   AND bo.id = ie.order_id
           LEFT JOIN sample_orders so ON ie.order_type = 'sample' AND so.id = ie.order_id
           ORDER BY ie.created_at DESC LIMIT 100"""
    ).fetchall()
    return jsonify([dict(r) for r in rows]), 200


@admin_bp.route("/contact-messages", methods=["GET"])
@require_role("Admin", "Manager")
def list_contact_messages():
    """Messages submitted through the public Contact Us form, newest first."""
    db = get_db()
    rows = db.execute(
        "SELECT * FROM contact_messages ORDER BY created_at DESC LIMIT 200"
    ).fetchall()
    return jsonify([dict(r) for r in rows]), 200


@admin_bp.route("/contact-messages/<int:msg_id>/read", methods=["POST"])
@require_role("Admin", "Manager")
def mark_contact_message_read(msg_id):
    """Mark a contact message as read."""
    db = get_db()
    db.execute("UPDATE contact_messages SET is_read=1 WHERE id=?", (msg_id,))
    db.commit()
    return jsonify({"message": "Marked read"}), 200
