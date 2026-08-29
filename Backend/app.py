"""
app.py — Garment Production Management System
==============================================
Flask application factory.
Registers all blueprints:
  /api/component1  — Sample Planning (ML)
  /api/component2  — Bulk Order Planning (ML)
  /api/component3  — Emergency Detection (ML)
  /api/component4  — Production Analysis (ML)
  /auth            — Authentication
  /admin           — Admin Portal
  /buyer           — Buyer Portal
  /plant           — Plant Manager Portal
"""

import os
from dotenv import load_dotenv
load_dotenv()   # Load .env before anything else

from flask import Flask, jsonify
from flask_cors import CORS

# ── ML Component blueprints (existing) ────────────────────────────────────
from components.component1 import component1_bp
from components.component2 import component2_bp
from components.component3 import component3_bp
from components.component4 import component4_bp

# ── New portal blueprints ──────────────────────────────────────────────────
from routes.auth   import auth_bp
from routes.admin  import admin_bp
from routes.buyer  import buyer_bp
from routes.plant  import plant_bp
from routes.styles import styles_bp
from routes.public import public_bp
from routes.analytics import analytics_bp
from routes.subplant import subplant_bp

# ── Database ──────────────────────────────────────────────────────────────
from database.db import register_db


def _start_inbound_email_poller():
    """
    Start a daemon thread that periodically reads customer email replies via IMAP.
    Controlled by INBOUND_POLL_SECONDS (0 disables) and only runs when IMAP is
    configured. Guarded so the dev reloader's parent process doesn't also poll.
    """
    import threading
    from services.inbound_email_service import is_configured, poll_inbox

    interval = int(os.environ.get("INBOUND_POLL_SECONDS", 120))
    if interval <= 0 or not is_configured():
        return
    # With the Werkzeug reloader active, only the child process runs the loop.
    if os.environ.get("FLASK_DEBUG") and os.environ.get("WERKZEUG_RUN_MAIN") != "true":
        return

    def _loop():
        import time
        while True:
            try:
                result = poll_inbox()
                if result.get("applied"):
                    print(f"[inbound] applied {result['applied']} email reply(ies) to orders")
            except Exception as exc:
                print(f"[inbound] poll error: {exc}")
            time.sleep(interval)

    t = threading.Thread(target=_loop, daemon=True)
    t.start()
    print(f"[inbound] IMAP reply poller started (every {interval}s)")


def create_app() -> Flask:
    app = Flask(__name__)
    CORS(app)  # Enable CORS for all routes
    app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "change-me")

    # ── Register ML component APIs ─────────────────────────────────────────
    app.register_blueprint(component1_bp, url_prefix="/api/component1")
    app.register_blueprint(component2_bp, url_prefix="/api/component2")
    app.register_blueprint(component3_bp, url_prefix="/api/component3")
    app.register_blueprint(component4_bp, url_prefix="/api/component4")

    # ── Register portal APIs ───────────────────────────────────────────────
    app.register_blueprint(auth_bp,   url_prefix="/auth")
    app.register_blueprint(admin_bp,  url_prefix="/admin")
    app.register_blueprint(analytics_bp, url_prefix="/analytics")
    app.register_blueprint(subplant_bp, url_prefix="/subplant")
    app.register_blueprint(buyer_bp,  url_prefix="/buyer")
    app.register_blueprint(plant_bp,  url_prefix="/plant")
    app.register_blueprint(styles_bp, url_prefix="/styles")
    app.register_blueprint(public_bp, url_prefix="/public")

    # ── Initialise database (creates tables if not exist) ─────────────────
    register_db(app)

    # ── Background IMAP poller for customer email replies ─────────────────
    _start_inbound_email_poller()

    # ── Health check ──────────────────────────────────────────────────────
    @app.route("/health", methods=["GET"])
    def health():
        return jsonify({"status": "ok", "service": "Garment Production Management API"})

    # ── Root index ────────────────────────────────────────────────────────
    @app.route("/", methods=["GET"])
    def index():
        return jsonify({
            "service": "Garment Production Management API",
            "version": "2.0.0",
            "endpoints": {
                "auth":       {"register": "POST /auth/register", "login": "POST /auth/login"},
                "admin":      {
                    "users":    "GET /admin/users/pending",
                    "approve":  "POST /admin/users/<id>/approve",
                    "orders":   "GET /admin/orders/sample | /admin/orders/bulk",
                    "assign":   "POST /admin/orders/sample/<id>/assign",
                    "capacity": "GET /admin/capacity",
                    "analysis": "GET /admin/orders/bulk/<id>/analysis",
                },
                "buyer":      {
                    "sample":   "POST /buyer/orders/sample",
                    "bulk":     "POST /buyer/orders/bulk",
                    "status":   "GET /buyer/orders/sample | /buyer/orders/bulk",
                },
                "plant":      {
                    "orders":   "GET /plant/orders",
                    "log":      "POST /plant/orders/<id>/log",
                    "ready":    "POST /plant/orders/<id>/ready",
                },
                "ml":         {
                    "component1": "POST /api/component1/predict",
                    "component2": "POST /api/component2/predict",
                    "component3": "POST /api/component3/predict",
                    "component4": "POST /api/component4/predict",
                },
            },
        })

    # ── Global error handlers ──────────────────────────────────────────────
    @app.errorhandler(404)
    def not_found(e):
        return jsonify({"error": "Endpoint not found", "status": 404}), 404

    @app.errorhandler(405)
    def method_not_allowed(e):
        return jsonify({"error": "Method not allowed", "status": 405}), 405

    @app.errorhandler(500)
    def internal_error(e):
        return jsonify({"error": "Internal server error", "status": 500}), 500

    return app


app = create_app()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
