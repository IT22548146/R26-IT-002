"""
Component 2 — Bulk Order Planning & Capacity Allocation (OpenAI drop-in)
=========================================================================
FIXES applied (vs previous version):
  1. monthly_capacity now accepted from request payload (per-plant override).
  2. working_days derived from monthly_capacity (styles/day ratio from Excel data).
  3. embroidery_days now increases with design area, stitch count, and color count
     — not purely driven by bulk_order_quantity.
  4. Plant ranking uses live monthly_capacity, not static constants; plants with
     very low capacity rank lower; sample plant gets explicit priority boost when
     it has capacity.
  5. can_handle_solo and working_days both update dynamically from monthly_capacity.
  6. Input validation: hard-reject physically impossible design values
     (stitch_count < 1,000 or > 500,000 | design_width/length > 52 cm | color_count > 15).
     Warning-only (no reject) for bulk_order_quantity > 500,000.
  7. Cutting/sewing tier tables extended to cover up to 500,000+ piece orders —
     previously capped at 30,000 pieces (18 cut / 30 sew days for everything above).

Same Blueprint name:   component2_bp
Same route:            POST /api/component2/predict
Same health route:     GET  /api/component2/health
"""

import json
import math
import os
from datetime import datetime, timedelta

from flask import Blueprint, request, jsonify
from openai import OpenAI

# ── Flask Blueprint ────────────────────────────────────────────────
component2_bp = Blueprint("component2", __name__)

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


# ── Static lookups ─────────────────────────────────────────────────

QUALITY_MAP = {
    "Dinusha Embroidery":        4.8,
    "Regal Image International": 4.6,
    "MRC Group":                 4.5,
    "The Bobbin Group":          4.4,
    "Sunrose Lanka (Pvt) Ltd":   4.3,
    "Amsral Lanka Enterprises":  4.2,
}

PLANT_LOCATIONS = {
    "Dinusha Embroidery":        "Weliweriya",
    "Regal Image International": "Maharagama",
    "MRC Group":                 "Colombo",
    "The Bobbin Group":          "Mount Lavinia",
    "Sunrose Lanka (Pvt) Ltd":   "Katubedda",
    "Amsral Lanka Enterprises":  "Boralesgamuwa",
}

# ── FIX 1: Default monthly capacities (styles/month) from Excel data ──
# These are January-2025 baselines; request can override via monthly_capacity.
DEFAULT_MONTHLY_CAPACITY = {
    "Dinusha Embroidery":        181,
    "The Bobbin Group":          178,
    "Regal Image International": 160,   # estimated (no file provided)
    "Sunrose Lanka (Pvt) Ltd":   146,
    "MRC Group":                 132,
    "Amsral Lanka Enterprises":  113,
}

# ── FIX 2: Styles-per-day ratio per plant (from Excel: total_styles / working_days)
# Used to derive working_days when monthly_capacity changes.
# Baseline: Jan-2025 — 27 working days for all plants
STYLES_PER_WORKING_DAY = {
    "Dinusha Embroidery":        round(181 / 27, 3),   # ≈ 6.70
    "The Bobbin Group":          round(178 / 27, 3),   # ≈ 6.59
    "Regal Image International": round(160 / 27, 3),   # ≈ 5.93 (estimated)
    "Sunrose Lanka (Pvt) Ltd":   round(146 / 27, 3),   # ≈ 5.41
    "MRC Group":                 round(132 / 27, 3),   # ≈ 4.89
    "Amsral Lanka Enterprises":  round(113 / 27, 3),   # ≈ 4.19
}

ALL_PLANTS = list(QUALITY_MAP.keys())

KNOWN_BUYERS = ["George", "Hirdaramani", "M&S", "Tesco"]

PRIORITY_VALUES = ["High", "Normal", "Low", "No Urgency"]

ALLOCATION_GUIDE = {
    ("High",       "High"):   ["Dinusha Embroidery", "Regal Image International"],
    ("High",       "Medium"): ["Dinusha Embroidery", "The Bobbin Group"],
    ("High",       "Low"):    ["Dinusha Embroidery", "Regal Image International"],
    ("Normal",     "High"):   ["Dinusha Embroidery", "Regal Image International"],
    ("Normal",     "Medium"): ["The Bobbin Group", "Sunrose Lanka (Pvt) Ltd"],
    ("Normal",     "Low"):    ["MRC Group", "Amsral Lanka Enterprises"],
    ("Low",        "Low"):    ["MRC Group", "Amsral Lanka Enterprises"],
    ("No Urgency", "Low"):    ["MRC Group", "Amsral Lanka Enterprises"],
    ("No Urgency", "Medium"): ["MRC Group", "Amsral Lanka Enterprises"],
    ("No Urgency", "High"):   ["The Bobbin Group", "Sunrose Lanka (Pvt) Ltd"],
    ("Low",        "Medium"): ["The Bobbin Group", "Sunrose Lanka (Pvt) Ltd"],
    ("Low",        "High"):   ["Dinusha Embroidery", "Regal Image International"],
}


# ── FIX 2: Derive working days from monthly capacity ────────────────

def _working_days_from_capacity(plant: str, monthly_styles: int) -> int:
    """
    Back-calculate working days from a given monthly styles capacity.
    Formula: working_days = round(monthly_styles / styles_per_day)
    Clamped to [18, 31] to be realistic.
    """
    spd = STYLES_PER_WORKING_DAY.get(plant, 5.5)
    days = round(monthly_styles / spd) if spd > 0 else 22
    return max(18, min(31, days))


# ── Design complexity derivation ────────────────────────────────────

def _matrix_complexity(w: float, l: float) -> str:
    if w <= 5:
        return "Low" if l <= 10 else "Medium"
    elif w <= 10:
        if l <= 5:    return "Low"
        elif l <= 15: return "Medium"
        else:         return "High"
    elif w <= 15:
        return "Medium" if l <= 10 else "High"
    else:
        return "Medium" if l <= 5 else "High"


def _color_impact(c: int) -> str:
    if c <= 3:   return "Low"
    elif c <= 6: return "Medium"
    return "High"


def _stitch_impact(s: int) -> str:
    if s <= 7000:    return "Low"
    elif s <= 15000: return "Medium"
    return "High"


def _derive_complexity(w: float, l: float, c: int, s: int) -> dict:
    enc = {"Low": 1, "Medium": 2, "High": 3}
    matrix = _matrix_complexity(w, l)
    color  = _color_impact(c)
    stitch = _stitch_impact(s)
    highest = max([matrix, color, stitch], key=lambda x: enc[x])
    return {
        "matrix_complexity": matrix,
        "color_impact":      color,
        "stitch_impact":     stitch,
        "final_complexity":  highest,
        "complexity_score":  round((enc[matrix] + enc[color] + enc[stitch]) / 3.0, 3),
    }


# ── FIX 3: Embroidery days include design-area & stitch adjustment ──
#
# Root cause of original bug:
#   embroidery_days = ceil(qty / daily_commitment)
#   This only changes with qty — NOT with design area or stitch count.
#
# Corrected formula:
#   base_emb_days = ceil(qty / daily_commitment)
#   design_area_factor  = 1 + (w * l - 100) / 2000   (neutral at 10×10=100 cm²)
#   stitch_factor       = 1 + (stitch_count - 10000) / 100000
#   color_factor        = 1 + max(0, color_count - 6) * 0.03
#   emb_days = ceil(base_emb_days * design_area_factor * stitch_factor * color_factor)
#
# Verified: for a 10×10 design, 10k stitches, 6 colors → factors ≈ 1.0 (no change).
# Larger designs, higher stitches → more embroidery days.

# FIX 6: Cutting days quantity tiers — extended from 30k cap to 500k+
# Tiers 5k–30k are unchanged (calibrated from real 400-row dataset).
# Tiers above 30k are scaled proportionally from the 30k anchor point:
#   30k → 14 cut days.  Each additional 50k adds ~4 days (multi-line assumption).
# Real-world note: orders above 100k run across multiple cutting lines simultaneously,
# so days scale sub-linearly.  The tiers below reflect that.
_CUTTING_TIERS = [
    (5_000,         5),
    (10_000,        7),
    (20_000,       10),
    (30_000,       14),
    (50_000,       18),
    (100_000,      25),
    (200_000,      35),
    (300_000,      45),
    (500_000,      60),
    (float("inf"), 75),
]

# FIX 6: Sewing days quantity tiers — extended from 30k cap to 500k+
# Sewing always ~1.5–2× cutting days.  Same sub-linear scaling above 30k.
_SEWING_TIERS = [
    (5_000,         8),
    (10_000,       10),
    (20_000,       14),
    (30_000,       20),
    (50_000,       26),
    (100_000,      38),
    (200_000,      55),
    (300_000,      70),
    (500_000,      90),
    (float("inf"), 110),
]

RECOMMENDED_DAILY_COMMITMENT = {
    "Low":    649,
    "Medium": 789,
    "High":   911,
}


def _calc_production_days(order_qty: int, daily_commitment: float,
                           design_width: float, design_length: float,
                           color_count: int, stitch_count: int,
                           sample_plant: str = "",
                           monthly_capacity: dict = None) -> dict:
    """
    Embroidery days scale with: design area, stitch count, color count,
    AND the sample plant's available embroidery machine capacity (FIX 8).

    Step 1 — base:
        base_emb_days  = ceil(qty / daily_commitment)

    Step 2 — design complexity factors:
        design_area_factor = 1 + (area - 100) / 2000   neutral at 10x10 cm2
        stitch_factor      = 1 + (stitch_count - 10000) / 100000
        color_factor       = 1 + max(0, color_count - 6) x 0.03
        design_emb_days    = ceil(base_emb x area_f x stitch_f x color_f)

    Step 3 — capacity factor (embroidery machines only):
        load_ratio  = order_qty / (monthly_capacity[plant] x daily_commitment)
        cap_factor  = 1 + load_ratio  clamped to [1.0, 4.0]
        emb_days    = ceil(design_emb_days x cap_factor)

        Low capacity  -> high load_ratio -> higher cap_factor -> more emb days
        Full capacity -> low load_ratio  -> cap_factor near 1 -> fewer emb days

    Cutting and sewing days are NOT adjusted here — those machines are separate
    from the embroidery machines tracked in the capacity Excel files.
    """
    base_emb = math.ceil(order_qty / max(daily_commitment, 1))

    area     = design_width * design_length
    area_f   = 1.0 + (area - 100.0) / 2000.0
    stitch_f = 1.0 + (stitch_count - 10000.0) / 100000.0
    color_f  = 1.0 + max(0, color_count - 6) * 0.03

    # Clamp design factors
    area_f   = max(0.8, min(2.5, area_f))
    stitch_f = max(0.8, min(2.5, stitch_f))
    color_f  = max(1.0, min(1.3, color_f))

    design_emb_days = math.ceil(base_emb * area_f * stitch_f * color_f)

    # FIX 8: Capacity factor — how strained is the plant's embroidery capacity?
    cap_factor     = 1.0
    load_ratio_emb = 0.0
    if monthly_capacity and sample_plant:
        cap_styles        = monthly_capacity.get(
            sample_plant, DEFAULT_MONTHLY_CAPACITY.get(sample_plant, 160)
        )
        monthly_piece_cap = cap_styles * max(daily_commitment, 1)
        if monthly_piece_cap > 0:
            load_ratio_emb = order_qty / monthly_piece_cap
            cap_factor     = max(1.0, min(4.0, 1.0 + load_ratio_emb))

    emb_days = math.ceil(design_emb_days * cap_factor)

    cut_days = _CUTTING_TIERS[-1][1]
    for threshold, days in _CUTTING_TIERS:
        if order_qty <= threshold:
            cut_days = days
            break

    sew_days = _SEWING_TIERS[-1][1]
    for threshold, days in _SEWING_TIERS:
        if order_qty <= threshold:
            sew_days = days
            break

    total_days = cut_days + sew_days + emb_days

    # FIX 6: Warning for very large orders (not a reject — just a flag for the AI)
    large_order_warning = (
        f"bulk_order_quantity {order_qty:,} exceeds 500,000 pieces. "
        "Cutting/sewing days use extended tiers assuming multi-line production. "
        "Manual capacity review recommended."
        if order_qty > 500_000 else None
    )

    return {
        "cutting_days":              cut_days,
        "sewing_days":               sew_days,
        "embroidery_days":           emb_days,
        "base_embroidery_days":      base_emb,
        "design_emb_days":           design_emb_days,
        "design_area_factor":        round(area_f, 3),
        "stitch_factor":             round(stitch_f, 3),
        "color_factor":              round(color_f, 3),
        "capacity_factor":           round(cap_factor, 3),
        "capacity_load_ratio":       round(load_ratio_emb, 4),
        "total_production_days":     total_days,
        "large_order_warning":       large_order_warning,
    }


# ── FIX 1 & 4: Plant capacity check using live monthly_capacity ────

def _resolve_monthly_capacity(payload: dict) -> dict:
    """
    Returns per-plant monthly capacity dict.
    If payload contains 'monthly_capacity', use those values (override);
    otherwise fall back to DEFAULT_MONTHLY_CAPACITY.
    Missing plants in the override still fall back to their default.
    """
    override = payload.get("monthly_capacity", {})
    resolved = {}
    for plant in ALL_PLANTS:
        if plant in override:
            resolved[plant] = int(override[plant])
        else:
            resolved[plant] = DEFAULT_MONTHLY_CAPACITY.get(plant, 160)
    return resolved


def _check_sample_plant_capacity(sample_plant: str,
                                  order_qty: int,
                                  daily_commitment: float,
                                  monthly_capacity: dict) -> dict:
    """
    FIX 1: Uses live monthly_capacity from request instead of static constant.
    FIX 2: Derives working_days from monthly_capacity.

    capacity_styles     = monthly_capacity[plant]  (styles/month)
    working_days        = derived from styles_per_day ratio
    monthly_piece_cap   = capacity_styles × daily_commitment
    load_ratio          = order_qty / monthly_piece_cap
    has_capacity        = load_ratio < 0.20
    """
    cap_styles        = monthly_capacity.get(sample_plant, DEFAULT_MONTHLY_CAPACITY.get(sample_plant, 160))
    working_days      = _working_days_from_capacity(sample_plant, cap_styles)
    monthly_piece_cap = cap_styles * max(daily_commitment, 1)
    load_ratio        = round(order_qty / monthly_piece_cap, 4) if monthly_piece_cap > 0 else 1.0
    has_capacity      = load_ratio < 0.20

    return {
        "plant":                  sample_plant,
        "plant_monthly_styles":   cap_styles,
        "plant_working_days":     working_days,
        "monthly_piece_capacity": round(monthly_piece_cap),
        "order_qty":              order_qty,
        "load_ratio":             load_ratio,
        "has_capacity":           has_capacity,
        "capacity_status":        "Yes" if has_capacity else "No",
        "utilisation_pct":        round(load_ratio * 100, 1),
        "manager_confirmation":   "Have Capacity" if has_capacity else "No Capacity",
    }


# ── FIX 4: Plant scoring uses live capacity + sample-plant boost ────

def _score_plants(priority: str, complexity: str,
                  order_qty: int, daily_commitment: float,
                  sample_plant: str, monthly_capacity: dict) -> list:
    """
    FIX 4: Ranking now:
      - Uses live monthly_capacity (not static constants) for capacity ratio.
      - Derives working_days per plant from monthly_capacity.
      - Sample plant gets a +0.3 quality bonus when it has capacity (first-priority rule).
      - Plants with very low capacity rank lower (capacity ratio penalises them).
      - can_handle_solo uses live capacity.
    """
    preferred = ALLOCATION_GUIDE.get(
        (priority, complexity),
        ALLOCATION_GUIDE.get(("No Urgency", "Low"), ALL_PLANTS)
    )

    results = []
    for plant in ALL_PLANTS:
        quality     = QUALITY_MAP[plant]
        pref_bonus  = 0.5 if plant in preferred else 0.0

        cap_styles        = monthly_capacity.get(plant, DEFAULT_MONTHLY_CAPACITY.get(plant, 160))
        working_days      = _working_days_from_capacity(plant, cap_styles)
        monthly_piece_cap = cap_styles * max(daily_commitment, 1)
        load_ratio        = order_qty / monthly_piece_cap if monthly_piece_cap > 0 else 1.0
        can_solo          = load_ratio < 0.20

        # Capacity ratio: max monthly_capacity plant = 1.0 reference (200 styles baseline)
        cap_ratio = cap_styles / 200.0

        # FIX 4: Sample plant priority boost if it has capacity
        sample_bonus = 0.3 if (plant == sample_plant and can_solo) else 0.0

        # Penalty for very low capacity (< 60 styles/month → significant deduction)
        capacity_penalty = max(0.0, (60 - cap_styles) / 100.0) if cap_styles < 60 else 0.0

        score = quality + pref_bonus + cap_ratio - 1.0 + sample_bonus - capacity_penalty

        results.append({
            "plant":            plant,
            "location":         PLANT_LOCATIONS[plant],
            "score":            round(score, 4),
            "quality_rating":   quality,
            "monthly_capacity": cap_styles,
            "working_days":     working_days,
            "can_handle_solo":  can_solo,
            "preferred":        plant in preferred,
            "is_sample_plant":  plant == sample_plant,
        })

    results.sort(key=lambda x: x["score"], reverse=True)
    for i, r in enumerate(results):
        r["rank"] = i + 1
    return results


# ── Build deterministic context ────────────────────────────────────

def _build_context(payload: dict) -> dict:
    order_qty        = int(payload["bulk_order_quantity"])
    daily_commitment = float(payload["daily_commitment"])
    design_width     = float(payload["design_width"])
    design_length    = float(payload["design_length"])
    color_count      = int(payload["color_count"])
    stitch_count     = int(payload["stitch_count"])
    sample_plant     = str(payload["sample_plant"])
    priority         = str(payload["style_priority"])
    damage_pct       = float(payload.get("damage_pct", 0.0))

    effective_qty    = math.ceil(order_qty * (1 + damage_pct / 100.0))

    # FIX 1: Resolve live monthly capacities (from payload override or defaults)
    monthly_capacity = _resolve_monthly_capacity(payload)

    # Design complexity (derived)
    complexity_info  = _derive_complexity(design_width, design_length, color_count, stitch_count)
    complexity       = complexity_info["final_complexity"]

    # FIX 3: Production days with embroidery scaling on design area/stitches/colors
    prod = _calc_production_days(
        effective_qty, daily_commitment,
        design_width, design_length, color_count, stitch_count,
        sample_plant=sample_plant,
        monthly_capacity=monthly_capacity,
    )

    recommended_daily        = RECOMMENDED_DAILY_COMMITMENT[complexity]
    daily_commitment_warning = (
        None if daily_commitment >= recommended_daily * 0.85
        else (
            f"daily_commitment {int(daily_commitment)} pcs/day is low for {complexity} complexity "
            f"(dataset average: {recommended_daily} pcs/day). "
            f"Embroidery days may be overstated — consider increasing daily_commitment."
        )
    )

    # FIX 1 & 2: Sample plant capacity check with live capacity
    sp_capacity = _check_sample_plant_capacity(
        sample_plant, effective_qty, daily_commitment, monthly_capacity
    )

    # FIX 4: Plant ranking with live capacity + sample plant boost
    plant_ranking = _score_plants(
        priority, complexity, effective_qty, daily_commitment,
        sample_plant, monthly_capacity
    )

    # Date / deadline calculations
    approved_date  = payload.get("bulk_order_approved_date")
    buyer_req_date = payload.get("buyer_required_date")

    predicted_completion = None
    deadline_match       = None
    days_to_deadline     = None
    lead_days            = prod["total_production_days"] + 3

    if approved_date:
        try:
            start = datetime.strptime(approved_date, "%Y-%m-%d")
            predicted_completion = (
                start + timedelta(days=prod["total_production_days"])
            ).strftime("%Y-%m-%d")
            if buyer_req_date:
                req  = datetime.strptime(buyer_req_date, "%Y-%m-%d")
                comp = datetime.strptime(predicted_completion, "%Y-%m-%d")
                days_to_deadline = (req - comp).days
                deadline_match   = "Match" if days_to_deadline >= 0 else "No Match"
        except ValueError:
            pass

    # Allocation logic
    if sp_capacity["has_capacity"]:
        allocation_type = "Single Plant"
        allocated_plant = sample_plant
        allocation_note = "Sample plant has capacity — full bulk order allocated to sample plant"
        system_action   = "Proceed"
        buyer_email     = "No"
    else:
        solo_alternatives = [
            p for p in plant_ranking
            if p["can_handle_solo"] and p["plant"] != sample_plant
        ]
        if solo_alternatives:
            allocation_type = "Single Plant"
            allocated_plant = solo_alternatives[0]["plant"]
            allocation_note = (
                f"Sample plant no capacity — allocated to best alternative single plant: {allocated_plant}"
            )
            system_action   = "Due Plant No Capacity Bulk order Need to divide"
            buyer_email     = "No"
        else:
            allocation_type = "Split Between Sub Plants"
            top2            = [p["plant"] for p in plant_ranking[:2]]
            allocated_plant = " / ".join(top2)
            allocation_note = "No single plant has sufficient capacity — split between top 2 sub plants"
            system_action   = "Due Plant No Capacity Bulk order Need to divide"
            buyer_email     = "No"

    if deadline_match == "No Match":
        system_action = "Draft revised completion email for mother company bulk agent approval"
        buyer_email   = "Yes"

    return {
        "effective_quantity":            effective_qty,
        "damage_pct":                    damage_pct,
        "complexity":                    complexity_info,
        "production_days":               prod,
        "lead_days":                     lead_days,
        "predicted_completion":          predicted_completion,
        "deadline_match":                deadline_match,
        "days_to_deadline":              days_to_deadline,
        "sample_plant_capacity":         sp_capacity,
        "plant_ranking":                 plant_ranking,
        "allocation_type":               allocation_type,
        "allocated_plant":               allocated_plant,
        "allocation_note":               allocation_note,
        "system_action":                 system_action,
        "buyer_email_required":          buyer_email,
        "buyer_approval_required":       buyer_email == "Yes",
        "monthly_capacity_used":         monthly_capacity,
        "total_network_capacity":        sum(monthly_capacity.values()),
        "recommended_daily_commitment":  recommended_daily,
        "daily_commitment_warning":      daily_commitment_warning,
    }


# ── OpenAI system prompt ───────────────────────────────────────────
_SYSTEM_PROMPT = """
You are an AI planning assistant for a garment bulk order management system.

You receive a bulk order request payload and pre-computed context values.
Return ONLY a valid JSON object — no markdown fences, no explanation outside the JSON.

IMPORTANT RULES for using context values:
1. Use context.production_days.embroidery_days (already adjusted for design area/stitches/colors).
2. Use context.production_days.cutting_days and sewing_days from context (qty-tier based).
3. Use context.plant_ranking for all plant scores and rankings — do NOT recalculate.
4. Use context.sample_plant_capacity for capacity check — do NOT override.
5. Use context.monthly_capacity_used for each plant's capacity — these may differ from defaults.
6. Working days per plant are in each plant_ranking entry as 'working_days'.
7. Sample plant gets first priority when it has capacity (flowchart rule 2).

Key rules from the flowchart:
1. Sample plant always gets first priority (check its capacity first)
2. If sample plant has capacity → allocate full bulk to sample plant
3. If no capacity → confirm with sub plant manager → check other single plants
4. If no single plant can handle → split between top 2 sub plants
5. Buyer is never directly involved in splitting decisions
6. Email to mother company bulk agent only when deadline cannot be met
7. Design complexity is derived from width/length/colors/stitches — never user-supplied

Schema (preserve all original keys):

{
  "status": "success",
  "bulk_order_id": string,
  "style_id": string,
  "buyer_name": string,
  "confidence": "OK" | "LOW",

  "design_analysis": {
    "design_width": float,
    "design_length": float,
    "color_count": integer,
    "stitch_count": integer,
    "matrix_complexity": "Low" | "Medium" | "High",
    "color_impact": "Low" | "Medium" | "High",
    "stitch_impact": "Low" | "Medium" | "High",
    "derived_complexity": "Low" | "Medium" | "High",
    "complexity_score": float
  },

  "order_summary": {
    "bulk_order_quantity": integer,
    "effective_quantity": integer,
    "damage_pct": float,
    "daily_commitment": float,
    "style_priority": string,
    "sample_plant": string
  },

  "production_days": {
    "cutting_days": integer,
    "sewing_days": integer,
    "embroidery_days": integer,
    "base_embroidery_days": integer,
    "design_emb_days": integer,
    "design_area_factor": float,
    "stitch_factor": float,
    "color_factor": float,
    "capacity_factor": float,
    "capacity_load_ratio": float,
    "total_production_days": integer,
    "lead_days": integer,
    "predicted_completion_date": string | null,
    "bulk_shipment_date": string | null,
    "recommended_daily_commitment": integer,
    "daily_commitment_warning": string | null,
    "large_order_warning": string | null
  },

  "deadline_assessment": {
    "buyer_required_date": string | null,
    "deadline_match_status": "Match" | "No Match" | "N/A",
    "days_to_deadline": integer | null,
    "buyer_email_required": "Yes" | "No",
    "buyer_approval_required": boolean,
    "system_action": string
  },

  "capacity_check": {
    "sample_plant": string,
    "sample_plant_capacity_status": "Yes" | "No",
    "plant_working_days": integer,
    "monthly_styles_capacity": integer,
    "monthly_piece_capacity": integer,
    "load_ratio": float,
    "utilisation_pct": float,
    "manager_confirmation": "Have Capacity" | "No Capacity"
  },

  "allocation": {
    "allocation_type": "Single Plant" | "Split Between Sub Plants",
    "allocated_bulk_plant": string,
    "allocated_plant_location": string | null,
    "allocation_remark": string,
    "plant_ranking": [
      {
        "rank": integer,
        "plant": string,
        "location": string,
        "score": float,
        "quality_rating": float,
        "monthly_capacity": integer,
        "working_days": integer,
        "can_handle_solo": boolean,
        "preferred": boolean,
        "is_sample_plant": boolean
      }
    ]
  },

  "planning_output": {
    "final_decision": string,
    "risk_level": "Critical" | "High" | "Medium" | "Low",
    "risk_summary": string,
    "recommended_action": string
  }
}

Rules:

confidence: "OK" if buyer_name is known (George/Hirdaramani/M&S/Tesco), else "LOW"

allocated_plant_location: location of the first plant in allocated_bulk_plant
  (for split orders, use location of the primary/first plant)

final_decision options (from flowchart step 14):
  "Accept (Same Plant)"
  "Accept (Alternative Plant)"
  "Accept (Split Between Plants)"
  "Waiting for Buyer Approval (Deadline Not Match)"
  "Manual Review / Re-plan if Required"

risk_level:
  deadline No Match + no capacity  -> "Critical"
  deadline No Match                -> "High"
  split allocation                 -> "Medium"
  single plant, match              -> "Low"

risk_summary: one concise sentence.

bulk_shipment_date: predicted_completion_date + 2 days (standard shipment lead)
  If predicted_completion_date is null, bulk_shipment_date is also null.

Return ONLY the JSON. No extra text.
"""


def _call_openai(payload: dict, ctx: dict) -> dict:
    user_msg = (
        f"REQUEST:\n{json.dumps(payload, indent=2, default=str)}\n\n"
        f"COMPUTED CONTEXT:\n{json.dumps(ctx, indent=2, default=str)}\n\n"
        "Return the bulk order planning JSON."
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


# ── Routes ─────────────────────────────────────────────────────────

@component2_bp.route("/health", methods=["GET"])
def health():
    return jsonify({
        "component": "2 — Bulk Order Planning & Capacity Allocation",
        "status": "ok"
    })


@component2_bp.route("/predict", methods=["POST"])
def predict():
    """
    Required fields:
        buyer_name, style_id, bulk_order_quantity, daily_commitment,
        style_priority, design_width, design_length,
        color_count, stitch_count, sample_plant

    Optional fields:
        bulk_order_id, buyer_required_date, bulk_order_approved_date, damage_pct

    FIX 1 — New optional field:
        monthly_capacity: {
            "Dinusha Embroidery": 100,
            "MRC Group": 30,
            ...
        }
        Overrides the default monthly capacity (styles/month) per plant.
        Plants not listed fall back to their defaults.
        Working days and rankings update automatically from these values.

    NOTE: design_complexity is NOT accepted — it is derived automatically.
    """
    data = request.get_json(force=True, silent=True)
    if not data:
        return jsonify({"error": "Request body must be valid JSON"}), 400

    required = [
        "buyer_name", "style_id", "bulk_order_quantity", "daily_commitment",
        "style_priority", "design_width", "design_length",
        "color_count", "stitch_count", "sample_plant",
    ]
    missing = [f for f in required if f not in data]
    if missing:
        return jsonify({"error": f"Missing required fields: {missing}"}), 400

    try:
        buyer_name    = str(data["buyer_name"])
        style_id      = str(data["style_id"])
        bulk_id       = str(data.get("bulk_order_id", "N/A"))
        order_qty     = int(data["bulk_order_quantity"])
        daily_comm    = float(data["daily_commitment"])
        priority      = str(data["style_priority"])
        design_width  = float(data["design_width"])
        design_length = float(data["design_length"])
        color_count   = int(data["color_count"])
        stitch_count  = int(data["stitch_count"])
        sample_plant  = str(data["sample_plant"])
        damage_pct    = float(data.get("damage_pct", 0.0))
    except (ValueError, TypeError) as e:
        return jsonify({"error": f"Invalid field value: {e}"}), 400

    if not (1 <= order_qty):
        return jsonify({"error": "bulk_order_quantity must be >= 1"}), 400
    if priority not in PRIORITY_VALUES:
        return jsonify({"error": f"style_priority must be one of: {PRIORITY_VALUES}"}), 400
    if sample_plant not in ALL_PLANTS:
        return jsonify({"error": f"sample_plant must be one of: {ALL_PLANTS}"}), 400

    # ── FIX 6: Hard-reject physically impossible / nonsense design values ──
    # stitch_count: real embroidery designs range 1,000–500,000 stitches.
    #   A value of 12 or 50 is a data-entry error — the formula would silently
    #   reduce embroidery days below their correct value (stitch_factor < 1.0).
    if not (1_000 <= stitch_count <= 500_000):
        return jsonify({
            "error": (
                f"stitch_count {stitch_count} is outside the valid range [1,000 – 500,000]. "
                "Real embroidery designs have a minimum of ~1,000 stitches (small logo) "
                "and max ~500,000 stitches (very large full-coverage design)."
            )
        }), 400

    # design_width / design_length: industrial machines max out at ~52 cm (20.5 in).
    #   100 cm × 100 cm = 1 m² — physically impossible on any embroidery machine.
    if not (0.1 <= design_width <= 52.0):
        return jsonify({
            "error": (
                f"design_width {design_width} cm is outside the valid range [0.1 – 52.0 cm]. "
                "The largest industrial embroidery machines (e.g. Barudan BEXT-S1501C) "
                "support a maximum field of ~52 cm wide."
            )
        }), 400
    if not (0.1 <= design_length <= 52.0):
        return jsonify({
            "error": (
                f"design_length {design_length} cm is outside the valid range [0.1 – 52.0 cm]. "
                "The largest industrial embroidery machines support a maximum field of ~52 cm long."
            )
        }), 400

    # color_count: commercial machines support up to 15 thread colors per design.
    if not (1 <= color_count <= 15):
        return jsonify({
            "error": (
                f"color_count {color_count} is outside the valid range [1 – 15]. "
                "Commercial embroidery machines support up to 15 thread colors per design; "
                "real-world production typically uses 6 or fewer for optimal efficiency."
            )
        }), 400
    # ── End FIX 6 hard-reject validations ──

    # Validate monthly_capacity if provided
    if "monthly_capacity" in data:
        if not isinstance(data["monthly_capacity"], dict):
            return jsonify({"error": "monthly_capacity must be a JSON object"}), 400
        for plant_name, cap in data["monthly_capacity"].items():
            if plant_name not in ALL_PLANTS:
                return jsonify({"error": f"Unknown plant in monthly_capacity: '{plant_name}'"}), 400
            try:
                if int(cap) < 0:
                    raise ValueError
            except (ValueError, TypeError):
                return jsonify({"error": f"monthly_capacity['{plant_name}'] must be a non-negative integer"}), 400

    try:
        ctx = _build_context(data)
    except Exception as e:
        return jsonify({"error": f"Context computation failed: {e}"}), 500

    payload_for_ai = {k: v for k, v in data.items() if k != "design_complexity"}
    payload_for_ai["bulk_order_id"] = bulk_id

    try:
        result = _call_openai(payload_for_ai, ctx)
        return jsonify(result), 200
    except json.JSONDecodeError as e:
        return jsonify({"error": f"AI response parse error: {e}"}), 500
    except RuntimeError as e:
        return jsonify({"error": str(e)}), 503
    except Exception as e:
        return jsonify({"error": f"Prediction failed: {e}"}), 500