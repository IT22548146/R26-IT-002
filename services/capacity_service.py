"""
services/capacity_service.py
Manages dynamic plant monthly capacity — deduction and availability queries.
"""

import json
import math
import os

from database.db import get_db

DEFAULT_MONTHLY_CAPACITY = int(os.environ.get("DEFAULT_MONTHLY_CAPACITY", 150))
WORKING_DAYS_PER_MONTH = 25


def _plant_baseline_capacity(db, plant_id: str) -> int:
    """Return the plant's latest known monthly capacity for an unseeded month."""
    row = db.execute(
        """SELECT total_capacity FROM plant_monthly_capacity
           WHERE plant_id=? ORDER BY month_year DESC LIMIT 1""",
        (plant_id,),
    ).fetchone()
    if row and row["total_capacity"]:
        return int(row["total_capacity"])
    return DEFAULT_MONTHLY_CAPACITY


def get_available_capacity(plant_id: str, month_year: str) -> dict:
    """
    Returns total, used, and available capacity for a plant in a given month.
    month_year format: 'YYYY-MM'
    Creates a row using the plant's own latest baseline if none exists yet.
    """
    db = get_db()
    row = db.execute(
        "SELECT total_capacity, used_capacity FROM plant_monthly_capacity WHERE plant_id=? AND month_year=?",
        (plant_id, month_year),
    ).fetchone()

    if row is None:
        total = _plant_baseline_capacity(db, plant_id)
        db.execute(
            "INSERT OR IGNORE INTO plant_monthly_capacity(plant_id, month_year, total_capacity, used_capacity) VALUES (?,?,?,?)",
            (plant_id, month_year, total, 0),
        )
        db.commit()
        used = 0
    else:
        total = row["total_capacity"]
        used = row["used_capacity"]

    return {
        "plant_id": plant_id,
        "month_year": month_year,
        "total_capacity": total,
        "used_capacity": used,
        "available_capacity": max(0, total - used),
    }


def deduct_capacity(plant_id: str, month_year: str, qty: int) -> dict:
    """
    Consume at most the capacity still available in this month.

    The caller can roll ``remaining`` into the following month, while
    ``used_capacity`` is guaranteed not to exceed ``total_capacity``.
    """
    current = get_available_capacity(plant_id, month_year)
    take = max(0, min(int(qty), current["available_capacity"]))

    if take:
        db = get_db()
        db.execute(
            """UPDATE plant_monthly_capacity
               SET used_capacity = used_capacity + ?
               WHERE plant_id = ? AND month_year = ?""",
            (take, plant_id, month_year),
        )
        db.commit()

    result = get_available_capacity(plant_id, month_year)
    result["deducted"] = take
    result["remaining"] = max(0, int(qty) - take)
    return result


def get_all_plants_monthly_capacity(month_year: str) -> dict:
    """
    Returns a dict of {plant_name: available_capacity} for all plants in a month.
    Used to feed into Component 2's monthly_capacity parameter.
    """
    db = get_db()
    # Registered plants only. External sub plants (Part B) must never inflate the
    # network capacity that Component 2 uses for allocation / can_handle_solo.
    plants = db.execute(
        "SELECT id, name FROM plants WHERE plant_type IS NULL OR plant_type='Registered'"
    ).fetchall()
    result = {}
    for plant in plants:
        cap = get_available_capacity(plant["id"], month_year)
        result[plant["name"]] = cap["available_capacity"]
    return result


def months_between(start_month: str, end_month: str, cap: int = 24) -> list:
    """Return inclusive ``YYYY-MM`` values, oldest first, with a safety cap."""
    try:
        sy, sm = (int(x) for x in str(start_month)[:7].split("-"))
        ey, em = (int(x) for x in str(end_month)[:7].split("-"))
    except (TypeError, ValueError):
        return [str(start_month)[:7]]

    result = []
    year, month = sy, sm
    while (year, month) <= (ey, em) and len(result) < cap:
        result.append(f"{year:04d}-{month:02d}")
        year, month = (year + 1, 1) if month == 12 else (year, month + 1)
    return result or [str(start_month)[:7]]


def get_all_plants_window_capacity(start_month: str, end_month: str) -> dict:
    """Return registered-plant capacity across the full production window."""
    db = get_db()
    plants = db.execute(
        "SELECT id, name FROM plants WHERE plant_type IS NULL OR plant_type='Registered'"
    ).fetchall()
    window = months_between(start_month, end_month)

    result = {}
    for plant in plants:
        result[plant["name"]] = sum(
            get_available_capacity(plant["id"], month)["available_capacity"] for month in window
        )
    return result


def calculate_assignment_daily_commitment(
    plant_id: str,
    allocated_qty: int,
    approved_date,
    buyer_required_date,
    c2_result,
    *,
    fallback_daily_commitment: int = 500,
    reserved_capacity_qty: int = 0,
    db=None,
) -> dict:
    """Calculate one allocation's stable, plant-specific daily target.

    Component 2 predicts the number of embroidery production days for the
    style.  The order allocation therefore supplies the required daily rate,
    while the assigned plant's currently available monthly capacity supplies
    the upper bound.  The resulting value is saved with the allocation so a
    later assignment cannot silently change an existing production target.
    """
    connection = db or get_db()
    quantity = max(1, int(allocated_qty))
    months = months_between(str(approved_date)[:7], str(buyer_required_date)[:7])

    available_window = 0
    for month in months:
        row = connection.execute(
            """SELECT total_capacity, used_capacity
               FROM plant_monthly_capacity
               WHERE plant_id=? AND month_year=?""",
            (plant_id, month),
        ).fetchone()
        if row:
            available_window += max(0, int(row["total_capacity"]) - int(row["used_capacity"] or 0))
        else:
            available_window += _plant_baseline_capacity(connection, plant_id)

    # Existing assignments were deducted before allocation-level snapshots
    # existed. A one-time backfill can add that assignment's own reservation
    # back to reconstruct the capacity that was visible when it was assigned.
    available_window += max(0, int(reserved_capacity_qty or 0))

    capacity_working_days = max(1, len(months) * WORKING_DAYS_PER_MONTH)
    plant_daily_capacity = max(1, int(math.floor(available_window / capacity_working_days)))

    if isinstance(c2_result, str):
        try:
            c2_data = json.loads(c2_result)
        except (TypeError, json.JSONDecodeError):
            c2_data = {}
    elif isinstance(c2_result, dict):
        c2_data = c2_result
    else:
        c2_data = {}

    production_days = c2_data.get("production_days") or {}
    raw_phase_days = production_days.get("embroidery_days") or production_days.get(
        "total_production_days"
    )
    try:
        planned_phase_days = max(1, int(math.ceil(float(raw_phase_days))))
    except (TypeError, ValueError):
        fallback = max(1, int(fallback_daily_commitment or 500))
        planned_phase_days = max(1, int(math.ceil(quantity / fallback)))

    required_daily_rate = max(1, int(math.ceil(quantity / planned_phase_days)))
    daily_commitment = max(
        1,
        min(quantity, required_daily_rate, plant_daily_capacity),
    )

    return {
        "daily_commitment": daily_commitment,
        "required_daily_rate": required_daily_rate,
        "plant_daily_capacity": plant_daily_capacity,
        "available_window_capacity": available_window,
        "capacity_working_days": capacity_working_days,
        "planned_phase_days": planned_phase_days,
        "capacity_sufficient": plant_daily_capacity >= required_daily_rate,
        "source": "assigned_plant_capacity_and_c2_embroidery_days",
    }
