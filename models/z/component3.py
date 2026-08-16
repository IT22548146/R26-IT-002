"""
Component 3 — Emergency Situation Detection & Daily Production Monitoring
=========================================================================
OpenAI-powered drop-in Flask Blueprint.

Follows the Component 3 flow diagram exactly:
  1.  Get Style_ID from Component 2
  2.  Get Bulk Order Approved Date
  3.  Calculate Bulk Start Date (Approved + 7 days)
  4.  Start Daily Production Monitoring loop
  5.  Get Daily Commitment
  6.  Get Actual Output
  7.  Calculate Output Gap  = Daily_Commitment - Plant_Daily_Output
  8.  Is Actual Output >= Daily Commitment?  →  No Risk
  9.  Check Machine Breakdown Count > 0     →  Machine Breakdown Issue
  10. Check Worker Shortage Count > 0       →  Working Hours Issue / Worker Issue
  11. Check Damage > Max Damage Threshold   →  Quality Issue
  12. Evaluate Output Gap %                 →  Commitment Too Low / Production Failure

Severity (from flowchart):
  Minor    : gap_pct  0 – 5%
  Moderate : gap_pct  5 – 15%
  Critical : gap_pct > 15%

Risk types (calibrated from 108-row dataset):
  No Issue            → gap <= 0 (output meets or exceeds commitment)
  Machine Breakdown   → machine_breakdown_count > 0
  Working Hours Issue → worker_shortage > 0  AND  gap_pct < 8%   (Minor)
  Worker Issue        → worker_shortage > 0  AND  gap_pct >= 8%  (Moderate/Critical)
  Quality Issue       → daily_damage > max_daily_damage  (no breakdown/worker flag)
  Commitment Too Low  → no specific cause AND gap_pct >= 15%

Alert targets:
  Minor    → Supervisor
  Moderate → Supervisor + Production Manager
  Critical → Supervisor + Production Manager + Top Management

Blueprint:  component3_bp
Routes:
  GET  /api/component3/health
  POST /api/component3/predict

POST /api/component3/predict — request body:
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

Setup:
    pip install flask openai
    export OPENAI_API_KEY="sk-..."
"""

import json
import math
import os
from datetime import datetime, timedelta

from flask import Blueprint, request, jsonify
from openai import OpenAI

# ── Flask Blueprint ───────────────────────────────────────────────
component3_bp = Blueprint("component3", __name__)

# ── OpenAI client ─────────────────────────────────────────────────
_openai_client = None

def _get_client():
    global _openai_client
    if _openai_client is None:
        api_key = os.environ.get("OPENAI_API_KEY")
        if not api_key:
            raise RuntimeError("OPENAI_API_KEY environment variable is not set.")
        _openai_client = OpenAI(api_key=api_key)
    return _openai_client


# ── Risk detection constants (calibrated from 108-row dataset) ────

# Gap percentage thresholds
GAP_MINOR_MAX    = 5.0    # 0–5%   → Minor
GAP_MODERATE_MAX = 15.0   # 5–15%  → Moderate
# >15% → Critical

# Working Hours Issue vs Worker Issue split point (from data: WH max gap_pct = 8.14%)
WORKER_SPLIT_PCT = 8.0

# Recommendations — exact strings from dataset
RECOMMENDATIONS = {
    "No Issue":               "Continue current production plan.",
    "Working Hours Issue":    "Increase working hours or add overtime to recover the small output gap.",
    "Worker Issue":           "Add operators or reassign workers from another line to recover lost pieces.",
    "Machine Breakdown":      "Repair machine immediately and shift remaining output to backup machine/line.",
    "Quality Issue":          "Check damaged pieces and improve quality inspection before continuing.",
    "Commitment Too Low":     "Daily output is below plan; increase plant working hours to reach actual plan.",
    "Production Failure":     "Immediate escalation required — reallocate order to another plant.",
}

# Alert targets per severity
ALERT_TARGETS = {
    "Minor":    ["Supervisor"],
    "Moderate": ["Supervisor", "Production Manager"],
    "Critical": ["Supervisor", "Production Manager", "Top Management"],
}


# ── Core deterministic logic ──────────────────────────────────────

def _detect_risk(output_gap: int, gap_pct: float,
                 machine_breakdown: int, worker_shortage: int,
                 daily_damage: int, max_damage: int) -> dict:
    """
    Implements flowchart steps 8–12 exactly.

    Step 8:  gap <= 0  →  No Risk
    Step 9:  machine_breakdown > 0  →  Machine Breakdown
    Step 10: worker_shortage > 0    →  Working Hours Issue (gap<8%) or Worker Issue (gap>=8%)
    Step 11: daily_damage > max     →  Quality Issue
    Step 12: evaluate gap_pct       →  Commitment Too Low / Production Failure
    """
    # Step 11 FIRST — quality/damage check runs regardless of gap
    # (Dataset: Quality Issue had gap_pct=-1.4%, output > commitment but damage exceeded)
    if daily_damage > max_damage:
        # Severity based on abs gap if output is below plan, else Minor
        dmg_sev = "Minor" if gap_pct <= GAP_MINOR_MAX else "Moderate" if gap_pct <= GAP_MODERATE_MAX else "Critical"
        dmg_sev = "Minor" if gap_pct <= 0 else dmg_sev   # output ok but damage high = Minor alert
        return {
            "risk_detected":  True,
            "risk_status":    "Risk",
            "risk_type":      "Quality Issue",
            "severity":       dmg_sev,
            "alert_targets":  ALERT_TARGETS[dmg_sev],
            "recommendation": RECOMMENDATIONS["Quality Issue"],
        }

    # Step 8 — no shortfall and no damage issue
    if output_gap <= 0:
        return {
            "risk_detected":    False,
            "risk_status":      "No Risk",
            "risk_type":        "No Issue",
            "severity":         None,
            "alert_targets":    [],
            "recommendation":   RECOMMENDATIONS["No Issue"],
        }

    # Severity from gap percentage (for steps 9, 10, 12)
    if gap_pct <= GAP_MINOR_MAX:
        severity = "Minor"
    elif gap_pct <= GAP_MODERATE_MAX:
        severity = "Moderate"
    else:
        severity = "Critical"

    # Step 9 — machine breakdown
    if machine_breakdown > 0:
        risk_type = "Machine Breakdown"
        return {
            "risk_detected":  True,
            "risk_status":    "Risk",
            "risk_type":      risk_type,
            "severity":       severity,
            "alert_targets":  ALERT_TARGETS[severity],
            "recommendation": RECOMMENDATIONS[risk_type],
        }

    # Step 10 — worker shortage
    if worker_shortage > 0:
        risk_type = "Working Hours Issue" if gap_pct < WORKER_SPLIT_PCT else "Worker Issue"
        return {
            "risk_detected":  True,
            "risk_status":    "Risk",
            "risk_type":      risk_type,
            "severity":       severity,
            "alert_targets":  ALERT_TARGETS[severity],
            "recommendation": RECOMMENDATIONS[risk_type],
        }

    # Step 12 — output gap evaluation (no specific root cause identified)
    if gap_pct > GAP_MODERATE_MAX:
        risk_type = "Commitment Too Low" if gap_pct <= 25.0 else "Production Failure"
    else:
        risk_type = "Commitment Too Low"

    return {
        "risk_detected":  True,
        "risk_status":    "Risk",
        "risk_type":      risk_type,
        "severity":       severity,
        "alert_targets":  ALERT_TARGETS[severity],
        "recommendation": RECOMMENDATIONS.get(risk_type, RECOMMENDATIONS["Commitment Too Low"]),
    }


def _build_context(data: dict) -> dict:
    """Pre-compute all deterministic values before calling OpenAI."""

    # Order-level fields
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

    production_date      = datetime.strptime(data["production_date"],         "%Y-%m-%d")
    buyer_req_date       = datetime.strptime(data["buyer_required_date"],      "%Y-%m-%d")
    approved_date        = datetime.strptime(data["bulk_order_approved_date"], "%Y-%m-%d")

    # Step 3: bulk start date = approved + 7 days
    bulk_start_date      = approved_date + timedelta(days=7)

    # Step 7: output gap = commitment - actual (positive = shortfall)
    output_gap           = daily_commitment - plant_daily_output
    gap_pct              = round((output_gap / daily_commitment) * 100, 2) if daily_commitment > 0 else 0.0

    # Remaining quantity
    remaining_qty        = full_order_qty - cumulative_done

    # Projected completion: add remaining working days from production_date
    # (skipping weekends — more accurate than the *7/5 approximation)
    days_remaining = math.ceil(remaining_qty / max(daily_commitment, 1))

    def _add_working_days(start: datetime, n: int) -> datetime:
        current = start
        added   = 0
        while added < n:
            current += timedelta(days=1)
            if current.weekday() < 5:   # Mon–Fri only
                added += 1
        return current

    projected_completion = _add_working_days(production_date, days_remaining)

    # Deadline check
    days_to_deadline     = (buyer_req_date - projected_completion).days
    on_track             = days_to_deadline >= 0

    # Completion percentage
    completion_pct       = round((cumulative_done / full_order_qty) * 100, 2) if full_order_qty > 0 else 0.0

    # Order-level risk level — based on days_to_deadline AND cumulative progress gap
    days_elapsed_pct     = round((working_day_no / total_working_days) * 100, 1)
    expected_done_pct    = days_elapsed_pct   # linear expectation
    progress_gap_pct     = round(completion_pct - expected_done_pct, 2)  # positive = ahead

    if days_to_deadline < -3 or progress_gap_pct < -15:
        order_risk_level = "Critical"
    elif days_to_deadline < 0 or progress_gap_pct < -5:
        order_risk_level = "High"
    elif days_to_deadline < 3 or progress_gap_pct < 0:
        order_risk_level = "Medium"
    else:
        order_risk_level = "Low"

    # Steps 8–12: risk detection
    risk = _detect_risk(output_gap, gap_pct, machine_breakdown,
                        worker_shortage, daily_damage_qty, max_daily_damage_qty)

    # Damage status
    damage_exceeded = daily_damage_qty > max_daily_damage_qty
    damage_pct      = round((daily_damage_qty / daily_commitment) * 100, 2) if daily_commitment > 0 else 0.0

    return {
        # Scheduling
        "bulk_start_date":          bulk_start_date.strftime("%Y-%m-%d"),
        "production_date":          production_date.strftime("%Y-%m-%d"),
        "buyer_required_date":      buyer_req_date.strftime("%Y-%m-%d"),
        "projected_completion_date": projected_completion.strftime("%Y-%m-%d"),
        "days_to_deadline":         days_to_deadline,
        "on_track":                 on_track,

        # Production metrics
        "output_gap":               output_gap,
        "gap_pct":                  gap_pct,
        "cumulative_completed_qty": cumulative_done,
        "remaining_qty":            remaining_qty,
        "completion_pct":           completion_pct,
        "days_elapsed_pct":         days_elapsed_pct,
        "progress_gap_pct":         progress_gap_pct,
        "order_risk_level":         order_risk_level,
        "working_days_remaining":   days_remaining,

        # Damage
        "damage_exceeded":          damage_exceeded,
        "damage_pct_of_commitment": damage_pct,

        # Risk detection (steps 8–12)
        "risk":                     risk,
    }


# ── System prompt ─────────────────────────────────────────────────
_SYSTEM_PROMPT = """
You are an AI production monitoring assistant for a garment manufacturing system.

You receive daily production data and pre-computed analysis context.
Return ONLY a valid JSON object — no markdown fences, no explanation outside the JSON.

Flowchart steps embedded in this component:
  Step 8:  gap <= 0 → No Risk → Continue Monitoring
  Step 9:  machine_breakdown > 0 → Machine Breakdown Issue
  Step 10: worker_shortage > 0 → Working Hours Issue (gap<8%) or Worker Issue (gap>=8%)
  Step 11: daily_damage > max_damage → Quality Issue
  Step 12: gap_pct >15% (no cause) → Commitment Too Low or Production Failure
  Alert:   Minor → Supervisor | Moderate → +Production Manager | Critical → +Top Management

Severity thresholds:
  Minor:    gap 0–5%
  Moderate: gap 5–15%
  Critical: gap >15%

Schema:

{
  "status": "success",
  "bulk_order_id": string,
  "style_id": string,
  "buyer_name": string,
  "allocated_bulk_plant": string,
  "plant_location": string,
  "working_day_no": integer,
  "production_date": "YYYY-MM-DD",

  "order_summary": {
    "full_order_qty": integer,
    "daily_commitment": integer,
    "cumulative_completed_qty": integer,
    "remaining_qty": integer,
    "completion_pct": float,
    "total_working_days": integer,
    "cutting_days": integer,
    "sewing_days": integer
  },

  "daily_production": {
    "plant_daily_output": integer,
    "daily_commitment": integer,
    "output_gap": integer,
    "gap_pct": float,
    "daily_damage_qty": integer,
    "max_daily_damage_qty": integer,
    "damage_exceeded": boolean,
    "damage_pct_of_commitment": float,
    "machine_breakdown_count": integer,
    "worker_shortage_count": integer
  },

  "risk_detection": {
    "risk_status": "Risk" | "No Risk",
    "risk_type": "No Issue" | "Machine Breakdown" | "Working Hours Issue" |
                 "Worker Issue" | "Quality Issue" | "Commitment Too Low" | "Production Failure",
    "severity": "Minor" | "Moderate" | "Critical" | null,
    "gap_severity_label": "Small Gap" | "Medium Gap" | "Large Gap" | "No Gap",
    "recommendation": string
  },

  "alert_system": {
    "alert_generated": boolean,
    "alert_targets": [string],
    "notify_via": ["System", "Email", "Dashboard"],
    "display_on": ["Dashboard", "Mobile App"]
  },

  "scheduling": {
    "bulk_order_approved_date": "YYYY-MM-DD",
    "bulk_start_date": "YYYY-MM-DD",
    "buyer_required_date": "YYYY-MM-DD",
    "projected_completion_date": "YYYY-MM-DD",
    "days_to_deadline": integer,
    "working_days_remaining": integer,
    "on_track": boolean
  },

  "order_progress": {
    "order_risk_level": "Low" | "Medium" | "High" | "Critical",
    "completion_pct": float,
    "days_elapsed_pct": float,
    "progress_gap_pct": float,
    "progress_summary": string
  },

  "planning_output": {
    "action_required": string,
    "escalation_needed": boolean,
    "next_step": string,
    "store_for_ml_training": true
  }
}

Rules:

gap_severity_label:
  gap_pct <= 0   → "No Gap"
  gap_pct 0–5%   → "Small Gap"
  gap_pct 5–15%  → "Medium Gap"
  gap_pct > 15%  → "Large Gap"

alert_generated: true if risk_status = "Risk"

notify_via: always ["System", "Email", "Dashboard"] when alert generated, else []
display_on: always ["Dashboard", "Mobile App"]

action_required:
  No Issue             → "Continue current production plan"
  Working Hours Issue  → "Increase working hours / Add overtime"
  Worker Issue         → "Add operators / Reassign workers from another line"
  Machine Breakdown    → "Repair / Maintain Machine immediately"
  Quality Issue        → "Improve QC & Process / Check damaged pieces"
  Commitment Too Low   → "Increase Working Hours / Efficiency"
  Production Failure   → "Reallocate to Another Plant"

escalation_needed: true if severity is "Critical"

progress_summary: one concise sentence describing completion progress vs timeline.

next_step: "Monitor Next Production Day" always (system loops until order completes)

store_for_ml_training: always true (system stores data for ML model training)

Return ONLY the JSON. No extra text.
"""


def _call_openai(payload: dict, ctx: dict) -> dict:
    user_msg = (
        f"REQUEST:\n{json.dumps(payload, indent=2, default=str)}\n\n"
        f"COMPUTED CONTEXT:\n{json.dumps(ctx, indent=2, default=str)}\n\n"
        "Return the daily production monitoring JSON."
    )
    client = _get_client()
    response = client.chat.completions.create(
        model="gpt-4o",
        temperature=0.0,
        messages=[
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user",   "content": user_msg},
        ],
    )
    raw = response.choices[0].message.content.strip()
    if raw.startswith("```"):
        parts = raw.split("```")
        raw = parts[1] if len(parts) > 1 else parts[0]
        if raw.startswith("json"):
            raw = raw[4:]
    return json.loads(raw.strip())


# ── Routes ────────────────────────────────────────────────────────

@component3_bp.route("/health", methods=["GET"])
def health():
    return jsonify({"component": "3 — Emergency Situation Detection", "status": "ok"})


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
        machine_breakdown_count, worker_shortage_count,
        cumulative_completed_qty
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
        "machine_breakdown_count", "worker_shortage_count",
        "cumulative_completed_qty",
    ]
    missing = [f for f in required if f not in data]
    if missing:
        return jsonify({"error": f"Missing required fields: {missing}"}), 400

    try:
        # Type coercions
        int_fields = [
            "full_order_qty", "daily_commitment", "plant_daily_output",
            "daily_damage_qty", "max_daily_damage_qty", "machine_breakdown_count",
            "worker_shortage_count", "cumulative_completed_qty",
            "working_day_no", "total_working_days", "cutting_days", "sewing_days",
        ]
        for f in int_fields:
            data[f] = int(data[f])

        datetime.strptime(data["production_date"],         "%Y-%m-%d")
        datetime.strptime(data["buyer_required_date"],     "%Y-%m-%d")
        datetime.strptime(data["bulk_order_approved_date"],"%Y-%m-%d")
    except (ValueError, TypeError) as e:
        return jsonify({"error": f"Invalid field value: {e}"}), 400

    # Validation
    if data["daily_commitment"] <= 0:
        return jsonify({"error": "daily_commitment must be > 0"}), 400
    if data["full_order_qty"] <= 0:
        return jsonify({"error": "full_order_qty must be > 0"}), 400

    # Build deterministic context
    try:
        ctx = _build_context(data)
    except Exception as e:
        return jsonify({"error": f"Context computation failed: {e}"}), 500

    # Call OpenAI
    try:
        result = _call_openai(data, ctx)
        return jsonify(result), 200
    except json.JSONDecodeError as e:
        return jsonify({"error": f"AI response parse error: {e}"}), 500
    except RuntimeError as e:
        return jsonify({"error": str(e)}), 503
    except Exception as e:
        return jsonify({"error": f"Prediction failed: {e}"}), 500