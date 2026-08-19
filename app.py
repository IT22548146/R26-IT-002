from flask import Flask, jsonify
from flask_cors import CORS
from models.z.component1 import component1_bp
from models.z.component2 import component2_bp
from components.component3 import component3_bp
from models.z.component4 import component4_bp

"""
Garment Production Management System — Flask API
=================================================
4 Blueprints, one server:
  /api/component1  — Sample Planning System
  /api/component2  — Bulk Order Planning & Capacity Allocation
  /api/component3  — Emergency Situation Detection
  /api/component4  — Production Analysis & Resource Optimization
"""


app = Flask(__name__)
CORS(app) # Enable CORS for all routes and origins

# ── Register blueprints ────────────────────────────────────────────
app.register_blueprint(component1_bp, url_prefix="/api/component1")
app.register_blueprint(component2_bp, url_prefix="/api/component2")
app.register_blueprint(component3_bp, url_prefix="/api/component3")
app.register_blueprint(component4_bp, url_prefix="/api/component4")


# ── Health check ──────────────────────────────────────────────────
@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok", "service": "Garment Production Management API"})


# ── Root index ────────────────────────────────────────────────────
@app.route("/", methods=["GET"])
def index():
    return jsonify({
        "service": "Garment Production Management API",
        "version": "1.0.0",
        "endpoints": {
            "component1": {
                "predict": "POST /api/component1/predict",
                "health":  "GET  /api/component1/health",
            },
            "component2": {
                "predict": "POST /api/component2/predict",
                "health":  "GET  /api/component2/health",
            },
            "component3": {
                "predict": "POST /api/component3/predict",
                "health":  "GET  /api/component3/health",
                "create_incident": "POST /api/component3/incidents",
                "incident_history": "GET /api/component3/incidents",
                "incident_detail": "GET /api/component3/incidents/{incident_id}",
                "save_daily_monitoring": "POST /api/component3/monitoring-records",
                "daily_monitoring_history": "GET /api/component3/monitoring-records",
                "verify_daily_outcome": "PUT /api/component3/monitoring-records/{record_id}/verification",
                "early_warning_readiness": "GET /api/component3/monitoring-readiness",
            },
            "component4": {
                "predict": "POST /api/component4/predict",
                "health":  "GET  /api/component4/health",
            },
        },
    })


# ── Global error handlers ─────────────────────────────────────────
@app.errorhandler(404)
def not_found(e):
    return jsonify({"error": "Endpoint not found", "status": 404}), 404


@app.errorhandler(405)
def method_not_allowed(e):
    return jsonify({"error": "Method not allowed", "status": 405}), 405


@app.errorhandler(500)
def internal_error(e):
    return jsonify({"error": "Internal server error", "status": 500}), 500


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5001, debug=True)
