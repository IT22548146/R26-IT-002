"""
routes/styles.py
Style Catalog — Admin and Plant Managers can add/edit styles.
Buyers can look up a style by style_number to auto-fill bulk order fields.

Endpoints:
  GET    /styles                     → list all styles (any logged-in user)
  GET    /styles/<style_number>      → lookup by style number (any logged-in user)
  POST   /styles                     → add new style (Admin or PlantManager)
  PUT    /styles/<style_number>      → update style (Admin or PlantManager)
  DELETE /styles/<style_number>      → delete style (Admin only)
"""

import os
from datetime import datetime
from flask import Blueprint, request, jsonify, g, send_file, abort
from database.db import get_db
from middleware.auth_middleware import require_auth, require_role
from services.upload_service import resolve_upload_path
from services.notification_service import create_notification
from services.email_service import send_style_approved, send_style_rejected

styles_bp = Blueprint("styles", __name__)


@styles_bp.route("", methods=["GET"])
@require_auth
def list_styles():
    """
    List catalog styles. Only Approved styles are returned (this is what feeds
    the buyer's order autocomplete), so pending/rejected submissions never leak
    into the selectable catalog.
    """
    db = get_db()
    q = request.args.get("q", "").strip()   # optional search by style_number or name
    if q:
        rows = db.execute(
            """SELECT s.*, u.full_name AS added_by_name
               FROM styles s LEFT JOIN users u ON s.added_by = u.id
               WHERE s.status = 'Approved' AND (s.style_number LIKE ? OR s.style_name LIKE ?)
               ORDER BY s.style_number""",
            (f"%{q}%", f"%{q}%"),
        ).fetchall()
    else:
        rows = db.execute(
            """SELECT s.*, u.full_name AS added_by_name
               FROM styles s LEFT JOIN users u ON s.added_by = u.id
               WHERE s.status = 'Approved'
               ORDER BY s.style_number"""
        ).fetchall()
    return jsonify([dict(r) for r in rows]), 200


# ── Style submission review (Admin + PlantManager) ──────────────────────────

@styles_bp.route("/submissions", methods=["GET"])
@require_role("Admin", "PlantManager", "Manager")
def list_style_submissions():
    """Buyer-submitted styles awaiting review (Pending), newest first."""
    db = get_db()
    rows = db.execute(
        """SELECT s.*, u.full_name AS submitted_by_name, o.name AS company_name
           FROM styles s
           LEFT JOIN users u ON s.added_by = u.id
           LEFT JOIN organizations o ON u.org_id = o.id
           WHERE s.status = 'Pending'
           ORDER BY s.created_at DESC"""
    ).fetchall()
    return jsonify([dict(r) for r in rows]), 200


@styles_bp.route("/<style_number>/approve", methods=["POST"])
@require_role("Admin", "PlantManager", "Manager")
def approve_style(style_number):
    """Approve a pending style so it enters the selectable catalog. Emails the buyer."""
    db = get_db()
    style = db.execute("SELECT * FROM styles WHERE style_number=?", (style_number,)).fetchone()
    if not style:
        return jsonify({"error": "Style not found"}), 404
    if style["status"] != "Pending":
        return jsonify({"error": f"Style is not pending (status: {style['status']})"}), 400

    db.execute(
        "UPDATE styles SET status='Approved', reviewed_by=?, reviewed_at=?, reject_reason=NULL WHERE style_number=?",
        (g.user_id, datetime.utcnow().isoformat(), style_number),
    )
    db.commit()

    submitter = db.execute("SELECT id, email FROM users WHERE id=?", (style["added_by"],)).fetchone()
    if submitter:
        send_style_approved(submitter["email"], style_number)
        create_notification(
            submitter["id"],
            f"Style Approved — {style_number}",
            f"Your style {style_number} has been approved and is now available for orders.",
            notif_type="success",
        )
    return jsonify({"message": "Style approved", "style_number": style_number}), 200


@styles_bp.route("/<style_number>/reject", methods=["POST"])
@require_role("Admin", "PlantManager", "Manager")
def reject_style(style_number):
    """Reject a pending style with an optional reason. Emails the buyer."""
    data = request.get_json(force=True, silent=True) or {}
    reason = (data.get("reason") or "").strip() or None

    db = get_db()
    style = db.execute("SELECT * FROM styles WHERE style_number=?", (style_number,)).fetchone()
    if not style:
        return jsonify({"error": "Style not found"}), 404
    if style["status"] != "Pending":
        return jsonify({"error": f"Style is not pending (status: {style['status']})"}), 400

    db.execute(
        "UPDATE styles SET status='Rejected', reviewed_by=?, reviewed_at=?, reject_reason=? WHERE style_number=?",
        (g.user_id, datetime.utcnow().isoformat(), reason, style_number),
    )
    db.commit()

    submitter = db.execute("SELECT id, email FROM users WHERE id=?", (style["added_by"],)).fetchone()
    if submitter:
        send_style_rejected(submitter["email"], style_number, reason)
        create_notification(
            submitter["id"],
            f"Style Rejected — {style_number}",
            f"Your style {style_number} was not approved." + (f" Reason: {reason}" if reason else ""),
            notif_type="warning",
        )
    return jsonify({"message": "Style rejected", "style_number": style_number}), 200


@styles_bp.route("/<style_number>/pdf", methods=["GET"])
@require_role("Admin", "PlantManager", "Manager")
def download_style_pdf(style_number):
    """Reviewer downloads the PDF attached to a submitted style."""
    db = get_db()
    style = db.execute("SELECT style_pdf_path FROM styles WHERE style_number=?", (style_number,)).fetchone()
    if not style or not style["style_pdf_path"]:
        return jsonify({"error": "No PDF for this style"}), 404
    abs_path = resolve_upload_path(style["style_pdf_path"])
    if not abs_path:
        abort(404)
    return send_file(abs_path, mimetype="application/pdf", as_attachment=True,
                     download_name=f"{style_number}_style.pdf")


@styles_bp.route("/<style_number>", methods=["GET"])
@require_auth
def get_style(style_number):
    """
    Look up a single style by style_number.
    Used by buyers to auto-fill bulk order form fields.
    Returns all technical specs for Component 2.
    """
    db = get_db()
    row = db.execute(
        "SELECT * FROM styles WHERE style_number = ?", (style_number,)
    ).fetchone()
    if not row:
        return jsonify({"error": f"Style '{style_number}' not found in catalog"}), 404
    return jsonify(dict(row)), 200


@styles_bp.route("", methods=["POST"])
@require_role("Admin", "PlantManager", "Manager")
def add_style():
    """
    Add a new style to the catalog.
    Required: style_number, design_width, design_length, color_count, stitch_count
    Optional: style_name, description, complexity, garment_type
    """
    data = request.get_json(force=True, silent=True) or {}
    required = ["style_number", "design_width", "design_length", "color_count", "stitch_count"]
    missing  = [f for f in required if data.get(f) is None]
    if missing:
        return jsonify({"error": f"Missing required fields: {missing}"}), 400

    complexity = data.get("complexity")
    if complexity and complexity not in ("Low", "Medium", "High", "Hard"):
        return jsonify({"error": "complexity must be one of: Low, Medium, High, Hard"}), 400

    db = get_db()
    existing = db.execute(
        "SELECT id FROM styles WHERE style_number = ?", (data["style_number"],)
    ).fetchone()
    if existing:
        return jsonify({"error": f"Style '{data['style_number']}' already exists. Use PUT to update."}), 409

    db.execute(
        """INSERT INTO styles
           (style_number, style_name, description, design_width, design_length,
            color_count, stitch_count, complexity, garment_type, added_by)
           VALUES (?,?,?,?,?,?,?,?,?,?)""",
        (
            data["style_number"].strip().upper(),
            data.get("style_name"),
            data.get("description"),
            float(data["design_width"]),
            float(data["design_length"]),
            int(data["color_count"]),
            int(data["stitch_count"]),
            complexity,
            data.get("garment_type"),
            g.user_id,
        ),
    )
    db.commit()

    style = db.execute(
        "SELECT * FROM styles WHERE style_number = ?", (data["style_number"].strip().upper(),)
    ).fetchone()
    return jsonify({"message": "Style added", "style": dict(style)}), 201


@styles_bp.route("/<style_number>", methods=["PUT"])
@require_role("Admin", "PlantManager", "Manager")
def update_style(style_number):
    """
    Update an existing style's technical specs.
    Only the fields you include in the body will be updated.
    """
    db = get_db()
    style = db.execute(
        "SELECT * FROM styles WHERE style_number = ?", (style_number,)
    ).fetchone()
    if not style:
        return jsonify({"error": f"Style '{style_number}' not found"}), 404

    data = request.get_json(force=True, silent=True) or {}

    # Build update dynamically — only update provided fields
    updatable = ["style_name", "description", "design_width", "design_length",
                 "color_count", "stitch_count", "complexity", "garment_type"]

    updates = {}
    for field in updatable:
        if field in data:
            updates[field] = data[field]

    if not updates:
        return jsonify({"error": "No updatable fields provided"}), 400

    if "complexity" in updates and updates["complexity"] not in (None, "Low", "Medium", "High", "Hard"):
        return jsonify({"error": "complexity must be one of: Low, Medium, High, Hard"}), 400

    updates["updated_by"] = g.user_id
    updates["updated_at"] = datetime.utcnow().isoformat()

    set_clause = ", ".join([f"{k} = ?" for k in updates.keys()])
    values     = list(updates.values()) + [style_number]

    db.execute(f"UPDATE styles SET {set_clause} WHERE style_number = ?", values)
    db.commit()

    updated = db.execute("SELECT * FROM styles WHERE style_number = ?", (style_number,)).fetchone()
    return jsonify({"message": "Style updated", "style": dict(updated)}), 200


@styles_bp.route("/<style_number>", methods=["DELETE"])
@require_role("Admin", "Manager")
def delete_style(style_number):
    """Delete a style from the catalog. Admin only."""
    db = get_db()
    style = db.execute("SELECT id FROM styles WHERE style_number = ?", (style_number,)).fetchone()
    if not style:
        return jsonify({"error": f"Style '{style_number}' not found"}), 404

    db.execute("DELETE FROM styles WHERE style_number = ?", (style_number,))
    db.commit()
    return jsonify({"message": f"Style '{style_number}' deleted"}), 200
