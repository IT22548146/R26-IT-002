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
from io import BytesIO
from datetime import datetime, timedelta
from flask import Blueprint, current_app, request, jsonify, send_file

from components.component3_features import FEATURES, build_feature_row
from components.component3_historical_import import (
    build_historical_import_preview,
    load_historical_order,
    prediction_inputs_match,
)
from components.component3_early_warning_inference import (
    EarlyWarningModelError,
    MODEL_SPECS as EARLY_WARNING_MODEL_SPECS,
    predict_early_warnings,
)
from components.component3_monitoring import (
    Component3MonitoringStore,
    normalize_monitoring_label_status,
    normalize_monitoring_risk_status,
    normalize_monitoring_verification_status,
)
from components.component3_recovery import (
    build_recovery_plan,
    normalize_recovery_parameters,
)
from components.component3_tracking import (
    Component3TrackingStore,
    TrackingConflictError,
    TrackingNotFoundError,
    normalize_status,
)
from components.component3_training_export import (
    build_verified_training_dataset,
    dataframe_to_csv_bytes,
    dataframe_to_xlsx_bytes,
)

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

PREDICTION_REQUIRED_FIELDS = [
    "bulk_order_id", "style_id", "buyer_name", "allocated_bulk_plant",
    "plant_location", "full_order_qty", "bulk_order_approved_date",
    "buyer_required_date", "total_working_days", "cutting_days",
    "sewing_days", "daily_commitment", "production_date", "working_day_no",
    "plant_daily_output", "daily_damage_qty", "max_daily_damage_qty",
    "machine_breakdown_count", "worker_shortage_count",
    "cumulative_completed_qty",
]

PREDICTION_INTEGER_FIELDS = [
    "full_order_qty", "daily_commitment", "plant_daily_output",
    "daily_damage_qty", "max_daily_damage_qty", "machine_breakdown_count",
    "worker_shortage_count", "cumulative_completed_qty",
    "working_day_no", "total_working_days", "cutting_days", "sewing_days",
]

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

def _get_severity(
    gap_pct: float,
    risk_type: str,
    machine_breakdown_count: int = 0,
    worker_shortage_count: int = 0,
    damage_exceeded: bool = False,
) -> str:
    """Combine the output gap and detected incident into one alert severity."""
    if risk_type == "No Issue":
        return "No Risk"

    if gap_pct <= 0:
        severity = "Minor"
    elif gap_pct <= GAP_MINOR_MAX:
        severity = "Minor"
    elif gap_pct <= GAP_MODERATE_MAX:
        severity = "Moderate"
    else:
        severity = "Critical"

    ranks = {"No Risk": 0, "Minor": 1, "Moderate": 2, "Critical": 3}

    def at_least(minimum: str) -> None:
        nonlocal severity
        if ranks[minimum] > ranks[severity]:
            severity = minimum

    if risk_type == "Quality Issue" or damage_exceeded:
        at_least("Moderate")
    if risk_type in {"Machine Breakdown", "Machine Breakdown Issue"}:
        at_least("Critical" if machine_breakdown_count >= 2 else "Moderate")
    if risk_type == "Worker Issue":
        if worker_shortage_count >= 10:
            at_least("Critical")
        elif worker_shortage_count >= 5:
            at_least("Moderate")
        else:
            at_least("Minor")

    return severity


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
    severity        = _get_severity(
        gap_pct,
        risk_type,
        machine_breakdown_count=machine_breakdown,
        worker_shortage_count=worker_shortage,
        damage_exceeded=ctx["damage_exceeded"],
    )
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

    # The models detect the risk; the deterministic engine calculates a
    # deadline-aware operational response using only declared capacity limits.
    recovery_plan = build_recovery_plan(
        data,
        detected_risk_type=risk_type,
    )

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

        "recovery_plan": recovery_plan,
    }


# ── Request validation & tracking helpers ─────────────────────────

def _validate_prediction_payload(raw_data: object) -> dict:
    if not isinstance(raw_data, dict) or not raw_data:
        raise ValueError("Request body must be valid JSON")

    data = dict(raw_data)
    missing = [field for field in PREDICTION_REQUIRED_FIELDS if field not in data]
    if missing:
        raise ValueError(f"Missing required fields: {missing}")

    try:
        for field in PREDICTION_INTEGER_FIELDS:
            data[field] = int(data[field])
        datetime.strptime(data["production_date"], "%Y-%m-%d")
        datetime.strptime(data["buyer_required_date"], "%Y-%m-%d")
        datetime.strptime(data["bulk_order_approved_date"], "%Y-%m-%d")
    except (ValueError, TypeError) as error:
        raise ValueError(f"Invalid field value: {error}") from error

    if data["daily_commitment"] <= 0:
        raise ValueError("daily_commitment must be > 0")
    if data["full_order_qty"] <= 0:
        raise ValueError("full_order_qty must be > 0")
    if data["total_working_days"] <= 0:
        raise ValueError("total_working_days must be > 0")
    if data["cumulative_completed_qty"] > data["full_order_qty"]:
        raise ValueError("cumulative_completed_qty cannot exceed full_order_qty")

    non_negative_fields = [
        "plant_daily_output", "daily_damage_qty", "max_daily_damage_qty",
        "machine_breakdown_count", "worker_shortage_count",
        "cumulative_completed_qty", "cutting_days", "sewing_days",
    ]
    negative_fields = [field for field in non_negative_fields if data[field] < 0]
    if negative_fields:
        raise ValueError(f"Fields must be >= 0: {negative_fields}")

    if not (1 <= data["working_day_no"] <= data["total_working_days"]):
        raise ValueError(
            "working_day_no must be between 1 and total_working_days"
        )

    try:
        data["recovery_parameters"] = normalize_recovery_parameters(
            data.get("recovery_parameters"),
            worker_shortage_count=data["worker_shortage_count"],
            machine_breakdown_count=data["machine_breakdown_count"],
        )
    except ValueError as error:
        raise ValueError(f"Invalid field value: {error}") from error

    return data


def _tracking_database_path() -> str:
    configured_path = current_app.config.get("COMPONENT3_TRACKING_DB")
    return str(configured_path or os.environ.get(
        "COMPONENT3_TRACKING_DB",
        os.path.join(BASE_DIR, "instance", "component3_tracking.db"),
    ))


def _tracking_store() -> Component3TrackingStore:
    return Component3TrackingStore(_tracking_database_path())


def _monitoring_store() -> Component3MonitoringStore:
    return Component3MonitoringStore(_tracking_database_path())


def _early_warning_models_directory() -> str:
    configured_path = current_app.config.get(
        "COMPONENT3_EARLY_WARNING_MODELS_DIR"
    )
    return str(configured_path or MODELS_DIR)


def _historical_component3_source_path() -> str:
    configured_path = current_app.config.get(
        "COMPONENT3_HISTORICAL_IMPORT_SOURCE"
    )
    return str(
        configured_path
        or os.environ.get(
            "COMPONENT3_HISTORICAL_IMPORT_SOURCE",
            os.path.join(BASE_DIR, "component3_final_preprossed dataset.xlsx"),
        )
    )


def _historical_component2_source_path() -> str:
    configured_path = current_app.config.get(
        "COMPONENT3_COMPONENT2_MASTER_SOURCE"
    )
    return str(
        configured_path
        or os.environ.get(
            "COMPONENT3_COMPONENT2_MASTER_SOURCE",
            os.path.join(BASE_DIR, "component2_bulk_order_aligned_to.xlsx"),
        )
    )


def _attach_early_warning(data: dict, analysis: dict) -> dict:
    """Add optional research warnings without breaking current detection."""
    risk_type = str(analysis["risk_detection"]["risk_type"])
    try:
        history = _monitoring_store().inference_history(
            str(data["bulk_order_id"]),
            before_working_day=int(data["working_day_no"]),
            before_production_date=str(data["production_date"]),
        )
        early_warning = predict_early_warnings(
            data,
            current_risk_type=risk_type,
            history=history,
            models_directory=_early_warning_models_directory(),
        )
    except EarlyWarningModelError as error:
        current_app.logger.warning("Early-warning unavailable: %s", error)
        early_warning = {
            "inference_version": "component3-early-warning-inference-v1",
            "status": "unavailable",
            "production_approved": False,
            "horizon_production_days": 3,
            "current_risk_type": risk_type,
            "alert_generated": False,
            "highest_warning": None,
            "warnings": [],
            "history": None,
            "message": str(error),
            "limitations": [
                "Current-day detection and recovery planning remain available."
            ],
        }
    analysis["early_warning"] = early_warning
    return analysis


def _build_complete_response(data: dict, models: dict) -> dict:
    return _attach_early_warning(data, _build_response(data, models))


def _required_text(data: dict, field: str) -> str:
    value = data.get(field)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} is required and must be a non-empty string")
    return value.strip()


def _optional_text(data: dict, field: str) -> str | None:
    value = data.get(field)
    if value is None or value == "":
        return None
    if not isinstance(value, str):
        raise ValueError(f"{field} must be a string")
    return value.strip() or None


def _iso_date(data: dict, field: str, *, required: bool = True) -> str | None:
    value = data.get(field)
    if not required and (value is None or value == ""):
        return None
    if not isinstance(value, str):
        raise ValueError(f"{field} must use YYYY-MM-DD format")
    try:
        datetime.strptime(value, "%Y-%m-%d")
    except ValueError as error:
        raise ValueError(f"{field} must use YYYY-MM-DD format") from error
    return value


def _non_negative_integer(
    data: dict,
    field: str,
    *,
    required: bool = True,
) -> int | None:
    value = data.get(field)
    if not required and (value is None or value == ""):
        return None
    if isinstance(value, bool):
        raise ValueError(f"{field} must be an integer")
    try:
        number = float(value)
    except (TypeError, ValueError) as error:
        raise ValueError(f"{field} must be an integer") from error
    if not math.isfinite(number) or not number.is_integer():
        raise ValueError(f"{field} must be an integer")
    if number < 0:
        raise ValueError(f"{field} must be >= 0")
    return int(number)


def _pagination_args() -> tuple[int, int]:
    try:
        limit = int(request.args.get("limit", 50))
        offset = int(request.args.get("offset", 0))
    except (TypeError, ValueError) as error:
        raise ValueError("limit and offset must be integers") from error
    if not 1 <= limit <= 100:
        raise ValueError("limit must be between 1 and 100")
    if offset < 0:
        raise ValueError("offset must be >= 0")
    return limit, offset


# ── Routes ────────────────────────────────────────────────────────

@component3_bp.route("/health", methods=["GET"])
def health():
    return jsonify({
        "component": "3 — Emergency Situation Detection",
        "status": "ok",
        "configured_model_version": os.environ.get("COMPONENT3_MODEL_VERSION", "v1"),
        "experimental_early_warning_models": len(EARLY_WARNING_MODEL_SPECS),
        "early_warning_production_approved": False,
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
    try:
        data = _validate_prediction_payload(
            request.get_json(force=True, silent=True)
        )
    except ValueError as e:
        return jsonify({"error": str(e)}), 400

    try:
        models = _load_models()
    except RuntimeError as e:
        return jsonify({"error": str(e)}), 503

    try:
        result = _build_complete_response(data, models)
        return jsonify(result), 200
    except Exception as e:
        return jsonify({"error": f"Prediction failed: {str(e)}"}), 500


@component3_bp.route("/monitoring-records", methods=["POST"])
def create_monitoring_record():
    """Run and save one canonical daily record, including stable days."""
    raw_data = request.get_json(force=True, silent=True)
    if not isinstance(raw_data, dict) or not raw_data:
        return jsonify({"error": "Request body must be valid JSON"}), 400

    raw_data = dict(raw_data)
    try:
        recorded_by = _required_text(
            {"recorded_by": raw_data.pop("recorded_by", "System User")},
            "recorded_by",
        )
        data = _validate_prediction_payload(raw_data)
    except ValueError as error:
        return jsonify({"error": str(error)}), 400

    try:
        models = _load_models()
    except RuntimeError as error:
        return jsonify({"error": str(error)}), 503

    try:
        analysis = _build_complete_response(data, models)
        monitoring_record = _monitoring_store().create_record(
            data,
            analysis,
            recorded_by=recorded_by,
        )
    except TrackingConflictError as error:
        return jsonify({"error": str(error)}), 409
    except Exception as error:
        return jsonify({
            "error": f"Daily monitoring record creation failed: {error}"
        }), 500

    return jsonify({
        "status": "success",
        "monitoring_record": monitoring_record,
    }), 201


@component3_bp.route("/monitoring-records", methods=["GET"])
def list_monitoring_records():
    """List stable and emergency daily records with optional filters."""
    try:
        limit, offset = _pagination_args()
        raw_risk_status = request.args.get("risk_status")
        raw_label_status = request.args.get("label_status")
        raw_verification_status = request.args.get("verification_status")
        result = _monitoring_store().list_records(
            bulk_order_id=request.args.get("bulk_order_id") or None,
            risk_status=(
                normalize_monitoring_risk_status(raw_risk_status)
                if raw_risk_status
                else None
            ),
            label_status=(
                normalize_monitoring_label_status(raw_label_status)
                if raw_label_status
                else None
            ),
            verification_status=(
                normalize_monitoring_verification_status(
                    raw_verification_status
                )
                if raw_verification_status
                else None
            ),
            limit=limit,
            offset=offset,
        )
    except ValueError as error:
        return jsonify({"error": str(error)}), 400
    return jsonify(result), 200


@component3_bp.route(
    "/orders/<bulk_order_id>/monitoring-records",
    methods=["GET"],
)
def order_monitoring_history(bulk_order_id: str):
    """Return the daily monitoring sequence for one bulk order."""
    try:
        limit, offset = _pagination_args()
        result = _monitoring_store().list_records(
            bulk_order_id=bulk_order_id,
            limit=limit,
            offset=offset,
        )
    except ValueError as error:
        return jsonify({"error": str(error)}), 400
    return jsonify(result), 200


@component3_bp.route("/monitoring-records/<record_id>", methods=["GET"])
def get_monitoring_record(record_id: str):
    """Return one monitoring record with its canonical input and analysis."""
    try:
        monitoring_record = _monitoring_store().get_record(record_id)
    except TrackingNotFoundError as error:
        return jsonify({"error": str(error)}), 404
    return jsonify({"monitoring_record": monitoring_record}), 200


@component3_bp.route(
    "/monitoring-records/<record_id>/verification",
    methods=["PUT"],
)
def verify_monitoring_record(record_id: str):
    """Confirm the actual daily outcome used for future ground truth."""
    raw_data = request.get_json(force=True, silent=True)
    if not isinstance(raw_data, dict) or not raw_data:
        return jsonify({"error": "Request body must be valid JSON"}), 400

    try:
        actual_emergency = raw_data.get("actual_emergency")
        if not isinstance(actual_emergency, bool):
            raise ValueError("actual_emergency must be true or false")
        verified_by = _required_text(raw_data, "verified_by")
        actual_emergency_type = _optional_text(
            raw_data,
            "actual_emergency_type",
        )
        verification_notes = _optional_text(
            raw_data,
            "verification_notes",
        )
        monitoring_record = _monitoring_store().verify_record(
            record_id,
            actual_emergency=actual_emergency,
            actual_emergency_type=actual_emergency_type,
            verified_by=verified_by,
            verification_notes=verification_notes,
        )
    except ValueError as error:
        return jsonify({"error": str(error)}), 400
    except TrackingNotFoundError as error:
        return jsonify({"error": str(error)}), 404

    return jsonify({
        "status": "success",
        "monitoring_record": monitoring_record,
    }), 200


@component3_bp.route("/historical-import/preview", methods=["GET"])
def historical_import_preview():
    """Audit the bundled retrospective sources without changing the DB."""
    try:
        preview = build_historical_import_preview(
            _historical_component3_source_path(),
            _historical_component2_source_path(),
            _monitoring_store().training_export_snapshot(),
        )
    except (FileNotFoundError, OSError, ValueError) as error:
        return jsonify({"error": str(error)}), 503
    return jsonify(preview), 200


@component3_bp.route("/historical-import", methods=["POST"])
def import_historical_order():
    """Import one historical order after explicit retrospective consent."""
    raw_data = request.get_json(force=True, silent=True)
    if not isinstance(raw_data, dict) or not raw_data:
        return jsonify({"error": "Request body must be valid JSON"}), 400

    try:
        bulk_order_id = _required_text(raw_data, "bulk_order_id")
        if raw_data.get("confirm_retrospective_training_data_reuse") is not True:
            raise ValueError(
                "confirm_retrospective_training_data_reuse must be true"
            )
        verify_outcomes = raw_data.get("verify_historical_outcomes", False)
        if not isinstance(verify_outcomes, bool):
            raise ValueError("verify_historical_outcomes must be true or false")
        imported_by = _required_text(
            {"imported_by": raw_data.get("imported_by", "System User")},
            "imported_by",
        )
        if len(imported_by) > 100:
            raise ValueError("imported_by must be 100 characters or fewer")
        verified_by = None
        if verify_outcomes:
            if raw_data.get("confirm_historical_outcomes_are_actual") is not True:
                raise ValueError(
                    "confirm_historical_outcomes_are_actual must be true "
                    "when automatic verification is requested"
                )
            verified_by = _required_text(raw_data, "verified_by")
            if len(verified_by) > 120:
                raise ValueError("verified_by must be 120 characters or fewer")
        source_records = load_historical_order(
            _historical_component3_source_path(),
            _historical_component2_source_path(),
            bulk_order_id,
        )
    except (FileNotFoundError, OSError) as error:
        return jsonify({"error": str(error)}), 503
    except ValueError as error:
        return jsonify({"error": str(error)}), 400

    try:
        models = _load_models()
    except RuntimeError as error:
        return jsonify({"error": str(error)}), 503

    store = _monitoring_store()
    existing_records = store.training_export_snapshot()
    existing_by_day = {
        (str(record["bulk_order_id"]), int(record["working_day_no"])): record
        for record in existing_records
    }
    existing_by_date = {
        (str(record["bulk_order_id"]), str(record["production_date"])): record
        for record in existing_records
    }
    result = {
        "status": "success",
        "mode": "retrospective_demo",
        "independent_validation": False,
        "bulk_order_id": bulk_order_id,
        "source_rows": len(source_records),
        "imported_rows": 0,
        "existing_matching_rows": 0,
        "verified_rows": 0,
        "already_verified_rows": 0,
        "conflicts": [],
        "processing_errors": [],
    }
    recorded_by = f"Historical Import - {imported_by}"

    for source in source_records:
        payload = source["prediction_input"]
        day_key = (bulk_order_id, int(payload["working_day_no"]))
        date_key = (bulk_order_id, str(payload["production_date"]))
        existing = existing_by_day.get(day_key) or existing_by_date.get(date_key)

        if existing is not None:
            if not prediction_inputs_match(payload, existing["prediction_input"]):
                result["conflicts"].append({
                    "working_day_no": payload["working_day_no"],
                    "production_date": payload["production_date"],
                    "reason": "Existing record has different monitoring values",
                })
                continue
            result["existing_matching_rows"] += 1
            if verify_outcomes:
                if existing["actual_outcome_status"] == "Verified":
                    result["already_verified_rows"] += 1
                elif existing.get("data_origin") == "historical_training_reuse":
                    store.verify_record(
                        existing["record_id"],
                        actual_emergency=source["actual_emergency"],
                        actual_emergency_type=source["actual_emergency_type"],
                        verified_by=str(verified_by),
                        verification_notes=(
                            "Retrospective source outcome from the original "
                            "Component 3 workbook; not independent validation. "
                            f"Recorded source risk: {source['source_risk_type']}."
                        ),
                    )
                    result["verified_rows"] += 1
                else:
                    result["conflicts"].append({
                        "working_day_no": payload["working_day_no"],
                        "production_date": payload["production_date"],
                        "reason": (
                            "Matching record was not created by the historical "
                            "importer and was not auto-verified"
                        ),
                    })
            continue

        try:
            validated = _validate_prediction_payload(payload)
            analysis = _build_complete_response(validated, models)
            analysis["historical_import"] = {
                "mode": "retrospective_demo",
                "independent_validation": False,
                "source_risk_type": source["source_risk_type"],
                "outcome_used_during_prediction": False,
            }
            created = store.create_record(
                validated,
                analysis,
                recorded_by=recorded_by,
                data_origin="historical_training_reuse",
                independent_validation_eligible=False,
            )
            result["imported_rows"] += 1
            existing_by_day[day_key] = created
            existing_by_date[date_key] = created
            if verify_outcomes:
                store.verify_record(
                    created["record_id"],
                    actual_emergency=source["actual_emergency"],
                    actual_emergency_type=source["actual_emergency_type"],
                    verified_by=str(verified_by),
                    verification_notes=(
                        "Retrospective source outcome from the original "
                        "Component 3 workbook; not independent validation. "
                        f"Recorded source risk: {source['source_risk_type']}."
                    ),
                )
                result["verified_rows"] += 1
        except TrackingConflictError as error:
            result["conflicts"].append({
                "working_day_no": payload["working_day_no"],
                "production_date": payload["production_date"],
                "reason": str(error),
            })
        except Exception as error:
            result["processing_errors"].append({
                "working_day_no": payload["working_day_no"],
                "production_date": payload["production_date"],
                "error": str(error),
            })

    if result["processing_errors"]:
        result["status"] = "partial"
    result["limitations"] = [
        "The imported source was used to train the current model artifacts.",
        "This import is a retrospective workflow demo, not independent validation.",
    ]
    return jsonify(result), 200


def _verified_training_export():
    return build_verified_training_dataset(
        _monitoring_store().training_export_snapshot()
    )


@component3_bp.route("/training-dataset-audit", methods=["GET"])
def training_dataset_audit():
    """Return leakage and class-balance evidence for the current export."""
    _, audit = _verified_training_export()
    return jsonify(audit), 200


@component3_bp.route("/training-dataset", methods=["GET"])
def download_training_dataset():
    """Download verified Ready rows as CSV or an audited Excel workbook."""
    export_format = request.args.get("format", "csv").strip().lower()
    if export_format not in {"csv", "xlsx"}:
        return jsonify({"error": "format must be csv or xlsx"}), 400

    dataset, audit = _verified_training_export()
    if dataset.empty:
        return jsonify({
            "error": "No verified Ready rows are available for export",
            "audit": audit,
        }), 409
    if not audit["leakage_controls"]["passed"]:
        return jsonify({
            "error": "Training export failed its leakage controls",
            "audit": audit,
        }), 409

    if export_format == "xlsx":
        content = dataframe_to_xlsx_bytes(dataset, audit)
        mimetype = (
            "application/vnd.openxmlformats-officedocument."
            "spreadsheetml.sheet"
        )
        filename = "component3_verified_training_dataset.xlsx"
    else:
        content = dataframe_to_csv_bytes(dataset)
        mimetype = "text/csv; charset=utf-8"
        filename = "component3_verified_training_dataset.csv"

    response = send_file(
        BytesIO(content),
        mimetype=mimetype,
        as_attachment=True,
        download_name=filename,
        max_age=0,
    )
    response.headers["X-Component3-Export-Rows"] = str(len(dataset))
    response.headers["X-Component3-Export-SHA256"] = audit["dataset"][
        "sha256_csv"
    ]
    response.headers["X-Component3-Training-Ready"] = str(
        audit["primary_target"]["training_ready"]
    ).lower()
    return response


@component3_bp.route("/monitoring-readiness", methods=["GET"])
def monitoring_readiness():
    """Report live early-warning label and grouped-training readiness."""
    return jsonify(_monitoring_store().readiness_summary()), 200


@component3_bp.route("/incidents", methods=["POST"])
def create_incident():
    """Run a canonical analysis and persist it as a trackable incident."""
    raw_data = request.get_json(force=True, silent=True)
    if not isinstance(raw_data, dict) or not raw_data:
        return jsonify({"error": "Request body must be valid JSON"}), 400

    raw_data = dict(raw_data)
    try:
        created_by = _required_text(
            {"created_by": raw_data.pop("created_by", "System User")},
            "created_by",
        )
        data = _validate_prediction_payload(raw_data)
    except ValueError as error:
        return jsonify({"error": str(error)}), 400

    try:
        models = _load_models()
    except RuntimeError as error:
        return jsonify({"error": str(error)}), 503

    try:
        analysis = _build_complete_response(data, models)
        if analysis["recovery_plan"]["recommended_option"] is None:
            return jsonify({
                "error": "The order is already complete and has no recovery "
                "action to track"
            }), 409
        incident = _tracking_store().create_incident(
            data,
            analysis,
            created_by=created_by,
        )
    except TrackingConflictError as error:
        return jsonify({"error": str(error)}), 409
    except Exception as error:
        return jsonify({"error": f"Incident creation failed: {error}"}), 500

    return jsonify({"status": "success", "incident": incident}), 201


@component3_bp.route("/incidents", methods=["GET"])
def list_incidents():
    """List recovery incidents with optional order and workflow filters."""
    try:
        limit, offset = _pagination_args()
        raw_status = request.args.get("status")
        status = normalize_status(raw_status) if raw_status else None
        bulk_order_id = request.args.get("bulk_order_id") or None
        result = _tracking_store().list_incidents(
            bulk_order_id=bulk_order_id,
            status=status,
            limit=limit,
            offset=offset,
        )
    except ValueError as error:
        return jsonify({"error": str(error)}), 400
    return jsonify(result), 200


@component3_bp.route("/orders/<bulk_order_id>/incidents", methods=["GET"])
def order_incident_history(bulk_order_id: str):
    """Return the incident history for one bulk order."""
    try:
        limit, offset = _pagination_args()
        result = _tracking_store().list_incidents(
            bulk_order_id=bulk_order_id,
            limit=limit,
            offset=offset,
        )
    except ValueError as error:
        return jsonify({"error": str(error)}), 400
    return jsonify(result), 200


@component3_bp.route("/incidents/<incident_id>", methods=["GET"])
def get_incident(incident_id: str):
    """Return one incident with its analysis, outcomes, and audit timeline."""
    try:
        incident = _tracking_store().get_incident(incident_id)
    except TrackingNotFoundError as error:
        return jsonify({"error": str(error)}), 404
    return jsonify({"incident": incident}), 200


@component3_bp.route("/incidents/<incident_id>/decision", methods=["POST"])
def approve_incident_decision(incident_id: str):
    """Select and approve one recovery option for a Pending incident."""
    data = request.get_json(force=True, silent=True)
    if not isinstance(data, dict):
        return jsonify({"error": "Request body must be valid JSON"}), 400
    try:
        incident = _tracking_store().approve_decision(
            incident_id,
            selected_option_id=_required_text(data, "selected_option_id"),
            approved_by=_required_text(data, "approved_by"),
            notes=_optional_text(data, "notes"),
        )
    except ValueError as error:
        return jsonify({"error": str(error)}), 400
    except TrackingNotFoundError as error:
        return jsonify({"error": str(error)}), 404
    except TrackingConflictError as error:
        return jsonify({"error": str(error)}), 409
    return jsonify({"status": "success", "incident": incident}), 200


@component3_bp.route("/incidents/<incident_id>/status", methods=["PATCH"])
def update_incident_status(incident_id: str):
    """Advance an approved recovery action through its workflow."""
    data = request.get_json(force=True, silent=True)
    if not isinstance(data, dict):
        return jsonify({"error": "Request body must be valid JSON"}), 400
    try:
        incident = _tracking_store().update_status(
            incident_id,
            new_status=normalize_status(data.get("status")),
            updated_by=_required_text(data, "updated_by"),
            notes=_optional_text(data, "notes"),
        )
    except ValueError as error:
        return jsonify({"error": str(error)}), 400
    except TrackingNotFoundError as error:
        return jsonify({"error": str(error)}), 404
    except TrackingConflictError as error:
        return jsonify({"error": str(error)}), 409
    return jsonify({"status": "success", "incident": incident}), 200


@component3_bp.route("/incidents/<incident_id>/outcomes", methods=["POST"])
def record_incident_outcome(incident_id: str):
    """Record actual production and calculate recovery effectiveness."""
    data = request.get_json(force=True, silent=True)
    if not isinstance(data, dict):
        return jsonify({"error": "Request body must be valid JSON"}), 400
    try:
        actual_daily_output = _non_negative_integer(
            data,
            "actual_daily_output",
        )
        cumulative_completed_qty = _non_negative_integer(
            data,
            "cumulative_completed_qty",
            required=False,
        )

        outcome = _tracking_store().record_outcome(
            incident_id,
            outcome_date=str(_iso_date(data, "outcome_date")),
            actual_daily_output=int(actual_daily_output),
            cumulative_completed_qty=cumulative_completed_qty,
            actual_completion_date=_iso_date(
                data,
                "actual_completion_date",
                required=False,
            ),
            notes=_optional_text(data, "notes"),
            recorded_by=_required_text(data, "recorded_by"),
        )
    except (TypeError, ValueError) as error:
        return jsonify({"error": str(error)}), 400
    except TrackingNotFoundError as error:
        return jsonify({"error": str(error)}), 404
    except TrackingConflictError as error:
        return jsonify({"error": str(error)}), 409
    return jsonify({"status": "success", "outcome": outcome}), 201
