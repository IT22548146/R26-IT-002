"""
Component 1 — Sample Planning System
=====================================
Models loaded:
  model1_overrun.pkl   — RandomForestRegressor  → Overrun_Days
  model3_delay.pkl     — GradientBoostingClassifier → Delayed / On Time
  le_priority.pkl      — LabelEncoder (Priority_Level)
  le_process.pkl       — LabelEncoder (Process_Type)
  le_buyer.pkl         — LabelEncoder (Buyer_Name)

Model 2 (Plant Selection) is rule-based scoring — no .pkl needed.
OpenAI removed — response JSON is assembled deterministically from model outputs.

POST /api/component1/predict
Request body (JSON):
{
    "buyer_name":        "Tesco",
    "style_id":          "KM123456",
    "sample_qty":        3,
    "buyer_required_date": "2025-03-15",
    "process_type":      "Embroidery",
    "receive_date":      "2025-03-01",
    "buffer_days":       5,
    "priority_level":    "High",
    "cap_util_pct":      75.0,
    "daily_cap_styles":  9,
    "quality_rating":    4.8,
    "is_emergency_shipment": 0
}
"""

import os
import joblib
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from flask import Blueprint, request, jsonify

component1_bp = Blueprint("component1", __name__)

# ── Paths ─────────────────────────────────────────────────────────
BASE_DIR   = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MODELS_DIR = os.path.join(BASE_DIR, "models")

# ── Static lookups ────────────────────────────────────────────────
QUALITY_MAP = {
    "Amsral Lanka Enterprises":  4.2,
    "Dinusha Embroidery":        4.8,
    "MRC Group":                 4.5,
    "Regal Image International": 4.6,
    "Sunrose Lanka (Pvt) Ltd":   4.3,
    "The Bobbin Group":          4.4,
}

HIST_DELAY = {
    "Amsral Lanka Enterprises":  0.350,
    "Dinusha Embroidery":        0.100,
    "MRC Group":                 0.280,
    "Regal Image International": 0.220,
    "Sunrose Lanka (Pvt) Ltd":   0.310,
    "The Bobbin Group":          0.260,
}

PLANT_LOCATIONS = {
    "Amsral Lanka Enterprises":  "Boralesgamuwa",
    "Dinusha Embroidery":        "Weliweriya",
    "MRC Group":                 "Colombo",
    "Regal Image International": "Maharagama",
    "Sunrose Lanka (Pvt) Ltd":   "Katubedda",
    "The Bobbin Group":          "Mount Lavinia",
}

PRINTING_PLANTS = [p for p in QUALITY_MAP if p != "Dinusha Embroidery"]

BUYER_SHIPMENT_SCHEDULE = {
    "Tesco":      "Monday",
    "George":     "Thursday",
    "M&S":        "Monday",
    "Hirdaramani":"Monday",
}

PRIORITY_RULES = {
    "High":       1,
    "Medium":     3,
    "Low":        6,
    "No Urgency": 999,
}

QTY_COMPLETION_MAP = [(3, 3), (5, 5), (10, 7)]
KNOWN_BUYERS = ["George", "Hirdaramani", "M&S", "Tesco"]

# ── Lazy model loader ─────────────────────────────────────────────
_models = {}


def _load_models():
    if _models:
        return _models
    try:
        _models["model1"]      = joblib.load(os.path.join(MODELS_DIR, "model1_overrun.pkl"))
        _models["model3"]      = joblib.load(os.path.join(MODELS_DIR, "model3_delay.pkl"))
        _models["le_priority"] = joblib.load(os.path.join(MODELS_DIR, "le_priority.pkl"))
        _models["le_process"]  = joblib.load(os.path.join(MODELS_DIR, "le_process.pkl"))
        _models["le_buyer"]    = joblib.load(os.path.join(MODELS_DIR, "le_buyer.pkl"))
    except FileNotFoundError as e:
        raise RuntimeError(f"Model file not found: {e}. Run the Component 1 notebook first.")
    return _models


# ── Helper functions ──────────────────────────────────────────────

def _completion_days(qty: int) -> int:
    for threshold, days in QTY_COMPLETION_MAP:
        if qty <= threshold:
            return days
    return 7


def _priority_from_buffer(buffer_days: int) -> str:
    if buffer_days <= 1:
        return "High"
    elif buffer_days <= 3:
        return "Medium"
    elif buffer_days <= 6:
        return "Low"
    return "No Urgency"


def _next_shipment_day(after_date: datetime, ship_day: str) -> datetime:
    """Find the next occurrence of the buyer's shipment weekday."""
    day_map = {
        "Monday": 0, "Tuesday": 1, "Wednesday": 2, "Thursday": 3,
        "Friday": 4, "Saturday": 5, "Sunday": 6,
    }
    target = day_map.get(ship_day, 0)
    days_ahead = (target - after_date.weekday()) % 7
    if days_ahead == 0:
        days_ahead = 7
    return after_date + timedelta(days=days_ahead)


def _score_plants(process_type: str, buffer_days: int, cap_util_pct: float) -> list:
    """Model 2 — Rule-based scoring. Returns ranked list."""
    if process_type == "Embroidery":
        return [{"rank": 1, "plant": "Dinusha Embroidery", "score": 10.0}]

    scores = {}
    for plant in PRINTING_PLANTS:
        quality     = QUALITY_MAP.get(plant, 4.3)
        delay_rate  = HIST_DELAY.get(plant, 0.30)
        cap_penalty = cap_util_pct / 100.0
        buf_bonus   = min(buffer_days * 0.05, 0.30)
        scores[plant] = round(quality - (delay_rate * 2) - cap_penalty + buf_bonus, 4)

    ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    return [
        {"rank": i + 1, "plant": p, "score": round(s, 4)}
        for i, (p, s) in enumerate(ranked)
    ]


def _build_feature_row(sample_qty, buffer_days, process_type, buyer_name,
                        priority_level, cap_util_pct, daily_cap, quality,
                        is_emergency, receive_month, is_q4, models) -> tuple:
    comp_days = _completion_days(sample_qty)
    qty_group = 0 if sample_qty <= 3 else 1 if sample_qty <= 5 else 2
    denom     = buffer_days + comp_days
    time_pres = min(comp_days / denom if denom > 0 else 2.0, 2.0)

    confidence_flag = "OK"
    if buyer_name not in KNOWN_BUYERS:
        buyer_enc       = 2
        confidence_flag = "LOW"
    else:
        buyer_enc = int(models["le_buyer"].transform([buyer_name])[0])

    row = pd.DataFrame([{
        "Sample_Qty":            sample_qty,
        "Qty_Group":             qty_group,
        "Completion_Days":       comp_days,
        "Buffer_Days":           buffer_days,
        "Priority_Enc":          int(models["le_priority"].transform([priority_level])[0]),
        "Process_Enc":           int(models["le_process"].transform([process_type])[0]),
        "Buyer_Enc":             buyer_enc,
        "Time_Pressure":         time_pres,
        "DailyCap_F":            daily_cap,
        "CapUtil_F":             cap_util_pct,
        "Quality_F":             quality,
        "Is_Emergency_Shipment": is_emergency,
        "Receive_Month":         receive_month,
        "Is_Q4":                 is_q4,
    }])
    return row, confidence_flag


# ── Deterministic response builder (replaces OpenAI) ─────────────

def _build_response(payload: dict, models: dict) -> dict:
    """
    Assembles the full planning JSON using ML model outputs + deterministic rules.
    Mirrors the exact schema previously returned by the OpenAI prompt.
    """
    buyer_name    = payload["buyer_name"]
    style_id      = payload["style_id"]
    sample_qty    = payload["sample_qty"]
    buffer_days   = payload["buffer_days"]
    process_type  = payload["process_type"]
    priority_lvl  = payload["priority_level"]
    cap_util_pct  = payload["cap_util_pct"]
    daily_cap     = payload["daily_cap_styles"]
    quality       = payload["quality_rating"]
    is_emergency  = payload["is_emergency_shipment"]
    receive_month = payload["receive_month"]
    is_q4         = payload["is_q4"]

    # ── Feature engineering ───────────────────────────────────
    comp_days = _completion_days(sample_qty)
    feature_row, confidence = _build_feature_row(
        sample_qty, buffer_days, process_type, buyer_name,
        priority_lvl, cap_util_pct, daily_cap, quality,
        is_emergency, receive_month, is_q4, models
    )

    # ── Model 1: Overrun prediction ───────────────────────────
    overrun_days = float(models["model1"].predict(feature_row)[0])
    interpretation = (
        "On time" if overrun_days < 0.5
        else f"{round(overrun_days)} day(s) late"
    )

    # ── Model 2: Plant scoring (rule-based) ───────────────────
    plant_ranking    = _score_plants(process_type, buffer_days, cap_util_pct)
    recommended_plant = plant_ranking[0]["plant"]

    # ── Model 3: Delay probability ────────────────────────────
    delay_prob = float(models["model3"].predict_proba(feature_row)[0][1])
    delay_pred = "Delayed" if delay_prob >= 0.5 else "On Time"

    # ── Feasibility & scheduling ──────────────────────────────
    feasible      = buffer_days > 0
    auto_priority = _priority_from_buffer(buffer_days)

    # ── Scheduling dates (if receive_date supplied) ───────────
    receive_date_str    = payload.get("receive_date")
    buyer_req_date_str  = payload.get("buyer_required_date")
    estimated_completion_date = None
    nearest_shipment_date     = None
    buyer_ship_day            = BUYER_SHIPMENT_SCHEDULE.get(buyer_name, "Monday")
    days_completion_to_ship   = None

    if receive_date_str:
        try:
            receive_date          = datetime.strptime(receive_date_str, "%Y-%m-%d")
            est_completion        = receive_date + timedelta(days=comp_days)
            estimated_completion_date = est_completion.strftime("%Y-%m-%d")
            nearest_ship          = _next_shipment_day(est_completion, buyer_ship_day)
            nearest_shipment_date = nearest_ship.strftime("%Y-%m-%d")
            days_completion_to_ship = (nearest_ship - est_completion).days
        except ValueError:
            pass

    # ── Planning output fields ────────────────────────────────
    if feasible and delay_pred == "On Time":
        allocation_remark  = "Normal Allocation"
        action_required    = "Proceed with plan"
        buyer_approval     = "Not Required"
        final_ship_date    = nearest_shipment_date
    elif feasible and delay_pred == "Delayed":
        allocation_remark  = "Shipment delayed – waiting for buyer approval"
        action_required    = "Inform Buyer / Obtain Approval"
        buyer_approval     = "Waiting for Buyer Approval"
        final_ship_date    = nearest_shipment_date
    else:
        allocation_remark  = "Cannot complete within buyer required date"
        action_required    = "Adjust Plan / Inform Buyer / Reassign Plant if possible"
        buyer_approval     = "Not Required"
        final_ship_date    = None

    # ── Risk level ────────────────────────────────────────────
    if buffer_days < 0:
        risk_level = "Critical"
    elif buffer_days <= 1:
        risk_level = "High"
    elif buffer_days <= 3:
        risk_level = "Medium"
    else:
        risk_level = "Low"

    risk_summary = (
        f"Buffer of {buffer_days} day(s) with {delay_pred.lower()} prediction "
        f"({round(delay_prob * 100, 1)}% delay probability); {action_required.lower()}."
    )

    return {
        "status":      "success",
        "style_id":    style_id,
        "buyer_name":  buyer_name,
        "confidence":  confidence,

        "input_summary": {
            "sample_qty":      sample_qty,
            "completion_days": comp_days,
            "buffer_days":     buffer_days,
            "process_type":    process_type,
            "priority_level":  priority_lvl,
            "is_q4":           bool(is_q4),
        },

        "model1_overrun": {
            "predicted_overrun_days": round(overrun_days, 2),
            "interpretation":         interpretation,
        },

        "model2_plant_selection": {
            "recommended_plant": recommended_plant,
            "ranking":           plant_ranking,
        },

        "model3_delay": {
            "delay_probability": round(delay_prob, 3),
            "delay_prediction":  delay_pred,
            "shipment_status":   delay_pred,
        },

        "planning_output": {
            "feasible":              feasible,
            "allocated":             feasible,
            "auto_priority":         auto_priority,
            "priority_level":        priority_lvl,
            "final_shipment_date":   final_ship_date,
            "allocation_remark":     allocation_remark,
            "action_required":       action_required,
            "buyer_approval_status": buyer_approval,
            "risk_level":            risk_level,
            "risk_summary":          risk_summary,
        },

        "scheduling": {
            "estimated_completion_date": estimated_completion_date,
            "nearest_shipment_date":     nearest_shipment_date,
            "buyer_ship_day":            buyer_ship_day,
            "days_completion_to_ship":   days_completion_to_ship,
        },
    }


# ── Routes ────────────────────────────────────────────────────────

@component1_bp.route("/health", methods=["GET"])
def health():
    return jsonify({"component": "1 — Sample Planning System", "status": "ok"})


@component1_bp.route("/predict", methods=["POST"])
def predict():
    """
    Full Component 1 sample planning prediction.
    Required fields: buyer_name, sample_qty, buffer_days, process_type,
                     priority_level, cap_util_pct, daily_cap_styles, quality_rating
    Optional fields: style_id, receive_date, buyer_required_date,
                     is_emergency_shipment, receive_month, is_q4
    """
    data = request.get_json(force=True, silent=True)
    if not data:
        return jsonify({"error": "Request body must be valid JSON"}), 400

    required = [
        "buyer_name", "sample_qty", "buffer_days", "process_type",
        "priority_level", "cap_util_pct", "daily_cap_styles", "quality_rating",
    ]
    missing = [f for f in required if f not in data]
    if missing:
        return jsonify({"error": f"Missing required fields: {missing}"}), 400

    try:
        buyer_name    = str(data["buyer_name"])
        sample_qty    = int(data["sample_qty"])
        buffer_days   = int(data["buffer_days"])
        process_type  = str(data["process_type"])
        priority_lvl  = str(data["priority_level"])
        cap_util_pct  = float(data["cap_util_pct"])
        daily_cap     = float(data["daily_cap_styles"])
        quality_rating= float(data["quality_rating"])
        is_emergency  = int(data.get("is_emergency_shipment", 0))
        receive_month = int(data.get("receive_month", datetime.now().month))
        is_q4         = int(data.get("is_q4", 1 if receive_month >= 10 else 0))
        style_id      = data.get("style_id", "N/A")
    except (ValueError, TypeError) as e:
        return jsonify({"error": f"Invalid field value: {e}"}), 400

    if not (1 <= sample_qty <= 10):
        return jsonify({"error": "sample_qty must be between 1 and 10"}), 400
    if process_type not in ("Embroidery", "Printing"):
        return jsonify({"error": "process_type must be 'Embroidery' or 'Printing'"}), 400
    if priority_lvl not in ("High", "Medium", "Low", "No Urgency"):
        return jsonify({"error": "priority_level must be High / Medium / Low / No Urgency"}), 400

    try:
        models = _load_models()
    except RuntimeError as e:
        return jsonify({"error": str(e)}), 503

    try:
        payload = {
            "buyer_name":            buyer_name,
            "style_id":              style_id,
            "sample_qty":            sample_qty,
            "buffer_days":           buffer_days,
            "process_type":          process_type,
            "priority_level":        priority_lvl,
            "cap_util_pct":          cap_util_pct,
            "daily_cap_styles":      daily_cap,
            "quality_rating":        quality_rating,
            "is_emergency_shipment": is_emergency,
            "receive_month":         receive_month,
            "is_q4":                 is_q4,
            "receive_date":          data.get("receive_date"),
            "buyer_required_date":   data.get("buyer_required_date"),
        }
        result = _build_response(payload, models)
        return jsonify(result), 200
    except Exception as e:
        return jsonify({"error": f"Prediction failed: {str(e)}"}), 500
