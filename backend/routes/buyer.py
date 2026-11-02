"""
routes/buyer.py
Buyer portal endpoints:
  - Submit sample orders (runs C1 automatically)
  - Submit bulk orders (runs C2 automatically, reads capacity from DB)
  - View own orders + status
  - Notifications inbox
"""

import os
import json
from datetime import datetime, date
from werkzeug.utils import secure_filename
from flask import Blueprint, request, jsonify, g, current_app, send_file, abort
from database.db import get_db
from middleware.auth_middleware import require_role
from services.email_service import send_new_sample_order_to_admin, send_new_bulk_order_to_admin
from services.notification_service import create_notification
from services.capacity_service import get_all_plants_monthly_capacity

buyer_bp = Blueprint("buyer", __name__)

# Style PDFs are stored on disk under <project_root>/uploads/style_pdfs and only
# the relative path is persisted in the DB.
_UPLOAD_SUBDIR = os.path.join("uploads", "style_pdfs")
_MAX_PDF_BYTES = 10 * 1024 * 1024   # 10 MB

# Daily commitment is no longer entered by the buyer. It is meant to come from
# C4 (prior-year plant output) and is plant-specific. Hardcoded for now — the
# real derivation drops into this one place later.
# TODO(Phase 4 follow-up): derive from C4 per assigned plant instead of a constant.
DEFAULT_DAILY_COMMITMENT = 500


def _save_style_pdf(pdf_file):
    """
    Persist an optional uploaded style PDF and return its relative path
    (e.g. 'uploads/style_pdfs/xyz.pdf'), or raise ValueError on a bad file.
    Returns None if no file was provided.
    """
    if not pdf_file or not pdf_file.filename:
        return None

    filename = secure_filename(pdf_file.filename)
    if not filename.lower().endswith(".pdf"):
        raise ValueError("Only PDF files are allowed for the style PDF.")

    # Size check without trusting the client-provided Content-Length.
    pdf_file.stream.seek(0, os.SEEK_END)
    size = pdf_file.stream.tell()
    pdf_file.stream.seek(0)
    if size > _MAX_PDF_BYTES:
        raise ValueError("Style PDF must be 10 MB or smaller.")

    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    dest_dir = os.path.join(project_root, _UPLOAD_SUBDIR)
    os.makedirs(dest_dir, exist_ok=True)

    stamp = datetime.now().strftime("%Y%m%d%H%M%S%f")
    stored_name = f"{g.user_id}_{stamp}_{filename}"
    pdf_file.save(os.path.join(dest_dir, stored_name))

    # Store a forward-slash relative path so it's portable across OSes.
    return f"{_UPLOAD_SUBDIR}/{stored_name}".replace("\\", "/")


def _get_admin():
    db = get_db()
    return db.execute("SELECT id, email FROM users WHERE role='Admin' LIMIT 1").fetchone()


# ── Sample Orders ─────────────────────────────────────────────────────────

@buyer_bp.route("/orders/sample", methods=["POST"])
@require_role("Buyer")
def submit_sample_order():
    """
    Buyer submits a sample order.
    Required: style_number, sample_qty, receive_date, buyer_required_date
    Optional: artwork_number, notes
    Automatically runs Component 1 and saves the full result.
    """
    # Accept both JSON and multipart/form-data (the latter carries the optional PDF).
    pdf_file = None
    if request.content_type and request.content_type.startswith("multipart/form-data"):
        data = request.form.to_dict()
        pdf_file = request.files.get("style_pdf")
    else:
        data = request.get_json(force=True, silent=True) or {}

    required = ["style_number", "sample_qty", "receive_date", "buyer_required_date"]
    missing  = [f for f in required if not data.get(f)]
    if missing:
        return jsonify({"error": f"Missing fields: {missing}"}), 400

    # Validate sample quantity (5–9 inclusive).
    try:
        sample_qty = int(data["sample_qty"])
    except (TypeError, ValueError):
        return jsonify({"error": "Sample quantity must be a whole number."}), 400
    if not (5 <= sample_qty <= 9):
        return jsonify({"error": "Sample quantity must be between 5 and 9."}), 400

    # Validate the required date is not in the past.
    try:
        required_date = datetime.strptime(data["buyer_required_date"], "%Y-%m-%d").date()
    except (TypeError, ValueError):
        return jsonify({"error": "Required date must be a valid date (YYYY-MM-DD)."}), 400
    if required_date < date.today():
        return jsonify({"error": "Required date cannot be in the past."}), 400

    # Persist the optional style PDF (validated) before touching the DB.
    try:
        style_pdf_path = _save_style_pdf(pdf_file)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400

    db = get_db()

    # Get buyer's company name (used as buyer_name in C1)
    user_org = db.execute(
        "SELECT o.name FROM users u JOIN organizations o ON u.org_id = o.id WHERE u.id = ?",
        (g.user_id,),
    ).fetchone()
    if not user_org:
        return jsonify({"error": "Buyer organisation not found"}), 400
    buyer_name = user_org["name"]

    # Fallback to a known buyer for the AI model prediction if the company is new
    from components.component1 import ALL_BUYERS
    c1_model_buyer = buyer_name if buyer_name in ALL_BUYERS else ALL_BUYERS[0]

    # Build C1 payload and call component1 internally
    c1_payload = {
        "buyer_name":          c1_model_buyer,
        "style_id":            data.get("artwork_number", data["style_number"]),
        "sample_qty":          sample_qty,
        "receive_date":        data["receive_date"],
        "buyer_required_date": data["buyer_required_date"],
    }

    with current_app.test_client() as client:
        resp = client.post(
            "/api/component1/predict",
            json=c1_payload,
            headers={"Content-Type": "application/json"},
        )
        c1_result = resp.get_json()

    feasible    = c1_result.get("planning_output", {}).get("feasible", False)
    feasibility = "Feasible" if feasible else "Infeasible"
    # Buyer-facing status always starts at Pending; feasibility is admin-only.
    status      = "Pending"

    # Save to DB
    db.execute(
        """INSERT INTO sample_orders
           (style_number, artwork_number, buyer_id, sample_qty,
            receive_date, buyer_required_date, notes, status, feasibility,
            c1_result_json, style_pdf_path)
           VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
        (
            data["style_number"],
            data.get("artwork_number"),
            g.user_id,
            sample_qty,
            data["receive_date"],
            data["buyer_required_date"],
            data.get("notes"),
            status,
            feasibility,
            json.dumps(c1_result),
            style_pdf_path,
        ),
    )
    db.commit()
    order_id = db.execute(
        "SELECT id FROM sample_orders WHERE buyer_id=? ORDER BY created_at DESC LIMIT 1",
        (g.user_id,),
    ).fetchone()["id"]

    # Notify admin
    admin = _get_admin()
    user  = db.execute("SELECT full_name, email FROM users WHERE id=?", (g.user_id,)).fetchone()
    if admin:
        send_new_sample_order_to_admin(
            admin["email"], buyer_name, user["email"], data["style_number"], order_id
        )
        create_notification(
            admin["id"],
            f"New Sample Order — {data['style_number']}",
            f"{user['full_name']} ({buyer_name}) submitted a new sample order #{order_id}. "
            f"AI feasibility: {feasibility}.",
            notif_type="info", related_order_type="sample_order", related_order_id=order_id,
        )

    return jsonify({
        "message":     "Sample order submitted",
        "order_id":    order_id,
        "status":      status,
        "feasibility": feasibility,
        "feasible":    feasible,
        "c1_result":   c1_result,
    }), 201


@buyer_bp.route("/orders/sample", methods=["GET"])
@require_role("Buyer")
def list_sample_orders():
    """Buyer's own sample orders."""
    db = get_db()
    orders = db.execute(
        """SELECT so.id, so.style_number, so.artwork_number, so.sample_qty,
                  so.receive_date, so.buyer_required_date, so.notes, so.status, so.created_at,
                  so.assigned_at, so.style_pdf_path, so.production_stage,
                  p.name AS assigned_plant_name
           FROM sample_orders so
           LEFT JOIN plants p ON so.assigned_plant_id = p.id
           WHERE so.buyer_id = ?
           ORDER BY so.created_at DESC""",
        (g.user_id,),
    ).fetchall()
    return jsonify([dict(o) for o in orders]), 200


@buyer_bp.route("/orders/sample/<int:order_id>", methods=["GET"])
@require_role("Buyer")
def get_sample_order(order_id):
    """Single sample order detail with full C1 result."""
    db = get_db()
    order = db.execute(
        "SELECT * FROM sample_orders WHERE id=? AND buyer_id=?",
        (order_id, g.user_id),
    ).fetchone()
    if not order:
        return jsonify({"error": "Order not found"}), 404
    row = dict(order)
    # Feasibility and the raw C1 result are admin-only — never expose to the buyer.
    row.pop("feasibility", None)
    row.pop("c1_result_json", None)
    return jsonify(row), 200


@buyer_bp.route("/orders/sample/<int:order_id>", methods=["PUT"])
@require_role("Buyer")
def update_sample_order(order_id):
    """
    Edit a Pending sample order (buyer's own). Only Pending orders are editable.
    Editable: sample_qty (5-9), buyer_required_date (not past), notes, artwork_number.
    Re-runs C1 so the admin-side feasibility stays accurate.
    """
    db = get_db()
    order = db.execute(
        "SELECT * FROM sample_orders WHERE id=? AND buyer_id=?", (order_id, g.user_id)
    ).fetchone()
    if not order:
        return jsonify({"error": "Order not found"}), 404
    if order["status"] != "Pending":
        return jsonify({"error": "Only pending orders can be edited."}), 400

    data = request.get_json(force=True, silent=True) or {}

    # Start from existing values, override with any provided.
    sample_qty          = order["sample_qty"]
    buyer_required_date = order["buyer_required_date"]
    notes               = order["notes"]
    artwork_number      = order["artwork_number"]

    if "sample_qty" in data:
        try:
            sample_qty = int(data["sample_qty"])
        except (TypeError, ValueError):
            return jsonify({"error": "Sample quantity must be a whole number."}), 400
        if not (5 <= sample_qty <= 9):
            return jsonify({"error": "Sample quantity must be between 5 and 9."}), 400

    if "buyer_required_date" in data and data["buyer_required_date"]:
        try:
            req_date = datetime.strptime(data["buyer_required_date"], "%Y-%m-%d").date()
        except (TypeError, ValueError):
            return jsonify({"error": "Required date must be a valid date (YYYY-MM-DD)."}), 400
        if req_date < date.today():
            return jsonify({"error": "Required date cannot be in the past."}), 400
        buyer_required_date = data["buyer_required_date"]

    if "notes" in data:
        notes = data.get("notes")
    if "artwork_number" in data:
        artwork_number = data.get("artwork_number")

    # Re-run C1 for updated feasibility.
    user_org = db.execute(
        "SELECT o.name FROM users u JOIN organizations o ON u.org_id=o.id WHERE u.id=?",
        (g.user_id,),
    ).fetchone()
    from components.component1 import ALL_BUYERS
    c1_model_buyer = user_org["name"] if user_org and user_org["name"] in ALL_BUYERS else ALL_BUYERS[0]
    with current_app.test_client() as client:
        resp = client.post("/api/component1/predict", json={
            "buyer_name":          c1_model_buyer,
            "style_id":            artwork_number or order["style_number"],
            "sample_qty":          sample_qty,
            "receive_date":        order["receive_date"],
            "buyer_required_date": buyer_required_date,
        }, headers={"Content-Type": "application/json"})
        c1_result = resp.get_json()
    feasibility = "Feasible" if c1_result.get("planning_output", {}).get("feasible", False) else "Infeasible"

    db.execute(
        """UPDATE sample_orders
           SET sample_qty=?, buyer_required_date=?, notes=?, artwork_number=?,
               feasibility=?, c1_result_json=?
           WHERE id=? AND buyer_id=?""",
        (sample_qty, buyer_required_date, notes, artwork_number,
         feasibility, json.dumps(c1_result), order_id, g.user_id),
    )
    db.commit()
    return jsonify({"message": "Sample order updated", "order_id": order_id}), 200


@buyer_bp.route("/orders/sample/<int:order_id>", methods=["DELETE"])
@require_role("Buyer")
def delete_sample_order(order_id):
    """Delete a Pending sample order (buyer's own). Processing orders can't be deleted."""
    db = get_db()
    order = db.execute(
        "SELECT status FROM sample_orders WHERE id=? AND buyer_id=?", (order_id, g.user_id)
    ).fetchone()
    if not order:
        return jsonify({"error": "Order not found"}), 404
    if order["status"] != "Pending":
        return jsonify({"error": "Only pending orders can be deleted."}), 400

    # Don't orphan a bulk order that was created from this sample.
    linked = db.execute(
        "SELECT 1 FROM bulk_orders WHERE sample_order_id=? LIMIT 1", (order_id,)
    ).fetchone()
    if linked:
        return jsonify({"error": "This sample is linked to a bulk order and can't be deleted."}), 400

    db.execute("DELETE FROM sample_orders WHERE id=? AND buyer_id=?", (order_id, g.user_id))
    db.commit()
    return jsonify({"message": "Sample order deleted"}), 200


@buyer_bp.route("/orders/sample/<int:order_id>/pdf", methods=["GET"])
@require_role("Buyer")
def get_sample_order_pdf(order_id):
    """Stream the buyer's own uploaded style PDF for a sample order, if any."""
    db = get_db()
    order = db.execute(
        "SELECT style_pdf_path, style_number FROM sample_orders WHERE id=? AND buyer_id=?",
        (order_id, g.user_id),
    ).fetchone()
    if not order:
        return jsonify({"error": "Order not found"}), 404
    if not order["style_pdf_path"]:
        return jsonify({"error": "No style PDF uploaded for this order"}), 404

    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    upload_root  = os.path.join(project_root, _UPLOAD_SUBDIR)
    abs_path     = os.path.abspath(os.path.join(project_root, order["style_pdf_path"]))

    # Guard against the stored path ever escaping the uploads directory.
    if os.path.commonpath([abs_path, upload_root]) != upload_root or not os.path.isfile(abs_path):
        abort(404)

    download_name = f"{order['style_number']}_style.pdf"
    return send_file(abs_path, mimetype="application/pdf", as_attachment=False, download_name=download_name)


# ── Bulk Orders ───────────────────────────────────────────────────────────

@buyer_bp.route("/orders/bulk", methods=["POST"])
@require_role("Buyer")
def submit_bulk_order():
    """
    Buyer submits a bulk order.
    ALWAYS Required: style_number, bulk_order_quantity, daily_commitment,
                     style_priority, bulk_order_approved_date, buyer_required_date
    Auto-filled from Style Catalog if style exists in DB:
                     design_width, design_length, color_count, stitch_count
    Optional: sample_order_id, damage_pct, shipment_days, artwork_number, style_pdf
    Monthly capacity is read from DB automatically — no need to provide it.
    """
    # Accept JSON or multipart/form-data (the latter carries the optional style PDF).
    pdf_file = None
    if request.content_type and request.content_type.startswith("multipart/form-data"):
        data = request.form.to_dict()
        pdf_file = request.files.get("style_pdf")
    else:
        data = request.get_json(force=True, silent=True) or {}

    # Persist the optional style PDF (validated) before running C2.
    try:
        style_pdf_path = _save_style_pdf(pdf_file)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400

    db = get_db()

    # ── Auto-fill technical specs from Style Catalog ──────────────────────
    style_record = None
    if data.get("style_number"):
        style_record = db.execute(
            "SELECT * FROM styles WHERE style_number = ?",
            (str(data["style_number"]).strip().upper(),),
        ).fetchone()
        if style_record:
            for field in ["design_width", "design_length", "color_count", "stitch_count"]:
                if data.get(field) is None:
                    data[field] = style_record[field]

    always_required = [
        "style_number", "bulk_order_quantity", "style_priority",
        "bulk_order_approved_date", "buyer_required_date",
    ]
    also_required = ["design_width", "design_length", "color_count", "stitch_count"]
    missing = [f for f in always_required + also_required if data.get(f) is None]
    if missing:
        return jsonify({"error": f"Missing fields: {missing}"}), 400

    # Validate the required date is not in the past.
    try:
        req_date = datetime.strptime(str(data["buyer_required_date"]), "%Y-%m-%d").date()
    except (TypeError, ValueError):
        return jsonify({"error": "Required date must be a valid date (YYYY-MM-DD)."}), 400
    if req_date < date.today():
        return jsonify({"error": "Required date cannot be in the past."}), 400

    # Daily commitment is derived server-side (not a buyer input).
    daily_commitment = int(data.get("daily_commitment") or DEFAULT_DAILY_COMMITMENT)

    user_org = db.execute(
        "SELECT o.name FROM users u JOIN organizations o ON u.org_id=o.id WHERE u.id=?",
        (g.user_id,),
    ).fetchone()
    buyer_name = user_org["name"]

    # Get live monthly capacity from DB
    month_year     = str(data["bulk_order_approved_date"])[:7]
    monthly_cap    = get_all_plants_monthly_capacity(month_year)

    # Determine sample plant (use top-capacity plant as default)
    sample_plant    = data.get("sample_plant") or max(monthly_cap, key=monthly_cap.get)
    sp_cap_util_pct = data.get("sp_cap_util_pct", 85.0)

    # Fallback to a known buyer for the AI model prediction if the company is new
    from components.component2 import KNOWN_BUYERS
    c2_model_buyer = buyer_name if buyer_name in KNOWN_BUYERS else KNOWN_BUYERS[0]

    c2_payload = {
        "buyer_name":              c2_model_buyer,
        "style_id":                data.get("artwork_number", data["style_number"]),
        "bulk_order_quantity":     int(data["bulk_order_quantity"]),
        "daily_commitment":        daily_commitment,
        "style_priority":          data["style_priority"],
        "design_width":            float(data["design_width"]),
        "design_length":           float(data["design_length"]),
        "color_count":             int(data["color_count"]),
        "stitch_count":            int(data["stitch_count"]),
        "sample_plant":            sample_plant,
        "sp_cap_util_pct":         float(sp_cap_util_pct),
        "bulk_order_approved_date": data["bulk_order_approved_date"],
        "buyer_required_date":     data["buyer_required_date"],
        "damage_pct":              float(data.get("damage_pct", 0.0)),
        "shipment_days":           int(data.get("shipment_days", 18)),
        "monthly_capacity":        monthly_cap,   # from DB
    }

    with current_app.test_client() as client:
        resp = client.post(
            "/api/component2/predict",
            json=c2_payload,
            headers={"Content-Type": "application/json"},
        )
        c2_result = resp.get_json()

    # If the prediction failed it comes back as {"error": "..."} — persist NULL
    # (not the error object), so the order shows a clean "AI unavailable" state
    # instead of an empty plant menu / blank timeline downstream.
    c2_ok = bool(c2_result) and "error" not in c2_result
    if not c2_ok:
        current_app.logger.warning(
            "Component 2 prediction failed for style %s: %s",
            data.get("style_number"), (c2_result or {}).get("error"),
        )
    c2_result_json = json.dumps(c2_result) if c2_ok else None

    # Save to DB
    db.execute(
        """INSERT INTO bulk_orders
           (sample_order_id, style_number, buyer_id, bulk_order_quantity,
            daily_commitment, style_priority, design_width, design_length,
            color_count, stitch_count, approved_date, buyer_required_date,
            damage_pct, shipment_days, status, c2_result_json, style_pdf_path, notes)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            data.get("sample_order_id"),
            data["style_number"],
            g.user_id,
            int(data["bulk_order_quantity"]),
            daily_commitment,
            data["style_priority"],
            float(data["design_width"]),
            float(data["design_length"]),
            int(data["color_count"]),
            int(data["stitch_count"]),
            data["bulk_order_approved_date"],
            data["buyer_required_date"],
            float(data.get("damage_pct", 0.0)),
            int(data.get("shipment_days", 18)),
            "Pending",
            c2_result_json,
            style_pdf_path,
            data.get("notes"),
        ),
    )
    db.commit()
    order_id = db.execute(
        "SELECT id FROM bulk_orders WHERE buyer_id=? ORDER BY created_at DESC LIMIT 1",
        (g.user_id,),
    ).fetchone()["id"]

    # Notify admin
    admin = _get_admin()
    user  = db.execute("SELECT full_name, email FROM users WHERE id=?", (g.user_id,)).fetchone()
    if admin:
        send_new_bulk_order_to_admin(
            admin["email"], buyer_name, user["email"], data["style_number"],
            order_id, int(data["bulk_order_quantity"]),
        )
        create_notification(
            admin["id"],
            f"New Bulk Order — {data['style_number']}",
            f"{buyer_name} submitted bulk order #{order_id} (Qty: {int(data['bulk_order_quantity']):,}).",
            notif_type="info", related_order_type="bulk_order", related_order_id=order_id,
        )

    return jsonify({
        "message":   "Bulk order submitted",
        "order_id":  order_id,
        "status":    "Pending",
        "c2_result": c2_result,
    }), 201


@buyer_bp.route("/orders/bulk", methods=["GET"])
@require_role("Buyer")
def list_bulk_orders():
    """Buyer's own bulk orders."""
    db = get_db()
    orders = db.execute(
        """SELECT bo.id, bo.style_number, bo.bulk_order_quantity, bo.style_priority,
                  bo.approved_date, bo.buyer_required_date, bo.status,
                  bo.customer_response, bo.customer_message, bo.extension_days_requested,
                  bo.timeline_email_sent_at, bo.assigned_at,
                  bo.plant_approved_at, bo.ready_at, bo.shipped_at, bo.created_at,
                  bo.style_pdf_path, bo.production_stage, bo.notes
           FROM bulk_orders bo
           WHERE bo.buyer_id = ?
           ORDER BY bo.created_at DESC""",
        (g.user_id,),
    ).fetchall()
    return jsonify([dict(o) for o in orders]), 200


@buyer_bp.route("/orders/bulk/<int:order_id>/pdf", methods=["GET"])
@require_role("Buyer")
def get_bulk_order_pdf(order_id):
    """Stream the buyer's own uploaded style PDF for a bulk order, if any."""
    db = get_db()
    order = db.execute(
        "SELECT style_pdf_path, style_number FROM bulk_orders WHERE id=? AND buyer_id=?",
        (order_id, g.user_id),
    ).fetchone()
    if not order:
        return jsonify({"error": "Order not found"}), 404
    if not order["style_pdf_path"]:
        return jsonify({"error": "No style PDF uploaded for this order"}), 404
    from services.upload_service import resolve_upload_path
    abs_path = resolve_upload_path(order["style_pdf_path"])
    if not abs_path:
        abort(404)
    return send_file(abs_path, mimetype="application/pdf", as_attachment=False,
                     download_name=f"{order['style_number']}_style.pdf")


@buyer_bp.route("/orders/bulk/<int:order_id>", methods=["GET"])
@require_role("Buyer")
def get_bulk_order(order_id):
    """Single bulk order detail with C2 result and current status."""
    db = get_db()
    order = db.execute(
        "SELECT * FROM bulk_orders WHERE id=? AND buyer_id=?",
        (order_id, g.user_id),
    ).fetchone()
    if not order:
        return jsonify({"error": "Order not found"}), 404
    row = dict(order)
    if row.get("c2_result_json"):
        row["c2_result"] = json.loads(row["c2_result_json"])
        del row["c2_result_json"]
    # Attach plant allocations
    allocs = db.execute(
        "SELECT opa.*, p.name AS plant_name FROM order_plant_allocations opa JOIN plants p ON opa.plant_id=p.id WHERE opa.bulk_order_id=?",
        (order_id,),
    ).fetchall()
    row["allocations"] = [dict(a) for a in allocs]
    return jsonify(row), 200


@buyer_bp.route("/orders/bulk/<int:order_id>", methods=["PUT"])
@require_role("Buyer")
def update_bulk_order(order_id):
    """
    Edit a Pending bulk order (buyer's own). Only Pending orders are editable.
    Editable: bulk_order_quantity, style_priority, buyer_required_date.
    Re-runs C2 so the allocation recommendation stays accurate.
    """
    db = get_db()
    order = db.execute(
        "SELECT * FROM bulk_orders WHERE id=? AND buyer_id=?", (order_id, g.user_id)
    ).fetchone()
    if not order:
        return jsonify({"error": "Order not found"}), 404
    if order["status"] != "Pending":
        return jsonify({"error": "Only pending orders can be edited."}), 400

    data = request.get_json(force=True, silent=True) or {}
    qty      = order["bulk_order_quantity"]
    priority = order["style_priority"]
    req_date = order["buyer_required_date"]
    notes    = data["notes"] if "notes" in data else order["notes"]

    if "bulk_order_quantity" in data:
        try:
            qty = int(data["bulk_order_quantity"])
        except (TypeError, ValueError):
            return jsonify({"error": "Quantity must be a whole number."}), 400
        if qty <= 0:
            return jsonify({"error": "Quantity must be greater than zero."}), 400
    if "style_priority" in data:
        if data["style_priority"] not in ("High", "Normal", "Low", "No Urgency"):
            return jsonify({"error": "Invalid priority."}), 400
        priority = data["style_priority"]
    if "buyer_required_date" in data and data["buyer_required_date"]:
        try:
            d = datetime.strptime(str(data["buyer_required_date"]), "%Y-%m-%d").date()
        except (TypeError, ValueError):
            return jsonify({"error": "Required date must be a valid date (YYYY-MM-DD)."}), 400
        if d < date.today():
            return jsonify({"error": "Required date cannot be in the past."}), 400
        req_date = data["buyer_required_date"]

    # Re-run C2 with the updated values and the order's stored specs.
    user_org = db.execute(
        "SELECT o.name FROM users u JOIN organizations o ON u.org_id=o.id WHERE u.id=?",
        (g.user_id,),
    ).fetchone()
    from components.component2 import KNOWN_BUYERS
    c2_model_buyer = user_org["name"] if user_org and user_org["name"] in KNOWN_BUYERS else KNOWN_BUYERS[0]
    month_year  = str(order["approved_date"])[:7]
    monthly_cap = get_all_plants_monthly_capacity(month_year)
    sample_plant = max(monthly_cap, key=monthly_cap.get)

    c2_payload = {
        "buyer_name": c2_model_buyer, "style_id": order["style_number"],
        "bulk_order_quantity": qty, "daily_commitment": order["daily_commitment"],
        "style_priority": priority,
        "design_width": float(order["design_width"] or 0), "design_length": float(order["design_length"] or 0),
        "color_count": int(order["color_count"] or 0), "stitch_count": int(order["stitch_count"] or 0),
        "sample_plant": sample_plant, "sp_cap_util_pct": 85.0,
        "bulk_order_approved_date": order["approved_date"], "buyer_required_date": req_date,
        "damage_pct": float(order["damage_pct"] or 0.0), "shipment_days": int(order["shipment_days"] or 18),
        "monthly_capacity": monthly_cap,
    }
    with current_app.test_client() as client:
        resp = client.post("/api/component2/predict", json=c2_payload,
                           headers={"Content-Type": "application/json"})
        c2_result = resp.get_json()

    db.execute(
        """UPDATE bulk_orders
           SET bulk_order_quantity=?, style_priority=?, buyer_required_date=?, notes=?, c2_result_json=?
           WHERE id=? AND buyer_id=?""",
        (qty, priority, req_date, notes, json.dumps(c2_result), order_id, g.user_id),
    )
    db.commit()
    return jsonify({"message": "Bulk order updated", "order_id": order_id}), 200


@buyer_bp.route("/orders/bulk/<int:order_id>", methods=["DELETE"])
@require_role("Buyer")
def delete_bulk_order(order_id):
    """Delete a Pending bulk order (buyer's own). Processing+ orders can't be deleted."""
    db = get_db()
    order = db.execute(
        "SELECT status FROM bulk_orders WHERE id=? AND buyer_id=?", (order_id, g.user_id)
    ).fetchone()
    if not order:
        return jsonify({"error": "Order not found"}), 404
    if order["status"] != "Pending":
        return jsonify({"error": "Only pending orders can be deleted."}), 400

    db.execute("DELETE FROM bulk_orders WHERE id=? AND buyer_id=?", (order_id, g.user_id))
    db.commit()
    return jsonify({"message": "Bulk order deleted"}), 200


@buyer_bp.route("/orders/bulk/<int:order_id>/respond", methods=["POST"])
@require_role("Buyer")
def respond_to_timeline(order_id):
    """
    Buyer replies (in-app) to the completion-timeline message. This is how the
    customer's reply gets back into the system.
    Body: {
      response: 'Approved' | 'Rejected',
      extension_days: int (optional, when requesting more time),
      message: str (optional free-text reply)
    }
    Approved  -> customer_response='Approved', still CustomerPending (admin then assigns a plant).
    Rejected  -> customer_response='Rejected', status='Hold', with the requested extension/message.
    """
    data = request.get_json(force=True, silent=True) or {}
    response = data.get("response")
    if response not in ("Approved", "Rejected"):
        return jsonify({"error": "response must be 'Approved' or 'Rejected'"}), 400

    db = get_db()
    order = db.execute(
        "SELECT * FROM bulk_orders WHERE id=? AND buyer_id=?", (order_id, g.user_id)
    ).fetchone()
    if not order:
        return jsonify({"error": "Order not found"}), 404
    if order["status"] != "CustomerPending":
        return jsonify({"error": "This order is not awaiting your response."}), 400

    ext_days = None
    if response == "Rejected" and data.get("extension_days") not in (None, ""):
        try:
            ext_days = int(data["extension_days"])
        except (TypeError, ValueError):
            return jsonify({"error": "Requested days must be a whole number."}), 400

    message   = (data.get("message") or "").strip() or None
    new_status = "CustomerPending" if response == "Approved" else "Hold"

    db.execute(
        """UPDATE bulk_orders
           SET customer_response=?, status=?, customer_message=?,
               extension_days_requested=?, customer_responded_at=?
           WHERE id=? AND buyer_id=?""",
        (response, new_status, message, ext_days, datetime.utcnow(), order_id, g.user_id),
    )
    db.commit()

    # Notify the admin that the customer replied.
    admin = _get_admin()
    if admin:
        if response == "Approved":
            body = f"The buyer approved the timeline for bulk order #{order_id}. You can now assign a plant."
        else:
            extra = f" and requested +{ext_days} day(s)" if ext_days else ""
            body = f"The buyer declined the timeline for bulk order #{order_id}{extra}." + (f" Message: {message}" if message else "")
        create_notification(
            admin["id"], f"Customer Reply — Bulk Order #{order_id}", body,
            notif_type="info", related_order_type="bulk_order", related_order_id=order_id,
        )
    return jsonify({"message": "Response recorded", "status": new_status}), 200


# ── Notifications ─────────────────────────────────────────────────────────

@buyer_bp.route("/notifications", methods=["GET"])
@require_role("Buyer")
def get_notifications():
    """Buyer notification inbox."""
    db = get_db()
    notifs = db.execute(
        "SELECT * FROM notifications WHERE user_id=? ORDER BY created_at DESC LIMIT 50",
        (g.user_id,),
    ).fetchall()
    return jsonify([dict(n) for n in notifs]), 200


@buyer_bp.route("/notifications/<int:notif_id>/read", methods=["POST"])
@require_role("Buyer")
def mark_notification_read(notif_id):
    db = get_db()
    db.execute(
        "UPDATE notifications SET is_read=1 WHERE id=? AND user_id=?",
        (notif_id, g.user_id),
    )
    db.commit()
    return jsonify({"message": "Marked as read"}), 200


# ── Style submissions (buyer proposes a new style for approval) ─────────────

@buyer_bp.route("/styles", methods=["POST"])
@require_role("Buyer")
def submit_style():
    """
    Buyer submits a new style for admin/plant approval.
    Multipart/form-data. A style PDF is MANDATORY.
    Required: style_number, design_width, design_length, color_count, stitch_count, style_pdf
    Optional: style_name, description, complexity, garment_type
    The style is stored with status 'Pending' until reviewed.
    """
    if not (request.content_type or "").startswith("multipart/form-data"):
        return jsonify({"error": "Style submissions must be multipart/form-data with a PDF."}), 400

    data = request.form.to_dict()
    pdf_file = request.files.get("style_pdf")
    if not pdf_file or not pdf_file.filename:
        return jsonify({"error": "A style PDF is required."}), 400

    required = ["style_number", "design_width", "design_length", "color_count", "stitch_count"]
    missing  = [f for f in required if not (data.get(f) or "").strip()]
    if missing:
        return jsonify({"error": f"Missing required fields: {missing}"}), 400

    complexity = data.get("complexity") or None
    if complexity and complexity not in ("Low", "Medium", "High", "Hard"):
        return jsonify({"error": "complexity must be one of: Low, Medium, High, Hard"}), 400

    style_number = data["style_number"].strip().upper()
    db = get_db()
    if db.execute("SELECT 1 FROM styles WHERE style_number=?", (style_number,)).fetchone():
        return jsonify({"error": f"Style '{style_number}' already exists."}), 409

    # Validate numeric specs.
    try:
        design_width  = float(data["design_width"])
        design_length = float(data["design_length"])
        color_count   = int(data["color_count"])
        stitch_count  = int(data["stitch_count"])
    except (TypeError, ValueError):
        return jsonify({"error": "Design width/length must be numbers and colours/stitches whole numbers."}), 400

    # Persist the mandatory PDF (reuses the style-PDF storage + validation).
    try:
        style_pdf_path = _save_style_pdf(pdf_file)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400

    db.execute(
        """INSERT INTO styles
           (style_number, style_name, description, design_width, design_length,
            color_count, stitch_count, complexity, garment_type, added_by,
            status, style_pdf_path)
           VALUES (?,?,?,?,?,?,?,?,?,?, 'Pending', ?)""",
        (style_number, data.get("style_name"), data.get("description"),
         design_width, design_length, color_count, stitch_count,
         complexity, data.get("garment_type"), g.user_id, style_pdf_path),
    )
    db.commit()

    # Notify admin(s) to review.
    admin = _get_admin()
    if admin:
        create_notification(
            admin["id"],
            f"New Style Submission — {style_number}",
            f"A buyer submitted style {style_number} for review.",
            notif_type="info",
        )
    return jsonify({"message": "Style submitted for approval", "style_number": style_number, "status": "Pending"}), 201


@buyer_bp.route("/styles", methods=["GET"])
@require_role("Buyer")
def list_my_styles():
    """The buyer's own submitted styles (any status)."""
    db = get_db()
    rows = db.execute(
        """SELECT style_number, style_name, garment_type, design_width, design_length,
                  color_count, stitch_count, complexity, description, status,
                  reject_reason, style_pdf_path, created_at
           FROM styles WHERE added_by=? ORDER BY created_at DESC""",
        (g.user_id,),
    ).fetchall()
    return jsonify([dict(r) for r in rows]), 200


@buyer_bp.route("/styles/<style_number>/pdf", methods=["GET"])
@require_role("Buyer")
def get_my_style_pdf(style_number):
    """Stream the PDF the buyer attached to their own style submission."""
    from services.upload_service import resolve_upload_path
    db = get_db()
    style = db.execute(
        "SELECT style_pdf_path FROM styles WHERE style_number=? AND added_by=?",
        (style_number, g.user_id),
    ).fetchone()
    if not style or not style["style_pdf_path"]:
        return jsonify({"error": "No PDF for this style"}), 404
    abs_path = resolve_upload_path(style["style_pdf_path"])
    if not abs_path:
        abort(404)
    return send_file(abs_path, mimetype="application/pdf", as_attachment=False,
                     download_name=f"{style_number}_style.pdf")
