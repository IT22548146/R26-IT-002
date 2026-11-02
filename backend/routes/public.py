"""
routes/public.py
Public (no-auth) endpoints for the marketing site:
  - Contact Us form submission → contact_messages inbox + admin email/notification
  - Company info for the public pages
"""

import os
from flask import Blueprint, request, jsonify
from database.db import get_db
from services.email_service import send_email, _wrap_html
from services.notification_service import create_notification

public_bp = Blueprint("public", __name__)

MOTHER_COMPANY_NAME = os.environ.get("MOTHER_COMPANY_NAME", "FabricFlow International")
ADMIN_EMAIL         = os.environ.get("ADMIN_EMAIL", "admin@fabricflow.com")


def _get_admin():
    db = get_db()
    return db.execute("SELECT id, email FROM users WHERE role='Admin' LIMIT 1").fetchone()


@public_bp.route("/company", methods=["GET"])
def company_info():
    """Basic mother-company info for the public site (name shown on login/nav)."""
    return jsonify({"name": MOTHER_COMPANY_NAME}), 200


@public_bp.route("/contact", methods=["POST"])
def submit_contact():
    """
    Public Contact Us form.
    Required: name, email, message. Optional: subject.
    Stores the message for the admin inbox and notifies the admin.
    """
    data = request.get_json(force=True, silent=True) or {}
    name    = (data.get("name") or "").strip()
    email   = (data.get("email") or "").strip()
    subject = (data.get("subject") or "").strip()
    message = (data.get("message") or "").strip()

    missing = [f for f, v in (("name", name), ("email", email), ("message", message)) if not v]
    if missing:
        return jsonify({"error": f"Missing fields: {missing}"}), 400
    if len(message) > 5000:
        return jsonify({"error": "Message is too long (max 5000 characters)."}), 400

    db = get_db()
    db.execute(
        "INSERT INTO contact_messages (name, email, subject, message) VALUES (?,?,?,?)",
        (name, email, subject or None, message),
    )
    db.commit()

    # Notify the admin (in-app + email). Email is best-effort and non-blocking.
    admin = _get_admin()
    if admin:
        create_notification(
            admin["id"],
            f"New Contact Message — {subject or 'No subject'}",
            f"{name} ({email}) sent a message via the Contact Us form.",
            notif_type="info",
        )
        body = _wrap_html(
            "New Contact Message",
            f"<p><strong>From:</strong> {name} &lt;{email}&gt;</p>"
            f"<p><strong>Subject:</strong> {subject or '(none)'}</p>"
            f"<p><strong>Message:</strong></p><p>{message}</p>",
        )
        send_email(admin["email"] or ADMIN_EMAIL, f"[Contact Us] {subject or 'New message'}", body)

    return jsonify({"message": "Thanks for reaching out — we'll get back to you soon."}), 201
