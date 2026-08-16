"""
Component 3 — Emergency Situation Detection & Management
==========================================================
Models loaded:
  c3_model1_risk_type.pkl    — RandomForestClassifier  → Risk Type (7 classes)
  c3_model2_order_risk.pkl   — GradientBoostingClassifier → High / Low order risk

OpenAI removed — response JSON assembled deterministically from model outputs
using the same business rules that were in the OpenAI system prompt.

POST /api/component3/predict
Request body (JSON):
{
    "bulk_order_id":           "BULK0001",
    "style_id":                "AH2495",
    "buyer_name":              "Hirdaramani",
    "allocated_bulk_plant":    "Sunrose Lanka (Pvt) Ltd",
    "plant_location":          "Katubedda",
    "full_order_qty":          46430,
    "bulk_order_approved_date":"2024-06-29",
    "buyer_required_date":     "2024-11-27",
    "total_working_days":      108,
    "cutting_days":            25,
    "sewing_days":             30,
    "daily_commitment":        430,
    "production_date":         "2024-07-02",
    "working_day_no":          2,
    "plant_daily_output":      407,
    "daily_damage_qty":        10,
    "max_daily_damage_qty":    13,
    "machine_breakdown_count": 0,
    "worker_shortage_count":   3,
    "cumulative_completed_qty":845
}
"""

import math
import os
import joblib
from datetime import datetime, timedelta
from flask import Blueprint, request, jsonify

from components.component3_features import FEATURES, build_feature_row

component3_bp = Blueprint("component3", __name__)

# ── Paths ─────────────────────────────────────────────────────────
BASE_DIR   = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MODELS_DIR = os.path.join(BASE_DIR, "models")

# ── Risk type mapping ─────────────────────────────────────────────
RISK_TYPE_MAP = {
    "No Issue":               0,
    "Minor Delay":            1,
    "Working Hours Issue":    2,
    "Worker Issue":           3,
    "Commitment Too Low":     4,
    "Machine Breakdown Issue":5,
    "Quality Issue":          6,
}
RISK_LABELS = list(RISK_TYPE_MAP.keys())

# Gap thresholds (from component3.py flowchart calibration)
GAP_MINOR_MAX    = 5.0
GAP_MODERATE_MAX = 15.0
WORKER_SPLIT_PCT = 8.0

# ── Recommendations ───────────────────────────────────────────────
RECOMMENDATIONS = {
    "No Issue":               "Continue current production plan.",
    "Working Hours Issue":    "Increase working hours or add overtime to recover the small output gap.",
    "Worker Issue":           "Add operators or reassign workers from another line to recover lost pieces.",
    "Machine Breakdown":      "Repair machine immediately and shift remaining output to backup machine/line.",
    "Machine Breakdown Issue":"Repair machine immediately and shift remaining output to backup machine/line.",
    "Quality Issue":          "Check damaged pieces and improve quality inspection before continuing.",
    "Commitment Too Low":     "Daily output is below plan; increase plant working hours to reach actual plan.",
    "Minor Delay":            "Increase line monitoring and add small overtime to recover the daily gap.",
    "Production Failure":     "Immediate escalation required — reallocate order to another plant.",
}

ALERT_TARGETS = {
    "Minor":    ["Supervisor"],
    "Moderate": ["Supervisor", "Production Manager"],
    "Critical": ["Supervisor", "Production Manager", "Top Management"],
}

ACTION_MAP = {
    "No Issue":               "Continue current production plan",
    "Working Hours Issue":    "Increase working hours / Add overtime",
    "Worker Issue":           "Add operators / Reassign workers from another line",
    "Machine Breakdown":      "Repair / Maintain Machine immediately",
    "Machine Breakdown Issue":"Repair / Maintain Machine immediately",
    "Quality Issue":          "Improve QC & Process / Check damaged pieces",
    "Commitment Too Low":     "Increase Working Hours / Efficiency",
    "Minor Delay":            "Increase Working Hours / Efficiency",
    "Production Failure":     "Reallocate to Another Plant",
}

FEATS = FEATURES

# ── Lazy model loader ─────────────────────────────────────────────
_models = {}

MODEL_FILES = {
    "v1": {
        "risk_type": "c3_model1_risk_type.pkl",
        "order_risk": "c3_model2_order_risk.pkl",
    },
    "v2": {
        "risk_type": "c3_model1_risk_type_v2.pkl",
        "order_risk": "c3_model2_order_risk_v2.pkl",
    },
}


def _load_models():
    version = os.environ.get("COMPONENT3_MODEL_VERSION", "v1").strip().lower()
    if version not in MODEL_FILES:
        raise RuntimeError(
            f"Unsupported COMPONENT3_MODEL_VERSION={version!r}; "
            f"expected one of {sorted(MODEL_FILES)}"
        )
    if _models.get("version") == version:
        return _models
    _models.clear()
    missing = []
    for key, fname in MODEL_FILES[version].items():
        path = os.path.join(MODELS_DIR, fname)
        if not os.path.exists(path):
            missing.append(fname)
        else:
            _models[key] = joblib.load(path)
    if missing:
        _models.clear()
        raise RuntimeError(f"Missing model files: {missing}. Run the Component 3 notebook first.")
    _models["version"] = version
    return _models


# ── Severity & helpers ────────────────────────────────────────────

def _get_severity(gap_pct: float) -> str:
    if gap_pct <= 0:          return "No Risk"
    elif gap_pct <= GAP_MINOR_MAX:    return "Minor"
    elif gap_pct <= GAP_MODERATE_MAX: return "Moderate"
    return "Critical"


def _get_alert_colour(severity: str) -> str:
    return {"No Risk": "Green", "Minor": "Yellow",
            "Moderate": "Orange", "Critical": "Red"}.get(severity, "Yellow")


def _gap_severity_label(gap_pct: float) -> str:
    if gap_pct <= 0:          return "No Gap"
    elif gap_pct <= 5:        return "Small Gap"
    elif gap_pct <= 15:       return "Medium Gap"
    return "Large Gap"


def _combine_order_risk(model_level: str, schedule_level: str) -> str:
    """Return the more severe of the ML and schedule-based risk levels."""
    rank = {"Low": 0, "Medium": 1, "High": 2, "Critical": 3}
    return max((model_level, schedule_level), key=lambda level: rank[level])


def _add_working_days(start: datetime, n: int) -> datetime:
    current, added = start, 0
    while added < n:
        current += timedelta(days=1)
        if current.weekday() < 5:
            added += 1
    return current


# ── Feature row builder ───────────────────────────────────────────

def _build_feature_row(daily_commitment, plant_daily_output,
                       machine_breakdown_count, worker_shortage_count,
                       daily_damage_qty, max_daily_damage_qty,
                       working_day_no, total_working_days,
                       cutting_days, sewing_days,
                       remaining_qty, full_order_qty,
                       cumulative_completed_qty) -> tuple:
    """Compatibility wrapper around the shared training/inference builder."""
    expected_remaining = full_order_qty - cumulative_completed_qty
    if remaining_qty != expected_remaining:
        raise ValueError("remaining_qty is inconsistent with cumulative production")
    return build_feature_row(
        daily_commitment=daily_commitment,
        plant_daily_output=plant_daily_output,
        machine_breakdown_count=machine_breakdown_count,
        worker_shortage_count=worker_shortage_count,
        daily_damage_qty=daily_damage_qty,
        max_daily_damage_qty=max_daily_damage_qty,
        working_day_no=working_day_no,
        total_working_days=total_working_days,
        cutting_days=cutting_days,
        sewing_days=sewing_days,
        full_order_qty=full_order_qty,
        cumulative_completed_qty=cumulative_completed_qty,
    )


# ── Deterministic context builder ────────────────────────────────

def _build_context(data: dict) -> dict:
    full_order_qty       = int(data["full_order_qty"])
    daily_commitment     = int(data["daily_commitment"])
    plant_daily_output   = int(data["plant_daily_output"])
    daily_damage_qty     = int(data["daily_damage_qty"])
    max_daily_damage_qty = int(data["max_daily_damage_qty"])
    machine_breakdown    = int(data["machine_breakdown_count"])
    worker_shortage      = int(data["worker_shortage_count"])
    cumulative_done      = int(data["cumulative_completed_qty"])
    working_day_no       = int(data["working_day_no"])
    total_working_days   = int(data["total_working_days"])

    production_date = datetime.strptime(data["production_date"],         "%Y-%m-%d")
    buyer_req_date  = datetime.strptime(data["buyer_required_date"],     "%Y-%m-%d")
    approved_date   = datetime.strptime(data["bulk_order_approved_date"],"%Y-%m-%d")

    bulk_start_date = approved_date + timedelta(days=7)

    output_gap     = daily_commitment - plant_daily_output
    gap_pct        = round((output_gap / daily_commitment) * 100, 2) if daily_commitment > 0 else 0.0
    remaining_qty  = full_order_qty - cumulative_done
    days_remaining = math.ceil(remaining_qty / max(daily_commitment, 1))

    projected_completion = _add_working_days(production_date, days_remaining)
    days_to_deadline     = (buyer_req_date - projected_completion).days
    on_track             = days_to_deadline >= 0
    completion_pct       = round((cumulative_done / full_order_qty) * 100, 2) if full_order_qty > 0 else 0.0
    days_elapsed_pct     = round((working_day_no / total_working_days) * 100, 1)
    progress_gap_pct     = round(completion_pct - days_elapsed_pct, 2)

    if days_to_deadline < -3 or progress_gap_pct < -15:
        order_risk_level = "Critical"
    elif days_to_deadline < 0 or progress_gap_pct < -5:
        order_risk_level = "High"
    elif days_to_deadline < 3 or progress_gap_pct < 0:
        order_risk_level = "Medium"
    else:
        order_risk_level = "Low"

    damage_exceeded = daily_damage_qty > max_daily_damage_qty
    damage_pct_comm = round((daily_damage_qty / daily_commitment) * 100, 2) if daily_commitment > 0 else 0.0

    return {
        "bulk_start_date":           bulk_start_date.strftime("%Y-%m-%d"),
        "production_date":           production_date.strftime("%Y-%m-%d"),
        "buyer_required_date":       buyer_req_date.strftime("%Y-%m-%d"),
        "projected_completion_date": projected_completion.strftime("%Y-%m-%d"),
        "days_to_deadline":          days_to_deadline,
        "on_track":                  on_track,
        "output_gap":                output_gap,
        "gap_pct":                   gap_pct,
        "remaining_qty":             remaining_qty,
        "completion_pct":            completion_pct,
        "days_elapsed_pct":          days_elapsed_pct,
        "progress_gap_pct":          progress_gap_pct,
        "order_risk_level":          order_risk_level,
        "working_days_remaining":    days_remaining,
        "damage_exceeded":           damage_exceeded,
        "damage_pct_of_commitment":  damage_pct_comm,
    }


# ── Deterministic response builder (replaces OpenAI) ─────────────

def _build_response(data: dict, models: dict) -> dict:
    """
    Assembles the full daily monitoring JSON using ML model outputs +
    deterministic rules. Mirrors the exact schema from the OpenAI system prompt.
    """
    bulk_order_id        = data.get("bulk_order_id", "N/A")
    style_id             = data.get("style_id", "N/A")
    buyer_name           = data.get("buyer_name", "N/A")
    allocated_bulk_plant = data.get("allocated_bulk_plant", "N/A")
    plant_location       = data.get("plant_location", "N/A")
    working_day_no       = int(data["working_day_no"])
    total_working_days   = int(data["total_working_days"])
    cutting_days         = int(data["cutting_days"])
    sewing_days          = int(data["sewing_days"])
    full_order_qty       = int(data["full_order_qty"])
    daily_commitment     = int(data["daily_commitment"])
    plant_daily_output   = int(data["plant_daily_output"])
    daily_damage_qty     = int(data["daily_damage_qty"])
    max_daily_damage_qty = int(data["max_daily_damage_qty"])
    machine_breakdown    = int(data["machine_breakdown_count"])
    worker_shortage      = int(data["worker_shortage_count"])
    cumulative_done      = int(data["cumulative_completed_qty"])

    remaining_qty = full_order_qty - cumulative_done
    ctx           = _build_context(data)

    # ── Feature row for pkl models ────────────────────────────
    row, gap_pct = _build_feature_row(
        daily_commitment, plant_daily_output,
        machine_breakdown, worker_shortage,
        daily_damage_qty, max_daily_damage_qty,
        working_day_no, total_working_days,
        cutting_days, sewing_days,
        remaining_qty, full_order_qty, cumulative_done
    )

    # ── Model 1: Risk type ────────────────────────────────────
    risk_type_enc    = int(models["risk_type"].predict(row[FEATS])[0])
    risk_type        = RISK_LABELS[risk_type_enc]
    risk_proba       = models["risk_type"].predict_proba(row[FEATS])[0]
    risk_confidence  = float(risk_proba[risk_type_enc])

    # ── Model 2: Order risk level ─────────────────────────────
    order_risk_prob  = float(models["order_risk"].predict_proba(row[FEATS])[0][1])
    order_risk       = "High" if order_risk_prob >= 0.5 else "Low"

    # ── Rule-based outputs ────────────────────────────────────
    output_gap_val  = daily_commitment - plant_daily_output
    severity        = _get_severity(gap_pct)
    alert_colour    = _get_alert_colour(severity)
    recommendation  = RECOMMENDATIONS.get(risk_type, RECOMMENDATIONS["Commitment Too Low"])
    action_required = ACTION_MAP.get(risk_type, "Continue current production plan")
    alert_to        = ALERT_TARGETS.get(severity, [])
    risk_status     = "No Risk" if risk_type == "No Issue" else "Risk"
    alert_generated = risk_status == "Risk"

    # Combine the binary ML result with the more detailed schedule-based result.
    # The final result always reflects the more severe of the two assessments.
    schedule_order_risk = ctx["order_risk_level"]
    final_order_risk = _combine_order_risk(order_risk, schedule_order_risk)

    # ── Scheduling fields ─────────────────────────────────────
    output_gap_f      = float(row["Output_Gap"].iloc[0])
    days_remaining_f  = int(row["Days_Remaining"].iloc[0])
    day_progress_f    = float(row["Day_Progress_Pct"].iloc[0])
    req_daily_rate_f  = float(row["Required_Daily_Rate"].iloc[0])

    progress_summary = (
        f"{ctx['completion_pct']:.1f}% complete at day {working_day_no}/{total_working_days} "
        f"({ctx['progress_gap_pct']:+.1f}% vs expected); "
        f"{'on track' if ctx['on_track'] else 'behind schedule'} — "
        f"{ctx['days_to_deadline']} day(s) {'buffer' if ctx['days_to_deadline'] >= 0 else 'overdue'} to deadline."
    )

    return {
        "status":              "success",
        "model_version":       models.get("version", "unknown"),
        "bulk_order_id":       bulk_order_id,
        "style_id":            style_id,
        "buyer_name":          buyer_name,
        "allocated_bulk_plant":allocated_bulk_plant,
        "plant_location":      plant_location,
        "working_day_no":      working_day_no,
        "production_date":     data["production_date"],

        "order_summary": {
            "full_order_qty":           full_order_qty,
            "daily_commitment":         daily_commitment,
            "cumulative_completed_qty": cumulative_done,
            "remaining_qty":            remaining_qty,
            "completion_pct":           ctx["completion_pct"],
            "total_working_days":       total_working_days,
            "cutting_days":             cutting_days,
            "sewing_days":              sewing_days,
        },

        "daily_production": {
            "plant_daily_output":      plant_daily_output,
            "daily_commitment":        daily_commitment,
            "output_gap":              int(output_gap_f),
            "gap_pct":                 round(gap_pct, 2),
            "daily_damage_qty":        daily_damage_qty,
            "max_daily_damage_qty":    max_daily_damage_qty,
            "damage_exceeded":         ctx["damage_exceeded"],
            "damage_pct_of_commitment":ctx["damage_pct_of_commitment"],
            "machine_breakdown_count": machine_breakdown,
            "worker_shortage_count":   worker_shortage,
        },

        "risk_detection": {
            "risk_status":       risk_status,
            "risk_type":         risk_type,
            "risk_confidence":   round(risk_confidence, 3),
            "severity":          severity if alert_generated else None,
            "alert_colour":      alert_colour,
            "gap_severity_label":_gap_severity_label(gap_pct),
            "order_risk_level":  final_order_risk,
            "ml_order_risk_level": order_risk,
            "schedule_order_risk_level": schedule_order_risk,
            "order_risk_probability": round(order_risk_prob, 3),
            "recommendation":    recommendation,
        },

        "alert_system": {
            "alert_generated": alert_generated,
            "alert_targets":   alert_to,
            "notify_via":      ["System", "Email", "Dashboard"] if alert_generated else [],
            "display_on":      ["Dashboard", "Mobile App"],
        },

        "scheduling": {
            "bulk_order_approved_date":  data["bulk_order_approved_date"],
            "bulk_start_date":           ctx["bulk_start_date"],
            "buyer_required_date":       ctx["buyer_required_date"],
            "projected_completion_date": ctx["projected_completion_date"],
            "days_to_deadline":          ctx["days_to_deadline"],
            "working_days_remaining":    ctx["working_days_remaining"],
            "on_track":                  ctx["on_track"],
        },

        "order_progress": {
            "order_risk_level":  final_order_risk,
            "ml_order_risk_level": order_risk,
            "schedule_order_risk_level": schedule_order_risk,
            "completion_pct":    ctx["completion_pct"],
            "days_elapsed_pct":  ctx["days_elapsed_pct"],
            "progress_gap_pct":  ctx["progress_gap_pct"],
            "progress_summary":  progress_summary,
        },

        "production_summary": {
            "daily_commitment":     daily_commitment,
            "actual_output":        plant_daily_output,
            "output_gap":           int(output_gap_f),
            "gap_pct":              round(gap_pct, 2),
            "required_daily_rate":  round(req_daily_rate_f, 1),
            "cumulative_completed": cumulative_done,
            "remaining_qty":        remaining_qty,
        },

        "action": {
            "recommendation":  recommendation,
            "action_required": action_required,
            "escalation_needed": severity == "Critical",
            "alert_recipients":  alert_to,
            "notify_channels":  (
                ["System", "Email", "Dashboard", "Mobile App"]
                if severity == "Critical" else ["System", "Dashboard"]
            ),
            "next_step":            "Monitor Next Production Day",
            "store_for_ml_training": True,
        },

        "planning_output": {
            "action_required":       action_required,
            "escalation_needed":     severity == "Critical",
            "next_step":             "Monitor Next Production Day",
            "store_for_ml_training": True,
        },
    }


# ── Routes ────────────────────────────────────────────────────────

@component3_bp.route("/health", methods=["GET"])
def health():
    return jsonify({
        "component": "3 — Emergency Situation Detection",
        "status": "ok",
        "configured_model_version": os.environ.get("COMPONENT3_MODEL_VERSION", "v1"),
    })


@component3_bp.route("/predict", methods=["POST"])
def predict():
    """
    Daily production monitoring endpoint.

    Required fields:
        bulk_order_id, style_id, buyer_name, allocated_bulk_plant,
        plant_location, full_order_qty, bulk_order_approved_date,
        buyer_required_date, total_working_days, cutting_days,
        sewing_days, daily_commitment, production_date, working_day_no,
        plant_daily_output, daily_damage_qty, max_daily_damage_qty,
        machine_breakdown_count, worker_shortage_count, cumulative_completed_qty
    """
    data = request.get_json(force=True, silent=True)
    if not data:
        return jsonify({"error": "Request body must be valid JSON"}), 400

    required = [
        "bulk_order_id", "style_id", "buyer_name", "allocated_bulk_plant",
        "plant_location", "full_order_qty", "bulk_order_approved_date",
        "buyer_required_date", "total_working_days", "cutting_days",
        "sewing_days", "daily_commitment", "production_date", "working_day_no",
        "plant_daily_output", "daily_damage_qty", "max_daily_damage_qty",
        "machine_breakdown_count", "worker_shortage_count", "cumulative_completed_qty",
    ]
    missing = [f for f in required if f not in data]
    if missing:
        return jsonify({"error": f"Missing required fields: {missing}"}), 400

    try:
        int_fields = [
            "full_order_qty", "daily_commitment", "plant_daily_output",
            "daily_damage_qty", "max_daily_damage_qty", "machine_breakdown_count",
            "worker_shortage_count", "cumulative_completed_qty",
            "working_day_no", "total_working_days", "cutting_days", "sewing_days",
        ]
        for f in int_fields:
            data[f] = int(data[f])
        datetime.strptime(data["production_date"],          "%Y-%m-%d")
        datetime.strptime(data["buyer_required_date"],      "%Y-%m-%d")
        datetime.strptime(data["bulk_order_approved_date"], "%Y-%m-%d")
    except (ValueError, TypeError) as e:
        return jsonify({"error": f"Invalid field value: {e}"}), 400

    if data["daily_commitment"] <= 0:
        return jsonify({"error": "daily_commitment must be > 0"}), 400
    if data["full_order_qty"] <= 0:
        return jsonify({"error": "full_order_qty must be > 0"}), 400
    if data["total_working_days"] <= 0:
        return jsonify({"error": "total_working_days must be > 0"}), 400

    non_negative_fields = [
        "plant_daily_output", "daily_damage_qty", "max_daily_damage_qty",
        "machine_breakdown_count", "worker_shortage_count",
        "cumulative_completed_qty", "cutting_days", "sewing_days",
    ]
    negative_fields = [field for field in non_negative_fields if data[field] < 0]
    if negative_fields:
        return jsonify({
            "error": f"Fields must be >= 0: {negative_fields}"
        }), 400

    if not (1 <= data["working_day_no"] <= data["total_working_days"]):
        return jsonify({"error": "working_day_no must be between 1 and total_working_days"}), 400

    try:
        models = _load_models()
    except RuntimeError as e:
        return jsonify({"error": str(e)}), 503

    try:
        result = _build_response(data, models)
        return jsonify(result), 200
    except Exception as e:
        return jsonify({"error": f"Prediction failed: {str(e)}"}), 500
