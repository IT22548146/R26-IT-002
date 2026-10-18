"""Whole-order priority queue and capacity-aware planning for Component 1."""

from __future__ import annotations

import json
import os
from datetime import date, datetime, timedelta

ACTIVE_PLAN_STATUSES = ("Draft", "AwaitingBuyer", "BuyerApproved", "Scheduled")
DEFAULT_MONTHLY_CAPACITY = int(os.environ.get("DEFAULT_MONTHLY_CAPACITY", 150))


def _as_date(value) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return datetime.strptime(str(value)[:10], "%Y-%m-%d").date()


def _completion_days(quantity: int) -> int:
    if quantity <= 3:
        return 3
    if quantity <= 5:
        return 5
    return 7


def _next_weekday(day: date, weekday: int) -> date:
    return day + timedelta(days=(weekday - day.weekday()) % 7)


def _next_month(day: date) -> date:
    return date(day.year + 1, 1, 1) if day.month == 12 else date(day.year, day.month + 1, 1)


def _next_workday(day: date) -> date:
    while day.weekday() >= 5:
        day += timedelta(days=1)
    return day


def normalize_priority_ranks(db, buyer_id: int) -> list[int]:
    """Normalize the buyer's editable pending queue and return ordered IDs."""
    locked = db.execute(
        """SELECT COALESCE(MAX(buyer_priority_rank), 0) AS last_rank
           FROM sample_orders
           WHERE buyer_id=? AND status='Pending' AND priority_locked_at IS NOT NULL""",
        (buyer_id,),
    ).fetchone()
    first_rank = int(locked["last_rank"] or 0) + 1
    rows = db.execute(
        """SELECT id FROM sample_orders
           WHERE buyer_id=? AND status='Pending' AND priority_locked_at IS NULL
           ORDER BY CASE WHEN buyer_priority_rank IS NULL THEN 1 ELSE 0 END,
                    buyer_priority_rank, created_at, id""",
        (buyer_id,),
    ).fetchall()
    ordered_ids = [int(row["id"]) for row in rows]
    for rank, order_id in enumerate(ordered_ids, start=first_rank):
        db.execute(
            "UPDATE sample_orders SET buyer_priority_rank=? WHERE id=?",
            (rank, order_id),
        )
    return ordered_ids


def set_priority_order(
    db,
    buyer_id: int,
    ordered_order_ids: list[int],
    reasons: dict[str, str] | None = None,
) -> list[int]:
    """Atomically apply a complete ordering for one buyer's editable queue."""
    current_ids = normalize_priority_ranks(db, buyer_id)
    try:
        requested_ids = [int(order_id) for order_id in ordered_order_ids]
    except (TypeError, ValueError) as exc:
        raise ValueError("ordered_order_ids must contain whole-number order IDs") from exc

    if len(requested_ids) != len(set(requested_ids)):
        raise ValueError("ordered_order_ids cannot contain duplicates")
    if set(requested_ids) != set(current_ids):
        raise ValueError(
            "Submit every editable pending sample order exactly once; "
            "processing, completed, cancelled, or locked orders cannot be reordered."
        )

    timestamp = datetime.utcnow()
    reasons = reasons or {}
    locked = db.execute(
        """SELECT COALESCE(MAX(buyer_priority_rank), 0) AS last_rank
           FROM sample_orders
           WHERE buyer_id=? AND status='Pending' AND priority_locked_at IS NOT NULL""",
        (buyer_id,),
    ).fetchone()
    first_rank = int(locked["last_rank"] or 0) + 1
    for rank, order_id in enumerate(requested_ids, start=first_rank):
        reason = reasons.get(str(order_id))
        db.execute(
            """UPDATE sample_orders
               SET buyer_priority_rank=?, priority_reason=COALESCE(?, priority_reason),
                   priority_updated_at=?
               WHERE id=? AND buyer_id=?""",
            (
                rank,
                reason.strip() if isinstance(reason, str) and reason.strip() else None,
                timestamp,
                order_id,
                buyer_id,
            ),
        )
    return requested_ids


def _shipment_weekday(db, buyer_id: int) -> int:
    row = db.execute(
        """SELECT bc.shipment_dow_index
           FROM users u
           JOIN organizations o ON o.id=u.org_id
           LEFT JOIN buyers_config bc ON bc.org_id=o.id
           WHERE u.id=?""",
        (buyer_id,),
    ).fetchone()
    return int(row["shipment_dow_index"]) if row and row["shipment_dow_index"] is not None else 0


def _plant_score(order, plant_name: str, fallback: float) -> float:
    try:
        c1 = json.loads(order["c1_result_json"] or "{}")
        scores = c1.get("model2_plant_selection", {}).get("all_scores", [])
        match = next((item for item in scores if item.get("plant") == plant_name), None)
        return float(match["composite_score"]) if match else fallback
    except (TypeError, ValueError, json.JSONDecodeError, KeyError):
        return fallback


def _capacity_for_month(db, plant_id: str, month_year: str) -> tuple[int, int]:
    row = db.execute(
        """SELECT total_capacity, used_capacity FROM plant_monthly_capacity
           WHERE plant_id=? AND month_year=?""",
        (plant_id, month_year),
    ).fetchone()
    if row:
        total, used = int(row["total_capacity"]), int(row["used_capacity"] or 0)
    else:
        baseline = db.execute(
            """SELECT total_capacity FROM plant_monthly_capacity
               WHERE plant_id=? ORDER BY month_year DESC LIMIT 1""",
            (plant_id,),
        ).fetchone()
        total, used = (
            int(baseline["total_capacity"]) if baseline else DEFAULT_MONTHLY_CAPACITY,
            0,
        )
    tentative = db.execute(
        """SELECT COALESCE(SUM(reserved_quantity), 0) AS quantity
           FROM sample_capacity_reservations
           WHERE plant_id=? AND capacity_month=? AND status='Tentative'""",
        (plant_id, month_year),
    ).fetchone()
    return total, used + int(tentative["quantity"] or 0)


def release_order_reservations(db, order_id: int) -> None:
    db.execute(
        """UPDATE sample_capacity_reservations
           SET status='Released', released_at=?
           WHERE sample_order_id=? AND status='Tentative'""",
        (datetime.utcnow(), order_id),
    )


def reserve_plan_capacity(db, order_id: int, plan: dict) -> dict:
    """Tentatively hold a delayed proposal's capacity while the buyer decides."""
    snapshot = plan.get("capacity_snapshot") or {}
    month_year = snapshot.get("capacity_month")
    quantity = int(snapshot.get("quantity") or 0)
    if not month_year or quantity <= 0:
        raise ValueError("Plan does not contain a valid capacity snapshot")

    release_order_reservations(db, order_id)
    total, committed_and_held = _capacity_for_month(
        db, plan["recommended_plant_id"], month_year
    )
    available = max(0, total - committed_and_held)
    if available < quantity:
        raise ValueError("Plant capacity changed; regenerate the plan before proposing it")

    cursor = db.execute(
        """INSERT INTO sample_capacity_reservations
           (sample_order_id, plan_id, plant_id, capacity_month,
            reserved_quantity, status)
           VALUES (?,?,?,?,?,'Tentative')
           ON CONFLICT(plan_id) DO UPDATE SET
               plant_id=excluded.plant_id,
               capacity_month=excluded.capacity_month,
               reserved_quantity=excluded.reserved_quantity,
               status='Tentative',
               released_at=NULL""",
        (order_id, plan["id"], plan["recommended_plant_id"], month_year, quantity),
    )
    return {
        "id": cursor.lastrowid,
        "plant_id": plan["recommended_plant_id"],
        "capacity_month": month_year,
        "reserved_quantity": quantity,
        "status": "Tentative",
    }


def confirm_order_reservation(db, order_id: int, plan_id: int) -> None:
    db.execute(
        """UPDATE sample_capacity_reservations
           SET status='Confirmed'
           WHERE sample_order_id=? AND plan_id=? AND status='Tentative'""",
        (order_id, plan_id),
    )


def _find_capacity_window(db, plant_id: str, quantity: int, earliest: date, remaining: dict):
    candidate = earliest
    for _ in range(12):
        month_year = candidate.strftime("%Y-%m")
        key = (plant_id, month_year)
        if key not in remaining:
            total, used = _capacity_for_month(db, plant_id, month_year)
            remaining[key] = max(0, total - used)
        if remaining[key] >= quantity:
            return _next_workday(candidate), month_year, remaining[key]
        candidate = _next_month(candidate)
    return None


def _serialize_plan(row) -> dict | None:
    if not row:
        return None
    plan = dict(row)
    raw_snapshot = plan.pop("capacity_snapshot_json", None)
    if raw_snapshot:
        try:
            plan["capacity_snapshot"] = json.loads(raw_snapshot)
        except json.JSONDecodeError:
            plan["capacity_snapshot"] = None
    plan["can_meet_original_date"] = bool(plan.get("can_meet_original_date"))
    return plan


def get_current_plan(db, order_id: int) -> dict | None:
    row = db.execute(
        """SELECT sop.*, p.name AS recommended_plant_name,
                  p.location AS recommended_plant_location
           FROM sample_order_plans sop
           JOIN plants p ON p.id=sop.recommended_plant_id
           WHERE sop.sample_order_id=? AND sop.plan_status!='Superseded'
           ORDER BY sop.id DESC LIMIT 1""",
        (order_id,),
    ).fetchone()
    return _serialize_plan(row)


def plan_buyer_queue(db, buyer_id: int) -> list[dict]:
    """Rebuild draft plans for one buyer's unlocked pending orders in rank order."""
    normalize_priority_ranks(db, buyer_id)
    orders = db.execute(
        """SELECT * FROM sample_orders
           WHERE buyer_id=? AND status='Pending' AND priority_locked_at IS NULL
           ORDER BY buyer_priority_rank, created_at, id""",
        (buyer_id,),
    ).fetchall()
    if not orders:
        return []

    plants = db.execute(
        """SELECT id, name, location, quality_rating, historical_on_time_rate
           FROM plants
           WHERE plant_type IS NULL OR plant_type='Registered'
           ORDER BY name"""
    ).fetchall()
    if not plants:
        raise ValueError("No registered plants are available for sample planning")

    shipment_weekday = _shipment_weekday(db, buyer_id)
    today = date.today()
    plant_ready = {plant["id"]: today for plant in plants}
    remaining: dict[tuple[str, str], int] = {}
    results = []

    for order in orders:
        quantity = int(order["sample_qty"])
        receive_date = max(today, _as_date(order["receive_date"]))
        required_date = _as_date(order["buyer_required_date"])
        duration = _completion_days(quantity)
        candidates = []

        for plant in plants:
            earliest = max(receive_date, plant_ready[plant["id"]])
            window = _find_capacity_window(db, plant["id"], quantity, earliest, remaining)
            if not window:
                continue
            start_date, month_year, capacity_before = window
            completion_date = start_date + timedelta(days=duration)
            shipment_date = _next_weekday(completion_date, shipment_weekday)
            can_meet = shipment_date <= required_date
            base_score = (
                0.7 * float(plant["historical_on_time_rate"] or 0.75)
                + 0.3 * (float(plant["quality_rating"] or 4.0) / 5.0)
            )
            suitability = _plant_score(order, plant["name"], base_score)
            candidates.append(
                {
                    "plant_id": plant["id"],
                    "plant_name": plant["name"],
                    "plant_location": plant["location"],
                    "start_date": start_date,
                    "completion_date": completion_date,
                    "shipment_date": shipment_date,
                    "month_year": month_year,
                    "capacity_before": capacity_before,
                    "suitability_score": round(suitability, 4),
                    "can_meet": can_meet,
                }
            )

        if not candidates:
            raise ValueError(
                f"No plant has capacity for sample order #{order['id']} in the next 12 months"
            )

        on_time = [candidate for candidate in candidates if candidate["can_meet"]]
        if on_time:
            chosen = sorted(
                on_time,
                key=lambda item: (
                    item["shipment_date"],
                    -item["suitability_score"],
                    item["plant_id"],
                ),
            )[0]
        else:
            chosen = sorted(
                candidates,
                key=lambda item: (
                    item["shipment_date"],
                    -item["suitability_score"],
                    item["plant_id"],
                ),
            )[0]

        capacity_key = (chosen["plant_id"], chosen["month_year"])
        remaining[capacity_key] -= quantity
        plant_ready[chosen["plant_id"]] = _next_workday(
            chosen["completion_date"] + timedelta(days=1)
        )
        delay_days = max(0, (chosen["shipment_date"] - required_date).days)
        action = (
            "Proceed with the original required date"
            if chosen["can_meet"]
            else "Propose the earliest achievable shipment date to the buyer"
        )
        snapshot = {
            "buyer_priority_rank": int(order["buyer_priority_rank"]),
            "quantity": quantity,
            "capacity_month": chosen["month_year"],
            "available_before": chosen["capacity_before"],
            "available_after": remaining[capacity_key],
            "suitability_score": chosen["suitability_score"],
            "shipment_weekday": shipment_weekday,
        }

        db.execute(
            """UPDATE sample_order_plans SET plan_status='Superseded', updated_at=?
               WHERE sample_order_id=?
                 AND plan_status IN ('Draft','AwaitingBuyer','BuyerRejected')""",
            (datetime.utcnow(), order["id"]),
        )
        cursor = db.execute(
            """INSERT INTO sample_order_plans
               (sample_order_id, recommended_plant_id, estimated_start_date,
                estimated_completion_date, planned_shipment_date,
                original_required_date, can_meet_original_date, delay_days,
                planning_action, plan_status, capacity_snapshot_json)
               VALUES (?,?,?,?,?,?,?,?,?,'Draft',?)""",
            (
                order["id"],
                chosen["plant_id"],
                chosen["start_date"].isoformat(),
                chosen["completion_date"].isoformat(),
                chosen["shipment_date"].isoformat(),
                required_date.isoformat(),
                int(chosen["can_meet"]),
                delay_days,
                action,
                json.dumps(snapshot),
            ),
        )
        db.execute(
            "UPDATE sample_orders SET feasibility=? WHERE id=?",
            ("Feasible" if chosen["can_meet"] else "Infeasible", order["id"]),
        )
        plan = get_current_plan(db, order["id"])
        if plan:
            plan["id"] = cursor.lastrowid
            results.append(plan)

    return results
