"""
Component 4 — Production Analysis & Resource Optimization
==========================================================
Models loaded  (produced by Component4_ML_Training_3.ipynb):
  model_A_perf_regressor.pkl          — GradientBoostingRegressor   → Performance Score (1.0–5.0)
  model_B_star_classifier.pkl         — GradientBoostingClassifier  → Star Rating (1★–5★)
  model_D_best_plant.pkl              — RandomForestClassifier       → Best Plant Category (3 classes)
  model_E_multilabel_recommendation.pkl — MultiOutputClassifier     → Priority-ranked recommendations (multi-label)
  scaler.pkl                          — StandardScaler               → feature scaler
  encoders.pkl                        — dict of label maps           → PLANT_ENC, RECOM_DEC, BEST_DEC, STAR_MAP, etc.

POST /api/component4/predict
Accepts a FRIENDLY payload — all computed/derived fields are resolved automatically.

Required fields:
{
    "plant_name":                 "MRC Group",       ← human name; mapped to plant_id internally
    "order_quantity":             12000,
    "planned_completion_days":    28,
    "actual_completion_days":     33,
    "machine_count":              16,
    "active_machine_count":       11,
    "employee_count":             48,
    "daily_output_avg":           450,
    "total_workload":             18000,
    "urgent_style_flag":          "Yes",             ← "Yes"/"No" or 1/0 both accepted
    "urgent_handled_count":       2,
    "risk_count_from_component3": 6,
    "machine_breakdown_days":     4,
    "worker_shortage_days":       2,
    "damage_rate":                3.2
}

Auto-derived fields (no need to send):
    plant_id            — looked up from plant_name
    urgent_flag         — converted from "Yes"/"No"
    machine_utilization — active_machine_count / machine_count
    delay_days          — actual_completion_days - planned_completion_days
    on_time_rate        — static per-plant KPI (from training data)
    quality_rating      — static per-plant KPI (from training data)

Legacy raw format (all fields explicit) is also still accepted.
"""

import os
import joblib
import numpy as np
from flask import Blueprint, request, jsonify

component4_bp = Blueprint("component4", __name__)

# ── Paths ──────────────────────────────────────────────────────────
# ── Plant name → plant_id lookup (matches training data exactly) ───
# Source: component4_production_analysis_resource_optimization_dataset.xlsx
PLANT_NAME_TO_ID = {
    "Dinusha Embroidery"           : "PL01",
    "MRC Group"                    : "PL02",
    "Bobbin Group"                 : "PL03",
    "The Bobbin Group"             : "PL03",
    "Sunrose Lanka"                : "PL04",
    "Sunrose Lanka (Pvt) Ltd"      : "PL04",   # exact name as stored in the plants table
    "Regal Image"                  : "PL05",
    "Regal Image International"    : "PL05",
    "Amsral Lanka"                 : "PL06",
    "Amsral Lanka Enterprises"     : "PL06",
}

# ── Per-plant static KPIs (from training dataset — never vary per record) ──
# on_time_rate and quality_rating are plant-level constants, not per-order metrics.
# Derived from: component4_production_analysis_resource_optimization_dataset.xlsx
PLANT_KPI = {
    #  plant_id  on_time_rate  quality_rating
    "PL01":  {"on_time_rate": 0.92, "quality_rating": 4.8},
    "PL02":  {"on_time_rate": 0.88, "quality_rating": 4.5},
    "PL03":  {"on_time_rate": 0.85, "quality_rating": 4.3},
    "PL04":  {"on_time_rate": 0.83, "quality_rating": 4.2},
    "PL05":  {"on_time_rate": 0.80, "quality_rating": 4.0},
    "PL06":  {"on_time_rate": 0.78, "quality_rating": 3.8},
}

BASE_DIR   = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MODELS_DIR = os.path.join(BASE_DIR, "models")

# ── Feature list (must match notebook FEATURE_COLS exactly) ────────
FEATURE_COLS = [
    # Plant capacity
    "machine_count",
    "active_machine_count",
    "machine_utilization",
    "employee_count",
    "daily_output_avg",
    "total_workload",
    "order_quantity",
    # Urgency
    "urgent_flag",
    "urgent_handled_count",
    # Risk signals (from Component 3)
    "risk_count_from_component3",
    "machine_breakdown_days",
    "worker_shortage_days",
    # Quality & timing — raw, not combined
    "quality_rating",
    "on_time_rate",
    "damage_rate",
    # Outcome
    "delay_days",
    # Plant identity
    "plant_enc",
]

# ── Model E label definitions (must match notebook exactly) ─────────
LABEL_COLS_E = [
    "maintenance", "workforce", "risk_monitor",
    "output_mon",  "quality_act", "urgent_ok", "maintain",
]
LABEL_NAMES_E = [
    "Increase machine maintenance support",
    "Improve workforce allocation",
    "Reduce risk days and add supervisor monitoring",
    "Increase daily output monitoring",
    "Quality improvement action needed",
    "Suitable for urgent style handling",
    "Maintain current resource allocation",
]
SEVERITY_WEIGHTS_E = {
    "maintenance" : 0.142,
    "workforce"   : 0.158,
    "risk_monitor": 0.066,
    "output_mon"  : 0.329,
    "quality_act" : 0.340,
    "urgent_ok"   : 0.000,
    "maintain"    : 0.000,
}
DEVIATION_CONFIG_E = {
    # maintenance: two signals — worst drives severity
    #   A: machine_breakdown_days  (threshold=3,    worst=10,   higher_worse)
    #   B: machine_utilization     (threshold=0.70, worst=0.30, lower_worse)
    "maintenance"  : [
        ("machine_breakdown_days", 3,    10,   "higher_worse"),
        ("machine_utilization",    0.70, 0.30, "lower_worse"),
    ],
    # workforce: two signals — worst drives severity
    #   A: worker_shortage_days    (threshold=3,  worst=11,  higher_worse)
    #   B: employee_count          (threshold=35, worst=20,  lower_worse)
    "workforce"    : [
        ("worker_shortage_days", 3,  11, "higher_worse"),
        ("employee_count",       35, 20, "lower_worse"),
    ],
    "risk_monitor" : ("risk_count_from_component3",    5,    16,   "higher_worse"),
    "output_mon"   : ("on_time_rate",                  0.70, 0.30, "lower_worse"),
    "quality_act"  : ("damage_rate",                   5.0,  9.5,  "higher_worse"),
    "urgent_ok"    : (None, None, None, None),
    "maintain"     : (None, None, None, None),
}

# ── OOD guard thresholds (derived from training data real-record ranges) ──────
# Fields where inputs below/above these values are out-of-distribution.
# Source: component4_production_analysis_resource_optimization_dataset.xlsx (500 real records)
OOD_GUARDS = [
    # (field, direction, ood_threshold, label_to_inject, hard_error)
    # direction "below" = fire when value < threshold
    # direction "above" = fire when value > threshold
    # hard_error=True  = reject request with 400 (input is physically implausible)
    # hard_error=False = inject recommendation + warning (OOD but recoverable)
    ("machine_utilization", "below", 0.60,  "maintenance", False),
    ("employee_count",      "below", 28,    "workforce",   False),
    ("machine_count",       "below", 8,     None,          True),
    ("machine_count",       "above", 22,    None,          True),
    ("active_machine_count","below", 5,     "maintenance", False),
    ("employee_count",      "above", 68,    None,          True),
    ("daily_output_avg",    "below", 84.9,  "output_mon",  False),
    ("daily_output_avg",    "above", 1088.2,None,          True),
    ("order_quantity",      "below", 2017,  None,          True),
    ("order_quantity",      "above", 59951, None,          True),
    ("urgent_handled_count","above", 6,     None,          True),
    ("machine_breakdown_days","above",6,    "maintenance", False),
    ("worker_shortage_days","above", 8,     "workforce",   False),
    ("risk_count_from_component3","above",16,"risk_monitor",False),
    ("damage_rate",         "above", 4.45,  "quality_act", False),
    ("damage_rate",         "below", 1.89,  None,          False),
]

# Threshold for low-confidence flag (matches notebook)
LOW_CONF_THRESHOLD   = 0.65
MODEL_E_THRESHOLD    = 0.50

# ── Lazy model loader ──────────────────────────────────────────────
_models = {}


def _load_models():
    if _models:
        return _models

    files = {
        "model_A": "model_A_perf_regressor.pkl",
        "model_B": "model_B_star_classifier.pkl",
        "model_D": "model_D_best_plant.pkl",
        "model_E": "model_E_multilabel_recommendation.pkl",
        "scaler":  "scaler.pkl",
        "encoders":"encoders.pkl",
    }
    missing = []
    for key, fname in files.items():
        path = os.path.join(MODELS_DIR, fname)
        if not os.path.exists(path):
            missing.append(fname)
        else:
            _models[key] = joblib.load(path)
    if missing:
        raise RuntimeError(
            f"Missing model files: {missing}. "
            f"Run Component4_ML_Training_3.ipynb first."
        )
    return _models


# ── Helper: build scaled feature vector ────────────────────────────
def _build_feature_vector(record: dict, scaler, plant_enc: dict) -> np.ndarray:
    """
    Convert a raw input dict to a 1×17 scaled numpy array.
    'plant_id' is mapped to 'plant_enc' via the encoder built during training.
    Missing keys default to 0.
    """
    # Encode plant_id → plant_enc integer
    plant_id  = record.get("plant_id", "")
    record_fe = dict(record)
    record_fe["plant_enc"] = float(plant_enc.get(plant_id, 0))

    X_raw = np.array(
        [record_fe.get(f, 0) for f in FEATURE_COLS],
        dtype=float
    ).reshape(1, -1)
    return scaler.transform(X_raw)


# ── Helper: Model E deviation score ────────────────────────────────
def _deviation_score(record: dict, label: str) -> float:
    """
    Compute deviation score for a label.
    Supports single-signal tuples and multi-signal lists (takes the worst score).
    """
    config = DEVIATION_CONFIG_E[label]

    # Multi-signal: list of tuples — compute each, return the worst (highest)
    if isinstance(config, list):
        scores = []
        for feat, threshold, worst, direction in config:
            if feat is None:
                scores.append(0.0)
                continue
            val = record.get(feat, 0)
            if direction == "higher_worse":
                s = (val - threshold) / (worst - threshold + 1e-9)
            else:
                s = (threshold - val) / (threshold - worst + 1e-9)
            scores.append(float(np.clip(s, 0.0, 1.0)))
        return max(scores)

    # Single-signal: plain tuple
    feat, threshold, worst, direction = config
    if feat is None:
        return 0.0
    val = record.get(feat, 0)
    if direction == "higher_worse":
        score = (val - threshold) / (worst - threshold + 1e-9)
    else:
        score = (threshold - val) / (threshold - worst + 1e-9)
    return float(np.clip(score, 0.0, 1.0))


# ── Helper: Model E priority-ranked multi-label recommendations ─────
def _predict_recommendations(record: dict, model_E, scaler,
                              plant_enc: dict,
                              threshold: float = MODEL_E_THRESHOLD) -> dict:
    """
    Returns all applicable recommendations sorted by severity (most urgent first).
    """
    plant_id  = record.get("plant_id", "")
    record_fe = dict(record)
    record_fe["plant_enc"] = float(plant_enc.get(plant_id, 0))

    X_inp = np.array(
        [record_fe.get(f, 0) for f in FEATURE_COLS],
        dtype=float
    ).reshape(1, -1)
    X_sc = scaler.transform(X_inp)

    proba = np.array(
        [est.predict_proba(X_sc)[:, 1] for est in model_E.estimators_]
    ).flatten()

    fired = [
        (col, float(p))
        for col, p in zip(LABEL_COLS_E, proba)
        if p >= threshold
    ]
    if not fired:
        fired = [("maintain", float(proba[LABEL_COLS_E.index("maintain")]))]
    elif any(col != "maintain" for col, _ in fired):
        fired = [(col, p) for col, p in fired if col != "maintain"]

    results = []
    for label, prob in fired:
        dev = _deviation_score(record, label)
        sev = round(SEVERITY_WEIGHTS_E[label] * dev, 4)
        results.append({
            "action"         : LABEL_NAMES_E[LABEL_COLS_E.index(label)],
            "label_key"      : label,
            "probability"    : round(prob, 3),
            "severity_score" : sev,
        })

    results.sort(key=lambda x: x["severity_score"], reverse=True)
    for i, r in enumerate(results, 1):
        r["priority_rank"] = i

    n = len(results)
    overall_priority = (
        "ok"       if results[0]["label_key"] == "maintain"
        else "critical" if n >= 3
        else "attention"
    )
    return {
        "recommendations"  : results,
        "n_recommendations": n,
        "overall_priority" : overall_priority,
    }


# ── Routes ─────────────────────────────────────────────────────────
@component4_bp.route("/health", methods=["GET"])
def health():
    return jsonify({
        "component": "4 — Production Analysis & Resource Optimization",
        "status": "ok",
    })


@component4_bp.route("/predict", methods=["POST"])
def predict():
    """
    Full Component 4 production analysis prediction.

    Required fields:
        plant_id, machine_count, active_machine_count, machine_utilization,
        employee_count, daily_output_avg, total_workload, order_quantity,
        urgent_flag, urgent_handled_count, risk_count_from_component3,
        machine_breakdown_days, worker_shortage_days,
        quality_rating, on_time_rate, damage_rate, delay_days

    Returns:
        performance_score      — float 1.0–5.0  (Model A)
        star_rating            — str  "⭐"–"⭐⭐⭐⭐⭐"  (Model B)
        star_rating_num        — int  1–5
        confidence             — float probability of predicted star class
        star_probabilities     — dict {"1★": p, ..., "5★": p}
        low_confidence_flag    — bool  True when confidence < 0.65
        recommendations        — list of dicts, priority-ranked (Model E)
        overall_priority       — "ok" | "attention" | "critical"
        best_plant_category    — str (Model D)
        plant_id               — echoed from input
    """
    data = request.get_json(force=True, silent=True)
    if not data:
        return jsonify({"error": "Request body must be valid JSON"}), 400

    # ── Always-required fields (cannot be derived) ─────────────────
    always_required = [
        "machine_count", "active_machine_count",
        "employee_count", "daily_output_avg", "total_workload", "order_quantity",
        "urgent_handled_count",
        "risk_count_from_component3", "machine_breakdown_days", "worker_shortage_days",
        "damage_rate",
    ]
    # Either plant_name OR plant_id must be present
    if "plant_name" not in data and "plant_id" not in data:
        always_required.append("plant_name_or_plant_id")
    # Either the friendly day fields OR explicit delay/completion fields
    needs_completion = "delay_days" not in data or "planned_completion_days" not in data
    if needs_completion and "planned_completion_days" not in data and "delay_days" not in data:
        always_required.append("planned_completion_days_or_delay_days")

    missing = [f for f in always_required if f not in data]
    if missing:
        return jsonify({"error": f"Missing required fields: {missing}"}), 400

    # ── Parse & validate inputs ────────────────────────────────────
    try:
        machine_count          = int(data["machine_count"])
        active_machine_count   = int(data["active_machine_count"])
        employee_count         = int(data["employee_count"])
        daily_output_avg       = float(data["daily_output_avg"])
        total_workload         = float(data["total_workload"])
        order_quantity         = float(data["order_quantity"])
        urgent_handled_count   = int(data["urgent_handled_count"])
        risk_count             = float(data["risk_count_from_component3"])
        machine_breakdown_days = float(data["machine_breakdown_days"])
        worker_shortage_days   = float(data["worker_shortage_days"])
        damage_rate            = float(data["damage_rate"])
    except (ValueError, TypeError) as e:
        return jsonify({"error": f"Invalid field value: {e}"}), 400

    # ── Resolve plant_id from plant_name (if name given) ──────────
    if "plant_id" in data:
        plant_id = str(data["plant_id"])
    else:
        raw_name = str(data["plant_name"]).strip()
        plant_id = PLANT_NAME_TO_ID.get(raw_name)
        if plant_id is None:
            known = sorted(PLANT_NAME_TO_ID.keys())
            return jsonify({
                "error": f"Unknown plant_name '{raw_name}'. "
                         f"Known names: {known}"
            }), 400

    # ── Resolve urgent_flag from urgent_style_flag or urgent_flag ──
    if "urgent_flag" in data:
        try:
            urgent_flag = int(data["urgent_flag"])
        except (ValueError, TypeError):
            return jsonify({"error": "urgent_flag must be 0 or 1"}), 400
    elif "urgent_style_flag" in data:
        val = str(data["urgent_style_flag"]).strip().lower()
        if val in ("yes", "1", "true"):
            urgent_flag = 1
        elif val in ("no", "0", "false"):
            urgent_flag = 0
        else:
            return jsonify({
                "error": f"urgent_style_flag must be 'Yes' or 'No', got '{data['urgent_style_flag']}'"
            }), 400
    else:
        urgent_flag = 0   # safe default

    # ── Derive machine_utilization ─────────────────────────────────
    if "machine_utilization" in data:
        try:
            machine_utilization = float(data["machine_utilization"])
        except (ValueError, TypeError):
            return jsonify({"error": "machine_utilization must be a float (e.g. 0.93)"}), 400
    else:
        if machine_count == 0:
            return jsonify({"error": "machine_count cannot be 0 (used to derive machine_utilization)"}), 400
        machine_utilization = round(active_machine_count / machine_count, 6)

    # ── Derive delay_days ──────────────────────────────────────────
    if "delay_days" in data:
        try:
            delay_days = float(data["delay_days"])
        except (ValueError, TypeError):
            return jsonify({"error": "delay_days must be a number"}), 400
    else:
        try:
            planned = int(data["planned_completion_days"])
            actual  = int(data["actual_completion_days"])
        except (KeyError, ValueError, TypeError):
            return jsonify({
                "error": "Provide either 'delay_days' directly, or both "
                         "'planned_completion_days' and 'actual_completion_days'."
            }), 400
        delay_days = float(actual - planned)

    # ── Resolve on_time_rate and quality_rating (plant-level KPIs) ─
    # These are static per-plant constants in the training data.
    # Caller may still override them explicitly for advanced use.
    plant_kpi = PLANT_KPI.get(plant_id, {})
    if "on_time_rate" in data:
        try:
            on_time_rate = float(data["on_time_rate"])
        except (ValueError, TypeError):
            return jsonify({"error": "on_time_rate must be a float in [0, 1]"}), 400
    else:
        on_time_rate = plant_kpi.get("on_time_rate", 0.83)   # fallback: median plant

    if "quality_rating" in data:
        try:
            quality_rating = float(data["quality_rating"])
        except (ValueError, TypeError):
            return jsonify({"error": "quality_rating must be a float in [1.0, 5.0]"}), 400
    else:
        quality_rating = plant_kpi.get("quality_rating", 4.2)  # fallback: median plant

    # ── Validate ranges ────────────────────────────────────────────
    warnings_list = []
    if not (0.0 <= machine_utilization <= 1.0):
        warnings_list.append(
            f"machine_utilization={machine_utilization} is outside [0, 1]. "
            f"Expected a ratio (e.g. 0.93 for 93%)."
        )
    if not (0.0 <= on_time_rate <= 1.0):
        warnings_list.append(
            f"on_time_rate={on_time_rate} is outside [0, 1]. "
            f"Expected a ratio (e.g. 0.92 for 92%)."
        )
    if not (1.0 <= quality_rating <= 5.0):
        warnings_list.append(
            f"quality_rating={quality_rating} is outside [1.0, 5.0]."
        )
    if active_machine_count > machine_count:
        warnings_list.append(
            f"active_machine_count ({active_machine_count}) > "
            f"machine_count ({machine_count}). Check input."
        )

    # ── Hard OOD validation — reject physically implausible inputs ──
    # These fields go so far outside training range that predictions are meaningless.
    _hard_check = {
        "machine_count"       : machine_count,
        "employee_count"      : employee_count,
        "daily_output_avg"    : daily_output_avg,
        "order_quantity"      : order_quantity,
        "urgent_handled_count": urgent_handled_count,
    }
    hard_errors = []
    for field, direction, threshold, _, is_hard in OOD_GUARDS:
        if not is_hard:
            continue
        val = _hard_check.get(field, None)
        if val is None:
            continue
        if (direction == "below" and val < threshold) or            (direction == "above" and val > threshold):
            hard_errors.append(
                f"{field}={val} is {'below' if direction == 'below' else 'above'} "
                f"the training data {'minimum' if direction == 'below' else 'maximum'} "
                f"of {threshold}. Predictions would be unreliable."
            )
    if hard_errors:
        return jsonify({
            "error"  : "Input values are outside the model's training range.",
            "details": hard_errors,
        }), 400

    # ── Load models ────────────────────────────────────────────────
    try:
        models = _load_models()
    except RuntimeError as e:
        return jsonify({"error": str(e)}), 503

    scaler    = models["scaler"]
    encoders  = models["encoders"]
    plant_enc = encoders["plant_enc"]
    star_inv  = encoders["star_inv"]
    best_inv  = encoders["best_plant_inv"]

    # ── Resolve plant_enc — warn if unknown ────────────────────────
    if plant_id not in plant_enc:
        warnings_list.append(
            f"plant_id '{plant_id}' was not seen during training. "
            f"Defaulting plant_enc=0. Predictions may be less reliable."
        )
    plant_enc_val = float(plant_enc.get(plant_id, 0))

    # ── Assemble raw record dict (with plant_enc resolved) ─────────
    record = {
        "machine_count"              : machine_count,
        "active_machine_count"       : active_machine_count,
        "machine_utilization"        : machine_utilization,
        "employee_count"             : employee_count,
        "daily_output_avg"           : daily_output_avg,
        "total_workload"             : total_workload,
        "order_quantity"             : order_quantity,
        "urgent_flag"                : urgent_flag,
        "urgent_handled_count"       : urgent_handled_count,
        "risk_count_from_component3" : risk_count,
        "machine_breakdown_days"     : machine_breakdown_days,
        "worker_shortage_days"       : worker_shortage_days,
        "quality_rating"             : quality_rating,
        "on_time_rate"               : on_time_rate,
        "damage_rate"                : damage_rate,
        "delay_days"                 : delay_days,
        "plant_enc"                  : plant_enc_val,
    }

    try:
        # ── Build scaled feature vector ────────────────────────────
        X_raw = np.array(
            [record.get(f, 0) for f in FEATURE_COLS], dtype=float
        ).reshape(1, -1)
        X_sc = scaler.transform(X_raw)

        # ── Model A: Performance Score ─────────────────────────────
        perf_score = float(models["model_A"].predict(X_sc)[0])
        perf_score = round(float(np.clip(perf_score, 1.0, 5.0)), 3)

        # ── Model B: Star Rating ───────────────────────────────────
        star_num   = int(models["model_B"].predict(X_sc)[0])
        star_proba = models["model_B"].predict_proba(X_sc)[0]
        confidence = float(max(star_proba))
        star_label = star_inv.get(star_num, f"{star_num}★")

        star_probabilities = {
            f"{i + 1}★": round(float(p), 3)
            for i, p in enumerate(star_proba)
        }

        low_confidence_flag = confidence < LOW_CONF_THRESHOLD
        if low_confidence_flag:
            warnings_list.append(
                f"Star rating confidence={confidence:.3f} is below "
                f"{LOW_CONF_THRESHOLD}. Recommend manual review."
            )

        # ── Model D: Best Plant Category ───────────────────────────
        best_enc_val      = int(models["model_D"].predict(X_sc)[0])
        best_plant_cat    = best_inv.get(best_enc_val, f"class_{best_enc_val}")

        # ── Model E: Multi-label priority-ranked recommendations ───
        # Pass the original record dict (with plant_enc already resolved)
        proba_E = np.array(
            [est.predict_proba(X_sc)[:, 1] for est in models["model_E"].estimators_]
        ).flatten()

        fired = [
            (col, float(p))
            for col, p in zip(LABEL_COLS_E, proba_E)
            if p >= MODEL_E_THRESHOLD
        ]

        # ── OOD guard: rule-based label injection for out-of-distribution inputs ──
        # For each field that falls outside the training data range:
        #   hard_error=True  → already rejected above in validation (400 error)
        #   hard_error=False → inject the linked recommendation label + add warning
        # This ensures the model never silently ignores extreme inputs it wasn't trained on.
        _ood_record = {
            "machine_utilization"        : machine_utilization,
            "employee_count"             : employee_count,
            "machine_count"              : machine_count,
            "active_machine_count"       : active_machine_count,
            "daily_output_avg"           : daily_output_avg,
            "order_quantity"             : order_quantity,
            "urgent_handled_count"       : urgent_handled_count,
            "machine_breakdown_days"     : machine_breakdown_days,
            "worker_shortage_days"       : worker_shortage_days,
            "risk_count_from_component3" : risk_count,
            "damage_rate"                : damage_rate,
        }
        fired_labels = [col for col, _ in fired]
        for field, direction, threshold, inject_label, _ in OOD_GUARDS:
            if _ is True:
                continue  # hard errors handled in validation block below
            val = _ood_record.get(field, None)
            if val is None:
                continue
            triggered = (direction == "below" and val < threshold) or                         (direction == "above" and val > threshold)
            if triggered:
                warnings_list.append(
                    f"OOD: {field}={val} is {'below' if direction == 'below' else 'above'} "
                    f"training range boundary ({threshold}). "
                    f"{'Recommendation injected via rule-based override.' if inject_label else 'Prediction reliability reduced.'}"
                )
                if inject_label and inject_label not in fired_labels:
                    fired.append((inject_label, 1.0))
                    fired_labels.append(inject_label)

        if not fired:
            fired = [("maintain", float(proba_E[LABEL_COLS_E.index("maintain")]))]
        elif any(col != "maintain" for col, _ in fired):
            fired = [(col, p) for col, p in fired if col != "maintain"]

        recommendations = []
        for label, prob in fired:
            dev = _deviation_score(record, label)
            sev = round(SEVERITY_WEIGHTS_E[label] * dev, 4)
            recommendations.append({
                "action"         : LABEL_NAMES_E[LABEL_COLS_E.index(label)],
                "label_key"      : label,
                "probability"    : round(prob, 3),
                "severity_score" : sev,
            })

        recommendations.sort(key=lambda x: x["severity_score"], reverse=True)
        for i, r in enumerate(recommendations, 1):
            r["priority_rank"] = i

        n_rec = len(recommendations)
        overall_priority = (
            "ok"       if recommendations[0]["label_key"] == "maintain"
            else "critical" if n_rec >= 3
            else "attention"
        )

        # ── Build response ─────────────────────────────────────────
        return jsonify({
            "status"               : "success",
            "plant_id"             : plant_id,
            "warnings"             : warnings_list,
            "performance_score"    : perf_score,
            "star_rating"          : star_label,
            "star_rating_num"      : star_num,
            "confidence"           : round(confidence, 3),
            "star_probabilities"   : star_probabilities,
            "low_confidence_flag"  : low_confidence_flag,
            "recommendations"      : recommendations,
            "n_recommendations"    : n_rec,
            "overall_priority"     : overall_priority,
            "best_plant_category"  : best_plant_cat,
            "derived": {
                "plant_id"            : plant_id,
                "plant_enc"           : int(plant_enc_val),
                "urgent_flag"         : urgent_flag,
                "machine_utilization" : round(machine_utilization, 4),
                "on_time_rate"        : round(on_time_rate, 4),
                "quality_rating"      : round(quality_rating, 4),
                "delay_days"          : delay_days,
                "damage_rate"         : round(damage_rate, 4),
            },
        })

    except Exception as e:
        return jsonify({"error": f"Prediction failed: {str(e)}"}), 500