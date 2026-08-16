"""
Component 4 — Production Analysis & Resource Optimization (OpenAI drop-in)
===========================================================================
Replaces the original component4.ipynb (XGBoost + GradientBoosting .pkl approach).

No .pkl files needed. No sklearn. No XGBoost.

Same endpoint:   POST /api/component4/predict
Health check:    GET  /api/component4/health

Flow (matches flowchart exactly):
  1. Data Collection     — validate & clean incoming payload
  2. Feature Engineering — derive metrics (efficiency_score, delay_ratio,
                           machine_idle_rate, overrun_days, risk_per_workload,
                           breakdown_worker_days)
  3. Production Analysis — rule-based performance scoring (calibrated from
                           500-row real dataset correlations)
  4. Star Rating         — map performance score to 1–5 star band
  5. Recommendation      — rule-based action text (7 conditions)
  6. Plant Recommender   — order-size-aware best plant suggestion
  7. Optimisation Engine — workload balance, machine allocation, risk flags
  8. AI Narrative        — OpenAI generates planning_output summary

Performance score formula (calibrated from real data correlations):
  score = 3.167
          - 0.0254 × delay_days
          + 1.833  × machine_utilization
          - 0.0465 × damage_rate
          - 0.0074 × risk_count
          - 0.0144 × machine_breakdown_days
          - 0.011  × worker_shortage_days
          + 0.0037 × urgent_handled_count
  clamped to [1.0, 5.0]

Per-plant quality baseline (from Plant_Ratings sheet):
  Dinusha Embroidery  4.35  (rank 1)
  MRC Group           4.07  (rank 2)
  Bobbin Group        3.92  (rank 3)
  Sunrose Lanka       3.84  (rank 4)
  Regal Image         3.70  (rank 5)
  Amsral Lanka        3.60  (rank 6)

Plant p75 daily output (from real dataset — used for order-size filtering):
  Sunrose Lanka       724.1 units/day
  Dinusha Embroidery  697.0
  Bobbin Group        674.7
  Amsral Lanka        644.8
  Regal Image         631.4
  MRC Group           628.1

Star rating bands:
  ≥ 4.5  → ⭐⭐⭐⭐⭐  Excellent
  ≥ 4.0  → ⭐⭐⭐⭐   Good
  ≥ 3.5  → ⭐⭐⭐    Average
  ≥ 3.0  → ⭐⭐     Poor
  < 3.0  → ⭐       Critical
"""

import json
import math
import os
from flask import Blueprint, request, jsonify
from openai import OpenAI

# ── Blueprint ──────────────────────────────────────────────────────
component4_bp = Blueprint("component4", __name__)

# ── OpenAI client ──────────────────────────────────────────────────
_openai_client = None

def _get_client():
    global _openai_client
    if _openai_client is None:
        api_key = os.environ.get("OPENAI_API_KEY")
        if not api_key:
            raise RuntimeError("OPENAI_API_KEY environment variable is not set.")
        _openai_client = OpenAI(api_key=api_key)
    return _openai_client


# ── Static lookups (calibrated from real dataset & flowchart) ──────

PLANT_QUALITY = {
    "Dinusha Embroidery": 4.35,
    "MRC Group":          4.07,
    "Bobbin Group":       3.92,
    "Sunrose Lanka":      3.84,
    "Regal Image":        3.70,
    "Amsral Lanka":       3.60,
}

PLANT_LOCATIONS = {
    "Dinusha Embroidery": "Weliweriya",
    "MRC Group":          "Colombo",
    "Bobbin Group":       "Mount Lavinia",
    "Sunrose Lanka":      "Katubedda",
    "Regal Image":        "Maharagama",
    "Amsral Lanka":       "Boralesgamuwa",
}

PLANT_IDS = {
    "Dinusha Embroidery": "PL01",
    "MRC Group":          "PL02",
    "Bobbin Group":       "PL03",
    "Sunrose Lanka":      "PL04",
    "Regal Image":        "PL05",
    "Amsral Lanka":       "PL06",
}

# p75 daily output per plant — from real 500-row dataset
# Used to filter plants that cannot sustain the required production rate
PLANT_P75_OUTPUT = {
    "Sunrose Lanka":      724.1,
    "Dinusha Embroidery": 697.0,
    "Bobbin Group":       674.7,
    "Amsral Lanka":       644.8,
    "Regal Image":        631.4,
    "MRC Group":          628.1,
}

# Average machines per plant from dataset
PLANT_AVG_MACHINES = {
    "Dinusha Embroidery": 18.3,
    "MRC Group":          16.6,
    "Bobbin Group":       14.3,
    "Sunrose Lanka":      13.6,
    "Regal Image":        12.3,
    "Amsral Lanka":       11.9,
}

ALL_PLANTS     = list(PLANT_QUALITY.keys())
KNOWN_BUYERS   = ["George", "Hirdaramani", "M&S", "Tesco"]
DELAY_STATUS   = ["Delayed", "On Time", "Early"]


# ── Step 2: Feature Engineering ────────────────────────────────────

def _engineer_features(data: dict) -> dict:
    """
    Derive all secondary metrics from raw inputs.
    Matches the feature set used in the original ML pipeline exactly.
    """
    planned = data["planned_completion_days"]
    actual  = data["actual_completion_days"]
    machines      = data["machine_count"]
    active_mach   = data["active_machine_count"]
    employees     = data["employee_count"]
    daily_output  = data["daily_output_avg"]
    workload      = data["total_workload"]
    risk_count    = data["risk_count_from_component3"]
    breakdown     = data["machine_breakdown_days"]
    worker_short  = data["worker_shortage_days"]

    delay_days    = max(0, actual - planned)
    overrun_days  = max(0, actual - planned)

    if actual < planned:
        delay_status = "Early"
    elif delay_days == 0:
        delay_status = "On Time"
    else:
        delay_status = "Delayed"

    machine_util      = round(active_mach / max(machines, 1), 6)
    machine_idle_rate = round(1.0 - machine_util, 6)
    efficiency_score  = round(daily_output / max(employees, 1), 3)
    delay_ratio       = round(delay_days / max(planned, 1), 4)
    risk_per_workload = round(risk_count / (workload / 1000 + 1), 4)
    breakdown_worker_days = breakdown + worker_short

    return {
        "delay_days":             delay_days,
        "delay_status":           delay_status,
        "delay_ratio":            delay_ratio,
        "overrun_days":           overrun_days,
        "machine_utilization":    machine_util,
        "machine_idle_rate":      machine_idle_rate,
        "efficiency_score":       efficiency_score,
        "risk_per_workload":      risk_per_workload,
        "breakdown_worker_days":  breakdown_worker_days,
    }


# ── Step 3: Performance Score (rule-based, calibrated from dataset) ─

def _compute_performance_score(features: dict, data: dict) -> float:
    """
    Calibrated from real dataset correlations:
      machine_utilization : +0.765 (strongest positive driver)
      delay_days          : -0.545 (strongest negative driver)
      risk_count          : -0.415
      damage_rate         : -0.286
      machine_breakdown   : -0.317
      worker_shortage     : -0.308
    """
    score = (
        3.167
        - 0.0254 * features["delay_days"]
        + 1.833  * features["machine_utilization"]
        - 0.0465 * data["damage_rate"]
        - 0.0074 * data["risk_count_from_component3"]
        - 0.0144 * data["machine_breakdown_days"]
        - 0.011  * data["worker_shortage_days"]
        + 0.0037 * data["urgent_handled_count"]
    )
    return round(float(max(1.0, min(5.0, score))), 3)


# ── Step 4: Star Rating ────────────────────────────────────────────

def _score_to_star(score: float) -> dict:
    """Map performance score to star band with label."""
    if score >= 4.5:
        return {"stars": 5, "emoji": "⭐⭐⭐⭐⭐", "label": "Excellent",
                "description": "Always on-time, excellent performance"}
    elif score >= 4.0:
        return {"stars": 4, "emoji": "⭐⭐⭐⭐",  "label": "Good",
                "description": "Minor delays, good overall performance"}
    elif score >= 3.5:
        return {"stars": 3, "emoji": "⭐⭐⭐",   "label": "Average",
                "description": "Average performance, frequent minor delays"}
    elif score >= 3.0:
        return {"stars": 2, "emoji": "⭐⭐",    "label": "Poor",
                "description": "Frequent delays, performance needs improvement"}
    else:
        return {"stars": 1, "emoji": "⭐",     "label": "Critical",
                "description": "Very poor performance, immediate intervention required"}


# ── Step 5: Recommendation (7 rule conditions from flowchart) ──────

def _get_recommendation(score: float, is_urgent: bool, risk_count: int,
                         breakdown_days: int, worker_shortage_days: int,
                         features: dict) -> dict:
    """
    Rule-based recommendation system matching flowchart conditions.
    Priority order: score >= 4.5 → urgent capable → breakdown → risk → output → critical → workforce
    """
    if score >= 4.5:
        action = "Maintain current resource allocation"
        best   = "Best for urgent/high priority orders"
    elif is_urgent and score >= 4.0:
        action = "Suitable for urgent style handling"
        best   = "Best for urgent/high priority orders"
    elif breakdown_days >= 5:
        action = "Increase machine maintenance support"
        best   = "Recommended for medium-high orders"
    elif risk_count >= 8:
        action = "Reduce risk days and add supervisor monitoring"
        best   = "Recommended for medium-high orders"
    elif score >= 4.0:
        action = "Increase daily output monitoring"
        best   = "Recommended for medium-high orders"
    elif score < 3.5:
        action = "Critical: Immediate intervention required"
        best   = "Not recommended - requires improvement"
    else:
        action = "Improve workforce allocation"
        best   = "Use for normal priority orders"

    return {"recommendation": action, "best_plant_recommendation": best}


# ── Step 6: Plant Recommender (order-size-aware) ───────────────────

def _recommend_plant(order_qty: int, planned_days: int,
                      is_urgent: bool, exclude_plant: str = "") -> dict:
    """
    Order-size-aware plant recommender (Model 3 equivalent).

    Logic:
      1. Compute required_daily_rate = order_qty / planned_days
      2. Filter out plants whose p75_daily_output < required_daily_rate
         (plant cannot reliably sustain the production rate needed)
      3. Among eligible plants, rank by quality score
         (urgent orders get +0.2 bonus for Dinusha and MRC Group)
      4. If no single plant is eligible → recommend split (Component 2)

    p75 (75th percentile) is used — a plant must reliably hit this rate,
    not just occasionally peak. Conservative but fair.
    """
    required_rate = order_qty / max(planned_days, 1)

    eligible   = []
    ineligible = []

    for plant in ALL_PLANTS:
        p75 = PLANT_P75_OUTPUT[plant]
        quality = PLANT_QUALITY[plant]
        urgent_bonus = 0.2 if (is_urgent and plant in ["Dinusha Embroidery", "MRC Group"]) else 0.0
        adjusted_score = quality + urgent_bonus

        if p75 >= required_rate:
            eligible.append({
                "plant":          plant,
                "location":       PLANT_LOCATIONS[plant],
                "quality_score":  PLANT_QUALITY[plant],
                "adjusted_score": round(adjusted_score, 3),
                "p75_output":     p75,
                "can_handle":     True,
            })
        else:
            ineligible.append({
                "plant":          plant,
                "location":       PLANT_LOCATIONS[plant],
                "quality_score":  PLANT_QUALITY[plant],
                "p75_output":     p75,
                "can_handle":     False,
                "reason":         f"p75 output {p75} < required rate {required_rate:.1f} units/day",
            })

    eligible.sort(key=lambda x: x["adjusted_score"], reverse=True)

    split_needed = len(eligible) == 0

    if split_needed:
        recommended = None
        rec_score   = None
        rec_note    = "No single plant can sustain the required production rate — split order recommended (see Component 2)"
    else:
        top = eligible[0]
        # Skip excluded plant (e.g. if sample plant already allocated)
        if exclude_plant and top["plant"] == exclude_plant and len(eligible) > 1:
            top = eligible[1]
        recommended = top["plant"]
        rec_score   = top["adjusted_score"]
        rec_note    = (
            f"Order requires {required_rate:.1f} units/day. "
            f"{len(eligible)} plant(s) eligible. "
            f"{'Urgent bonus applied.' if is_urgent else ''}"
        ).strip()

    return {
        "recommended_plant":   recommended,
        "plant_score":         rec_score,
        "required_daily_rate": round(required_rate, 2),
        "eligible_plants":     [p["plant"] for p in eligible],
        "eligible_count":      len(eligible),
        "ineligible_plants":   [p["plant"] for p in ineligible],
        "split_needed":        split_needed,
        "urgent_bonus_applied": is_urgent,
        "recommendation_note": rec_note,
        "plant_ranking":       [
            {
                "rank":          i + 1,
                "plant":         p["plant"],
                "location":      p["location"],
                "quality_score": p["quality_score"],
                "p75_output":    p["p75_output"],
                "can_handle":    True,
            }
            for i, p in enumerate(eligible)
        ] + [
            {
                "rank":       None,
                "plant":      p["plant"],
                "location":   p["location"],
                "quality_score": p["quality_score"],
                "p75_output": p["p75_output"],
                "can_handle": False,
                "reason":     p["reason"],
            }
            for p in ineligible
        ],
    }


# ── Step 7: Optimisation Engine ────────────────────────────────────

def _optimization_analysis(data: dict, features: dict,
                            score: float, star: dict) -> dict:
    """
    Optimisation & recommendation engine (flowchart section 5).
    Produces workload balance, machine allocation advice, workforce plan,
    priority handling flags, and risk summary.
    """
    machines     = data["machine_count"]
    active_mach  = data["active_machine_count"]
    employees    = data["employee_count"]
    idle_rate    = features["machine_idle_rate"]
    breakdown    = data["machine_breakdown_days"]
    worker_short = data["worker_shortage_days"]
    risk_count   = data["risk_count_from_component3"]
    is_urgent    = data["urgent_style_flag"] == "Yes"
    daily_output = data["daily_output_avg"]
    workload     = data["total_workload"]

    # Machine allocation advice
    idle_machines = machines - active_mach
    if idle_rate > 0.25:
        machine_advice = (
            f"{idle_machines} machine(s) idle ({idle_rate*100:.1f}% idle rate). "
            "Reallocate idle machines to active styles or schedule for maintenance."
        )
    elif breakdown >= 5:
        machine_advice = (
            f"{breakdown} breakdown days recorded. "
            "Schedule preventive maintenance immediately to avoid further capacity loss."
        )
    else:
        machine_advice = f"Machine utilization is healthy ({features['machine_utilization']*100:.1f}%). No immediate reallocation needed."

    # Workforce advice
    if worker_short >= 5:
        workforce_advice = (
            f"{worker_short} worker shortage days. "
            "Increase manpower allocation or cross-train workers from lower-priority lines."
        )
    else:
        workforce_advice = f"Workforce stable. Efficiency score: {features['efficiency_score']:.2f} units/worker/day."

    # Workload balance
    days_to_process = math.ceil(workload / max(daily_output, 1))
    workload_advice = (
        f"Total workload {workload:,} units at {daily_output:.0f} units/day "
        f"requires ~{days_to_process} days. "
        + ("Workload is manageable within planned schedule."
           if days_to_process <= data["planned_completion_days"]
           else f"Workload EXCEEDS planned {data['planned_completion_days']} days — increase daily capacity.")
    )

    # Priority handling
    if is_urgent and score >= 4.0:
        priority_flag = "URGENT — Plant capable of handling urgent/high-priority styles"
    elif is_urgent and score < 4.0:
        priority_flag = "URGENT — WARNING: Plant performance below threshold for urgent orders"
    else:
        priority_flag = "NORMAL priority — no urgent escalation required"

    # Risk summary
    risk_flags = []
    if risk_count >= 8:     risk_flags.append(f"High C3 risk count ({risk_count})")
    if breakdown >= 5:      risk_flags.append(f"Excessive machine breakdown days ({breakdown})")
    if worker_short >= 5:   risk_flags.append(f"Persistent worker shortage ({worker_short} days)")
    if idle_rate > 0.25:    risk_flags.append(f"High machine idle rate ({idle_rate*100:.1f}%)")
    if features["delay_days"] >= 10:
        risk_flags.append(f"Significant delay ({features['delay_days']} days)")

    risk_level = (
        "Critical" if len(risk_flags) >= 4 else
        "High"     if len(risk_flags) >= 2 else
        "Medium"   if len(risk_flags) == 1 else
        "Low"
    )

    return {
        "machine_allocation_advice": machine_advice,
        "workforce_plan":            workforce_advice,
        "workload_balance":          workload_advice,
        "priority_handling":         priority_flag,
        "risk_level":                risk_level,
        "risk_flags":                risk_flags,
        "risk_flag_count":           len(risk_flags),
        "days_to_clear_workload":    days_to_process,
    }


# ── Step 8: OpenAI narrative generation ────────────────────────────

_SYSTEM_PROMPT = """
You are an AI planning assistant for a garment production management system — Component 4.

You receive a completed production order record with pre-computed analysis values.
Return ONLY a valid JSON object — no markdown fences, no explanation outside the JSON.

Your role: synthesise the pre-computed metrics into a concise, actionable planning output.
Do NOT recalculate scores, stars, or recommendations — those are pre-computed and must be used as-is.

Output schema:

{
  "status": "success",
  "record_id": string,
  "plant_name": string,
  "plant_location": string,
  "buyer_name": string,
  "style_id": string,
  "confidence": "OK" | "LOW",

  "production_summary": {
    "order_quantity": integer,
    "planned_completion_days": integer,
    "actual_completion_days": integer,
    "delay_days": integer,
    "delay_status": "Delayed" | "On Time" | "Early",
    "overrun_days": integer,
    "machine_utilization": float,
    "machine_idle_rate": float,
    "efficiency_score": float,
    "delay_ratio": float,
    "risk_per_workload": float,
    "breakdown_worker_days": integer
  },

  "performance_analysis": {
    "performance_score": float,
    "star_rating": string,
    "star_label": string,
    "star_description": string,
    "recommendation": string,
    "best_plant_recommendation": string
  },

  "plant_recommendation": {
    "recommended_plant": string | null,
    "plant_score": float | null,
    "required_daily_rate": float,
    "eligible_plants": list,
    "eligible_count": integer,
    "ineligible_plants": list,
    "split_needed": boolean,
    "urgent_bonus_applied": boolean,
    "recommendation_note": string,
    "plant_ranking": list
  },

  "optimization": {
    "machine_allocation_advice": string,
    "workforce_plan": string,
    "workload_balance": string,
    "priority_handling": string,
    "risk_level": "Critical" | "High" | "Medium" | "Low",
    "risk_flags": list,
    "risk_flag_count": integer,
    "days_to_clear_workload": integer
  },

  "planning_output": {
    "final_assessment": string,
    "key_issues": list of strings (max 4),
    "immediate_actions": list of strings (max 3),
    "future_strategy": string
  }
}

Rules:
- confidence: "OK" if buyer_name is one of George/Hirdaramani/M&S/Tesco, else "LOW"
- planning_output.final_assessment: one paragraph, professional tone, max 60 words
- planning_output.key_issues: list the top issues found in the pre-computed analysis (use risk_flags + delay status + star rating)
- planning_output.immediate_actions: list the top 3 concrete actions from the optimization advice
- planning_output.future_strategy: one sentence about long-term improvement focus
- All numeric fields must exactly match the pre-computed values provided — do NOT round or alter them

Return ONLY the JSON. No extra text.
"""


def _call_openai(payload: dict, ctx: dict) -> dict:
    user_msg = (
        f"PRODUCTION ORDER RECORD:\n{json.dumps(payload, indent=2, default=str)}\n\n"
        f"PRE-COMPUTED ANALYSIS:\n{json.dumps(ctx, indent=2, default=str)}\n\n"
        "Generate the Component 4 planning output JSON."
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


# ── Full context builder ────────────────────────────────────────────

def _build_context(data: dict) -> dict:
    """Run all deterministic steps before calling OpenAI."""

    # Step 2: Feature engineering
    features = _engineer_features(data)

    # Step 3: Performance score
    score = _compute_performance_score(features, data)

    # Step 4: Star rating
    star = _score_to_star(score)

    # Step 5: Recommendation
    rec = _get_recommendation(
        score,
        data["urgent_style_flag"] == "Yes",
        data["risk_count_from_component3"],
        data["machine_breakdown_days"],
        data["worker_shortage_days"],
        features,
    )

    # Step 6: Plant recommender
    plant_rec = _recommend_plant(
        data["order_quantity"],
        data["planned_completion_days"],
        data["urgent_style_flag"] == "Yes",
        exclude_plant=data.get("plant_name", ""),
    )

    # Step 7: Optimisation engine
    optimisation = _optimization_analysis(data, features, score, star)

    return {
        "features":        features,
        "performance_score": score,
        "star_rating":     star,
        "recommendation":  rec,
        "plant_recommendation": plant_rec,
        "optimisation":    optimisation,
    }


# ── Input validation ───────────────────────────────────────────────

REQUIRED_FIELDS = [
    "plant_name", "buyer_name", "style_id",
    "order_quantity", "planned_completion_days", "actual_completion_days",
    "machine_count", "active_machine_count", "employee_count",
    "daily_output_avg", "total_workload",
    "urgent_style_flag", "urgent_handled_count",
    "risk_count_from_component3",
    "machine_breakdown_days", "worker_shortage_days",
    "damage_rate",
]


def _validate(data: dict) -> list:
    errors = []

    for f in REQUIRED_FIELDS:
        if f not in data:
            errors.append(f"Missing required field: {f}")

    if errors:
        return errors  # stop early — rest of validation needs these fields

    if data["plant_name"] not in ALL_PLANTS:
        errors.append(f"plant_name must be one of: {ALL_PLANTS}")

    if data["urgent_style_flag"] not in ["Yes", "No"]:
        errors.append("urgent_style_flag must be 'Yes' or 'No'")

    try:
        oq = int(data["order_quantity"])
        if oq < 1:
            errors.append("order_quantity must be >= 1")
    except (ValueError, TypeError):
        errors.append("order_quantity must be an integer")

    try:
        pd_ = int(data["planned_completion_days"])
        ad  = int(data["actual_completion_days"])
        if pd_ < 1:
            errors.append("planned_completion_days must be >= 1")
        if ad < 1:
            errors.append("actual_completion_days must be >= 1")
    except (ValueError, TypeError):
        errors.append("planned_completion_days and actual_completion_days must be integers")

    try:
        mc = int(data["machine_count"])
        am = int(data["active_machine_count"])
        if mc < 1:
            errors.append("machine_count must be >= 1")
        if am < 0 or am > mc:
            errors.append("active_machine_count must be between 0 and machine_count")
    except (ValueError, TypeError):
        errors.append("machine_count and active_machine_count must be integers")

    try:
        dr = float(data["damage_rate"])
        if not (0.0 <= dr <= 100.0):
            errors.append("damage_rate must be between 0.0 and 100.0")
    except (ValueError, TypeError):
        errors.append("damage_rate must be a float")

    return errors


# ── Routes ─────────────────────────────────────────────────────────

@component4_bp.route("/health", methods=["GET"])
def health():
    return jsonify({
        "component": "4 — Production Analysis & Resource Optimization",
        "status":    "ok",
        "models": {
            "performance_score": "rule-based (calibrated from 500-row real dataset)",
            "star_rating":       "rule-based band mapping",
            "plant_recommender": "order-size-aware rule-based scoring",
            "planning_output":   "OpenAI gpt-4o",
        }
    })


@component4_bp.route("/predict", methods=["POST"])
def predict():
    """
    POST /api/component4/predict

    Required fields:
        plant_name                  — one of the 6 plant names
        buyer_name                  — buyer (George/Hirdaramani/M&S/Tesco → confidence OK)
        style_id                    — style code string
        order_quantity              — integer, total units
        planned_completion_days     — integer
        actual_completion_days      — integer
        machine_count               — integer, total machines at plant
        active_machine_count        — integer, machines actively running
        employee_count              — integer
        daily_output_avg            — float, units produced per day
        total_workload              — integer, total units in pipeline
        urgent_style_flag           — "Yes" or "No"
        urgent_handled_count        — integer, urgent styles handled
        risk_count_from_component3  — integer, risk incidents from C3
        machine_breakdown_days      — integer
        worker_shortage_days        — integer
        damage_rate                 — float (percentage, e.g. 3.2 means 3.2%)

    Optional fields:
        record_id                   — string (defaults to "N/A")
        plant_id                    — string (auto-resolved from plant_name if omitted)
    """
    data = request.get_json(force=True, silent=True)
    if not data:
        return jsonify({"error": "Request body must be valid JSON"}), 400

    errors = _validate(data)
    if errors:
        return jsonify({"errors": errors}), 400

    # Cast types
    data["order_quantity"]             = int(data["order_quantity"])
    data["planned_completion_days"]    = int(data["planned_completion_days"])
    data["actual_completion_days"]     = int(data["actual_completion_days"])
    data["machine_count"]              = int(data["machine_count"])
    data["active_machine_count"]       = int(data["active_machine_count"])
    data["employee_count"]             = int(data["employee_count"])
    data["daily_output_avg"]           = float(data["daily_output_avg"])
    data["total_workload"]             = int(data["total_workload"])
    data["urgent_handled_count"]       = int(data["urgent_handled_count"])
    data["risk_count_from_component3"] = int(data["risk_count_from_component3"])
    data["machine_breakdown_days"]     = int(data["machine_breakdown_days"])
    data["worker_shortage_days"]       = int(data["worker_shortage_days"])
    data["damage_rate"]                = float(data["damage_rate"])

    # Auto-fill optional fields
    data.setdefault("record_id", "N/A")
    data.setdefault("plant_id",  PLANT_IDS.get(data["plant_name"], "N/A"))
    data.setdefault("plant_location", PLANT_LOCATIONS.get(data["plant_name"], "Unknown"))

    # Build deterministic context
    try:
        ctx = _build_context(data)
    except Exception as e:
        return jsonify({"error": f"Context computation failed: {e}"}), 500

    # Call OpenAI for narrative planning output
    try:
        result = _call_openai(data, ctx)
        return jsonify(result), 200
    except Exception as e:
        return jsonify({"error": f"Prediction failed: {e}"}), 500