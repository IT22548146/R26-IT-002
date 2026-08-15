"""
Component 1 — Sample Planning System (v5)
==========================================
Aligned with: garment_component1_ml_training_v5.ipynb

Models loaded:
  m1_overrun_classifier.pkl  — XGBoost/GradientBoosting  → Overrun_Class (0–6 days)
  m3_delay_classifier.pkl    — XGBoost/GradientBoosting  → Delay_Binary (0/1)
  le_priority.pkl            — LabelEncoder (Priority_Level)
  le_buyer.pkl               — LabelEncoder (Buyer_Name)
  le_plant.pkl               — LabelEncoder (Plant_Name)

Changes from previous version:
  - M1: regression → 7-class classifier (Overrun_Class 0–6)
  - M2: rule-based scorer uses live capacity table (capacity_full_year_2024.xlsx)
        classifier removed — it was leaking via Quality_Rating_F and Cap_Total_Machines
  - M3: Is_Overtime removed from feature vector — it was leaking Shipment_Status
  - Process_Type removed from features — all plants are Embroidery
  - le_process.pkl no longer needed
  - New capacity features: Cap_Free_Machine_Ratio, Cap_Monthly_Avg_Util,
    Qty_vs_Capacity_Pressure, Concurrent_High_Priority, Weekly_Load_Ratio, Cap_Time_Pressure
  - Hirdaramani corrected to Thursday (was Monday)
  - Is_Emergency derived automatically: buffer <= 2 AND priority == High

POST /api/component1/predict
Request body (JSON):
{
    "buyer_name":           "Tesco",
    "style_id":             "KM123456",
    "sample_qty":           5,
    "receive_date":         "2024-08-10",
    "buyer_required_date":  "2024-08-18"
}
All other fields are derived automatically from these 5 inputs.
"""

import os
import joblib
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from flask import Blueprint, request, jsonify

component1_bp = Blueprint("component1", __name__)

# ── Paths ──────────────────────────────────────────────────────────────
BASE_DIR      = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MODELS_DIR    = os.path.join(BASE_DIR, "models")
CAPACITY_PATH = os.path.join(MODELS_DIR, "capacity_full_year_2024.xlsx")

# ── Business constants ─────────────────────────────────────────────────
BUYER_SHIPMENT_SCHEDULE = {
    "Tesco":       "Monday",
    "George":      "Thursday",   # corrected from old version
    "M&S":         "Monday",
    "Hirdaramani": "Thursday",   # corrected from old version
}
BUYER_DOW = {"Tesco": 0, "George": 3, "M&S": 0, "Hirdaramani": 3}

ALL_PLANTS = [
    "Amsral Lanka Enterprises", "Dinusha Embroidery", "MRC Group",
    "Regal Image International", "Sunrose Lanka (Pvt) Ltd", "The Bobbin Group",
]
ALL_BUYERS = ["George", "Hirdaramani", "M&S", "Tesco"]

PLANT_QUALITY = {
    "Amsral Lanka Enterprises":  4.2,
    "Dinusha Embroidery":        4.8,
    "MRC Group":                 4.5,
    "Regal Image International": 4.6,
    "Sunrose Lanka (Pvt) Ltd":   4.3,
    "The Bobbin Group":          4.4,
}

PLANT_LOCATIONS = {
    "Amsral Lanka Enterprises":  "Boralesgamuwa",
    "Dinusha Embroidery":        "Weliweriya",
    "MRC Group":                 "Colombo",
    "Regal Image International": "Maharagama",
    "Sunrose Lanka (Pvt) Ltd":   "Katubedda",
    "The Bobbin Group":          "Mount Lavinia",
}

# Monthly utilisation multipliers derived from real delay rates
MONTHLY_UTIL_MULTIPLIER = {
    1: 0.973, 2: 0.930, 3: 0.990, 4: 0.999,  5: 1.018,
    6: 0.989, 7: 0.976, 8: 1.070, 9: 0.966, 10: 0.982,
    11: 0.991, 12: 0.979,
}

QTY_COMPLETION_MAP = [(3, 3), (5, 5), (10, 7)]

# M1 class labels for response
OVERRUN_CLASS_LABEL = {
    0: "On Time",
    1: "1-day overrun",
    2: "2-day overrun",
    3: "3-day overrun (rework/machine risk)",
    4: "4-day overrun (high-risk combination)",
    5: "5-day overrun (severe: multi-cause)",
    6: "6-day overrun (worst case)",
}

# ── Lazy loaders ───────────────────────────────────────────────────────
_models   = {}
_capacity = {}   # {(plant, date): row}
_cap_df   = None


def _load_models():
    if _models:
        return _models
    try:
        _models["m1"] = joblib.load(os.path.join(MODELS_DIR, "m1_overrun_classifier.pkl"))
        _models["m3"] = joblib.load(os.path.join(MODELS_DIR, "m3_delay_classifier.pkl"))
        _models["le_priority"] = joblib.load(os.path.join(MODELS_DIR, "le_priority.pkl"))
        _models["le_buyer"]    = joblib.load(os.path.join(MODELS_DIR, "le_buyer.pkl"))
        _models["le_plant"]    = joblib.load(os.path.join(MODELS_DIR, "le_plant.pkl"))
    except FileNotFoundError as e:
        raise RuntimeError(
            f"Model file not found: {e}. "
            "Run garment_component1_ml_training_v5.ipynb first."
        )
    return _models


def _load_capacity():
    """Load full-year capacity table once and cache it."""
    global _cap_df
    if _cap_df is not None:
        return _cap_df
    if not os.path.exists(CAPACITY_PATH):
        return None
    df = pd.read_excel(CAPACITY_PATH)
    df["Date"] = pd.to_datetime(df["Date"])
    _cap_df = df
    return _cap_df


# ── Helper functions ───────────────────────────────────────────────────

def _completion_days(qty: int) -> int:
    for threshold, days in QTY_COMPLETION_MAP:
        if qty <= threshold:
            return days
    return 7


def _priority_from_buffer(buffer_days: int) -> str:
    if buffer_days <= 1:   return "High"
    if buffer_days <= 3:   return "Medium"
    if buffer_days <= 6:   return "Low"
    return "No Urgency"


def _next_weekday(after_date: datetime, weekday: int) -> datetime:
    """Return next occurrence of weekday (0=Mon) on or after after_date."""
    days_ahead = (weekday - after_date.weekday()) % 7
    return after_date + timedelta(days=days_ahead)


def _get_capacity_for_plant(plant: str, date: datetime, cap_df) -> dict:
    """
    Look up daily capacity for a plant on the nearest available business day.
    Falls back to plant-average defaults if capacity table not loaded.
    """
    defaults = {
        "util_pct":        85.0,
        "free_machine_r":  0.15,
        "styles_can_do":   5.0,
        "total_machines":  15.0,
    }
    if cap_df is None:
        return defaults

    plant_data = cap_df[cap_df["Plant_Name"] == plant].copy()
    if plant_data.empty:
        return defaults

    target = pd.Timestamp(date).normalize()
    # Find nearest date on or before target
    before = plant_data[plant_data["Date"] <= target]
    if before.empty:
        before = plant_data   # use earliest available
    row = before.sort_values("Date").iloc[-1]

    return {
        "util_pct":       float(row.get("Utilization_Pct",    defaults["util_pct"])),
        "free_machine_r": float(row.get("Free_Machine_Ratio", defaults["free_machine_r"])),
        "styles_can_do":  float(row.get("Styles_Can_Do",      defaults["styles_can_do"])),
        "total_machines": float(row.get("Total_Machines",     defaults["total_machines"])),
    }


def _score_plants(receive_date: datetime, priority: str, sample_qty: int,
                   cap_df, plant_ontime_rates: dict) -> list:
    """
    M2 — Rule-based plant scorer using live capacity.
    All 6 plants do Embroidery — no process_type filter.
    Weights: util=0.30, free_ratio=0.25, history=0.25, quality=0.15
    """
    priority_bonus = {"High": 0.20, "Medium": 0.10, "Low": 0.05, "No Urgency": 0.0}
    scores = []

    for plant in ALL_PLANTS:
        cap        = _get_capacity_for_plant(plant, receive_date, cap_df)
        quality    = PLANT_QUALITY.get(plant, 4.3)
        util_score = max(0.0, 1.0 - cap["util_pct"] / 100.0)
        free_score = cap["free_machine_r"]
        qual_score = (quality - 4.0) / 1.0
        hist_rate  = plant_ontime_rates.get(plant, 0.75)
        pbonus     = priority_bonus.get(priority, 0.0)
        qty_penalty = max(0.0, (sample_qty - cap["styles_can_do"]) / 10.0) * 0.1

        composite = (
            0.30 * util_score +
            0.25 * free_score +
            0.25 * hist_rate  +
            0.15 * qual_score +
            pbonus - qty_penalty
        )
        scores.append({
            "rank":              0,
            "plant":             plant,
            "location":          PLANT_LOCATIONS.get(plant, ""),
            "composite_score":   round(composite, 4),
            "live_util_pct":     round(cap["util_pct"], 1),
            "live_free_ratio":   round(cap["free_machine_r"], 3),
            "live_styles_can_do":round(cap["styles_can_do"], 1),
            "quality_rating":    quality,
            "historical_ontime": round(hist_rate, 3),
        })

    scores.sort(key=lambda x: x["composite_score"], reverse=True)
    for i, s in enumerate(scores):
        s["rank"] = i + 1

    return scores


def _build_feature_vector(
    sample_qty, completion_days, buffer_days, priority,
    buyer_name, plant_name, quality_rating,
    is_emergency, receive_month, is_q4, is_aug,
    cap_free_machine_ratio, cap_monthly_avg_util,
    qty_vs_cap_pressure, concurrent_high, weekly_load_ratio,
    models
) -> tuple:
    """
    Build the feature vector matching M1_FEATURES and M3_FEATURES exactly.
    Returns (feature_array, confidence_flag).

    M1_FEATURES = M3_FEATURES (same 20 features, Is_Overtime excluded):
      Sample_Qty, Completion_Days, Buffer_Days, Priority_Enc,
      Buyer_Enc, Plant_Enc, Quality_Rating_F,
      Is_Emergency,
      Receive_Month, Is_Q4, Is_Aug, Qty_Group,
      Time_Pressure, Buffer_Ratio,
      Cap_Free_Machine_Ratio, Cap_Monthly_Avg_Util,
      Qty_vs_Capacity_Pressure, Concurrent_High_Priority,
      Weekly_Load_Ratio, Cap_Time_Pressure
    """
    qty_group   = 0 if sample_qty <= 3 else 1 if sample_qty <= 5 else 2
    denom       = max(buffer_days + completion_days, 1)
    time_press  = min(completion_days / denom, 6.0)
    buf_ratio   = np.clip(buffer_days / completion_days, -1.0, 5.0)
    cap_tp      = np.clip((cap_monthly_avg_util / 100.0) * time_press, 0.0, 6.0)

    confidence = "OK"

    # Priority encoding — order matches notebook: No Urgency=0, Low=1, Medium=2, High=3
    try:
        priority_enc = int(models["le_priority"].transform([priority])[0])
    except Exception:
        priority_enc = 3   # fallback High
        confidence   = "LOW"

    # Buyer encoding
    if buyer_name in ALL_BUYERS:
        try:
            buyer_enc = int(models["le_buyer"].transform([buyer_name])[0])
        except Exception:
            buyer_enc  = 0
            confidence = "LOW"
    else:
        buyer_enc  = 0
        confidence = "LOW"

    # Plant encoding
    try:
        plant_enc = int(models["le_plant"].transform([plant_name])[0])
    except Exception:
        plant_enc  = 0
        confidence = "LOW"

    feat = np.array([[
        sample_qty,              # Sample_Qty
        completion_days,         # Completion_Days
        buffer_days,             # Buffer_Days
        priority_enc,            # Priority_Enc
        buyer_enc,               # Buyer_Enc
        plant_enc,               # Plant_Enc
        quality_rating,          # Quality_Rating_F
        is_emergency,            # Is_Emergency
        receive_month,           # Receive_Month
        int(is_q4),              # Is_Q4
        int(is_aug),             # Is_Aug
        qty_group,               # Qty_Group
        time_press,              # Time_Pressure
        buf_ratio,               # Buffer_Ratio
        cap_free_machine_ratio,  # Cap_Free_Machine_Ratio
        cap_monthly_avg_util,    # Cap_Monthly_Avg_Util
        qty_vs_cap_pressure,     # Qty_vs_Capacity_Pressure
        concurrent_high,         # Concurrent_High_Priority
        weekly_load_ratio,       # Weekly_Load_Ratio
        cap_tp,                  # Cap_Time_Pressure
    ]], dtype=float)

    return feat, confidence


# ── Historical on-time rates (from real data in notebook) ─────────────
# Update these values after retraining with new real data
PLANT_ONTIME_RATES = {
    "Amsral Lanka Enterprises":  0.65,
    "Dinusha Embroidery":        0.90,
    "MRC Group":                 0.72,
    "Regal Image International": 0.78,
    "Sunrose Lanka (Pvt) Ltd":   0.69,
    "The Bobbin Group":          0.74,
}


# ── Main response builder ──────────────────────────────────────────────

def _build_response(data: dict, models: dict) -> dict:
    # ── Parse inputs ──────────────────────────────────────────────────
    buyer_name       = str(data["buyer_name"])
    style_id         = data.get("style_id", "N/A")
    sample_qty       = int(data["sample_qty"])
    receive_date_str = str(data["receive_date"])
    buyer_req_str    = str(data["buyer_required_date"])

    # Parse dates
    try:
        receive_date = datetime.strptime(receive_date_str, "%Y-%m-%d")
        buyer_req    = datetime.strptime(buyer_req_str,    "%Y-%m-%d")
    except ValueError as e:
        raise ValueError(f"Invalid date format — use YYYY-MM-DD: {e}")

    # ── Step 2: Completion days from qty ──────────────────────────────
    completion_days = _completion_days(sample_qty)

    # ── Step 3: Estimated completion date ─────────────────────────────
    est_completion = receive_date + timedelta(days=completion_days)

    # ── Steps 4–5: Nearest shipment date ──────────────────────────────
    dow          = BUYER_DOW.get(buyer_name, 0)
    nearest_ship = _next_weekday(est_completion, dow)
    buyer_ship_day = BUYER_SHIPMENT_SCHEDULE.get(buyer_name, "Monday")

    # ── Step 7: Buffer days ───────────────────────────────────────────
    buffer_days = (buyer_req - est_completion).days

    # ── Step 8: Priority and emergency flag ───────────────────────────
    priority     = _priority_from_buffer(buffer_days)
    is_emergency = int(buffer_days <= 2 and priority == "High")

    # ── Step 9: Feasibility ───────────────────────────────────────────
    feasible = buffer_days >= 0

    # ── Date features ─────────────────────────────────────────────────
    receive_month = receive_date.month
    is_q4         = int(receive_month >= 10)
    is_aug        = int(receive_month == 8)

    # ── Load capacity table ───────────────────────────────────────────
    cap_df = _load_capacity()

    # ── Step 6: M2 — Score and assign best plant ──────────────────────
    plant_scores     = _score_plants(receive_date, priority, sample_qty,
                                      cap_df, PLANT_ONTIME_RATES)
    assigned_plant   = plant_scores[0]["plant"]
    assigned_quality = PLANT_QUALITY.get(assigned_plant, 4.4)

    # ── Get live capacity for assigned plant ──────────────────────────
    cap = _get_capacity_for_plant(assigned_plant, receive_date, cap_df)

    cap_monthly_avg_util  = round(
        85.0 * MONTHLY_UTIL_MULTIPLIER.get(receive_month, 1.0), 1
    )
    qty_vs_cap_pressure   = round(
        min(sample_qty / max(cap["styles_can_do"], 1.0), 5.0), 4
    )
    # Conservative inference-time defaults for weekly/concurrent features
    concurrent_high   = 1 if priority == "High" else 0
    weekly_load_ratio = round(min((concurrent_high + 2) / max(cap["styles_can_do"] * 5, 1), 3.0), 4)

    # ── Build feature vector ──────────────────────────────────────────
    feat, confidence = _build_feature_vector(
        sample_qty       = sample_qty,
        completion_days  = completion_days,
        buffer_days      = buffer_days,
        priority         = priority,
        buyer_name       = buyer_name,
        plant_name       = assigned_plant,
        quality_rating   = assigned_quality,
        is_emergency     = is_emergency,
        receive_month    = receive_month,
        is_q4            = is_q4,
        is_aug           = is_aug,
        cap_free_machine_ratio = cap["free_machine_r"],
        cap_monthly_avg_util   = cap_monthly_avg_util,
        qty_vs_cap_pressure    = qty_vs_cap_pressure,
        concurrent_high        = concurrent_high,
        weekly_load_ratio      = weekly_load_ratio,
        models                 = models,
    )

    # ── M1: Overrun class prediction ──────────────────────────────────
    overrun_class = int(models["m1"].predict(feat)[0])
    overrun_label = OVERRUN_CLASS_LABEL.get(overrun_class, f"{overrun_class}-day overrun")

    # ── M3: Delay probability ─────────────────────────────────────────
    delay_prob = float(models["m3"].predict_proba(feat)[0][1])
    delay_pred = "Delayed" if delay_prob >= 0.5 else "On Time"

    # ── Final shipment date ───────────────────────────────────────────
    actual_completion = est_completion + timedelta(days=overrun_class)
    final_ship        = _next_weekday(actual_completion, dow)

    # ── Planning logic (Steps 10–12) ──────────────────────────────────
    if not feasible:
        allocation_remark  = "Cannot complete within buyer required date"
        action_required    = "Adjust Plan / Inform Buyer / Reassign Plant if possible"
        buyer_approval     = "Waiting for Buyer Approval"
        final_ship_str     = None
    elif delay_pred == "Delayed":
        allocation_remark  = "Shipment delayed — waiting for buyer approval"
        action_required    = "Inform Buyer / Obtain Approval"
        buyer_approval     = "Waiting for Buyer Approval"
        final_ship_str     = final_ship.strftime("%Y-%m-%d")
    else:
        allocation_remark  = "Normal Allocation"
        action_required    = "Proceed with plan"
        buyer_approval     = "Not Required"
        final_ship_str     = final_ship.strftime("%Y-%m-%d")

    # ── Risk level ────────────────────────────────────────────────────
    if buffer_days < 0:       risk_level = "Critical"
    elif buffer_days <= 1:    risk_level = "High"
    elif buffer_days <= 3:    risk_level = "Medium"
    else:                     risk_level = "Low"

    risk_summary = (
        f"Buffer {buffer_days}d | priority {priority} | "
        f"M1 overrun class {overrun_class} ({overrun_label}) | "
        f"M3 delay probability {round(delay_prob * 100, 1)}% | "
        f"{action_required.lower()}"
    )

    return {
        "status":     "success",
        "style_id":   style_id,
        "buyer_name": buyer_name,
        "confidence": confidence,

        "input_summary": {
            "sample_qty":      sample_qty,
            "completion_days": completion_days,
            "buffer_days":     buffer_days,
            "priority_level":  priority,
            "is_emergency":    bool(is_emergency),
            "is_q4":           bool(is_q4),
            "is_aug":          bool(is_aug),
            "receive_month":   receive_month,
        },

        "scheduling": {
            "receive_date":              receive_date_str,
            "estimated_completion_date": est_completion.strftime("%Y-%m-%d"),
            "buyer_required_date":       buyer_req_str,
            "nearest_shipment_date":     nearest_ship.strftime("%Y-%m-%d"),
            "final_shipment_date":       final_ship_str,
            "buyer_ship_day":            buyer_ship_day,
            "days_completion_to_ship":   (nearest_ship - est_completion).days,
        },

        "model1_overrun": {
            "overrun_class":     overrun_class,
            "overrun_days":      overrun_class,
            "interpretation":    overrun_label,
        },

        "model2_plant_selection": {
            "recommended_plant": assigned_plant,
            "location":          PLANT_LOCATIONS.get(assigned_plant, ""),
            "live_util_pct":     plant_scores[0]["live_util_pct"],
            "live_styles_can_do":plant_scores[0]["live_styles_can_do"],
            "composite_score":   plant_scores[0]["composite_score"],
            "all_scores":        plant_scores,
        },

        "model3_delay": {
            "delay_probability": round(delay_prob, 3),
            "delay_prediction":  delay_pred,
            "shipment_status":   delay_pred,
        },

        "planning_output": {
            "feasible":              feasible,
            "allocated":             feasible,
            "allocation_remark":     allocation_remark,
            "action_required":       action_required,
            "buyer_approval_status": buyer_approval,
            "risk_level":            risk_level,
            "risk_summary":          risk_summary,
        },
    }


# ── Routes ─────────────────────────────────────────────────────────────

@component1_bp.route("/health", methods=["GET"])
def health():
    return jsonify({
        "component": "1 — Sample Planning System",
        "version":   "v5",
        "status":    "ok",
        "models": [
            "m1_overrun_classifier.pkl",
            "m3_delay_classifier.pkl",
            "le_priority.pkl", "le_buyer.pkl", "le_plant.pkl",
        ],
        "capacity_table": os.path.exists(CAPACITY_PATH),
    })


@component1_bp.route("/predict", methods=["POST"])
def predict():
    """
    Component 1 sample planning prediction.

    Minimum required fields (everything else is derived):
      buyer_name, sample_qty, receive_date, buyer_required_date

    Optional:
      style_id

    All capacity, priority, buffer, scheduling fields are
    computed internally from the 4 required inputs.
    """
    data = request.get_json(force=True, silent=True)
    if not data:
        return jsonify({"error": "Request body must be valid JSON"}), 400

    required = ["buyer_name", "sample_qty", "receive_date", "buyer_required_date"]
    missing  = [f for f in required if f not in data]
    if missing:
        return jsonify({"error": f"Missing required fields: {missing}"}), 400

    # Validate types
    try:
        buyer_name  = str(data["buyer_name"])
        sample_qty  = int(data["sample_qty"])
        _           = datetime.strptime(data["receive_date"],         "%Y-%m-%d")
        _           = datetime.strptime(data["buyer_required_date"],  "%Y-%m-%d")
    except (ValueError, TypeError) as e:
        return jsonify({"error": f"Invalid field value: {e}"}), 400

    # Validate ranges
    if not (1 <= sample_qty <= 10):
        return jsonify({"error": "sample_qty must be between 1 and 10"}), 400
    if buyer_name not in ALL_BUYERS:
        return jsonify({
            "error": f"buyer_name must be one of {ALL_BUYERS}",
            "received": buyer_name,
        }), 400

    try:
        models = _load_models()
    except RuntimeError as e:
        return jsonify({"error": str(e)}), 503

    try:
        result = _build_response(data, models)
        return jsonify(result), 200
    except Exception as e:
        return jsonify({"error": f"Prediction failed: {str(e)}"}), 500