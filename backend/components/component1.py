"""
Component 1 — Sample Planning System (v7)
  - M3 retargeted: Delay_Binary → Is_Overtime
    (factory overtime risk, not buyer date miss — removes buffer leakage)
  - model3_delay renamed to model3_factory_overtime in response
  - buyer_impact computed as pure arithmetic, never from model
==========================================
Aligned with: garment_component1_ml_training_v6.ipynb

Models loaded:
  m1_overrun_classifier.pkl  — XGBoost/GradientBoosting  → Overrun_Class (0–6 days)
  m3_delay_classifier.pkl    — XGBoost/GradientBoosting  → Delay_Binary (0/1)
  le_priority.pkl            — LabelEncoder (Priority_Level)
  le_buyer.pkl               — LabelEncoder (Buyer_Name)
  le_plant.pkl               — LabelEncoder (Plant_Name)

Changes from v5:
  - Dataset: component1_balanced_corrected.xlsx used for training
      * 26 synthetic No Urgency Delayed rows corrected to On Time
      * 8 synthetic rows with wrong priority label corrected (buffer<=6 → Medium/Low)
  - M2 classifier fully removed — plant assignment via rule-based scorer only
      * Quality_Rating leaked plant identity (6 unique values = 6 plants)
      * Cap_* features were post-assignment — circular leakage
  - M3 feature vector cleaned — removed all post-outcome features:
      * Is_Overtime removed  (derived from Shipment_Status — direct label leak)
      * Buffer_Days removed  (encodes outcome urgency — high leak corr=-0.70)
      * Priority_Enc removed (derived from Buffer_Days — indirect leak)
      * Buffer_Ratio removed (derived from Buffer_Days — indirect leak)
      * Time_Pressure removed (derived from Buffer_Days — indirect leak)
      * Cap_Time_Pressure removed (derived from Time_Pressure — indirect leak)
      * Is_Emergency removed (derived from Buffer_Days + Priority — indirect leak)
      * Plant_Enc removed   (post-assignment info)
      * Quality_Rating removed (plant fingerprint — same as M2 leak)
  - M1 feature vector cleaned — same leaking features removed as M3
  - actual_overrun_days added to response: max(0, final_ship - buyer_required_date)
  - met_buyer_date added to response: True if final_ship <= buyer_required_date
  - Version bumped to v6

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
BASE_DIR   = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MODELS_DIR = os.path.join(BASE_DIR, "models")

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

# ── M1 Rule-Based Overrun Predictor ───────────────────────────────────
# Thresholds derived from 2024 real data Pressure_Score distributions.
# Pressure_Score = (sample_qty / 9.0) * (util_pct / 100)
M1_THRESHOLDS = {
    "T01": 0.35,   # On Time    → 1-day overrun
    "T12": 0.56,   # 1-day      → 2-day overrun
    "T23": 0.83,   # 2-day      → 3-day overrun
    "T34": 1.00,   # 3-day      → 4+ day overrun
}

def _m1_predict_overrun_class(pressure_score: float) -> int:
    """Rule-based M1: predicts overrun class from Pressure_Score.
    Always monotonically non-decreasing with pressure_score.
    """
    t = M1_THRESHOLDS
    if pressure_score < t["T01"]:   return 0   # On Time
    elif pressure_score < t["T12"]: return 1   # 1-day overrun
    elif pressure_score < t["T23"]: return 2   # 2-day overrun
    elif pressure_score < t["T34"]: return 3   # 3-day overrun
    else:                           return 4   # 4+ day overrun


# ── Lazy loaders ───────────────────────────────────────────────────────
_models   = {}
_capacity = {}   # {(plant, date): row}
_cap_df   = None


def _load_models():
    if _models:
        return _models
    try:
        # M1 is now rule-based — no pkl file needed
        _models["m3"] = joblib.load(os.path.join(MODELS_DIR, "m3_delay_classifier.pkl"))
        _models["le_priority"] = joblib.load(os.path.join(MODELS_DIR, "le_priority.pkl"))
        _models["le_buyer"]    = joblib.load(os.path.join(MODELS_DIR, "le_buyer.pkl"))
    except FileNotFoundError as e:
        raise RuntimeError(
            f"Model file not found: {e}. "
            "Run garment_component1_ml_training_v5.ipynb first."
        )
    return _models


def _load_capacity():
    """
    Load capacity data from the SQLite DB (plant_capacity_history table).
    Returns a pandas DataFrame with columns matching the old Excel format,
    or None if the DB has no capacity rows yet.
    """
    global _cap_df
    if _cap_df is not None:
        return _cap_df
    try:
        import sqlite3, os as _os
        db_path = _os.environ.get("DATABASE_PATH", "garment.db")
        conn = sqlite3.connect(db_path)
        df = pd.read_sql_query(
            """
            SELECT p.name AS Plant_Name,
                   pch.record_date      AS Date,
                   pch.utilization_pct  AS Utilization_Pct,
                   pch.free_machine_ratio AS Free_Machine_Ratio,
                   pch.styles_can_do    AS Styles_Can_Do,
                   pch.total_machines   AS Total_Machines
            FROM plant_capacity_history pch
            JOIN plants p ON pch.plant_id = p.id
            """,
            conn,
        )
        conn.close()
        if df.empty:
            return None
        df["Date"] = pd.to_datetime(df["Date"])
        _cap_df = df
        return _cap_df
    except Exception as exc:
        print(f"[C1] Warning: could not load capacity from DB: {exc}")
        return None


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
    sample_qty, completion_days, buyer_name, receive_month, is_q4, is_aug,
    cap_free_machine_ratio, cap_monthly_avg_util, qty_vs_cap_pressure,
    concurrent_high, weekly_load_ratio, models, cap_util_pct=88.0
) -> tuple:
    qty_group  = 0 if sample_qty <= 3 else 1 if sample_qty <= 5 else 2
    confidence = "OK"

    # Buyer encoding
    if buyer_name in ALL_BUYERS:
        try:
            buyer_enc = int(models["le_buyer"].transform([buyer_name])[0])
        except Exception:
            buyer_enc, confidence = 0, "LOW"
    else:
        buyer_enc, confidence = 0, "LOW"

    # 6 features matching M3 training (component1_v11_final.xlsx):
    # Sample_Qty, Qty_vs_Capacity_Pressure, Cap_Utilization_Pct,
    # Cap_Monthly_Avg_Util, Pressure_Score, Buyer_Enc
    util_pct_val   = cap_util_pct
    pressure_score = round(qty_vs_cap_pressure * (util_pct_val / 100.0), 4)

    feat = np.array([[
        sample_qty,              # [0]  Sample_Qty
        qty_vs_cap_pressure,     # [1]  Qty_vs_Capacity_Pressure
        util_pct_val,            # [2]  Cap_Utilization_Pct
        cap_monthly_avg_util,    # [3]  Cap_Monthly_Avg_Util
        pressure_score,          # [4]  Pressure_Score
        buyer_enc,               # [5]  Buyer_Enc
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

# ── Normalised capacity constants ─────────────────────────────────────
# MAX_STYLES_CONSTANT: highest styles_can_do ever recorded across all
# capacity files (2024 + 2026). Used to normalise cap_press to a fixed
# 0.0–1.11 range so the value means the same thing regardless of which
# year's capacity file is loaded at inference.
# *** If a future capacity file shows styles_can_do > 9.0, update this
#     constant, regenerate the dataset, and retrain. ***
MAX_STYLES_CONSTANT = 9.0

# Per-plant utilisation range across all historical capacity files.
# Used to compute concurrent_high as a relative (0–5) signal instead of
# absolute thresholds that break when plant load patterns shift year to year.
# *** Update min/max if a new capacity file extends a plant's range. ***
PLANT_UTIL_RANGE = {
    "Amsral Lanka Enterprises":    {"min": 33.33, "max": 100.0},
    "Dinusha Embroidery":          {"min": 75.00, "max": 100.0},
    "MRC Group":                   {"min": 33.33, "max": 100.0},
    "Regal Image International":   {"min": 33.33, "max": 100.0},
    "Sunrose Lanka (Pvt) Ltd":     {"min": 33.33, "max": 100.0},
    "The Bobbin Group":            {"min": 80.00, "max": 100.0},
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
    # Look up buyer shipment schedule from DB (falls back to Monday/0 if not found)
    try:
        import sqlite3 as _sqlite3, os as _os
        _db = _sqlite3.connect(_os.environ.get("DATABASE_PATH", "garment.db"))
        _row = _db.execute(
            "SELECT shipment_day, shipment_dow_index FROM buyers_config WHERE buyer_name=?",
            (buyer_name,)
        ).fetchone()
        _db.close()
        dow            = _row[1] if _row else BUYER_DOW.get(buyer_name, 0)
        buyer_ship_day = _row[0] if _row else BUYER_SHIPMENT_SCHEDULE.get(buyer_name, "Monday")
    except Exception:
        dow            = BUYER_DOW.get(buyer_name, 0)
        buyer_ship_day = BUYER_SHIPMENT_SCHEDULE.get(buyer_name, "Monday")
    nearest_ship = _next_weekday(est_completion, dow)

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
    # Normalised cap_press: qty / MAX_STYLES_CONSTANT (fixed = 9.0).
    # Produces a stable 0.11-1.11 range regardless of which year's capacity
    # file is loaded — the value always means the same thing to M1.
    qty_vs_cap_pressure = round(sample_qty / MAX_STYLES_CONSTANT, 4)

    # Relative concurrent_high: how busy is this plant vs its own historical
    # range (0 = quietest ever, 5 = busiest ever).
    # Replaces the old absolute threshold approach (>=97->5, >=92->4 ...)
    # which broke when all plants moved into the 93-99% band in 2026.
    util_pct    = cap.get("util_pct", 88.0)
    plant_range = PLANT_UTIL_RANGE.get(assigned_plant, {"min": 33.33, "max": 100.0})
    rel_load    = (util_pct - plant_range["min"]) / max(plant_range["max"] - plant_range["min"], 1.0)
    concurrent_high = int(round(rel_load * 5))

    weekly_load_ratio = round(min((concurrent_high + 2) / max(cap["styles_can_do"] * 5, 1), 3.0), 4)

    # ── Build feature vector ──────────────────────────────────────────
    feat, confidence = _build_feature_vector(
            sample_qty             = sample_qty,
            completion_days        = completion_days,
            buyer_name             = buyer_name,
            receive_month          = receive_month,
            is_q4                  = is_q4,
            is_aug                 = is_aug,
            cap_free_machine_ratio = cap["free_machine_r"],
            cap_monthly_avg_util   = cap_monthly_avg_util,
            qty_vs_cap_pressure    = qty_vs_cap_pressure,
            concurrent_high        = concurrent_high,
            weekly_load_ratio      = weekly_load_ratio,
            models                 = models,
            cap_util_pct           = cap.get("util_pct", 88.0),
        )

    # ── M1: Overrun class prediction ──────────────────────────────────
    # When buffer_days < 0 the order is already infeasible before production
    # starts (est_completion > buyer_req). M1 overrun_class is not meaningful
    # in that case — it answers "how many factory days over est_completion?"
    # which is irrelevant when the schedule itself is broken.
    if feasible:
        # M1 is now rule-based — predicts overrun class from Pressure_Score
        pressure_score = round(qty_vs_cap_pressure * (cap.get("util_pct", 88.0) / 100.0), 4)
        overrun_class  = _m1_predict_overrun_class(pressure_score)
        overrun_label  = OVERRUN_CLASS_LABEL.get(overrun_class, f"{overrun_class}-day overrun")
    else:
        overrun_class = None   # not applicable — infeasible before production
        overrun_label = "N/A — infeasible schedule (est_completion already past buyer_req)"

    # ── M3: Delay probability ─────────────────────────────────────────
    # When infeasible, M3 still runs mechanically but its answer is meaningless
    # because it has no feature for buffer_days (removed as a leak).
    # It would say "On Time" based on factory conditions alone, ignoring the
    # fact the schedule is already broken. Suppress it when infeasible.
    if feasible:
        # M3 now predicts Is_Overtime (factory ran late vs estimate)
        # NOT Delay_Binary (buyer date miss) — that was buffer-driven (leakage)
        # overtime_prob = P(factory finishes AFTER estimated completion date)
        overtime_prob = float(models["m3"].predict_proba(feat)[0][1])
        delay_pred    = "Overtime likely" if overtime_prob >= 0.5 else "On Time"
        # Buyer impact is computed separately via actual_overrun_days (pure arithmetic)
    else:
        overtime_prob = None
        delay_pred    = "Infeasible — schedule already broken before production starts"
    # Keep delay_prob as alias for backward compatibility
    delay_prob = overtime_prob

    # ── Final shipment date ───────────────────────────────────────────
    if feasible and overrun_class is not None:
        actual_completion = est_completion + timedelta(days=overrun_class)
        final_ship        = _next_weekday(actual_completion, dow)
    else:
        # Infeasible: nearest possible shipment is still nearest_ship
        actual_completion = est_completion
        final_ship        = nearest_ship

    # Actual overrun vs buyer required date (0 = within window)
    # Split into two parts for clarity:
    #   scheduling_gap: days est_completion is already past buyer_req (buffer < 0 → abs value)
    #   factory_overrun: additional days M1 predicts beyond est_completion
    scheduling_gap  = max(0, (est_completion - buyer_req).days)
    factory_overrun = overrun_class if overrun_class is not None else 0
    actual_overrun_days = max(0, (final_ship - buyer_req).days)
    met_buyer_date      = actual_overrun_days == 0

    # ── Planning logic (Steps 10–12) ──────────────────────────────────
    # IMPORTANT: M1 and M3 have no knowledge of buffer_days (removed as leak).
    # They assess factory stress conditions only.
    # A stressed factory (concurrent=5, August) will always look like class 3-4
    # to M1 regardless of whether the buffer is 1 day or 69 days.
    # The actual risk to the buyer is captured by actual_overrun_days and
    # met_buyer_date — these must be the primary planning decision drivers.
    #
    # Rule: if the buyer date is met (actual_overrun_days=0), the M1/M3
    # raw predictions are informational only — they describe factory stress,
    # not buyer impact. The planning action must reflect the ACTUAL outcome.

    if not feasible:
        allocation_remark  = "Cannot complete within buyer required date"
        action_required    = "Adjust Plan / Inform Buyer / Reassign Plant if possible"
        buyer_approval     = "Waiting for Buyer Approval"
        final_ship_str     = None

    elif not met_buyer_date:
        allocation_remark  = "Shipment delayed — waiting for buyer approval"
        action_required    = "Inform Buyer / Obtain Approval"
        buyer_approval     = "Waiting for Buyer Approval"
        final_ship_str     = final_ship.strftime("%Y-%m-%d")

    elif met_buyer_date and buffer_days > 6:
        # No Urgency / Low priority: buffer is large enough to absorb any factory
        # overrun M1 predicts. The buyer date is safe regardless of factory stress.
        # M1/M3 warnings here are factory monitoring signals, not buyer risk alerts.
        if overtime_prob is not None and overtime_prob >= 0.5 and overrun_class is not None and overrun_class >= 3:
            allocation_remark = (
                f"Normal Allocation — buyer date safe (buffer {buffer_days}d absorbs "                f"predicted {overrun_class}-day factory overrun). Monitor factory load."
            )
            action_required   = "Proceed with plan — monitor factory capacity"
            buyer_approval    = "Not Required"
        else:
            allocation_remark = "Normal Allocation"
            action_required   = "Proceed with plan"
            buyer_approval    = "Not Required"
        final_ship_str = final_ship.strftime("%Y-%m-%d")

    elif met_buyer_date and buffer_days <= 6 and overtime_prob is not None and overtime_prob >= 0.5:
        # Tight buffer but still within date — genuine risk worth monitoring
        allocation_remark  = "Delay risk flagged — monitor closely"
        action_required    = "Monitor Progress / Pre-alert Buyer"
        buyer_approval     = "Not Required (within date)"
        final_ship_str     = final_ship.strftime("%Y-%m-%d")

    else:
        allocation_remark  = "Normal Allocation"
        action_required    = "Proceed with plan"
        buyer_approval     = "Not Required"
        final_ship_str     = final_ship.strftime("%Y-%m-%d")

    # ── Risk level ────────────────────────────────────────────────────
    # Risk level is driven by ACTUAL buyer impact (actual_overrun_days),
    # not by raw M1 class. Buffer and feasibility determine operational urgency.
    if buffer_days < 0:
        risk_level = "Critical"           # already missed before production
    elif buffer_days <= 1:
        risk_level = "High"               # one day to absorb any delay
    elif buffer_days <= 3:
        risk_level = "Medium"             # tight but manageable
    elif buffer_days <= 6:
        risk_level = "Low"                # some buffer available
    else:
        risk_level = "Safe"               # large buffer — buyer date not at risk

    risk_summary = (
        f"Buffer {buffer_days}d | priority {priority} | "
        f"M1 factory overrun {overrun_class if overrun_class is not None else 'N/A (infeasible)'} ({overrun_label}) | scheduling gap {scheduling_gap}d | "
        f"actual overrun vs buyer date {actual_overrun_days}d | "
        f"M3 overtime probability {round(overtime_prob * 100, 1) if overtime_prob is not None else 'N/A (infeasible)'}% | "
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
            "overrun_class":        overrun_class,
            "overrun_days":         overrun_class,
            "interpretation":       overrun_label,
            "scheduling_gap_days":  scheduling_gap,
            "factory_overrun_days": factory_overrun,
            "actual_overrun_days":  actual_overrun_days,
            "met_buyer_date":       met_buyer_date,
        },

        "model2_plant_selection": {
            "recommended_plant": assigned_plant,
            "location":          PLANT_LOCATIONS.get(assigned_plant, ""),
            "live_util_pct":     plant_scores[0]["live_util_pct"],
            "live_styles_can_do":plant_scores[0]["live_styles_can_do"],
            "composite_score":   plant_scores[0]["composite_score"],
            "all_scores":        plant_scores,
        },

        "model3_factory_overtime": {
            "overtime_probability":  round(overtime_prob, 3) if overtime_prob is not None else None,
            "overtime_prediction":   delay_pred,
            "interpretation":        (
                "Factory will likely run beyond estimated completion — monitor capacity"
                if overtime_prob is not None and overtime_prob >= 0.5
                else "Factory expected to finish within estimated time"
                if overtime_prob is not None
                else "Infeasible — schedule already broken"
            ),
            "buyer_impact":  (
                "Safe — buffer absorbs overrun" if met_buyer_date
                else "At risk — buyer date may be missed"
                if feasible else "Infeasible"
            ),
            "shipment_status": "Infeasible" if not feasible else (
                "Delayed" if not met_buyer_date else "On Time"
            ),
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
        "version":   "v7",
        "status":    "ok",
        "models": [
            "m1_overrun_classifier.pkl",
            "m3_delay_classifier.pkl  — now predicts Is_Overtime (factory late vs estimate)",
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