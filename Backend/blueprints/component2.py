"""
Component 2 — Bulk Order Planning & Capacity Allocation
=========================================================
Models loaded:
  c2_model_cutting.pkl    — RandomForestRegressor  → Cutting_Days
  c2_model_sewing_.pkl    — RandomForestRegressor  → Sewing_Days
  c2_model_embroide.pkl   — RandomForestRegressor  → Embroidery_Days
  c2_model4_alloc.pkl     — GradientBoostingClassifier → Single vs Split
  c2_model5_deadline.pkl  — GradientBoostingClassifier → Deadline Match

POST /api/component2/predict
Request body (JSON):
{
    "style_id":            "KM740232",
    "buyer_name":          "Tesco",
    "bulk_order_quantity": 20000,
    "daily_commitment":    700,
    "style_priority":      "High",
    "design_width":        12.0,
    "design_length":       13.5,
    "color_count":         8,
    "stitch_count":        18500,
    "sample_plant":        "Dinusha Embroidery",
    "sp_monthly_cap":      208,
    "sp_cap_util_pct":     75.0,
    "sp_quality":          4.8,
    "shipment_days":       20,
    "receive_month":       6,
    "damage_pct":          0.0,
    "monthly_capacity":    {
        "Dinusha Embroidery":        180,
        "Regal Image International": 170,
        "MRC Group":                 160,
        "The Bobbin Group":          165,
        "Sunrose Lanka (Pvt) Ltd":   149,
        "Amsral Lanka Enterprises":  155
    }
}
"""

import math
import os
import joblib
import numpy as np
import pandas as pd
from flask import Blueprint, request, jsonify

component2_bp = Blueprint("component2", __name__)

# ── Paths ─────────────────────────────────────────────────────────
BASE_DIR   = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MODELS_DIR = os.path.join(BASE_DIR, "models")

# ── Static lookups ────────────────────────────────────────────────
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
    ("High",       "High"):   ["Dinusha Embroidery", "Regal Image International"],  # Fix 1
    ("High",       "Medium"): ["Dinusha Embroidery", "The Bobbin Group"],
    ("Normal",     "High"):   ["Dinusha Embroidery", "Regal Image International"],  # Fix 1
    ("Normal",     "Medium"): ["The Bobbin Group", "Sunrose Lanka (Pvt) Ltd"],
    ("Low",        "Low"):    ["MRC Group", "Amsral Lanka Enterprises"],
    ("No Urgency", "Low"):    ["MRC Group", "Amsral Lanka Enterprises"],
}

PRIORITY_ENC   = {"No Urgency": 0, "Low": 1, "Normal": 2, "High": 3}
COMPLEXITY_ENC = {"Low": 1, "Medium": 2, "High": 3, "Hard": 3}
BUYER_ENC      = {"George": 0, "Hirdaramani": 1, "M&S": 2, "Tesco": 3}
KNOWN_BUYERS   = list(BUYER_ENC.keys())

# Shared features for M1–M3
SHARED_FEATS = [
    "Bulk_Order_Quantity", "Daily_Commitment",
    "Design_Width", "Design_Length", "Design_Area",
    "Color_Count", "Stitch_Count",
    "Design_Complexity_Enc", "Complexity_Matrix_Enc",
    "Color_Impact_Enc", "Stitch_Impact_Enc", "Design_Score",
    "Priority_Enc", "Buyer_Enc",
    "SP_Monthly_Cap_F", "SP_Cap_Util_F", "SP_Quality_F",
    "Total_Network_Cap", "Order_vs_SP_Cap", "Order_vs_Network",
    "Order_Month", "Is_Q4",
    "Damage_Pct", "Cap_Pressure_Index",
]

M4_FEATS = [
    "Bulk_Order_Quantity", "Daily_Commitment",
    "Design_Complexity_Enc", "Complexity_Matrix_Enc", "Design_Score",
    "Priority_Enc", "Buyer_Enc",
    "SP_Monthly_Cap_F", "SP_Cap_Util_F", "SP_Quality_F", "SP_Working_Days",
    "Total_Network_Cap", "Order_vs_SP_Cap", "Order_vs_Network",
    "Order_Month", "Is_Q4",
    "Color_Count", "Stitch_Count", "Design_Area",
]

M5_FEATS = SHARED_FEATS + [
    "Cutting_Days", "Sewing_Days", "Embroidery_Days",
    "Total_Production_Days", "Shipment_Days", "Lead_Days",
    "P1_Cap_Util_F", "P1_Monthly_Cap_F",
    "Split_Alloc_Flag", "Damage_Pct", "Cap_Pressure_Index",
]

# ── Lazy model loader ─────────────────────────────────────────────
_models = {}


def _load_models():
    if _models:
        return _models
    names = {
        "cutting":    "c2_model_cutting.pkl",
        "sewing":     "c2_model_sewing_.pkl",
        "embroidery": "c2_model_embroide.pkl",
        "alloc":      "c2_model4_alloc.pkl",
        "deadline":   "c2_model5_deadline.pkl",
    }
    missing = []
    for key, fname in names.items():
        path = os.path.join(MODELS_DIR, fname)
        if not os.path.exists(path):
            missing.append(fname)
        else:
            _models[key] = joblib.load(path)
    if missing:
        raise RuntimeError(f"Missing model files: {missing}. Run the Component 2 notebook first.")
    return _models


# ── Design complexity helpers (from notebook rules) ───────────────
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


# ── Plant scoring ─────────────────────────────────────────────────
HIST_MISS = {
    "Dinusha Embroidery":        0.05,
    "Regal Image International": 0.08,
    "MRC Group":                 0.12,
    "The Bobbin Group":          0.10,
    "Sunrose Lanka (Pvt) Ltd":   0.13,
    "Amsral Lanka Enterprises":  0.15,
}


def _score_plants_bulk(priority: str, complexity: str,
                        shipment_days: int, sp_cap_util: float,
                        monthly_caps: dict, order_qty: int,
                        daily_commitment: float = 500,   # Fix 2
                        sp_working_days: int = 26) -> list:
    """
    Returns list of (plant_name, score, can_handle_solo).
    Fix 2: daily_commitment added; can_solo now uses piece-based formula.
    Fix 2: util_est no longer fabricated per-plant from monthly_cap.
    """
    preferred = ALLOCATION_GUIDE.get(
        (priority, complexity),
        ALLOCATION_GUIDE.get(("No Urgency", "Low"), ALL_PLANTS)
    )

    days_needed = math.ceil(order_qty / max(daily_commitment, 1))

    results = []
    for plant in ALL_PLANTS:
        quality    = QUALITY_MAP[plant]
        miss_rate  = HIST_MISS.get(plant, 0.12)
        buf_bonus  = min(shipment_days * 0.03, 0.30)
        pref_bonus = 0.5 if plant in preferred else 0.0
        cap_penalty = sp_cap_util / 100.0

        score = quality - (miss_rate * 3) - cap_penalty + buf_bonus + pref_bonus

        # Fix 2: per-plant solo check — styles/month >= production days needed
        plant_cap = monthly_caps.get(plant, sp_working_days)
        can_solo  = plant_cap >= days_needed

        results.append((plant, round(score, 4), can_solo))

    return sorted(results, key=lambda x: x[1], reverse=True)


# ── Feature engineering ───────────────────────────────────────────
def _build_features(order_qty, daily_commitment, design_width, design_length,
                     color_count, stitch_count, priority, buyer_name,
                     sp_cap, sp_util, sp_quality, order_month, is_q4,
                     damage_pct=0.0,
                     sp_working_days=25,
                     monthly_caps=None) -> pd.DataFrame:   # Fix 4

    # Derived design features
    matrix_c  = _matrix_complexity(design_width, design_length)
    color_imp = _color_impact(color_count)
    stitch_imp= _stitch_impact(stitch_count)
    design_area = design_width * design_length

    m_enc = {"Low": 1, "Medium": 2, "High": 3}
    design_score = (m_enc[matrix_c] + m_enc[color_imp] + m_enc[stitch_imp]) / 3.0

    # Buyer encoding — OOV fallback
    buyer_enc = BUYER_ENC.get(buyer_name, 2)

    # Fix 4: use actual monthly_caps sum instead of hardcoded 160 * 6
    total_network_cap    = sum(monthly_caps.values()) if monthly_caps else 160 * 6
    order_vs_sp          = round(order_qty / (sp_cap * sp_working_days + 1), 4)
    order_vs_network     = round(order_qty / (total_network_cap + 1), 6)
    cap_pressure         = round((sp_util / 100.0) * order_vs_sp, 6)

    return pd.DataFrame([{
        "Bulk_Order_Quantity":   order_qty,
        "Daily_Commitment":      daily_commitment,
        "Design_Width":          design_width,
        "Design_Length":         design_length,
        "Design_Area":           design_area,
        "Color_Count":           color_count,
        "Stitch_Count":          stitch_count,
        "Design_Complexity_Enc": max(m_enc[matrix_c], m_enc[color_imp], m_enc[stitch_imp]),  # derived — never user-supplied
        "Complexity_Matrix_Enc": m_enc[matrix_c],
        "Color_Impact_Enc":      m_enc[color_imp],
        "Stitch_Impact_Enc":     m_enc[stitch_imp],
        "Design_Score":          design_score,
        "Priority_Enc":          PRIORITY_ENC.get(priority, 2),
        "Buyer_Enc":             buyer_enc,
        "SP_Monthly_Cap_F":      sp_cap,
        "SP_Cap_Util_F":         sp_util,
        "SP_Quality_F":          sp_quality,
        "Total_Network_Cap":     total_network_cap,   # Fix 4
        "Order_vs_SP_Cap":       order_vs_sp,
        "Order_vs_Network":      order_vs_network,    # Fix 4
        "Order_Month":           order_month,
        "Is_Q4":                 is_q4,
        "Damage_Pct":            damage_pct,
        "Cap_Pressure_Index":    cap_pressure,
        "SP_Working_Days":       sp_working_days,
        # M5 placeholders — filled after M1–M3 run
        "Cutting_Days":          0,
        "Sewing_Days":           0,
        "Embroidery_Days":       0,
        "Total_Production_Days": 0,
        "Shipment_Days":         0,
        "Lead_Days":             0,
        "P1_Cap_Util_F":         sp_util,
        "P1_Monthly_Cap_F":      sp_cap,
        "Split_Alloc_Flag":      0,
    }])


# ── Routes ────────────────────────────────────────────────────────
@component2_bp.route("/health", methods=["GET"])
def health():
    return jsonify({"component": "2 — Bulk Order Planning & Capacity Allocation", "status": "ok"})


@component2_bp.route("/predict", methods=["POST"])
def predict():
    """
    Full Component 2 bulk order planning prediction.
    Required fields: buyer_name, bulk_order_quantity, daily_commitment,
                     style_priority, design_width, design_length,
                     color_count, stitch_count, sp_monthly_cap, sp_cap_util_pct
    Note: design_complexity is not required — derived from sub-rules automatically.
    """
    data = request.get_json(force=True, silent=True)
    if not data:
        return jsonify({"error": "Request body must be valid JSON"}), 400

    required = [
        "buyer_name", "bulk_order_quantity", "daily_commitment",
        "style_priority", "design_width",
        "design_length", "color_count", "stitch_count",
        "sp_monthly_cap", "sp_cap_util_pct",
    ]
    missing = [f for f in required if f not in data]
    if missing:
        return jsonify({"error": f"Missing required fields: {missing}"}), 400

    try:
        buyer_name       = str(data["buyer_name"])
        order_qty        = int(data["bulk_order_quantity"])
        daily_commitment = float(data["daily_commitment"])
        priority         = str(data["style_priority"])
        design_width     = float(data["design_width"])
        design_length    = float(data["design_length"])
        color_count      = int(data["color_count"])
        stitch_count     = int(data["stitch_count"])
        sp_cap           = float(data["sp_monthly_cap"])
        sp_util          = float(data["sp_cap_util_pct"])
        sp_quality       = float(data.get("sp_quality", 4.3))
        shipment_days    = int(data.get("shipment_days", 20))
        order_month      = int(data.get("receive_month", 6))
        is_q4            = int(data.get("is_q4", 1 if order_month >= 10 else 0))
        damage_pct       = float(data.get("damage_pct", 0.0))
        style_id            = data.get("style_id", "N/A")
        monthly_caps        = data.get("monthly_capacity", {p: 160 for p in ALL_PLANTS})
        buyer_required_date = data.get("buyer_required_date", None)
    except (ValueError, TypeError) as e:
        return jsonify({"error": f"Invalid field value: {e}"}), 400

    if priority not in PRIORITY_ENC:
        return jsonify({"error": f"style_priority must be one of: {list(PRIORITY_ENC.keys())}"}), 400

    try:
        models = _load_models()
    except RuntimeError as e:
        return jsonify({"error": str(e)}), 503

    try:
        X = _build_features(
            order_qty, daily_commitment, design_width, design_length,
            color_count, stitch_count, priority, buyer_name,
            sp_cap, sp_util, sp_quality, order_month, is_q4,
            damage_pct,
            monthly_caps=monthly_caps    # Fix 4
        )

        # Derive complexity label from encoded value in feature row
        derived_complexity = {1: "Low", 2: "Medium", 3: "High"}[
            int(X["Design_Complexity_Enc"].iloc[0])
        ]

        # ── M1–M3: Production days ────────────────────────────
        cutting_raw     = float(models["cutting"].predict(X[SHARED_FEATS])[0])
        sewing_raw      = float(models["sewing"].predict(X[SHARED_FEATS])[0])
        embroidery_raw  = float(models["embroidery"].predict(X[SHARED_FEATS])[0])
        ml_total        = cutting_raw + sewing_raw + embroidery_raw

        # Option 3 Hybrid: max(formula_floor, ml_total)
        # formula_floor = ceil(qty/daily) — capacity minimum
        # ml_total = M1+M2+M3 raw — complexity-aware (stitch/width/height affect this)
        # Final = max(both): complexity raises days above floor when design is complex
        formula_total   = math.ceil(order_qty / max(daily_commitment, 1))
        ml_total_ceil   = math.ceil(ml_total)
        total_prod_days = max(formula_total, ml_total_ceil)
        days_driver     = "ML (complexity)" if ml_total_ceil > formula_total else "formula (capacity)"

        if ml_total > 0:
            scale           = total_prod_days / ml_total
            cutting_days    = round(cutting_raw    * scale, 1)
            sewing_days     = round(sewing_raw     * scale, 1)
            embroidery_days = round(embroidery_raw * scale, 1)
        else:
            cutting_days = sewing_days = embroidery_days = round(total_prod_days / 3, 1)

        completion_qty  = daily_commitment * total_prod_days
        lead_days       = total_prod_days + shipment_days

        # Fill M5 input columns (scaled breakdown values)
        X["Cutting_Days"]          = cutting_days
        X["Sewing_Days"]           = sewing_days
        X["Embroidery_Days"]       = embroidery_days
        X["Total_Production_Days"] = total_prod_days
        X["Shipment_Days"]         = shipment_days
        X["Lead_Days"]             = lead_days
        X["P1_Cap_Util_F"]         = sp_util
        X["P1_Monthly_Cap_F"]      = sp_cap
        X["SP_Working_Days"]       = 25

        # ── M4: Allocation type ───────────────────────────────
        alloc_prob  = float(models["alloc"].predict_proba(X[M4_FEATS])[0][1])
        alloc_type  = "Split Between Sub Plants" if alloc_prob > 0.5 else "Single Plant"
        X["Split_Alloc_Flag"] = 1 if alloc_type == "Split Between Sub Plants" else 0

        # ── M5: Deadline match ────────────────────────────────
        deadline_prob  = float(models["deadline"].predict_proba(X[M5_FEATS])[0][1])
        deadline_match = "Match" if deadline_prob > 0.5 else "No Match"

        # ── Deadline gap (deterministic, no ML) ──────────────────
        deadline_gap = None
        if buyer_required_date is not None:
            try:
                days_available = int(buyer_required_date)
                gap = lead_days - days_available
                if gap > 0:
                    prod_days_needed = days_available - shipment_days
                    min_daily = (math.ceil(order_qty / prod_days_needed)
                                 if prod_days_needed > 0 else None)
                    deadline_gap = {
                        "status":              "Cannot meet deadline",
                        "days_available":       days_available,
                        "lead_days_needed":     lead_days,
                        "gap_days":             gap,
                        "prod_days_if_to_meet": max(prod_days_needed, 0),
                        "min_daily_commitment": min_daily,
                        "note": (f"Need {min_daily:,} pcs/day to meet deadline "
                                 f"(currently {int(daily_commitment):,} pcs/day)"
                                 if min_daily else
                                 "Impossible — shipment days alone exceed available time"),
                    }
                else:
                    deadline_gap = {
                        "status":           ("Deadline met" if gap == 0
                                            else f"Deadline met with {abs(gap)} days buffer"),
                        "days_available":   days_available,
                        "lead_days_needed": lead_days,
                        "gap_days":         0,
                        "buffer_days":      abs(gap),
                    }
            except (ValueError, TypeError):
                deadline_gap = {"error": "buyer_required_date must be an integer"}

        # ── Plant scoring ─────────────────────────────────────
        ranked_plants = _score_plants_bulk(
            priority, derived_complexity, shipment_days, sp_util,
            monthly_caps, order_qty,
            daily_commitment=daily_commitment    # Fix 2
        )
        top_plant     = ranked_plants[0][0]
        top_can_solo  = ranked_plants[0][2]

        # OOV buyer flag
        confidence = "LOW" if buyer_name not in KNOWN_BUYERS else "OK"

        return jsonify({
            "status":     "success",
            "style_id":   style_id,
            "buyer_name": buyer_name,
            "confidence": confidence,
            "derived_complexity": derived_complexity,
            "production_days": {
                "cutting_days":          cutting_days,
                "sewing_days":           sewing_days,
                "embroidery_days":       embroidery_days,
                "total_production_days": total_prod_days,
                "days_driver":           days_driver,
                "formula_floor":         formula_total,
                "ml_prediction":         round(ml_total, 1),
                "completion_check":      f"{daily_commitment} pcs/day × {total_prod_days} days = {completion_qty:,.0f} pcs",
                "shipment_days":         shipment_days,
                "total_lead_days":       lead_days,
            },
            "deadline_gap":  deadline_gap,
            "allocation": {
                "allocation_type":      alloc_type,
                "split_probability":    round(alloc_prob, 3),
            },
            "deadline": {
                "deadline_match":       deadline_match,
                "deadline_match_prob":  round(deadline_prob, 3),
            },
            "plant_recommendation": {
                "top_plant":            top_plant,
                "can_handle_solo":      top_can_solo,
                "ranking": [
                    {
                        "rank": i + 1,
                        "plant": p,
                        "score": round(s, 4),
                        "can_handle_solo": solo,
                    }
                    for i, (p, s, solo) in enumerate(ranked_plants)
                ],
            },
        })

    except Exception as e:
        return jsonify({"error": f"Prediction failed: {str(e)}"}), 500