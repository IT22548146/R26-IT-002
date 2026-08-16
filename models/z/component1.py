from dotenv import load_dotenv
load_dotenv()

import json
import os
from datetime import datetime, timedelta

from flask import Blueprint, request, jsonify
from openai import OpenAI

# ── Flask Blueprint (same name as original) ───────────────────────
component1_bp = Blueprint("component1", __name__)

# ── client ─────────────────────────────────────────────────
_openai_client = None

def _get_client():
    global _openai_client
    if _openai_client is None:
        api_key = os.environ.get("OPENAI_API_KEY")
        if not api_key:
            raise RuntimeError("environment variable is not set.")
        _openai_client = OpenAI(api_key=api_key)
    return _openai_client


# ── Static lookups — calibrated from real 700-row dataset ─────────

QUALITY_MAP = {
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

# Real delay rates from 700-row dataset (Delayed / Allocated per plant)
HIST_DELAY = {
    "Amsral Lanka Enterprises":  0.319,
    "Dinusha Embroidery":        0.227,
    "MRC Group":                 0.314,
    "Regal Image International": 0.253,
    "Sunrose Lanka (Pvt) Ltd":   0.189,
    "The Bobbin Group":          0.281,
}

ALL_PLANTS = list(QUALITY_MAP.keys())

# All 4 buyers confirmed Monday shipment from real dataset
BUYER_SHIPMENT_SCHEDULE = {
    "George":      "Monday",
    "Tesco":       "Monday",
    "M&S":         "Monday",
    "Hirdaramani": "Monday",
}

KNOWN_BUYERS = list(BUYER_SHIPMENT_SCHEDULE.keys())

QTY_COMPLETION_MAP = [(3, 3), (5, 5), (10, 7)]


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


def _next_monday(after_date: datetime) -> datetime:
    days_ahead = (0 - after_date.weekday()) % 7
    if days_ahead == 0:
        days_ahead = 7
    return after_date + timedelta(days=days_ahead)


def _score_plants(buffer_days: int, cap_util_pct: float) -> list:
    cap_penalty = cap_util_pct / 100.0
    buf_bonus   = min(max(buffer_days, 0) * 0.05, 0.30)
    scores = {
        p: round(QUALITY_MAP[p] - (HIST_DELAY[p] * 2) - cap_penalty + buf_bonus, 4)
        for p in ALL_PLANTS
    }
    ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    return [
        {"rank": i + 1, "plant": p, "score": s,
         "location": PLANT_LOCATIONS[p],
         "quality_rating": QUALITY_MAP[p],
         "hist_delay_rate": HIST_DELAY[p]}
        for i, (p, s) in enumerate(ranked)
    ]


def _build_context(buyer_name, sample_qty, receive_date, buyer_req_date, cap_util_pct):
    comp_days      = _completion_days(sample_qty)
    est_completion = receive_date + timedelta(days=comp_days)
    nearest_ship   = _next_monday(est_completion)
    buffer_days    = (buyer_req_date - est_completion).days
    priority       = _priority_from_buffer(buffer_days)
    feasible       = buffer_days >= 0
    plant_ranking  = _score_plants(buffer_days, cap_util_pct)
    recommended    = plant_ranking[0]

    return {
        "completion_days":           comp_days,
        "estimated_completion_date": est_completion.strftime("%Y-%m-%d"),
        "buyer_ship_day":            BUYER_SHIPMENT_SCHEDULE.get(buyer_name, "Monday"),
        "nearest_shipment_date":     nearest_ship.strftime("%Y-%m-%d"),
        "days_completion_to_ship":   (nearest_ship - est_completion).days,
        "buffer_days":               buffer_days,
        "priority_level":            priority,
        "feasible":                  feasible,
        "plant_ranking":             plant_ranking,
        "recommended_plant":         recommended["plant"],
        "recommended_location":      recommended["location"],
        "recommended_quality":       recommended["quality_rating"],
        "recommended_delay_rate":    recommended["hist_delay_rate"],
    }


# ── OpenAI system prompt ──────────────────────────────────────────

_SYSTEM_PROMPT = """
You are an AI planning assistant for a garment sample management system.

You receive a buyer request payload and pre-computed context values.
Return ONLY a valid JSON object — no markdown fences, no explanation.

Schema (preserve all these keys to stay compatible with the existing system):

{
  "status": "success",
  "style_id": string,
  "buyer_name": string,
  "confidence": "OK" | "LOW",

  "input_summary": {
    "sample_qty": integer,
    "completion_days": integer,
    "buffer_days": integer,
    "receive_date": "YYYY-MM-DD",
    "buyer_required_date": "YYYY-MM-DD",
    "priority_level": string,
    "is_q4": boolean
  },

  "model1_overrun": {
    "predicted_overrun_days": float,
    "interpretation": string
  },

  "model2_plant_selection": {
    "recommended_plant": string,
    "ranking": [{"rank": integer, "plant": string, "score": float}]
  },

  "model3_delay": {
    "delay_probability": float,
    "delay_prediction": "Delayed" | "On Time",
    "shipment_status": "Delayed" | "On Time"
  },

  "planning_output": {
    "feasible": boolean,
    "allocated": boolean,
    "auto_priority": string,
    "priority_level": string,
    "final_shipment_date": "YYYY-MM-DD" | null,
    "allocation_remark": string,
    "action_required": string,
    "buyer_approval_status": "Waiting for Buyer Approval" | "Not Required",
    "risk_level": "Critical" | "High" | "Medium" | "Low",
    "risk_summary": string
  },

  "scheduling": {
    "estimated_completion_date": "YYYY-MM-DD",
    "nearest_shipment_date": "YYYY-MM-DD",
    "buyer_ship_day": "Monday",
    "days_completion_to_ship": integer
  }
}

Rules:

confidence: "OK" if buyer_name is a known buyer, else "LOW"

predicted_overrun_days (model1 equivalent):
  buffer < 0  -> 2.0
  buffer = 0  -> 2.0
  buffer = 1  -> 1.5
  buffer 2-3  -> 0.5
  buffer >= 4 -> 0.0

interpretation: "On time" if predicted_overrun_days < 0.5 else "{N} day(s) late"

delay_probability (model3 equivalent):
  buffer < 0  -> 0.95
  buffer = 0  -> 0.85
  buffer = 1  -> 0.75
  buffer 2-3  -> 0.50
  buffer 4-6  -> 0.25
  buffer > 6  -> 0.10
  +0.05 if is_emergency_shipment. Cap at 1.0. Round to 3 dp.

delay_prediction: "Delayed" if delay_probability >= 0.5 else "On Time"

feasible: true if buffer_days >= 0
allocated: same as feasible

allocation_remark:
  "Normal Allocation"                             if allocated AND On Time
  "Shipment delayed – waiting for buyer approval" if allocated AND Delayed
  "Cannot complete within buyer required date"    if not allocated

action_required:
  feasible + On Time  -> "Proceed with plan"
  feasible + Delayed  -> "Inform Buyer / Obtain Approval"
  not feasible        -> "Adjust Plan / Inform Buyer / Reassign Plant if possible"

buyer_approval_status:
  "Waiting for Buyer Approval" if Delayed else "Not Required"

final_shipment_date: nearest_shipment_date if feasible else null

is_q4: true if receive_date month >= 10

risk_level:
  buffer < 0  -> "Critical"
  buffer <= 1 -> "High"
  buffer <= 3 -> "Medium"
  else        -> "Low"

risk_summary: one sentence summarising risk and action.

Return ONLY the JSON. No extra text.
"""


def _call_openai(payload: dict, ctx: dict) -> dict:
    user_msg = (
        f"REQUEST:\n{json.dumps(payload, indent=2, default=str)}\n\n"
        f"COMPUTED CONTEXT:\n{json.dumps(ctx, indent=2, default=str)}\n\n"
        "Return the planning JSON."
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


# ── Routes — same paths as original ──────────────────────────────

@component1_bp.route("/health", methods=["GET"])
def health():
    return jsonify({"component": "1 — Sample Planning System", "status": "ok"})


@component1_bp.route("/predict", methods=["POST"])
def predict():
    """
    Drop-in replacement for the original /predict endpoint.

    Required fields (simplified — no .pkl inputs needed):
        buyer_name, sample_qty, receive_date, buyer_required_date

    Optional fields:
        style_id, cap_util_pct, is_emergency_shipment
    """
    data = request.get_json(force=True, silent=True)
    if not data:
        return jsonify({"error": "Request body must be valid JSON"}), 400

    # ── Validate required fields ───────────────────────────────
    required = ["buyer_name", "sample_qty", "receive_date", "buyer_required_date"]
    missing = [f for f in required if f not in data]
    if missing:
        return jsonify({"error": f"Missing required fields: {missing}"}), 400

    try:
        buyer_name   = str(data["buyer_name"])
        sample_qty   = int(data["sample_qty"])
        cap_util_pct = float(data.get("cap_util_pct", 75.0))
        is_emergency = int(data.get("is_emergency_shipment", 0))
        style_id     = str(data.get("style_id", "N/A"))

        receive_date    = datetime.strptime(str(data["receive_date"]),        "%Y-%m-%d")
        buyer_req_date  = datetime.strptime(str(data["buyer_required_date"]), "%Y-%m-%d")
    except (ValueError, TypeError) as e:
        return jsonify({"error": f"Invalid field value: {e}"}), 400

    # ── Validation ─────────────────────────────────────────────
    if not (1 <= sample_qty <= 10):
        return jsonify({"error": "sample_qty must be between 1 and 10"}), 400
    if buyer_name not in KNOWN_BUYERS:
        # still process but flag confidence = LOW (handled in prompt)
        pass

    # ── Build deterministic context ────────────────────────────
    try:
        ctx = _build_context(buyer_name, sample_qty, receive_date,
                             buyer_req_date, cap_util_pct)
    except Exception as e:
        return jsonify({"error": f"Context computation failed: {e}"}), 500

    # ── Inject is_emergency into payload for the prompt ────────
    payload_for_ai = {
        "buyer_name":            buyer_name,
        "style_id":              style_id,
        "sample_qty":            sample_qty,
        "receive_date":          receive_date.strftime("%Y-%m-%d"),
        "buyer_required_date":   buyer_req_date.strftime("%Y-%m-%d"),
        "cap_util_pct":          cap_util_pct,
        "is_emergency_shipment": is_emergency,
    }

    # ── Call OpenAI ────────────────────────────────────────────
    try:
        result = _call_openai(payload_for_ai, ctx)
        return jsonify(result), 200
    except json.JSONDecodeError as e:
        return jsonify({"error": f"AI response parse error: {e}"}), 500
    except RuntimeError as e:
        return jsonify({"error": str(e)}), 503
    except Exception as e:
        return jsonify({"error": f"Prediction failed: {e}"}), 500