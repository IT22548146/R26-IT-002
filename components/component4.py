"""
Component 4 — Production Analysis & Resource Optimization
===========================================================
Models loaded:
  c4_model_perf_score.pkl  — XGBRegressor   → Performance Score (1.0–5.0)
  c4_model_star_rating.pkl — GradientBoostingClassifier → Star Rating (1–5 stars)

OpenAI removed — response JSON assembled deterministically from model outputs
using the same business rules that were in the OpenAI system prompt.

POST /api/component4/predict
Request body (JSON):
{
    "plant_name":               "Dinusha Embroidery",
    "buyer_name":               "Tesco",
    "style_id":                 "KM740232",
    "order_quantity":           20000,
    "planned_completion_days":  30,
    "actual_completion_days":   32,
    "machine_count":            18,
    "active_machine_count":     16,
    "employee_count":           55,
    "daily_output_avg":         750.0,
    "total_workload":           28000,
    "urgent_style_flag":        "Yes",
    "urgent_handled_count":     3,
    "risk_count_from_component3": 4,
    "machine_breakdown_days":   2,
    "worker_shortage_days":     1,
    "damage_rate":              2.5
}
"""

import os
import joblib
import numpy as np
import pandas as pd
from flask import Blueprint, request, jsonify

component4_bp = Blueprint("component4", __name__)

# ── Paths ─────────────────────────────────────────────────────────
BASE_DIR   = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MODELS_DIR = os.path.join(BASE_DIR, "models")

# ── Static lookups ────────────────────────────────────────────────
PLANT_NAMES = sorted([
    "Amsral Lanka", "Bobbin Group", "Dinusha Embroidery",
    "MRC Group", "Regal Image", "Sunrose Lanka",
])
BUYER_NAMES = sorted(["George", "Hirdaramani", "M&S", "Tesco"])

PLANT_ENC_MAP = {p: i for i, p in enumerate(PLANT_NAMES)}
BUYER_ENC_MAP = {b: i for i, b in enumerate(BUYER_NAMES)}

DELAY_MAP = {"Delayed": 0, "On Time": 1, "Early": 2}

STAR_LABELS = {
    1: "⭐",
    2: "⭐⭐",
    3: "⭐⭐⭐",
    4: "⭐⭐⭐⭐",
    5: "⭐⭐⭐⭐⭐",
}

STAR_INTERPRETATIONS = {
    5: "Excellent — Always on-time",
    4: "Good — Minor delays",
    3: "Average performance",
    2: "Poor — Frequent delays",
    1: "Critical — Very poor performance",
}

ML_FEATURES = [
    "plant_enc", "buyer_enc",
    "order_quantity", "planned_completion_days", "actual_completion_days",
    "delay_days", "delay_status_enc", "delay_ratio", "overrun_days",
    "machine_count", "active_machine_count", "machine_utilization", "machine_idle_rate",
    "employee_count", "daily_output_avg", "efficiency_score",
    "total_workload", "urgent_flag_enc", "urgent_handled_count",
    "risk_count_from_component3", "risk_per_workload",
    "machine_breakdown_days", "worker_shortage_days", "breakdown_worker_days",
    "damage_rate",
]

# ── Lazy model loader ─────────────────────────────────────────────
_models = {}


def _load_models():
    if _models:
        return _models
    names = {
        "perf_score":  "c4_model1_perf_score.pkl",
        "star_rating": "c4_model2_star_rating.pkl",
    }
    missing = []
    for key, fname in names.items():
        path = os.path.join(MODELS_DIR, fname)
        if not os.path.exists(path):
            missing.append(fname)
        else:
            _models[key] = joblib.load(path)
    if missing:
        raise RuntimeError(f"Missing model files: {missing}. Run the Component 4 notebook first.")
    return _models


# ── Rule-based scoring ────────────────────────────────────────────

def _compute_perf_score(delay_days, machine_utilization, damage_rate,
                         risk_count, machine_breakdown_days,
                         worker_shortage_days, urgent_handled_count) -> float:
    score = (3.167
             - 0.0254  * delay_days
             + 1.833   * machine_utilization
             - 0.0465  * damage_rate
             - 0.0074  * risk_count
             - 0.0144  * machine_breakdown_days
             - 0.011   * worker_shortage_days
             + 0.0037  * urgent_handled_count)
    return float(np.clip(score, 1.0, 5.0).round(2))


def _score_to_star_int(s: float) -> int:
    if s >= 4.5: return 5
    elif s >= 4.0: return 4
    elif s >= 3.5: return 3
    elif s >= 3.0: return 2
    return 1


def _recommendation(score, urgent, risk_count, breakdown_days) -> str:
    if score >= 4.5:
        return "Maintain current resource allocation"
    elif urgent and score >= 4.0:
        return "Suitable for urgent style handling"
    elif breakdown_days >= 5:
        return "Increase machine maintenance support"
    elif risk_count >= 8:
        return "Reduce risk days and add supervisor monitoring"
    elif score >= 4.0:
        return "Increase daily output monitoring"
    elif score < 3.5:
        return "Critical: Immediate intervention required"
    return "Improve workforce allocation"


def _best_plant_label(score: float) -> str:
    if score >= 4.5:   return "Best for urgent/high priority orders"
    elif score >= 4.0: return "Recommended for medium-high orders"
    elif score >= 3.5: return "Use for normal priority orders"
    return "Not recommended — requires improvement"


def _get_actions(score, breakdown_days, worker_days, risk_count,
                 damage_rate, delay_days) -> list:
    actions = []
    if breakdown_days >= 3:
        actions.append("Schedule preventive machine maintenance")
    if worker_days >= 3:
        actions.append("Review workforce planning and absenteeism policy")
    if risk_count >= 5:
        actions.append("Increase daily production supervision")
    if damage_rate >= 3.0:
        actions.append("Strengthen quality control checkpoints")
    if delay_days >= 5:
        actions.append("Review production scheduling and buffer time")
    if score < 3.5:
        actions.append("Escalate to plant manager — performance below threshold")
    if not actions:
        actions.append("No immediate action required — maintain current operations")
    return actions


# ── Feature engineering ───────────────────────────────────────────

def _build_features(plant_name, buyer_name, order_quantity,
                     planned_days, actual_days,
                     machine_count, active_machine_count, employee_count,
                     daily_output_avg, total_workload, urgent_flag,
                     urgent_handled_count, risk_count,
                     machine_breakdown_days, worker_shortage_days,
                     damage_rate) -> tuple:
    delay_days        = actual_days - planned_days
    overrun_days      = max(0, delay_days)
    delay_status      = ("Early" if delay_days < 0
                         else "On Time" if delay_days == 0 else "Delayed")
    machine_util      = active_machine_count / machine_count if machine_count > 0 else 0.0
    efficiency_score  = round(daily_output_avg / employee_count, 3) if employee_count > 0 else 0.0
    delay_ratio       = round(delay_days / planned_days, 6) if planned_days > 0 else 0.0
    machine_idle_rate = round(1 - machine_util, 6)
    risk_per_workload = round(risk_count / (total_workload / 1000 + 1), 6)
    breakdown_wkr_days = machine_breakdown_days + worker_shortage_days

    plant_enc = PLANT_ENC_MAP.get(plant_name, 2)
    buyer_enc = BUYER_ENC_MAP.get(buyer_name, 2)

    row = pd.DataFrame([{
        "plant_enc":                    plant_enc,
        "buyer_enc":                    buyer_enc,
        "order_quantity":               order_quantity,
        "planned_completion_days":      planned_days,
        "actual_completion_days":       actual_days,
        "delay_days":                   delay_days,
        "delay_status_enc":             DELAY_MAP.get(delay_status, 0),
        "delay_ratio":                  delay_ratio,
        "overrun_days":                 overrun_days,
        "machine_count":                machine_count,
        "active_machine_count":         active_machine_count,
        "machine_utilization":          round(machine_util, 6),
        "machine_idle_rate":            machine_idle_rate,
        "employee_count":               employee_count,
        "daily_output_avg":             daily_output_avg,
        "efficiency_score":             efficiency_score,
        "total_workload":               total_workload,
        "urgent_flag_enc":              1 if urgent_flag == "Yes" else 0,
        "urgent_handled_count":         urgent_handled_count,
        "risk_count_from_component3":   risk_count,
        "risk_per_workload":            risk_per_workload,
        "machine_breakdown_days":       machine_breakdown_days,
        "worker_shortage_days":         worker_shortage_days,
        "breakdown_worker_days":        breakdown_wkr_days,
        "damage_rate":                  damage_rate,
    }])
    return row, delay_status, round(machine_util, 4), delay_days


# ── Deterministic response builder (replaces OpenAI) ─────────────

def _build_response(data: dict, models: dict) -> dict:
    """
    Assembles the full performance analysis JSON using ML model outputs +
    deterministic rules. Mirrors the exact schema from the OpenAI system prompt.
    """
    plant_name           = str(data["plant_name"])
    buyer_name           = str(data["buyer_name"])
    style_id             = data.get("style_id", "N/A")
    planned_days         = int(data["planned_completion_days"])
    actual_days          = int(data["actual_completion_days"])
    machine_count        = int(data["machine_count"])
    active_machine_count = int(data["active_machine_count"])
    employee_count       = int(data["employee_count"])
    daily_output_avg     = float(data["daily_output_avg"])
    total_workload       = float(data["total_workload"])
    urgent_flag          = str(data["urgent_style_flag"])
    urgent_handled       = int(data["urgent_handled_count"])
    risk_count           = int(data["risk_count_from_component3"])
    breakdown_days       = int(data["machine_breakdown_days"])
    worker_days          = int(data["worker_shortage_days"])
    damage_rate          = float(data["damage_rate"])
    order_qty            = int(data.get("order_quantity", 0))

    # ── Feature engineering ───────────────────────────────────
    X, delay_status, machine_util, delay_days = _build_features(
        plant_name, buyer_name, order_qty,
        planned_days, actual_days,
        machine_count, active_machine_count, employee_count,
        daily_output_avg, total_workload, urgent_flag,
        urgent_handled, risk_count, breakdown_days,
        worker_days, damage_rate
    )

    # ── ML: Performance score ─────────────────────────────────
    perf_score_ml = float(
        np.clip(models["perf_score"].predict(X[ML_FEATURES])[0], 1.0, 5.0)
    )

    # ── Rule-based: Performance score (audit / interpretable) ─
    perf_score_rule = _compute_perf_score(
        delay_days, machine_util, damage_rate, risk_count,
        breakdown_days, worker_days, urgent_handled
    )

    # ML is primary, rule-based is audit
    final_score = perf_score_ml

    # ── ML: Star rating ───────────────────────────────────────
    star_int = int(models["star_rating"].predict(X[ML_FEATURES])[0])
    star_int = max(1, min(5, star_int))

    # ── Rule-based outputs ────────────────────────────────────
    rec         = _recommendation(final_score, urgent_flag == "Yes",
                                   risk_count, breakdown_days)
    best_label  = _best_plant_label(final_score)
    star_label  = STAR_LABELS[star_int]
    star_interp = STAR_INTERPRETATIONS[star_int]
    actions     = _get_actions(
        final_score, breakdown_days, worker_days,
        risk_count, damage_rate, delay_days
    )

    confidence = ("LOW" if plant_name not in PLANT_ENC_MAP
                          or buyer_name not in BUYER_ENC_MAP else "OK")

    return {
        "status":     "success",
        "style_id":   style_id,
        "plant_name": plant_name,
        "buyer_name": buyer_name,
        "confidence": confidence,

        "order_summary": {
            "order_quantity":           order_qty,
            "planned_completion_days":  planned_days,
            "actual_completion_days":   actual_days,
            "delay_days":               delay_days,
            "delay_status":             delay_status,
            "machine_utilization_pct":  round(machine_util * 100, 1),
        },

        "performance": {
            "performance_score_ml":    round(perf_score_ml, 2),
            "performance_score_rule":  perf_score_rule,
            "final_performance_score": round(final_score, 2),
            "star_rating_count":       star_int,
            "star_rating_display":     star_label,
            "star_interpretation":     star_interp,
        },

        "optimization": {
            "recommendation":    rec,
            "best_plant_label":  best_label,
            "suggested_actions": actions,
        },
    }


# ── Routes ────────────────────────────────────────────────────────

@component4_bp.route("/health", methods=["GET"])
def health():
    return jsonify({
        "component": "4 — Production Analysis & Resource Optimization",
        "status": "ok"
    })


@component4_bp.route("/predict", methods=["POST"])
def predict():
    """
    Retrospective plant performance scoring & recommendation.

    Required fields: plant_name, buyer_name, planned_completion_days,
                     actual_completion_days, machine_count, active_machine_count,
                     employee_count, daily_output_avg, total_workload,
                     urgent_style_flag, urgent_handled_count,
                     risk_count_from_component3, machine_breakdown_days,
                     worker_shortage_days, damage_rate
    """
    data = request.get_json(force=True, silent=True)
    if not data:
        return jsonify({"error": "Request body must be valid JSON"}), 400

    required = [
        "plant_name", "buyer_name",
        "planned_completion_days", "actual_completion_days",
        "machine_count", "active_machine_count",
        "employee_count", "daily_output_avg", "total_workload",
        "urgent_style_flag", "urgent_handled_count",
        "risk_count_from_component3",
        "machine_breakdown_days", "worker_shortage_days", "damage_rate",
    ]
    missing = [f for f in required if f not in data]
    if missing:
        return jsonify({"error": f"Missing required fields: {missing}"}), 400

    try:
        plant_name           = str(data["plant_name"])
        buyer_name           = str(data["buyer_name"])
        planned_days         = int(data["planned_completion_days"])
        actual_days          = int(data["actual_completion_days"])
        machine_count        = int(data["machine_count"])
        active_machine_count = int(data["active_machine_count"])
        employee_count       = int(data["employee_count"])
        daily_output_avg     = float(data["daily_output_avg"])
        total_workload       = float(data["total_workload"])
        urgent_flag          = str(data["urgent_style_flag"])
        urgent_handled       = int(data["urgent_handled_count"])
        risk_count           = int(data["risk_count_from_component3"])
        breakdown_days       = int(data["machine_breakdown_days"])
        worker_days          = int(data["worker_shortage_days"])
        damage_rate          = float(data["damage_rate"])
    except (ValueError, TypeError) as e:
        return jsonify({"error": f"Invalid field value: {e}"}), 400

    if urgent_flag not in ("Yes", "No"):
        return jsonify({"error": "urgent_style_flag must be 'Yes' or 'No'"}), 400

    try:
        models = _load_models()
    except RuntimeError as e:
        return jsonify({"error": str(e)}), 503

    try:
        result = _build_response(data, models)
        return jsonify(result), 200
    except Exception as e:
        return jsonify({"error": f"Prediction failed: {str(e)}"}), 500
