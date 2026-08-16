"""
Component 2 — Bulk Order Planning & Capacity Allocation
=========================================================
Models loaded:
  c2_model_cutting.pkl    — RandomForestRegressor  → Cutting_Days
  c2_model_sewing_.pkl    — RandomForestRegressor  → Sewing_Days
  c2_model_embroide.pkl   — RandomForestRegressor  → Embroidery_Days
  c2_model4_alloc.pkl     — GradientBoostingClassifier → Single vs Split
  c2_model5_deadline.pkl  — GradientBoostingClassifier → Deadline Match

OpenAI removed — response JSON assembled deterministically from model outputs
using the same business rules that were in the OpenAI system prompt.

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
from datetime import datetime, timedelta
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

PLANT_LOCATIONS = {
    "Dinusha Embroidery":        "Weliweriya",
    "Regal Image International": "Maharagama",
    "MRC Group":                 "Colombo",
    "The Bobbin Group":          "Mount Lavinia",
    "Sunrose Lanka (Pvt) Ltd":   "Katubedda",
    "Amsral Lanka Enterprises":  "Boralesgamuwa",
}

ALL_PLANTS = list(QUALITY_MAP.keys())

KNOWN_BUYERS   = ["George", "Hirdaramani", "M&S", "Tesco"]
PRIORITY_VALUES = ["High", "Normal", "Low", "No Urgency"]

PRIORITY_ENC   = {"No Urgency": 0, "Low": 1, "Normal": 2, "High": 3}
COMPLEXITY_ENC = {"Low": 1, "Medium": 2, "High": 3, "Hard": 3}
BUYER_ENC      = {"George": 0, "Hirdaramani": 1, "M&S": 2, "Tesco": 3}

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

HIST_MISS = {
    "Dinusha Embroidery":        0.05,
    "Regal Image International": 0.08,
    "MRC Group":                 0.12,
    "The Bobbin Group":          0.10,
    "Sunrose Lanka (Pvt) Ltd":   0.13,
    "Amsral Lanka Enterprises":  0.15,
}

DEFAULT_MONTHLY_CAPACITY = {
    "Dinusha Embroidery":        181,
    "The Bobbin Group":          178,
    "Regal Image International": 160,
    "Sunrose Lanka (Pvt) Ltd":   146,
    "MRC Group":                 132,
    "Amsral Lanka Enterprises":  113,
}

STYLES_PER_WORKING_DAY = {p: round(v / 27, 3) for p, v in DEFAULT_MONTHLY_CAPACITY.items()}

RECOMMENDED_DAILY_COMMITMENT = {"Low": 649, "Medium": 789, "High": 911}

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


# ── Design complexity helpers ─────────────────────────────────────

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


def _derive_complexity(w, l, c, s) -> dict:
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


# ── Capacity helpers ──────────────────────────────────────────────

def _working_days_from_capacity(plant: str, monthly_styles: int) -> int:
    spd  = STYLES_PER_WORKING_DAY.get(plant, 5.5)
    days = round(monthly_styles / spd) if spd > 0 else 22
    return max(18, min(31, days))


def _resolve_monthly_capacity(payload: dict) -> dict:
    override = payload.get("monthly_capacity", {})
    return {
        plant: int(override[plant]) if plant in override
               else DEFAULT_MONTHLY_CAPACITY.get(plant, 160)
        for plant in ALL_PLANTS
    }


def _check_sample_plant_capacity(sample_plant, order_qty, daily_commitment,
                                  monthly_capacity) -> dict:
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


# ── Plant scoring ─────────────────────────────────────────────────

def _score_plants_bulk(priority, complexity, order_qty, daily_commitment,
                        sample_plant, monthly_capacity) -> list:
    preferred = ALLOCATION_GUIDE.get(
        (priority, complexity),
        ALLOCATION_GUIDE.get(("No Urgency", "Low"), ALL_PLANTS)
    )
    results = []
    for plant in ALL_PLANTS:
        quality       = QUALITY_MAP[plant]
        pref_bonus    = 0.5 if plant in preferred else 0.0
        cap_styles    = monthly_capacity.get(plant, DEFAULT_MONTHLY_CAPACITY.get(plant, 160))
        working_days  = _working_days_from_capacity(plant, cap_styles)
        monthly_piece = cap_styles * max(daily_commitment, 1)
        load_ratio    = order_qty / monthly_piece if monthly_piece > 0 else 1.0
        can_solo      = load_ratio < 0.20
        cap_ratio     = cap_styles / 200.0
        sample_bonus  = 0.3 if (plant == sample_plant and can_solo) else 0.0
        cap_penalty   = max(0.0, (60 - cap_styles) / 100.0) if cap_styles < 60 else 0.0
        score         = quality + pref_bonus + cap_ratio - 1.0 + sample_bonus - cap_penalty
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


# ── Feature engineering ───────────────────────────────────────────

def _build_features(order_qty, daily_commitment, design_width, design_length,
                     color_count, stitch_count, priority, buyer_name,
                     sp_cap, sp_util, sp_quality, order_month, is_q4,
                     damage_pct=0.0, sp_working_days=25,
                     monthly_caps=None) -> pd.DataFrame:
    matrix_c   = _matrix_complexity(design_width, design_length)
    color_imp  = _color_impact(color_count)
    stitch_imp = _stitch_impact(stitch_count)
    design_area = design_width * design_length
    m_enc = {"Low": 1, "Medium": 2, "High": 3}
    design_score      = (m_enc[matrix_c] + m_enc[color_imp] + m_enc[stitch_imp]) / 3.0
    buyer_enc         = BUYER_ENC.get(buyer_name, 2)
    total_network_cap = sum(monthly_caps.values()) if monthly_caps else 160 * 6
    order_vs_sp       = round(order_qty / (sp_cap * sp_working_days + 1), 4)
    order_vs_network  = round(order_qty / (total_network_cap + 1), 6)
    cap_pressure      = round((sp_util / 100.0) * order_vs_sp, 6)

    return pd.DataFrame([{
        "Bulk_Order_Quantity":   order_qty,
        "Daily_Commitment":      daily_commitment,
        "Design_Width":          design_width,
        "Design_Length":         design_length,
        "Design_Area":           design_area,
        "Color_Count":           color_count,
        "Stitch_Count":          stitch_count,
        "Design_Complexity_Enc": max(m_enc[matrix_c], m_enc[color_imp], m_enc[stitch_imp]),
        "Complexity_Matrix_Enc": m_enc[matrix_c],
        "Color_Impact_Enc":      m_enc[color_imp],
        "Stitch_Impact_Enc":     m_enc[stitch_imp],
        "Design_Score":          design_score,
        "Priority_Enc":          PRIORITY_ENC.get(priority, 2),
        "Buyer_Enc":             buyer_enc,
        "SP_Monthly_Cap_F":      sp_cap,
        "SP_Cap_Util_F":         sp_util,
        "SP_Quality_F":          sp_quality,
        "Total_Network_Cap":     total_network_cap,
        "Order_vs_SP_Cap":       order_vs_sp,
        "Order_vs_Network":      order_vs_network,
        "Order_Month":           order_month,
        "Is_Q4":                 is_q4,
        "Damage_Pct":            damage_pct,
        "Cap_Pressure_Index":    cap_pressure,
        "SP_Working_Days":       sp_working_days,
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


# ── Deterministic response builder (replaces OpenAI) ─────────────

def _build_response(data: dict, models: dict) -> dict:
    """
    Assembles the full bulk order planning JSON using ML model outputs +
    deterministic rules. Mirrors the exact schema from the OpenAI system prompt.
    """
    buyer_name     = str(data["buyer_name"])
    style_id       = str(data.get("style_id", "N/A"))
    bulk_id        = str(data.get("bulk_order_id", "N/A"))
    order_qty      = int(data["bulk_order_quantity"])
    daily_comm     = float(data["daily_commitment"])
    priority       = str(data["style_priority"])
    design_width   = float(data["design_width"])
    design_length  = float(data["design_length"])
    color_count    = int(data["color_count"])
    stitch_count   = int(data["stitch_count"])
    sample_plant   = str(data["sample_plant"])
    sp_cap         = float(data["sp_monthly_cap"])
    sp_util        = float(data["sp_cap_util_pct"])
    sp_quality     = float(data.get("sp_quality", 4.3))
    shipment_days  = int(data.get("shipment_days", 20))
    order_month    = int(data.get("receive_month", 6))
    is_q4          = int(data.get("is_q4", 1 if order_month >= 10 else 0))
    damage_pct     = float(data.get("damage_pct", 0.0))
    buyer_req_date_str       = data.get("buyer_required_date")
    bulk_approved_date_str   = data.get("bulk_order_approved_date")

    effective_qty = math.ceil(order_qty * (1 + damage_pct / 100.0))

    # ── Capacity resolution ───────────────────────────────────
    monthly_capacity = _resolve_monthly_capacity(data)
    sp_cap_info      = _check_sample_plant_capacity(
        sample_plant, effective_qty, daily_comm, monthly_capacity
    )
    sp_working_days  = sp_cap_info["plant_working_days"]

    # ── Complexity ────────────────────────────────────────────
    cplx          = _derive_complexity(design_width, design_length, color_count, stitch_count)
    derived_complexity = cplx["final_complexity"]
    recommended_daily  = RECOMMENDED_DAILY_COMMITMENT[derived_complexity]
    daily_commitment_warning = (
        None if daily_comm >= recommended_daily * 0.85
        else (
            f"daily_commitment {int(daily_comm)} pcs/day is low for {derived_complexity} complexity "
            f"(dataset average: {recommended_daily} pcs/day). "
            "Embroidery days may be overstated — consider increasing daily_commitment."
        )
    )

    # ── Feature row ───────────────────────────────────────────
    X = _build_features(
        effective_qty, daily_comm, design_width, design_length,
        color_count, stitch_count, priority, buyer_name,
        sp_cap, sp_util, sp_quality, order_month, is_q4,
        damage_pct, sp_working_days, monthly_capacity
    )

    # ── M1–M3: Production days ────────────────────────────────
    cutting_raw    = float(models["cutting"].predict(X[SHARED_FEATS])[0])
    sewing_raw     = float(models["sewing"].predict(X[SHARED_FEATS])[0])
    embroidery_raw = float(models["embroidery"].predict(X[SHARED_FEATS])[0])
    ml_total       = cutting_raw + sewing_raw + embroidery_raw

    formula_total   = math.ceil(effective_qty / max(daily_comm, 1))
    ml_total_ceil   = math.ceil(ml_total)
    total_prod_days = max(formula_total, ml_total_ceil)

    if ml_total > 0:
        scale           = total_prod_days / ml_total
        cutting_days    = round(cutting_raw    * scale, 1)
        sewing_days     = round(sewing_raw     * scale, 1)
        embroidery_days = round(embroidery_raw * scale, 1)
    else:
        cutting_days = sewing_days = embroidery_days = round(total_prod_days / 3, 1)

    lead_days = total_prod_days + shipment_days

    # ── Deadline / completion dates ───────────────────────────
    predicted_completion_date = None
    bulk_shipment_date        = None
    deadline_match_status     = "N/A"
    days_to_deadline          = None

    if bulk_approved_date_str:
        try:
            start = datetime.strptime(bulk_approved_date_str, "%Y-%m-%d")
            comp  = start + timedelta(days=total_prod_days)
            predicted_completion_date = comp.strftime("%Y-%m-%d")
            bulk_shipment_date = (comp + timedelta(days=2)).strftime("%Y-%m-%d")
            if buyer_req_date_str:
                req = datetime.strptime(buyer_req_date_str, "%Y-%m-%d")
                days_to_deadline  = (req - comp).days
                deadline_match_status = "Match" if days_to_deadline >= 0 else "No Match"
        except ValueError:
            pass

    # ── M4: Allocation type ───────────────────────────────────
    X["Cutting_Days"]          = cutting_days
    X["Sewing_Days"]           = sewing_days
    X["Embroidery_Days"]       = embroidery_days
    X["Total_Production_Days"] = total_prod_days
    X["Shipment_Days"]         = shipment_days
    X["Lead_Days"]             = lead_days
    X["P1_Cap_Util_F"]         = sp_util
    X["P1_Monthly_Cap_F"]      = sp_cap
    X["SP_Working_Days"]       = sp_working_days

    alloc_prob = float(models["alloc"].predict_proba(X[M4_FEATS])[0][1])
    alloc_type = "Split Between Sub Plants" if alloc_prob > 0.5 else "Single Plant"
    X["Split_Alloc_Flag"] = 1 if alloc_type == "Split Between Sub Plants" else 0

    # ── M5: Deadline match ────────────────────────────────────
    deadline_prob  = float(models["deadline"].predict_proba(X[M5_FEATS])[0][1])
    deadline_match = "Match" if deadline_prob > 0.5 else "No Match"

    # Prefer deterministic date-based deadline when dates are available
    if deadline_match_status != "N/A":
        deadline_match = deadline_match_status

    # ── Allocation logic (flowchart rules) ────────────────────
    ranked_plants = _score_plants_bulk(
        priority, derived_complexity, effective_qty, daily_comm,
        sample_plant, monthly_capacity
    )

    if sp_cap_info["has_capacity"]:
        allocation_type  = "Single Plant"
        allocated_plant  = sample_plant
        allocation_remark = "Sample plant has capacity — full bulk order allocated to sample plant"
        system_action    = "Proceed"
        buyer_email      = "No"
        final_decision   = "Accept (Same Plant)"
    else:
        solo_alts = [p for p in ranked_plants if p["can_handle_solo"] and p["plant"] != sample_plant]
        if solo_alts:
            allocation_type  = "Single Plant"
            allocated_plant  = solo_alts[0]["plant"]
            allocation_remark = (
                f"Sample plant no capacity — allocated to best alternative single plant: {allocated_plant}"
            )
            system_action  = "Due Plant No Capacity Bulk order Need to divide"
            buyer_email    = "No"
            final_decision = "Accept (Alternative Plant)"
        else:
            allocation_type  = "Split Between Sub Plants"
            top2             = [p["plant"] for p in ranked_plants[:2]]
            allocated_plant  = " / ".join(top2)
            allocation_remark = "No single plant has sufficient capacity — split between top 2 sub plants"
            system_action  = "Due Plant No Capacity Bulk order Need to divide"
            buyer_email    = "No"
            final_decision = "Accept (Split Between Plants)"

    if deadline_match == "No Match":
        system_action  = "Draft revised completion email for mother company bulk agent approval"
        buyer_email    = "Yes"
        final_decision = "Waiting for Buyer Approval (Deadline Not Match)"

    # ── Allocated plant location ──────────────────────────────
    first_plant = allocated_plant.split(" / ")[0].strip()
    allocated_location = PLANT_LOCATIONS.get(first_plant)

    # ── Risk level ────────────────────────────────────────────
    no_capacity = not sp_cap_info["has_capacity"]
    if deadline_match == "No Match" and no_capacity:
        risk_level = "Critical"
    elif deadline_match == "No Match":
        risk_level = "High"
    elif allocation_type == "Split Between Sub Plants":
        risk_level = "Medium"
    else:
        risk_level = "Low"

    risk_summary = (
        f"{allocation_type} allocation for {effective_qty:,} pcs "
        f"({total_prod_days}d production + {shipment_days}d shipment); "
        f"deadline {deadline_match.lower()} — risk {risk_level.lower()}."
    )

    recommended_action = {
        "Critical": "Immediate re-plan and buyer approval required",
        "High":     "Notify mother company bulk agent and propose revised date",
        "Medium":   "Confirm split allocation with sub plant managers",
        "Low":      "Proceed with plan",
    }[risk_level]

    confidence = "OK" if buyer_name in KNOWN_BUYERS else "LOW"

    large_order_warning = (
        f"bulk_order_quantity {order_qty:,} exceeds 500,000 pieces. "
        "Manual capacity review recommended."
        if order_qty > 500_000 else None
    )

    return {
        "status":        "success",
        "bulk_order_id": bulk_id,
        "style_id":      style_id,
        "buyer_name":    buyer_name,
        "confidence":    confidence,

        "design_analysis": {
            "design_width":      design_width,
            "design_length":     design_length,
            "color_count":       color_count,
            "stitch_count":      stitch_count,
            "matrix_complexity": cplx["matrix_complexity"],
            "color_impact":      cplx["color_impact"],
            "stitch_impact":     cplx["stitch_impact"],
            "derived_complexity":derived_complexity,
            "complexity_score":  cplx["complexity_score"],
        },

        "order_summary": {
            "bulk_order_quantity": order_qty,
            "effective_quantity":  effective_qty,
            "damage_pct":          damage_pct,
            "daily_commitment":    daily_comm,
            "style_priority":      priority,
            "sample_plant":        sample_plant,
        },

        "production_days": {
            "cutting_days":              int(cutting_days),
            "sewing_days":               int(sewing_days),
            "embroidery_days":           int(embroidery_days),
            "base_embroidery_days":      math.ceil(effective_qty / max(daily_comm, 1)),
            "design_emb_days":           int(embroidery_days),
            "design_area_factor":        round(design_width * design_length / 100, 3),
            "stitch_factor":             round(1 + (stitch_count - 10000) / 100000, 3),
            "color_factor":              round(1 + max(0, color_count - 6) * 0.03, 3),
            "capacity_factor":           round(
                max(1.0, min(4.0, 1.0 + effective_qty / (
                    monthly_capacity.get(sample_plant, DEFAULT_MONTHLY_CAPACITY.get(sample_plant, 160))
                    * max(daily_comm, 1)
                ))), 3
            ),
            "capacity_load_ratio":       round(
                effective_qty / (
                    monthly_capacity.get(sample_plant, DEFAULT_MONTHLY_CAPACITY.get(sample_plant, 160))
                    * max(daily_comm, 1)
                ), 4
            ),
            "total_production_days":     total_prod_days,
            "lead_days":                 lead_days,
            "predicted_completion_date": predicted_completion_date,
            "bulk_shipment_date":        bulk_shipment_date,
            "recommended_daily_commitment": recommended_daily,
            "daily_commitment_warning":  daily_commitment_warning,
            "large_order_warning":       large_order_warning,
        },

        "deadline_assessment": {
            "buyer_required_date":    buyer_req_date_str,
            "deadline_match_status":  deadline_match,
            "days_to_deadline":       days_to_deadline,
            "buyer_email_required":   buyer_email,
            "buyer_approval_required":buyer_email == "Yes",
            "system_action":          system_action,
        },

        "capacity_check": {
            "sample_plant":                  sample_plant,
            "sample_plant_capacity_status":  sp_cap_info["capacity_status"],
            "plant_working_days":            sp_cap_info["plant_working_days"],
            "monthly_styles_capacity":       sp_cap_info["plant_monthly_styles"],
            "monthly_piece_capacity":        sp_cap_info["monthly_piece_capacity"],
            "load_ratio":                    sp_cap_info["load_ratio"],
            "utilisation_pct":               sp_cap_info["utilisation_pct"],
            "manager_confirmation":          sp_cap_info["manager_confirmation"],
        },

        "allocation": {
            "allocation_type":       allocation_type,
            "allocated_bulk_plant":  allocated_plant,
            "allocated_plant_location": allocated_location,
            "allocation_remark":     allocation_remark,
            "plant_ranking":         ranked_plants,
        },

        "planning_output": {
            "final_decision":     final_decision,
            "risk_level":         risk_level,
            "risk_summary":       risk_summary,
            "recommended_action": recommended_action,
        },
    }


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
        color_count, stitch_count, sample_plant, sp_monthly_cap, sp_cap_util_pct

    Optional fields:
        bulk_order_id, buyer_required_date, bulk_order_approved_date,
        damage_pct, sp_quality, shipment_days, receive_month, monthly_capacity
    """
    data = request.get_json(force=True, silent=True)
    if not data:
        return jsonify({"error": "Request body must be valid JSON"}), 400

    required = [
        "buyer_name", "style_id", "bulk_order_quantity", "daily_commitment",
        "style_priority", "design_width", "design_length",
        "color_count", "stitch_count", "sample_plant",
        "sp_monthly_cap", "sp_cap_util_pct",
    ]
    missing = [f for f in required if f not in data]
    if missing:
        return jsonify({"error": f"Missing required fields: {missing}"}), 400

    try:
        order_qty     = int(data["bulk_order_quantity"])
        daily_comm    = float(data["daily_commitment"])
        priority      = str(data["style_priority"])
        design_width  = float(data["design_width"])
        design_length = float(data["design_length"])
        color_count   = int(data["color_count"])
        stitch_count  = int(data["stitch_count"])
        sample_plant  = str(data["sample_plant"])
    except (ValueError, TypeError) as e:
        return jsonify({"error": f"Invalid field value: {e}"}), 400

    if not (1 <= order_qty):
        return jsonify({"error": "bulk_order_quantity must be >= 1"}), 400
    if priority not in PRIORITY_VALUES:
        return jsonify({"error": f"style_priority must be one of: {PRIORITY_VALUES}"}), 400
    if sample_plant not in ALL_PLANTS:
        return jsonify({"error": f"sample_plant must be one of: {ALL_PLANTS}"}), 400
    if not (1_000 <= stitch_count <= 500_000):
        return jsonify({"error": f"stitch_count {stitch_count} outside valid range [1,000–500,000]"}), 400
    if not (0.1 <= design_width <= 52.0):
        return jsonify({"error": f"design_width {design_width} outside valid range [0.1–52.0 cm]"}), 400
    if not (0.1 <= design_length <= 52.0):
        return jsonify({"error": f"design_length {design_length} outside valid range [0.1–52.0 cm]"}), 400
    if not (1 <= color_count <= 15):
        return jsonify({"error": f"color_count {color_count} outside valid range [1–15]"}), 400

    if "monthly_capacity" in data:
        if not isinstance(data["monthly_capacity"], dict):
            return jsonify({"error": "monthly_capacity must be a JSON object"}), 400
        for p, cap in data["monthly_capacity"].items():
            if p not in ALL_PLANTS:
                return jsonify({"error": f"Unknown plant in monthly_capacity: '{p}'"}), 400
            try:
                if int(cap) < 0:
                    raise ValueError
            except (ValueError, TypeError):
                return jsonify({"error": f"monthly_capacity['{p}'] must be a non-negative integer"}), 400

    try:
        models = _load_models()
    except RuntimeError as e:
        return jsonify({"error": str(e)}), 503

    try:
        result = _build_response(data, models)
        return jsonify(result), 200
    except Exception as e:
        return jsonify({"error": f"Prediction failed: {str(e)}"}), 500
