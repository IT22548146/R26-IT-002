"""
routes/auth.py
Authentication endpoints: register, login, /me
"""

import os
from flask import Blueprint, request, jsonify, g, send_file, abort
from database.db import get_db
from middleware.auth_middleware import (
    hash_password, verify_password, generate_token, require_auth
)
from services.email_service import send_buyer_registered, send_buyer_registration_received
from services.notification_service import create_notification
from services.upload_service import save_upload, resolve_upload_path

auth_bp = Blueprint("auth", __name__)

ADMIN_EMAIL = os.environ.get("ADMIN_EMAIL", "admin@fabricflow.com")

_PROFILE_PIC_EXTS  = {".png", ".jpg", ".jpeg", ".webp"}
_PROFILE_PIC_BYTES = 5 * 1024 * 1024   # 5 MB


@auth_bp.route("/register", methods=["POST"])
def register():
    """
    Public — Buyer company registers.
    Required: company_name, full_name, email, password
    """
    # Accept JSON or multipart/form-data (the latter carries the optional profile pic).
    pic_file = None
    if request.content_type and request.content_type.startswith("multipart/form-data"):
        data = request.form.to_dict()
        pic_file = request.files.get("profile_pic")
    else:
        data = request.get_json(force=True, silent=True) or {}

    required = ["company_name", "full_name", "email", "password",
                "contact_no", "country", "address"]
    missing  = [f for f in required if not (data.get(f) or "").strip()]
    if missing:
        return jsonify({"error": f"Missing fields: {missing}"}), 400

    company_name = data["company_name"].strip()
    full_name    = data["full_name"].strip()
    email        = data["email"].strip().lower()
    password     = data["password"]
    contact_no   = data["contact_no"].strip()
    country      = data["country"].strip()
    address      = data["address"].strip()

    if len(password) < 8:
        return jsonify({"error": "Password must be at least 8 characters"}), 400

    db = get_db()

    # Check email not already taken
    if db.execute("SELECT id FROM users WHERE email = ?", (email,)).fetchone():
        return jsonify({"error": "An account with this email already exists"}), 409

    # Persist the optional profile picture (validated) before inserting.
    try:
        profile_pic_path = save_upload(
            pic_file, "profile_pics", _PROFILE_PIC_EXTS, _PROFILE_PIC_BYTES, owner_id=email.split("@")[0]
        )
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400

    # Create or get org
    org = db.execute(
        "SELECT id FROM organizations WHERE name = ? AND type = 'Buyer'", (company_name,)
    ).fetchone()
    if org is None:
        db.execute(
            "INSERT INTO organizations(name, type, contact_email) VALUES (?,?,?)",
            (company_name, "Buyer", email),
        )
        db.commit()
        org_id = db.execute(
            "SELECT id FROM organizations WHERE name = ?", (company_name,)
        ).fetchone()["id"]
    else:
        org_id = org["id"]

    # Create user (Pending until Admin approves)
    db.execute(
        """INSERT INTO users(org_id, full_name, email, password_hash, role, status,
                             contact_no, country, address, profile_pic_path)
           VALUES (?,?,?,?,?,?,?,?,?,?)""",
        (org_id, full_name, email, hash_password(password), "Buyer", "Pending",
         contact_no, country, address, profile_pic_path),
    )
    db.commit()
    new_user_id = db.execute("SELECT id FROM users WHERE email = ?", (email,)).fetchone()["id"]

    # Notify admin
    admin = db.execute("SELECT id, email FROM users WHERE role = 'Admin' LIMIT 1").fetchone()
    if admin:
        send_buyer_registered(admin["email"], company_name)
        create_notification(
            admin["id"],
            f"New Buyer Registration — {company_name}",
            f"{full_name} from {company_name} has registered and is awaiting approval.",
            notif_type="info",
        )

    # Notify buyer
    send_buyer_registration_received(email, company_name)

    return jsonify({
        "message": "Registration successful. Your account is pending admin approval.",
        "user_id": new_user_id,
    }), 201


@auth_bp.route("/login", methods=["POST"])
def login():
    """
    All roles — login with email and password.
    Returns a JWT token valid for JWT_EXPIRY_HOURS.
    """
    data = request.get_json(force=True, silent=True) or {}
    email    = (data.get("email") or "").strip().lower()
    password = data.get("password") or ""

    if not email or not password:
        return jsonify({"error": "email and password are required"}), 400

    db   = get_db()
    user = db.execute(
        "SELECT id, password_hash, role, status, plant_id, full_name FROM users WHERE email = ?",
        (email,),
    ).fetchone()

    if user is None or not verify_password(password, user["password_hash"]):
        return jsonify({"error": "Invalid email or password"}), 401

    if user["status"] == "Pending":
        return jsonify({"error": "Your account is pending admin approval"}), 403
    if user["status"] == "Rejected":
        return jsonify({"error": "Your account registration was not approved"}), 403

    token = generate_token(user["id"], user["role"], user["plant_id"])

    return jsonify({
        "token":    token,
        "user_id":  user["id"],
        "role":     user["role"],
        "name":     user["full_name"],
        "plant_id": user["plant_id"],
    }), 200


@auth_bp.route("/me", methods=["GET"])
@require_auth
def me():
    """Returns current user profile."""
    db   = get_db()
    user = db.execute(
        """SELECT u.id, u.full_name, u.email, u.role, u.status, u.plant_id,
                  u.contact_no, u.country, u.address, u.profile_pic_path,
                  o.name AS org_name, o.type AS org_type
           FROM users u JOIN organizations o ON u.org_id = o.id
           WHERE u.id = ?""",
        (g.user_id,),
    ).fetchone()
    if not user:
        return jsonify({"error": "User not found"}), 404
    return jsonify(dict(user)), 200


@auth_bp.route("/profile", methods=["PUT"])
@require_auth
def update_profile():
    """
    Update the current user's editable profile fields.
    Accepts JSON or multipart/form-data (the latter can carry a new profile pic).
    Editable: full_name, contact_no, country, address, profile_pic.
    Email, role, and company are not editable here.
    """
    pic_file = None
    if request.content_type and request.content_type.startswith("multipart/form-data"):
        data = request.form.to_dict()
        pic_file = request.files.get("profile_pic")
    else:
        data = request.get_json(force=True, silent=True) or {}

    db = get_db()

    fields, values = [], []
    for key in ("full_name", "contact_no", "country", "address"):
        if key in data:
            val = (data.get(key) or "").strip()
            if key == "full_name" and not val:
                return jsonify({"error": "Full name cannot be empty."}), 400
            fields.append(f"{key} = ?")
            values.append(val)

    if pic_file and pic_file.filename:
        try:
            path = save_upload(pic_file, "profile_pics", _PROFILE_PIC_EXTS,
                               _PROFILE_PIC_BYTES, owner_id=str(g.user_id))
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400
        fields.append("profile_pic_path = ?")
        values.append(path)

    if not fields:
        return jsonify({"error": "No fields to update."}), 400

    values.append(g.user_id)
    db.execute(f"UPDATE users SET {', '.join(fields)} WHERE id = ?", values)
    db.commit()
    return jsonify({"message": "Profile updated"}), 200


@auth_bp.route("/profile/photo", methods=["GET"])
@require_auth
def get_profile_photo():
    """Stream the current user's profile picture, if any."""
    db = get_db()
    row = db.execute("SELECT profile_pic_path FROM users WHERE id = ?", (g.user_id,)).fetchone()
    if not row or not row["profile_pic_path"]:
        return jsonify({"error": "No profile picture"}), 404
    abs_path = resolve_upload_path(row["profile_pic_path"])
    if not abs_path:
        abort(404)
    return send_file(abs_path)
