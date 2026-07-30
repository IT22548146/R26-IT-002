"""
Component 2 — Bulk Order Planning & Capacity Allocation
=========================================================
Models loaded  (produced by component2_all_fixes_notebook.ipynb):
  c2_model_cutting.pkl     — RandomForestRegressor  → Cutting_Days
  c2_model_sewing.pkl      — RandomForestRegressor  → Sewing_Days
  c2_model_embroidery.pkl  — RandomForestRegressor  → Embroidery_Days
  c2_model_allocation.pkl  — GradientBoostingClassifier → Single vs Split
  c2_model_deadline.pkl    — GradientBoostingClassifier → Deadline Match

POST /api/component2/predict
Request body (JSON):
{
    "style_id":                "BYGR5001",
    "buyer_name":              "George",
    "bulk_order_quantity":     10360,
    "daily_commitment":        364,
    "style_priority":          "Normal",
    "design_width":            25,
    "design_length":           38,
    "color_count":             8,
    "stitch_count":            1000,
    "sample_plant":            "MRC Group",
    "sp_cap_util_pct":         87.0,
    "bulk_order_approved_date":"2025-03-01",
    "buyer_required_date":     "2025-06-15",
    "damage_pct":              0.0,
    "shipment_days":           18,
    "monthly_capacity": {
        "Dinusha Embroidery":        11,
        "Regal Image International": 160,
        "MRC Group":                 132,
        "The Bobbin Group":          178,
        "Sunrose Lanka (Pvt) Ltd":   146,
        "Amsral Lanka Enterprises":  113
    }
}
"""

import os
import math
import datetime
import joblib
import numpy as np
import pandas as pd
from flask import Blueprint, request, jsonify

component2_bp = Blueprint("component2", __name__)

# ── Paths ──────────────────────────────────────────────────────────
BASE_DIR   = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MODELS_DIR = os.path.join(BASE_DIR, "models")

# ── Static lookups (must match notebook exactly) ───────────────────
QUALITY_MAP = {
    "Dinusha Embroidery":        4.8,
    "Regal Image International": 4.6,
    "MRC Group":                 4.5,
    "The Bobbin Group":          4.4,
    "Sunrose Lanka (Pvt) Ltd":   4.3,
    "Amsral Lanka Enterprises":  4.2,
}

ALL_PLANTS = list(QUALITY_MAP.keys())

ALLOCATION_GUIDE = {
    ("High",       "Hard"):   ["Dinusha Embroidery", "Regal Image International"],
    ("High",       "High"):   ["Dinusha Embroidery", "Regal Image International"],
    ("High",       "Medium"): ["Dinusha Embroidery", "The Bobbin Group"],
    ("Normal",     "High"):   ["Dinusha Embroidery", "Regal Image International"],
    ("Normal",     "Medium"): ["The Bobbin Group",   "Sunrose Lanka (Pvt) Ltd"],
    ("Low",        "Low"):    ["MRC Group",           "Amsral Lanka Enterprises"],
    ("No Urgency", "Low"):    ["MRC Group",           "Amsral Lanka Enterprises"],
}

PRIORITY_ENC   = {"No Urgency": 0, "Low": 1, "Normal": 2, "High": 3}
COMPLEXITY_ENC = {"Low": 1, "Medium": 2, "High": 3, "Hard": 3}
BUYER_ENC      = {"George": 0, "Hirdaramani": 1, "M&S": 2, "Tesco": 3}
KNOWN_BUYERS   = list(BUYER_ENC.keys())

# Stitch count training range (updated — dataset now includes 200–1017)
STITCH_MIN_TRAIN = 200
STITCH_MAX_TRAIN = 19992

# Daily commitment adjusted training range (min=130, max=1068 pcs/day)
# daily_commitment_adj values outside this range mean the ML models are
# extrapolating — the formula floor is more reliable than ML in that region.
DAILY_COMMIT_ADJ_MIN_TRAIN = 130
DAILY_COMMIT_ADJ_MAX_TRAIN = 1068

# ── Feature lists (must match notebook cell 09 exactly) ───────────
# ── M1/M2 features: quantity, capacity, design dimensions only ─────────────
# Stitch features intentionally excluded — cutting and sewing are physically
# independent of stitch count (confirmed bug: stitch changes shifted M1/M2).
# Total_Network_Cap / Order_vs_Network excluded from M1/M2/M3 — these are
# allocation-level signals, not physical production time drivers (confirmed bug:
# changing other plants' capacities shifted cutting/sewing days).
M1_M2_FEATS = [
    # Quantity & throughput
    "Bulk_Order_Quantity", "Daily_Commitment", "Daily_Commitment_Adj",
    # Design dimensions & area
    "Design_Width", "Design_Length", "Design_Area",
    # Color (affects thread setup — but NOT stitch)
    "Color_Count", "Color_Impact_Enc", "Color_Norm",
    # Design complexity (matrix only — no stitch component)
    "Complexity_Matrix_Enc", "Design_Complexity_Enc",
    # Order context
    "Priority_Enc", "Buyer_Enc",
    # Capacity signals (plant-level only)
    "SP_Monthly_Cap_F", "SP_Cap_Util_F", "SP_Quality_F",
    "Cap_Mult",
    "Cap_Headroom",
    "Order_vs_SP_Cap",
    # Time
    "Order_Month", "Is_Q4",
    # Risk
    "Damage_Pct", "Cap_Pressure_Index",
]

# ── M3 features: everything M1/M2 has PLUS all stitch features ────────────
# Embroidery days are physically driven by stitch count and design complexity.
M3_FEATS = M1_M2_FEATS + [
    "Stitch_Count", "Stitch_Norm", "Complexity_Mult",
    "Stitch_Density", "Stitch_Impact_Enc", "Design_Score",
]

# SHARED_FEATS kept as alias for M3_FEATS for backward compatibility
# (M5 and any callers that reference SHARED_FEATS continue to work)
SHARED_FEATS = M3_FEATS

M4_FEATS = [
    "Bulk_Order_Quantity", "Daily_Commitment",
    "Design_Complexity_Enc", "Complexity_Matrix_Enc", "Design_Score",
    "Priority_Enc", "Buyer_Enc",
    "SP_Monthly_Cap_F", "SP_Cap_Util_F", "SP_Quality_F",
    "Cap_Mult", "SP_Working_Days",
    # Network features kept here — allocation genuinely depends on network pressure
    "Total_Network_Cap", "Order_vs_SP_Cap", "Order_vs_Network",
    "Order_Month", "Is_Q4",
    "Color_Count", "Stitch_Count", "Design_Area",
]

# Design_Complexity_Enc excluded from M5 — was causing target leakage
# Complexity signal reaches M5 via Complexity_Mult, Stitch_Norm, Design_Score etc.
M5_FEATS = [f for f in SHARED_FEATS if f != "Design_Complexity_Enc"] + [
    "Cutting_Days", "Sewing_Days", "Embroidery_Days",
    "Total_Production_Days", "Shipment_Days", "Lead_Days",
    "Days_Available", "Lead_Gap",  # KEY: buyer deadline gap signal
    "P1_Cap_Util_F", "P1_Monthly_Cap_F",
    "Split_Alloc_Flag", "Damage_Pct", "Cap_Pressure_Index",
]

# ── Lazy model loader ──────────────────────────────────────────────
_models = {}

def _load_models():
    if _models:
        return _models
    names = {
        "cutting":    "c2_model_cutting.pkl",
        "sewing":     "c2_model_sewing.pkl",
        "embroidery": "c2_model_embroidery.pkl",
        "alloc":      "c2_model_allocation.pkl",
        "deadline":   "c2_model_deadline.pkl",
    }
    missing = []
    for key, fname in names.items():
        path = os.path.join(MODELS_DIR, fname)
        if not os.path.exists(path):
            missing.append(fname)
        else:
            _models[key] = joblib.load(path)
    if missing:
        raise RuntimeError(
            f"Missing model files: {missing}. "
            f"Run component2_final_notebook.ipynb first."
        )
    return _models


# ── Design complexity helpers (match notebook functions exactly) ───
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
    return "Low" if c <= 3 else "Medium" if c <= 6 else "High"


def _stitch_impact(s: int) -> str:
    return "Low" if s <= 7000 else "Medium" if s <= 15000 else "High"


def _validate_stitch(s: int):
    """
    Validate and clamp stitch count to training range (200–19992).
    Values 200–19992 pass through with no warning.
    Returns (clamped_value, warning_string or None).
    """
    if s < 10:
        return STITCH_MIN_TRAIN, (
            f"Stitch count {s} is extremely low — likely a data entry error. "
            f"Clamped to {STITCH_MIN_TRAIN}. Confidence=LOW."
        )
    if s < STITCH_MIN_TRAIN:
        return STITCH_MIN_TRAIN, (
            f"Stitch count {s} is below the training minimum ({STITCH_MIN_TRAIN}). "
            f"Clamped to {STITCH_MIN_TRAIN}. Confidence=LOW."
        )
    if s > STITCH_MAX_TRAIN:
        return STITCH_MAX_TRAIN, (
            f"Stitch count {s} exceeds the training maximum ({STITCH_MAX_TRAIN}). "
            f"Clamped to {STITCH_MAX_TRAIN}. Confidence=LOW."
        )
    return s, None  # 200–19992: accepted without clamping or warning


# ── Plant scoring (matches notebook score_plants_bulk) ─────────────
def _score_plants_bulk(priority: str, complexity: str,
                        buffer_days: int, cap_util_pct: float,
                        monthly_caps: dict, order_qty: int,
                        daily_commitment: int     = 500,
                        daily_commitment_adj: int = 500,
                        sp_working_days: int      = 25) -> list:
    """
    Returns list of (plant_name, score, can_handle_solo).

    Scoring formula (per plant):
        quality       — plant quality rating (4.2–4.8)
        miss_penalty  — historical miss rate × 3
        cap_penalty   — order_qty / (plant_monthly_cap × working_days) × 0.10
                        Raw ratio per plant so a plant with tiny monthly capacity
                        (e.g. cap=11) is heavily penalised vs one with large
                        capacity (cap=178).
        pref_bonus    — +0.5 if plant is in ALLOCATION_GUIDE for priority+complexity
        buf_bonus     — min(buffer_days × 0.03, 0.30)
        score         = quality - miss_penalty - cap_penalty + pref_bonus + buf_bonus

    can_handle_solo (FIX: network-share ratio, replaces unit-mismatched formula):
        A plant can handle the order solo only if it holds ≥ MIN_SOLO_SHARE (15%)
        of the combined network capacity. This correctly flags low-capacity plants
        (e.g. Bobbin at 10/634 = 1.6% → False) while accepting normal plants
        (e.g. Dinusha at 120/634 = 18.9% → True). The previous formula multiplied
        styles/month × pcs/day (unit mismatch), which always inflated small
        capacities into a passing value (10 × 400 = 4000 ≥ 1200 → True — wrong).
    """
    hist_miss = {
        "Dinusha Embroidery":        0.10,
        "Regal Image International": 0.12,
        "MRC Group":                 0.15,
        "The Bobbin Group":          0.13,
        "Sunrose Lanka (Pvt) Ltd":   0.14,
        "Amsral Lanka Enterprises":  0.16,
    }

    preferred = ALLOCATION_GUIDE.get(
        (priority, complexity),
        ALLOCATION_GUIDE.get(("No Urgency", "Low"), ALL_PLANTS)
    )

    scores = {}
    for plant in ALL_PLANTS:
        quality      = QUALITY_MAP.get(plant, 4.3)
        miss_r       = hist_miss.get(plant, 0.15)
        plant_cap    = monthly_caps.get(plant, 150)
        pref_bon     = 0.5 if plant in preferred else 0.0
        buf_bon      = min(buffer_days * 0.03, 0.30)

        # Per-plant capacity load: what share of this plant's AVAILABLE capacity
        # does the order consume? monthly_caps already holds units available over
        # the production window, so dividing by sp_working_days as well counted
        # the capacity 25x over and made this penalty almost meaningless
        # (dropping a plant from 60,000 free units to 2,000 moved its score by
        # 0.02). Compare the order against the capacity directly.
        raw_ratio = order_qty / max(plant_cap, 1)
        cap_pen   = raw_ratio * 0.10

        # can_solo now asks the literal question: does the order fit inside this
        # plant's available capacity for the production window? The old network
        # share test (>= 15% of total capacity) said nothing about whether the
        # order actually fits - a plant with 2,000 units free still passed it.
        can_solo = plant_cap >= order_qty

        score = quality - (miss_r * 3) - cap_pen + pref_bon + buf_bon
        scores[plant] = (round(score, 4), can_solo)

    ranked = sorted(scores.items(), key=lambda x: x[1][0], reverse=True)
    return [(p, s, solo) for p, (s, solo) in ranked]


# ── Feature engineering (all fixes applied) ───────────────────────
def _build_features(
        order_qty:            int,
        daily_commitment:     int,
        design_width:         float,
        design_length:        float,
        color_count:          int,
        stitch_clamped:       int,   # already validated/clamped
        priority:             str,
        buyer_name:           str,
        sp_monthly_cap:       float,
        sp_util:              float,
        sp_quality:           float,
        order_month:          int,
        is_q4:                int,
        damage_pct:           float  = 0.0,
        sp_working_days:      int    = 25,
        total_network_cap:    int    = 900,
) -> pd.DataFrame:

    enc_map     = {"Low": 1, "Medium": 2, "High": 3}
    matrix_c    = _matrix_complexity(design_width, design_length)
    color_imp   = _color_impact(color_count)
    stitch_imp  = _stitch_impact(stitch_clamped)
    design_area = design_width * design_length

    cmx_e  = enc_map[matrix_c]
    ci_e   = enc_map[color_imp]
    si_e   = enc_map[stitch_imp]
    dc_enc = max(cmx_e, ci_e, si_e)
    ds     = (cmx_e + ci_e + si_e) / 3.0

    # ── Fix 1: Stitch + Color normalized features ──────────────────
    stitch_norm     = (stitch_clamped - STITCH_MIN_TRAIN) / (STITCH_MAX_TRAIN - STITCH_MIN_TRAIN)
    color_norm      = (color_count - 1) / 8.0
    complexity_mult = round(1.0 + stitch_norm * 0.55 + color_norm * 0.25, 6)
    stitch_density  = round(stitch_clamped / (design_area + 1), 4)

    # ── Fix 2: Capacity multiplier ─────────────────────────────────
    # FIX A: training notebook uses quadratic formula:
    #   Cap_Mult = 1.0 + (util/100)^2 × 0.40
    # Previous inference code used a linear piecewise formula
    #   (1 + max(0,(util-60)/40) × 0.40) which diverges from training
    #   by up to 0.144 at util=60% and only converges at util=100%.
    # Matching the training formula ensures the ML models receive the
    # same Cap_Mult value they were trained on.
    cap_mult = round(1.0 + (sp_util / 100.0) ** 2 * 0.40, 6)
    cap_headroom = round(max(0.0, 60.0 - sp_util) / 60.0, 6)

    # ── Fix 3: Capacity-adjusted daily commitment ──────────────────
    daily_red            = max(0.0, (sp_util - 60.0) / 40.0) * 0.35
    daily_commitment_adj = max(50, int(daily_commitment * (1.0 - daily_red)))

    buyer_enc       = BUYER_ENC.get(buyer_name, 2)
    order_vs_sp     = round(order_qty / (sp_monthly_cap * sp_working_days + 1), 4)
    order_vs_net    = round(order_qty / (total_network_cap + 1), 6)
    cap_pressure    = round((sp_util / 100.0) * order_vs_sp, 6)

    return pd.DataFrame([{
        # Quantity & throughput
        "Bulk_Order_Quantity":   order_qty,
        "Daily_Commitment":      daily_commitment,
        "Daily_Commitment_Adj":  daily_commitment_adj,
        # Design
        "Design_Width":          design_width,
        "Design_Length":         design_length,
        "Design_Area":           design_area,
        # Stitch & color
        "Color_Count":           color_count,
        "Stitch_Count":          stitch_clamped,
        "Stitch_Norm":           round(stitch_norm, 6),
        "Color_Norm":            round(color_norm, 6),
        "Complexity_Mult":       complexity_mult,
        "Stitch_Density":        stitch_density,
        # Complexity encodings
        "Design_Complexity_Enc": dc_enc,
        "Complexity_Matrix_Enc": cmx_e,
        "Color_Impact_Enc":      ci_e,
        "Stitch_Impact_Enc":     si_e,
        "Design_Score":          ds,
        # Order context
        "Priority_Enc":          PRIORITY_ENC.get(priority, 2),
        "Buyer_Enc":             buyer_enc,
        # Capacity
        "SP_Monthly_Cap_F":      sp_monthly_cap,
        "SP_Cap_Util_F":         sp_util,
        "SP_Quality_F":          sp_quality,
        "Cap_Mult":              cap_mult,
        "Cap_Headroom":          cap_headroom,
        "Total_Network_Cap":     total_network_cap,
        "Order_vs_SP_Cap":       order_vs_sp,
        "Order_vs_Network":      order_vs_net,
        # Time
        "Order_Month":           order_month,
        "Is_Q4":                 is_q4,
        # Risk
        "Damage_Pct":            damage_pct,
        "Cap_Pressure_Index":    cap_pressure,
        # M4 extra
        "SP_Working_Days":       sp_working_days,
        # M5 placeholders — filled after M1–M3
        "Days_Available":        0,    # filled after lead_days is known
        "Lead_Gap":              0,    # filled after lead_days is known
        "Cutting_Days":          0.0,
        "Sewing_Days":           0.0,
        "Embroidery_Days":       0.0,
        "Total_Production_Days": 0.0,
        "Shipment_Days":         0.0,
        "Lead_Days":             0.0,
        "P1_Cap_Util_F":         sp_util,
        "P1_Monthly_Cap_F":      sp_monthly_cap,
        "Split_Alloc_Flag":      0,
    }])


# ── Routes ────────────────────────────────────────────────────────
@component2_bp.route("/health", methods=["GET"])
def health():
    return jsonify({
        "component": "2 — Bulk Order Planning & Capacity Allocation",
        "status": "ok"
    })


@component2_bp.route("/predict", methods=["POST"])
def predict():
    """
    Full Component 2 bulk order planning prediction.

    Required fields:
        buyer_name, bulk_order_quantity, daily_commitment,
        style_priority, design_width, design_length,
        color_count, stitch_count, sample_plant,
        sp_cap_util_pct, bulk_order_approved_date,
        monthly_capacity

    Optional fields:
        buyer_required_date  (YYYY-MM-DD)
        damage_pct           (default 0.0)
        shipment_days        (default 18)
        style_id
    """
    data = request.get_json(force=True, silent=True)
    if not data:
        return jsonify({"error": "Request body must be valid JSON"}), 400

    required = [
        "buyer_name", "bulk_order_quantity", "daily_commitment",
        "style_priority", "design_width", "design_length",
        "color_count", "stitch_count", "sample_plant",
        "sp_cap_util_pct", "bulk_order_approved_date",
        "monthly_capacity",
    ]
    missing = [f for f in required if f not in data]
    if missing:
        return jsonify({"error": f"Missing required fields: {missing}"}), 400

    # ── Parse & validate inputs ────────────────────────────────────
    try:
        style_id         = data.get("style_id", "N/A")
        buyer_name       = str(data["buyer_name"])
        order_qty        = int(data["bulk_order_quantity"])
        daily_commitment = int(data["daily_commitment"])
        priority         = str(data["style_priority"])
        design_width     = float(data["design_width"])
        design_length    = float(data["design_length"])
        color_count      = int(data["color_count"])
        stitch_count     = int(data["stitch_count"])
        sample_plant     = str(data["sample_plant"])
        sp_util          = float(data["sp_cap_util_pct"])
        monthly_caps     = dict(data["monthly_capacity"])
        damage_pct       = float(data.get("damage_pct", 0.0))
        shipment_days    = int(data.get("shipment_days", 18))
    except (ValueError, TypeError) as e:
        return jsonify({"error": f"Invalid field value: {e}"}), 400

    if priority not in PRIORITY_ENC:
        return jsonify({
            "error": f"style_priority must be one of: {list(PRIORITY_ENC.keys())}"
        }), 400

    # ── Auto-derive fields (no longer needed in payload) ──────────
    # sp_monthly_cap from monthly_capacity dict
    sp_monthly_cap = float(monthly_caps.get(sample_plant, 150))

    # total_network_cap = sum of all plant monthly capacities
    total_network_cap = int(sum(monthly_caps.values()))

    # receive_month + is_q4 from bulk_order_approved_date
    try:
        approved_dt   = datetime.date.fromisoformat(data["bulk_order_approved_date"])
        order_month   = approved_dt.month
        is_q4         = 1 if order_month >= 10 else 0
    except ValueError:
        return jsonify({
            "error": "bulk_order_approved_date must be YYYY-MM-DD format"
        }), 400

    # buyer_required_date → days_available (for gap analysis)
    days_available = None
    if "buyer_required_date" in data:
        try:
            required_dt    = datetime.date.fromisoformat(data["buyer_required_date"])
            days_available = (required_dt - approved_dt).days
        except ValueError:
            return jsonify({
                "error": "buyer_required_date must be YYYY-MM-DD format"
            }), 400

    # sp_quality from QUALITY_MAP (override allowed via payload)
    sp_quality = float(data.get("sp_quality", QUALITY_MAP.get(sample_plant, 4.3)))

    # ── Stitch count validation + clamping ─────────────────────────
    stitch_clamped, stitch_warning = _validate_stitch(stitch_count)
    confidence_flags = []
    if stitch_warning:
        confidence_flags.append("LOW_STITCH")
    if buyer_name not in KNOWN_BUYERS:
        confidence_flags.append("UNKNOWN_BUYER")

    # ── Near-saturated plant check ──────────────────────────────────
    # A plant at ≥95% utilisation has no realistic free capacity for a
    # new order. The prediction is still returned so the Spring Boot API
    # can make a routing decision, but capacity_status is set to BLOCKED
    # and a human-readable warning is added to the response.
    # The threshold is 95% — anything in the near-saturated zone (95–100%)
    # means the plant cannot reliably absorb new work without delay.
    BLOCKED_UTIL_THRESHOLD = 95.0
    plant_blocked = sp_util >= BLOCKED_UTIL_THRESHOLD
    plant_blocked_warning = (
        f"Sample plant '{sample_plant}' is at {sp_util}% utilisation "
        f"(≥{int(BLOCKED_UTIL_THRESHOLD)}% threshold). It has no realistic free "
        f"capacity for this order. Production days shown are indicative only — "
        f"the order cannot start until existing work clears. "
        f"Consider reassigning to a lower-utilisation plant."
    ) if plant_blocked else None
    if plant_blocked:
        confidence_flags.append("PLANT_BLOCKED")

    # ── Implausible monthly capacity check ──────────────────────────────────
    # If the order quantity exceeds 12 months of the sample plant's stated
    # monthly capacity, the capacity value is almost certainly a data entry
    # error (e.g. "1" typed instead of "100"). This causes cap_pen to explode
    # in plant scoring, producing nonsense negative scores and misleading
    # can_handle_solo=False flags for a plant that may actually be capable.
    # Threshold: order_qty > 12 x (sp_monthly_cap x sp_working_days).
    # 12 months means the order alone consumes more than a full year of that
    # plant's capacity — physically implausible for a single bulk order.
    _SP_WORKING_DAYS_DEFAULT = 25
    _implausible_cap_threshold = 12 * sp_monthly_cap * _SP_WORKING_DAYS_DEFAULT
    implausible_capacity = order_qty > _implausible_cap_threshold
    implausible_capacity_warning = (
        f"Sample plant '{sample_plant}' has monthly_capacity={sp_monthly_cap}, "
        f"which means this order ({order_qty} pcs) would consume "
        f"{order_qty / max(sp_monthly_cap * _SP_WORKING_DAYS_DEFAULT, 1):.1f}x "
        f"its monthly capacity. This is likely a data entry error. "
        f"Plant scores, can_handle_solo, and production days may be unreliable. "
        f"Please verify monthly_capacity['{sample_plant}']."
    ) if implausible_capacity else None
    if implausible_capacity:
        confidence_flags.append("IMPLAUSIBLE_CAPACITY")

    # ── Daily commitment OOD pre-check ─────────────────────────────
    # Compute daily_commitment_adj here (same formula as _build_features)
    # so we can flag OOD before model calls and adjust the hybrid logic.
    # FIX D: split OOD into two directions — high and low behave differently.
    #   OOD_HIGH (daily_adj > max): ML dramatically over-predicts — override
    #             with formula floor (previous behaviour, correct for this case).
    #   OOD_LOW  (daily_adj < min): formula floor is still correct for the total,
    #             but breakdown proportions are still meaningful, so only flag
    #             and let normal case logic handle it. Do NOT force formula
    #             override, which was squashing stitch sensitivity in the breakdown.
    _daily_red_precheck    = max(0.0, (sp_util - 60.0) / 40.0) * 0.35
    _daily_adj_precheck    = max(50, int(daily_commitment * (1.0 - _daily_red_precheck)))
    daily_commit_ood_high  = _daily_adj_precheck > DAILY_COMMIT_ADJ_MAX_TRAIN
    daily_commit_ood_low   = _daily_adj_precheck < DAILY_COMMIT_ADJ_MIN_TRAIN
    daily_commit_ood       = daily_commit_ood_high or daily_commit_ood_low
    if daily_commit_ood:
        confidence_flags.append("LOW_DAILY_COMMIT")

    confidence = ", ".join(confidence_flags) if confidence_flags else "OK"

    # ── Load models ────────────────────────────────────────────────
    try:
        models = _load_models()
    except RuntimeError as e:
        return jsonify({"error": str(e)}), 503

    try:
        # ── Build feature row ──────────────────────────────────────
        X = _build_features(
            order_qty        = order_qty,
            daily_commitment = daily_commitment,
            design_width     = design_width,
            design_length    = design_length,
            color_count      = color_count,
            stitch_clamped   = stitch_clamped,
            priority         = priority,
            buyer_name       = buyer_name,
            sp_monthly_cap   = sp_monthly_cap,
            sp_util          = sp_util,
            sp_quality       = sp_quality,
            order_month      = order_month,
            is_q4            = is_q4,
            damage_pct       = damage_pct,
            total_network_cap= total_network_cap,
        )

        # ── M1–M3: Raw ML predictions ──────────────────────────────
        # M1/M2 use M1_M2_FEATS (no stitch, no network features).
        # M3 uses M3_FEATS (includes all stitch and complexity features).
        # Raw values are kept separately so the formula-breakdown path can
        # use M1/M2 predictions directly without rescaling.
        cutting_raw    = float(models["cutting"].predict(X[M1_M2_FEATS])[0])
        sewing_raw     = float(models["sewing"].predict(X[M1_M2_FEATS])[0])
        embroidery_raw = float(models["embroidery"].predict(X[M3_FEATS])[0])
        ml_total       = cutting_raw + sewing_raw + embroidery_raw

        # Capacity floor: minimum days to process all pieces at adjusted throughput
        daily_commitment_adj = int(X["Daily_Commitment_Adj"].iloc[0])
        formula_base         = math.ceil(order_qty / daily_commitment_adj)

        # Formula-based embroidery floor — matches the training formula exactly:
        #   Embroidery_Days = ceil(Base_Days × Complexity_Mult × Cap_Mult)
        # This is always ≥ formula_base (multipliers ≥ 1.0), making it the
        # physically correct minimum for embroidery alone.
        complexity_mult_val = float(X["Complexity_Mult"].iloc[0])
        cap_mult_val        = float(X["Cap_Mult"].iloc[0])
        emb_formula         = math.ceil(formula_base * complexity_mult_val * cap_mult_val)

        # ── Option 1: Full decoupling — formula always for embroidery ──────
        #
        # DESIGN DECISION (confirmed with user):
        #   Cutting and sewing come directly from M1/M2 raw ML output — never
        #   scaled, never coupled to stitch count.
        #   Embroidery always comes from emb_formula — deterministic, stitch-
        #   sensitive, physically grounded.
        #   Total = arithmetic sum of the three components.
        #
        # This eliminates three confirmed bugs:
        #   BUG B — Case B scale mechanism caused cutting/sewing to DROP by 0.1
        #            when stitch increased (scale = ceil(ml_total)/ml_total shrank).
        #   BUG C — Small orders (formula_base<=10) had ceil() precision collapse:
        #            stitch 500-1999 all produced the same emb_formula value.
        #            Full decoupling removes the Case B path entirely.
        #   BUG D — OOD guard previously fired for BOTH above-max and below-min,
        #            using the same override logic. Now split: only OOD_HIGH
        #            triggers the formula override driver label; OOD_LOW is flagged
        #            in confidence but does not change the breakdown logic
        #            (the formula is always used for embroidery anyway).
        #
        # M3 (embroidery model) raw output is still computed and logged in
        # derived.emb_ml_raw for observability, but does not affect the response.

        cutting_days    = round(cutting_raw, 1)
        sewing_days     = round(sewing_raw,  1)
        embroidery_days = float(emb_formula)
        total_prod_days_int = math.ceil(cutting_days + sewing_days + embroidery_days)

        # days_driver label: explains what determined the production days total.
        # OOD_HIGH means ML would extrapolate far above training range — formula
        # is definitely more reliable. OOD_LOW means small throughput — formula
        # floor is correct for total but breakdown is still formula-driven anyway.
        if daily_commit_ood_high:
            days_driver = "formula (OOD: daily_commitment above training range)"
        elif daily_commit_ood_low:
            days_driver = "formula (OOD: daily_commitment below training range)"
        elif ml_total > formula_base:
            days_driver = "formula (embroidery) + ML (cutting/sewing)"
        else:
            days_driver = "formula (capacity floor)"

        # formula_total kept for response transparency (capacity floor only)
        formula_total   = formula_base
        total_prod_days = float(total_prod_days_int)
        lead_days       = total_prod_days + shipment_days

        # ── Fill M4 / M5 fields ────────────────────────────────────
        X["Cutting_Days"]          = cutting_days
        X["Sewing_Days"]           = sewing_days
        X["Embroidery_Days"]       = embroidery_days
        X["Total_Production_Days"] = total_prod_days
        X["Shipment_Days"]         = shipment_days
        X["Lead_Days"]             = lead_days
        # days_available resolved at top of function from buyer_required_date
        # default: lead_days + 30 (safe buffer) when buyer date not supplied
        _days_avail_m5            = days_available if days_available is not None else int(lead_days) + 30
        X["Days_Available"]        = _days_avail_m5
        X["Lead_Gap"]              = int(lead_days) - _days_avail_m5
        X["P1_Cap_Util_F"]         = sp_util
        X["P1_Monthly_Cap_F"]      = sp_monthly_cap

        # ── M4: Allocation type ────────────────────────────────────
        alloc_prob  = float(models["alloc"].predict_proba(X[M4_FEATS])[0][1])
        alloc_type  = "Split Between Sub Plants" if alloc_prob >= 0.5 else "Single Plant"

        # BLOCKED override: M4 was never trained on near-saturated plant scenarios.
        # When sp_util >= 95%, M4 incorrectly predicts Single Plant because training
        # data had no BLOCKED rows — high-util rows were always absorbed by one plant.
        # Override deterministically: a blocked sample plant cannot take this order
        # alone, so the allocation must split to the next available plants.
        alloc_override_note = None
        if plant_blocked:
            alloc_type          = "Split Between Sub Plants"
            alloc_prob          = 1.0   # deterministic, not ML
            alloc_override_note = (
                f"Allocation overridden to Split — sample plant '{sample_plant}' "
                f"is BLOCKED (util={sp_util}%). M4 ML prediction suppressed."
            )
        elif implausible_capacity:
            alloc_type          = "Split Between Sub Plants"
            alloc_prob          = 1.0   # deterministic, not ML
            alloc_override_note = (
                f"Allocation overridden to Split — sample plant '{sample_plant}' "
                f"has implausible monthly_capacity={sp_monthly_cap} "
                f"(order consumes {order_qty / max(sp_monthly_cap * 25, 1):.1f}x monthly cap). "
                f"M4 ML prediction suppressed. Verify monthly_capacity data."
            )
        X["Split_Alloc_Flag"] = 1 if alloc_type == "Split Between Sub Plants" else 0

        # ── M5: Deadline match ─────────────────────────────────────
        deadline_prob  = float(models["deadline"].predict_proba(X[M5_FEATS])[0][1])
        deadline_match = "Match" if deadline_prob >= 0.5 else "No Match"

        # ── Deadline gap analysis (deterministic) ──────────────────
        deadline_gap = None
        if days_available is not None:
            gap = math.ceil(lead_days) - days_available
            if gap > 0:
                prod_days_needed = days_available - shipment_days
                min_daily = (
                    math.ceil(order_qty / prod_days_needed)
                    if prod_days_needed > 0 else None
                )
                deadline_gap = {
                    "days_available":       days_available,
                    "lead_days_needed":     round(lead_days, 1),
                    "gap_days":             gap,
                    "min_daily_commitment": min_daily,
                    "status":               "Cannot meet deadline",
                }
            else:
                deadline_gap = {
                    "days_available":  days_available,
                    "lead_days_needed": round(lead_days, 1),
                    "gap_days":        0,
                    "buffer_days":     abs(gap),
                    "status": (
                        "Deadline met"
                        if gap == 0
                        else f"Deadline met with {abs(gap)} days buffer"
                    ),
                }

        # ── Plant scoring ──────────────────────────────────────────
        # derived_complexity for allocation guide lookup
        enc_map = {"Low": 1, "Medium": 2, "High": 3}
        cmx_e  = enc_map[_matrix_complexity(design_width, design_length)]
        ci_e   = enc_map[_color_impact(color_count)]
        si_e   = enc_map[_stitch_impact(stitch_clamped)]
        dc_enc = max(cmx_e, ci_e, si_e)
        derived_complexity = {1: "Low", 2: "Medium", 3: "High"}[dc_enc]

        # FIX: pass actual buffer_days from deadline gap analysis
        # was hardcoded to 10, causing buf_bon to always be capped at 0.30
        _actual_buffer = (
            deadline_gap.get("buffer_days", 0)
            if deadline_gap and deadline_gap.get("gap_days", 1) == 0
            else 0
        )
        ranked_plants = _score_plants_bulk(
            priority, derived_complexity, _actual_buffer,
            sp_util, monthly_caps, order_qty,
            daily_commitment=daily_commitment,
            daily_commitment_adj=daily_commitment_adj,
        )

        # No plant has room for this order in the window - say so instead of
        # returning a "top plant" with a nonsense negative score.
        network_available = sum(monthly_caps.values())
        best_plant_cap    = max(monthly_caps.values()) if monthly_caps else 0
        no_plant_fits     = best_plant_cap < order_qty
        network_too_small = network_available < order_qty
        if network_too_small:
            # capacity_status in the response is derived from plant_blocked, so set
            # that flag rather than a local (which would be dead code).
            plant_blocked = True
            plant_blocked_warning = (
                "No plant has capacity for this order. The network has "
                "%s units available across the production window but the order is "
                "%s pcs. Reduce the quantity, extend the timeline, or free capacity."
                % (f"{int(network_available):,}", f"{order_qty:,}")
            )
        elif no_plant_fits:
            # The network can absorb it, but only if the work is split.
            alloc_type = "Split Between Sub Plants"
            alloc_prob = max(alloc_prob, 0.99)
            if not alloc_override_note:
                alloc_override_note = (
                    "No single plant has room for %s pcs (largest free capacity is %s). "
                    "The order must be split across plants."
                    % (f"{order_qty:,}", f"{int(best_plant_cap):,}")
                )

        return jsonify({
            "status":          "success",
            "style_id":        style_id,
            "buyer_name":      buyer_name,
            "confidence":      confidence,
            "capacity_status": (
                "BLOCKED" if plant_blocked
                else "IMPLAUSIBLE_CAPACITY" if implausible_capacity
                else "OK"
            ),
            "warnings":        [w for w in [stitch_warning, plant_blocked_warning, implausible_capacity_warning] if w],
            "derived": {
                "complexity":            derived_complexity,
                "stitch_clamped":        stitch_clamped,
                "daily_commitment_adj":  int(X["Daily_Commitment_Adj"].iloc[0]),
                "cap_mult":              round(float(X["Cap_Mult"].iloc[0]), 4),
                "cap_headroom":          round(float(X["Cap_Headroom"].iloc[0]), 4),
                "complexity_mult":       round(float(X["Complexity_Mult"].iloc[0]), 4),
                "order_month":           order_month,
                "sp_monthly_cap":        sp_monthly_cap,
                "total_network_cap":     total_network_cap,
                "formula_floor_days":    formula_total,
                "emb_formula_days":      emb_formula,
                "emb_ml_raw":            round(embroidery_raw, 2),
                "days_driver":           days_driver,
            },
            "production_days": {
                "cutting_days":          round(cutting_days, 1),
                "sewing_days":           round(sewing_days, 1),
                "embroidery_days":       round(embroidery_days, 1),
                "total_production_days": round(total_prod_days, 1),
                "shipment_days":         shipment_days,
                "total_lead_days":       round(lead_days, 1),
                "production_days_note":  (
                    f"Production days computed using sample plant '{sample_plant}' "
                    f"features (sp_util={sp_util}%, sp_monthly_cap={sp_monthly_cap}). "
                    f"These estimates are unreliable because monthly_capacity is implausible. "
                    f"Resubmit with corrected monthly_capacity for accurate lead times."
                ) if implausible_capacity else None,
            },
            "allocation": {
                "allocation_type":   alloc_type,
                "split_probability": round(alloc_prob, 3),
                "allocation_note":   alloc_override_note,
            },
            "deadline": {
                "deadline_match":      deadline_match,
                "match_probability":   round(deadline_prob, 3),
                "deadline_gap":        deadline_gap,
                "deadline_note":       (
                    "Deadline match probability is unreliable — production day estimates "
                    f"are based on implausible monthly_capacity={sp_monthly_cap} for "
                    f"plant '{sample_plant}'. Actual lead time may differ significantly."
                ) if implausible_capacity else None,
            },
            "plant_recommendation": {
                "top_plant":                   ranked_plants[0][0],
                "can_handle_solo":             ranked_plants[0][2],
                "sample_plant":                sample_plant,
                "sample_plant_rank":           next(
                    (i + 1 for i, (p, _, _) in enumerate(ranked_plants) if p == sample_plant),
                    None
                ),
                "sample_plant_can_handle_solo": next(
                    (solo for p, _, solo in ranked_plants if p == sample_plant),
                    None
                ),
                "ranking": [
                    {
                        "rank":            i + 1,
                        "plant":           p,
                        "score":           round(s, 4),
                        "can_handle_solo": solo,
                    }
                    for i, (p, s, solo) in enumerate(ranked_plants)
                ],
            },
        })

    except Exception as e:
        return jsonify({"error": f"Prediction failed: {str(e)}"}), 500