"""
services/capacity_service.py
Manages dynamic plant monthly capacity — deduction and availability queries.
"""

import os
from database.db import get_db

DEFAULT_MONTHLY_CAPACITY = int(os.environ.get("DEFAULT_MONTHLY_CAPACITY", 150))


def _plant_baseline_capacity(db, plant_id: str) -> int:
    """
    The capacity a plant should default to for a month we have no row for.

    Using the flat DEFAULT_MONTHLY_CAPACITY here was a real bug: months beyond the
    seeded range collapsed every plant to 150 units (network 900 instead of
    300,000), which made every plant look saturated. Fall back to what this plant
    actually runs at instead.
    """
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
    Creates a row seeded from the plant's own baseline if none exists yet.
    """
    db = get_db()
    row = db.execute(
        "SELECT total_capacity, used_capacity FROM plant_monthly_capacity WHERE plant_id=? AND month_year=?",
        (plant_id, month_year),
    ).fetchone()

    if row is None:
        # Seed from this plant's own recent capacity, not a flat constant.
        total = _plant_baseline_capacity(db, plant_id)
        db.execute(
            "INSERT OR IGNORE INTO plant_monthly_capacity(plant_id, month_year, total_capacity, used_capacity) VALUES (?,?,?,?)",
            (plant_id, month_year, total, 0),
        )
        db.commit()
        used = 0
    else:
        total = row["total_capacity"]
        used  = row["used_capacity"]

    return {
        "plant_id":           plant_id,
        "month_year":         month_year,
        "total_capacity":     total,
        "used_capacity":      used,
        "available_capacity": max(0, total - used),
    }


def deduct_capacity(plant_id: str, month_year: str, qty: int) -> dict:
    """
    Consume up to `qty` of a plant's capacity in a month.

    Only takes what the month actually has left, so used_capacity can never
    exceed total_capacity (which previously drove "Available Units" negative when
    several orders landed in the same month). The caller must roll any remainder
    into the following month - see `deducted` / `remaining` in the result.
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
    """['YYYY-MM', ...] inclusive, oldest first. Capped so a bad date cannot loop away."""
    try:
        sy, sm = (int(x) for x in str(start_month)[:7].split("-"))
        ey, em = (int(x) for x in str(end_month)[:7].split("-"))
    except (TypeError, ValueError):
        return [str(start_month)[:7]]
    out = []
    y, m = sy, sm
    while (y, m) <= (ey, em) and len(out) < cap:
        out.append("%04d-%02d" % (y, m))
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return out or [str(start_month)[:7]]


def get_all_plants_window_capacity(start_month: str, end_month: str) -> dict:
    """
    {plant_name: capacity available across the whole production window}.

    A bulk order is produced over several months, so judging it against a single
    month understates what the network can absorb. This sums every month the work
    actually spans. Registered plants only - external sub plants must never
    inflate the capacity Component 2 sees.
    """
    db = get_db()
    plants = db.execute(
        "SELECT id, name FROM plants WHERE plant_type IS NULL OR plant_type='Registered'"
    ).fetchall()
    window = months_between(start_month, end_month)

    result = {}
    for plant in plants:
        total = 0
        for m in window:
            total += get_available_capacity(plant["id"], m)["available_capacity"]
        result[plant["name"]] = total
    return result
