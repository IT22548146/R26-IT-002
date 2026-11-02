"""
services/plant_analytics_service.py

Component 4 (plant-based) aggregation.

Rolls plant_daily_logs up to a plant-month, builds the Component 4 payload,
calls the C4 model, and stores the result in plant_performance.

This replaces the old per-order C4 call: every C4 input (machines, staff,
breakdowns, shortages, output) is a property of the PLANT, not of one order.
Values are clamped to Component 4's training ranges so predictions stay valid.
"""
import json
from calendar import monthrange
from datetime import date

from database.db import get_db

# Component 4 hard training-range guards (see OOD_GUARDS in components/component4.py).
# Requests outside these are rejected with 400, so clamp before calling.
C4_LIMITS = {
    "machine_count":        (8, 22),
    "employee_count":       (28, 68),
    "daily_output_avg":     (85, 1088),
    "order_quantity":       (2017, 59951),
    "urgent_handled_count": (0, 6),
}

# Nominal pieces per machine per day, used as the efficiency ceiling.
NOMINAL_PCS_PER_MACHINE_DAY = 28


def _clamp(value, field):
    lo, hi = C4_LIMITS[field]
    return max(lo, min(hi, value))


def month_bounds(month_year):
    """'YYYY-MM' -> (first_day, last_day) as ISO date strings."""
    y, m = (int(x) for x in month_year.split("-"))
    return date(y, m, 1).isoformat(), date(y, m, monthrange(y, m)[1]).isoformat()


def aggregate_plant_month(plant_id, month_year):
    """
    Aggregate one plant's daily logs for a month into the Component 4 payload.
    Returns None when the plant has no logs for that month.
    """
    db = get_db()
    plant = db.execute("SELECT * FROM plants WHERE id=?", (plant_id,)).fetchone()
    if not plant:
        return None

    start, end = month_bounds(month_year)
    logs = db.execute(
        """SELECT * FROM plant_daily_logs
           WHERE plant_id=? AND log_date BETWEEN ? AND ? ORDER BY log_date""",
        (plant_id, start, end),
    ).fetchall()
    if not logs:
        return None

    working_days    = len(logs)
    total_output    = sum(l["total_output"] or 0 for l in logs)
    total_damage    = sum(l["total_damage_qty"] or 0 for l in logs)
    avg_output      = total_output / working_days
    machines_total  = round(sum(l["machines_total"] for l in logs) / working_days)
    machines_active = round(sum(l["machines_active"] for l in logs) / working_days)
    employees       = round(sum(l["employees_present"] for l in logs) / working_days)
    breakdown_days  = sum(1 for l in logs if (l["machine_breakdown_count"] or 0) > 0)
    shortage_days   = sum(1 for l in logs if (l["worker_shortage_count"] or 0) > 0)
    urgent_handled  = sum(l["urgent_orders_handled"] or 0 for l in logs)
    damage_rate     = round((total_damage / max(total_output, 1)) * 100, 2)

    # Efficiency: actual output against the plant's theoretical ceiling
    # (all machines running at the nominal rate).
    theoretical = machines_total * NOMINAL_PCS_PER_MACHINE_DAY * working_days
    efficiency  = round(min(1.0, total_output / max(theoretical, 1)), 4)
    utilization = round(machines_active / max(machines_total, 1), 4)

    # Delay: how many days the month's output actually needed versus the days
    # worked. Under-performing against the ceiling reads as schedule slippage.
    planned_days = working_days
    actual_days  = round(planned_days / max(efficiency, 0.01))
    actual_days  = min(actual_days, planned_days * 3)      # keep it sane
    delay_ratio  = round(max(0, actual_days - planned_days) / max(planned_days, 1), 4)

    # Critical risk events flagged by Component 3 on this plant's order logs.
    risk_rows = db.execute(
        """SELECT c3_result_json FROM daily_logs
           WHERE plant_id=? AND log_date BETWEEN ? AND ? AND c3_result_json IS NOT NULL""",
        (plant_id, start, end),
    ).fetchall()
    risk_count = 0
    for r in risk_rows:
        try:
            sev = (json.loads(r["c3_result_json"]).get("risk_detection") or {}).get("severity")
            if sev == "Critical":
                risk_count += 1
        except Exception:
            continue

    machine_count_c4 = _clamp(machines_total, "machine_count")
    payload = {
        # Send plant_id as well as the name: Component 4 resolves the id directly,
        # which lets external sub plants (Part B) be scored too. Their id is not in
        # the model's encoder, so C4 falls back to plant_enc=0 and returns a warning
        # - the score is comparative, not trained on that specific plant.
        "plant_id":                   plant["id"],
        "plant_name":                 plant["name"],
        "order_quantity":             _clamp(total_output, "order_quantity"),
        "planned_completion_days":    planned_days,
        "actual_completion_days":     actual_days,
        "machine_count":              machine_count_c4,
        "active_machine_count":       max(5, min(machines_active, machine_count_c4)),
        "employee_count":             _clamp(employees, "employee_count"),
        "daily_output_avg":           round(_clamp(avg_output, "daily_output_avg"), 1),
        "total_workload":             _clamp(total_output, "order_quantity"),
        "urgent_style_flag":          "Yes" if urgent_handled > 0 else "No",
        "urgent_handled_count":       _clamp(urgent_handled, "urgent_handled_count"),
        "risk_count_from_component3": min(risk_count, 16),
        "machine_breakdown_days":     breakdown_days,
        "worker_shortage_days":       shortage_days,
        "damage_rate":                damage_rate,
    }

    metrics = {
        "working_days":     working_days,
        "total_output":     total_output,
        "total_damage":     total_damage,
        "damage_rate":      damage_rate,
        "efficiency":       efficiency,
        "utilization":      utilization,
        "delay_ratio":      delay_ratio,
        "daily_commitment": round(avg_output, 1),
        "urgent_handled":   urgent_handled,
        "breakdown_days":   breakdown_days,
        "shortage_days":    shortage_days,
    }
    return {"payload": payload, "metrics": metrics, "plant": dict(plant)}


def analyze_plant_month(plant_id, month_year):
    """
    Aggregate + run Component 4 for one plant-month, and persist the result.
    Returns a summary dict (or a dict carrying an "error" key).
    """
    from flask import current_app

    agg = aggregate_plant_month(plant_id, month_year)
    if not agg:
        return {"error": "No daily logs for %s in %s." % (plant_id, month_year)}

    with current_app.test_client() as client:
        resp = client.post("/api/component4/predict", json=agg["payload"],
                           headers={"Content-Type": "application/json"})
        c4 = resp.get_json()

    if not c4 or "error" in c4:
        return {"error": (c4 or {}).get("error", "Component 4 prediction failed."),
                "details": (c4 or {}).get("details")}

    m = agg["metrics"]
    db = get_db()
    db.execute(
        """INSERT OR REPLACE INTO plant_performance
           (plant_id, month_year, performance_score, star_rating_num, on_time_rate,
            efficiency, utilization, damage_rate, delay_ratio, daily_commitment,
            total_workload, urgent_handled, best_plant_category, c4_result_json)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (plant_id, month_year, c4.get("performance_score"), c4.get("star_rating_num"),
         (c4.get("derived") or {}).get("on_time_rate"), m["efficiency"], m["utilization"],
         m["damage_rate"], m["delay_ratio"], m["daily_commitment"], m["total_output"],
         m["urgent_handled"], c4.get("best_plant_category"), json.dumps(c4)),
    )
    db.commit()
    return {"plant_id": plant_id, "month_year": month_year,
            "performance_score": c4.get("performance_score"),
            "star_rating_num": c4.get("star_rating_num"),
            "metrics": m, "c4_result": c4}


def analyze_all_plants(month_year):
    """Run Component 4 for every plant that has logs in the month."""
    db = get_db()
    plants = db.execute("SELECT id FROM plants ORDER BY id").fetchall()
    done, skipped, failed = [], [], []
    for p in plants:
        res = analyze_plant_month(p["id"], month_year)
        if "error" in res:
            entry = {"plant_id": p["id"], "error": res["error"]}
            if "No daily logs" in res["error"]:
                skipped.append(entry)
            else:
                failed.append(entry)
        else:
            done.append(res["plant_id"])
    return {"month_year": month_year, "analysed": done,
            "skipped": skipped, "failed": failed}


def available_months(limit=12):
    """Distinct months that have plant daily logs, newest first."""
    db = get_db()
    rows = db.execute(
        """SELECT DISTINCT substr(log_date,1,7) AS m FROM plant_daily_logs
           ORDER BY m DESC LIMIT ?""", (limit,),
    ).fetchall()
    return [r["m"] for r in rows]
