"""
routes/analytics.py
Component 4 — Production Analysis & Resource Optimization (plant-based).

Endpoints:
  POST /analytics/analyze                 run C4 for all plants in a month
  POST /analytics/plants/<id>/analyze     run C4 for one plant-month
  GET  /analytics/months                  months that have plant logs
  GET  /analytics/overview                dashboard KPIs + plant ranking
  GET  /analytics/kpi-comparison          per-plant KPI matrix for charts
  GET  /analytics/delay-damage            delay + damage analysis (3% rule)
  GET  /analytics/workload                utilisation / workload classification
  GET  /analytics/recommendations         resource-optimization suggestions
  GET  /analytics/plants/<id>/trend       month-by-month trend for one plant
"""
import json
from datetime import date

from flask import Blueprint, request, jsonify

from database.db import get_db
from middleware.auth_middleware import require_role
from services.plant_analytics_service import (
    analyze_all_plants, analyze_plant_month, available_months, aggregate_plant_month,
)

analytics_bp = Blueprint("analytics", __name__)

# Document rule: damage is acceptable at or below 3%.
DAMAGE_THRESHOLD = 3.0

# Workload bands. Measured on the capacity-load ratio (actual output against the
# plant's theoretical ceiling), which is what doc section 6 means by "available
# production capacity vs current workload" - not raw machine utilisation.
UNDER_UTILISED = 0.72
OVERLOADED     = 0.92


def _current_month():
    return date.today().strftime("%Y-%m")


def _month_arg():
    return (request.args.get("month") or "").strip() or _current_month()


def _damage_band(rate):
    if rate is None:
        return "Unknown"
    if rate < 1.0:
        return "Excellent"
    if rate < 2.0:
        return "Very Good"
    if rate <= DAMAGE_THRESHOLD:
        return "Acceptable"
    return "Needs Improvement"


def _rows_for_month(month_year):
    """Stored plant_performance rows joined to plant details, best score first."""
    db = get_db()
    return db.execute(
        """SELECT pp.*, p.name AS plant_name, p.location, p.quality_rating,
                  p.total_machines, p.employee_count
           FROM plant_performance pp
           JOIN plants p ON p.id = pp.plant_id
           WHERE pp.month_year = ?
           ORDER BY pp.performance_score DESC""",
        (month_year,),
    ).fetchall()


# ── Running the analysis ──────────────────────────────────────────────────

@analytics_bp.route("/analyze", methods=["POST"])
@require_role("Admin", "Manager")
def analyze_month():
    """Run Component 4 for every plant with logs in the given month."""
    data = request.get_json(force=True, silent=True) or {}
    month_year = (data.get("month") or "").strip() or _current_month()
    return jsonify(analyze_all_plants(month_year)), 200


@analytics_bp.route("/plants/<plant_id>/analyze", methods=["POST"])
@require_role("Admin", "Manager")
def analyze_one(plant_id):
    """Run Component 4 for a single plant-month."""
    data = request.get_json(force=True, silent=True) or {}
    month_year = (data.get("month") or "").strip() or _current_month()
    res = analyze_plant_month(plant_id, month_year)
    return (jsonify(res), 400) if "error" in res else (jsonify(res), 200)


@analytics_bp.route("/months", methods=["GET"])
@require_role("Admin", "Manager")
def months():
    return jsonify({"months": available_months(), "current": _current_month()}), 200


# ── Dashboard + ranking (doc §2, §3) ──────────────────────────────────────

@analytics_bp.route("/overview", methods=["GET"])
@require_role("Admin", "Manager")
def overview():
    """Headline KPIs plus the plant performance ranking table."""
    month_year = _month_arg()
    rows = _rows_for_month(month_year)
    if not rows:
        return jsonify({"month_year": month_year, "analysed": False,
                        "kpis": None, "ranking": []}), 200

    ranking = []
    for i, r in enumerate(rows):
        ranking.append({
            "rank":              i + 1,
            "plant_id":          r["plant_id"],
            "plant_name":        r["plant_name"],
            "location":          r["location"],
            "overall_score":     r["performance_score"],
            "star_rating_num":   r["star_rating_num"],
            "on_time_rate":      r["on_time_rate"],
            "efficiency":        r["efficiency"],
            "utilization":       r["utilization"],
            "damage_rate":       r["damage_rate"],
            "damage_band":       _damage_band(r["damage_rate"]),
            "delay_ratio":       r["delay_ratio"],
            "daily_commitment":  r["daily_commitment"],
            "total_workload":    r["total_workload"],
            "urgent_handled":    r["urgent_handled"],
            "quality_rating":    r["quality_rating"],
            "category":          r["best_plant_category"],
        })

    n = len(rows)
    scores   = [r["performance_score"] or 0 for r in rows]
    on_times = [r["on_time_rate"] for r in rows if r["on_time_rate"] is not None]
    damages  = [r["damage_rate"] for r in rows if r["damage_rate"] is not None]
    kpis = {
        "avg_performance_score": round(sum(scores) / n, 2),
        "best_plant": {
            "plant_id":   rows[0]["plant_id"],
            "plant_name": rows[0]["plant_name"],
            "score":      rows[0]["performance_score"],
            "stars":      rows[0]["star_rating_num"],
        },
        "avg_on_time_rate":  round(sum(on_times) / len(on_times), 4) if on_times else None,
        "avg_damage_rate":   round(sum(damages) / len(damages), 2) if damages else None,
        "total_urgent_orders": sum(r["urgent_handled"] or 0 for r in rows),
        "plants_analysed":   n,
        "total_output":      sum(r["total_workload"] or 0 for r in rows),
    }
    return jsonify({"month_year": month_year, "analysed": True,
                    "kpis": kpis, "ranking": ranking}), 200


# ── KPI comparison (doc §4) ───────────────────────────────────────────────

@analytics_bp.route("/kpi-comparison", methods=["GET"])
@require_role("Admin", "Manager")
def kpi_comparison():
    """Per-plant KPI matrix, shaped for charting."""
    month_year = _month_arg()
    rows = _rows_for_month(month_year)
    kpis = [
        {"key": "quality_rating",   "label": "Quality Rating",   "max": 5},
        {"key": "on_time_rate",     "label": "On-Time Rate",     "max": 1},
        {"key": "efficiency",       "label": "Efficiency",       "max": 1},
        {"key": "utilization",      "label": "Utilization",      "max": 1},
        {"key": "damage_rate",      "label": "Damage %",         "max": 5, "lower_is_better": True},
        {"key": "delay_ratio",      "label": "Delay Ratio",      "max": 1, "lower_is_better": True},
        {"key": "daily_commitment", "label": "Daily Commitment", "max": None},
        {"key": "total_workload",   "label": "Workload",         "max": None},
        {"key": "urgent_handled",   "label": "Urgent Handled",   "max": None},
    ]
    plants = [{
        "plant_id":         r["plant_id"],
        "plant_name":       r["plant_name"],
        "quality_rating":   r["quality_rating"],
        "on_time_rate":     r["on_time_rate"],
        "efficiency":       r["efficiency"],
        "utilization":      r["utilization"],
        "damage_rate":      r["damage_rate"],
        "delay_ratio":      r["delay_ratio"],
        "daily_commitment": r["daily_commitment"],
        "total_workload":   r["total_workload"],
        "urgent_handled":   r["urgent_handled"],
        "performance_score": r["performance_score"],
    } for r in rows]
    return jsonify({"month_year": month_year, "kpis": kpis, "plants": plants}), 200


# ── Delay & damage analysis (doc §5) ──────────────────────────────────────

@analytics_bp.route("/delay-damage", methods=["GET"])
@require_role("Admin", "Manager")
def delay_damage():
    """Damage banding against the 3% rule, plus delay standing."""
    month_year = _month_arg()
    rows = _rows_for_month(month_year)
    items = []
    for r in rows:
        rate = r["damage_rate"]
        items.append({
            "plant_id":     r["plant_id"],
            "plant_name":   r["plant_name"],
            "damage_rate":  rate,
            "damage_band":  _damage_band(rate),
            "within_limit": (rate is not None and rate <= DAMAGE_THRESHOLD),
            "total_output": r["total_workload"],
            "damaged_qty":  round((rate or 0) / 100 * (r["total_workload"] or 0)),
            "delay_ratio":  r["delay_ratio"],
            "on_time_rate": r["on_time_rate"],
            "delayed":      (r["delay_ratio"] or 0) > 0,
        })
    breaching = [i for i in items if not i["within_limit"]]
    return jsonify({
        "month_year": month_year,
        "threshold":  DAMAGE_THRESHOLD,
        "items":      items,
        "breaching_count": len(breaching),
        "worst_damage":    items and max(items, key=lambda x: x["damage_rate"] or 0) or None,
        "worst_delay":     items and max(items, key=lambda x: x["delay_ratio"] or 0) or None,
    }), 200


# ── Workload & resource utilisation (doc §6) ──────────────────────────────

@analytics_bp.route("/workload", methods=["GET"])
@require_role("Admin", "Manager")
def workload():
    """Classify each plant as Underutilized / Optimal / Overloaded."""
    month_year = _month_arg()
    rows = _rows_for_month(month_year)
    db = get_db()
    items = []
    for r in rows:
        # Load ratio = how much of the plant's capacity the month's work consumed.
        load = r["efficiency"] or 0
        util = r["utilization"] or 0
        if load < UNDER_UTILISED:
            status, advice = "Underutilized", "Has spare capacity — allocate more orders here."
        elif util > OVERLOADED:
            status, advice = "Overloaded", "Running at the limit — move work to a lighter plant."
        else:
            status, advice = "Optimal", "Workload is well balanced."

        cap = db.execute(
            "SELECT total_capacity, used_capacity FROM plant_monthly_capacity WHERE plant_id=? AND month_year=?",
            (r["plant_id"], month_year),
        ).fetchone()
        items.append({
            "plant_id":       r["plant_id"],
            "plant_name":     r["plant_name"],
            "utilization":    util,
            "load_ratio":     load,
            "status":         status,
            "advice":         advice,
            "efficiency":     r["efficiency"],
            "total_workload": r["total_workload"],
            "daily_commitment": r["daily_commitment"],
            "total_capacity": cap["total_capacity"] if cap else None,
            "used_capacity":  cap["used_capacity"] if cap else None,
        })
    return jsonify({
        "month_year": month_year,
        "bands": {"underutilized_below": UNDER_UTILISED, "overloaded_above": OVERLOADED},
        "items": items,
        "counts": {
            "Underutilized": sum(1 for i in items if i["status"] == "Underutilized"),
            "Optimal":       sum(1 for i in items if i["status"] == "Optimal"),
            "Overloaded":    sum(1 for i in items if i["status"] == "Overloaded"),
        },
    }), 200


# ── Resource optimization recommendations (doc §21) ───────────────────────

@analytics_bp.route("/recommendations", methods=["GET"])
@require_role("Admin", "Manager")
def recommendations():
    """Network-level suggestions derived from the month's plant performance."""
    month_year = _month_arg()
    rows = _rows_for_month(month_year)
    if not rows:
        return jsonify({"month_year": month_year, "recommendations": []}), 200

    recs = []
    best, worst = rows[0], rows[-1]
    recs.append({"type": "allocate_more", "priority": "high",
                 "plant_id": best["plant_id"],
                 "message": "Allocate more orders to %s — highest overall score (%.2f)."
                            % (best["plant_name"], best["performance_score"] or 0)})

    for r in rows:
        if (r["damage_rate"] or 0) > DAMAGE_THRESHOLD:
            recs.append({"type": "quality_action", "priority": "high", "plant_id": r["plant_id"],
                         "message": "%s damage is %.2f%% (above the %.0f%% limit) — run quality improvement."
                                    % (r["plant_name"], r["damage_rate"], DAMAGE_THRESHOLD)})
        util = r["efficiency"] or 0
        if util < UNDER_UTILISED:
            recs.append({"type": "improve_utilization", "priority": "medium", "plant_id": r["plant_id"],
                         "message": "%s is only %.0f%% utilised — improve machine utilisation or send more work."
                                    % (r["plant_name"], util * 100)})
        elif util > OVERLOADED:
            recs.append({"type": "reduce_load", "priority": "medium", "plant_id": r["plant_id"],
                         "message": "%s is at %.0f%% utilisation — reduce its load."
                                    % (r["plant_name"], util * 100)})
        if (r["delay_ratio"] or 0) > 0.15:
            recs.append({"type": "delay_action", "priority": "medium", "plant_id": r["plant_id"],
                         "message": "%s is running %.0f%% behind schedule — review capacity."
                                    % (r["plant_name"], (r["delay_ratio"] or 0) * 100)})

    lowest_damage = min(rows, key=lambda r: r["damage_rate"] if r["damage_rate"] is not None else 99)
    recs.append({"type": "quality_pick", "priority": "low", "plant_id": lowest_damage["plant_id"],
                 "message": "For quality-critical styles choose %s — lowest damage (%.2f%%)."
                            % (lowest_damage["plant_name"], lowest_damage["damage_rate"] or 0)})

    best_commit = max(rows, key=lambda r: r["daily_commitment"] or 0)
    recs.append({"type": "throughput_pick", "priority": "low", "plant_id": best_commit["plant_id"],
                 "message": "For high-volume orders choose %s — best daily output (%.0f pcs/day)."
                            % (best_commit["plant_name"], best_commit["daily_commitment"] or 0)})

    if worst["plant_id"] != best["plant_id"]:
        recs.append({"type": "reduce_allocation", "priority": "low", "plant_id": worst["plant_id"],
                     "message": "Limit new orders to %s until its score improves (%.2f)."
                                % (worst["plant_name"], worst["performance_score"] or 0)})

    return jsonify({"month_year": month_year, "recommendations": recs}), 200


# ── Per-plant trend ───────────────────────────────────────────────────────

@analytics_bp.route("/plants/<plant_id>/trend", methods=["GET"])
@require_role("Admin", "Manager")
def plant_trend(plant_id):
    """Month-by-month performance history for one plant."""
    db = get_db()
    rows = db.execute(
        """SELECT month_year, performance_score, star_rating_num, efficiency,
                  utilization, damage_rate, delay_ratio, daily_commitment, total_workload
           FROM plant_performance WHERE plant_id=? ORDER BY month_year""",
        (plant_id,),
    ).fetchall()
    plant = db.execute("SELECT id, name, location FROM plants WHERE id=?", (plant_id,)).fetchone()
    return jsonify({
        "plant": dict(plant) if plant else None,
        "trend": [dict(r) for r in rows],
    }), 200


# ── Raw aggregate preview (what gets sent to the model) ───────────────────

@analytics_bp.route("/plants/<plant_id>/aggregate", methods=["GET"])
@require_role("Admin", "Manager")
def plant_aggregate(plant_id):
    """Inspect the exact Component 4 payload for a plant-month, without running it."""
    month_year = _month_arg()
    agg = aggregate_plant_month(plant_id, month_year)
    if not agg:
        return jsonify({"error": "No daily logs for %s in %s." % (plant_id, month_year)}), 404
    return jsonify({"month_year": month_year, "payload": agg["payload"],
                    "metrics": agg["metrics"]}), 200
