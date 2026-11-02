"""
services/capacity_service.py
Manages dynamic plant monthly capacity — deduction and availability queries.
"""

import os
from database.db import get_db

DEFAULT_MONTHLY_CAPACITY = int(os.environ.get("DEFAULT_MONTHLY_CAPACITY", 150))


def get_available_capacity(plant_id: str, month_year: str) -> dict:
    """
    Returns total, used, and available capacity for a plant in a given month.
    month_year format: 'YYYY-MM'
    Creates a row with DEFAULT_MONTHLY_CAPACITY if none exists yet.
    """
    db = get_db()
    row = db.execute(
        "SELECT total_capacity, used_capacity FROM plant_monthly_capacity WHERE plant_id=? AND month_year=?",
        (plant_id, month_year),
    ).fetchone()

    if row is None:
        # Initialise from the capacity history for that month (average util)
        total = DEFAULT_MONTHLY_CAPACITY
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
    Reduce the available capacity for a plant in a given month by qty.
    Creates the row if it doesn't exist.
    Returns updated capacity dict.
    """
    # Ensure row exists
    get_available_capacity(plant_id, month_year)

    db = get_db()
    db.execute(
        """UPDATE plant_monthly_capacity
           SET used_capacity = used_capacity + ?
           WHERE plant_id = ? AND month_year = ?""",
        (qty, plant_id, month_year),
    )
    db.commit()
    return get_available_capacity(plant_id, month_year)


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
