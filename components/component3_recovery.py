"""Deterministic emergency recovery planning for Component 3.

The ML models detect production risk.  This module turns the current order
state and explicitly supplied capacity limits into explainable recovery
options.  It intentionally contains no learned model so that every suggested
action can be traced back to a calculation.
"""

from __future__ import annotations

import math
from datetime import datetime, timedelta
from typing import Any


RECOVERY_PARAMETER_FIELDS = {
    "planned_worker_count",
    "planned_machine_count",
    "normal_shift_hours",
    "max_overtime_hours_per_day",
    "max_additional_workers",
    "available_backup_machines",
    "backup_line_daily_capacity",
    "expected_machine_repair_hours",
}


def _number(value: Any, field: str, *, integer: bool = False) -> int | float:
    if isinstance(value, bool):
        raise ValueError(f"recovery_parameters.{field} must be numeric")
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(
            f"recovery_parameters.{field} must be numeric"
        ) from exc
    if not math.isfinite(number):
        raise ValueError(f"recovery_parameters.{field} must be finite")
    if integer:
        if not number.is_integer():
            raise ValueError(f"recovery_parameters.{field} must be an integer")
        return int(number)
    return number


def normalize_recovery_parameters(
    raw: Any,
    *,
    worker_shortage_count: int,
    machine_breakdown_count: int,
) -> dict[str, int | float | None]:
    """Validate optional recovery inputs and apply conservative defaults."""
    if raw is None:
        raw = {}
    if not isinstance(raw, dict):
        raise ValueError("recovery_parameters must be a JSON object")

    unknown = sorted(set(raw) - RECOVERY_PARAMETER_FIELDS)
    if unknown:
        raise ValueError(f"Unknown recovery_parameters fields: {unknown}")

    integer_fields = {
        "planned_worker_count",
        "planned_machine_count",
        "max_additional_workers",
        "available_backup_machines",
    }
    parsed: dict[str, int | float | None] = {}
    for field, value in raw.items():
        if value is None and field in {
            "planned_worker_count",
            "planned_machine_count",
            "expected_machine_repair_hours",
        }:
            parsed[field] = None
            continue
        parsed[field] = _number(value, field, integer=field in integer_fields)

    config: dict[str, int | float | None] = {
        "planned_worker_count": parsed.get("planned_worker_count"),
        "planned_machine_count": parsed.get("planned_machine_count"),
        "normal_shift_hours": parsed.get("normal_shift_hours", 8.0),
        "max_overtime_hours_per_day": parsed.get(
            "max_overtime_hours_per_day", 2.0
        ),
        "max_additional_workers": parsed.get(
            "max_additional_workers", worker_shortage_count
        ),
        "available_backup_machines": parsed.get(
            "available_backup_machines", 0
        ),
        "backup_line_daily_capacity": parsed.get(
            "backup_line_daily_capacity", 0.0
        ),
        "expected_machine_repair_hours": parsed.get(
            "expected_machine_repair_hours"
        ),
    }

    for field in (
        "normal_shift_hours",
        "planned_worker_count",
        "planned_machine_count",
    ):
        value = config[field]
        if value is not None and value <= 0:
            raise ValueError(f"recovery_parameters.{field} must be > 0")

    for field in (
        "max_overtime_hours_per_day",
        "max_additional_workers",
        "available_backup_machines",
        "backup_line_daily_capacity",
        "expected_machine_repair_hours",
    ):
        value = config[field]
        if value is not None and value < 0:
            raise ValueError(f"recovery_parameters.{field} must be >= 0")

    planned_workers = config["planned_worker_count"]
    if planned_workers is not None and planned_workers < worker_shortage_count:
        raise ValueError(
            "recovery_parameters.planned_worker_count cannot be less than "
            "worker_shortage_count"
        )

    planned_machines = config["planned_machine_count"]
    if planned_machines is not None and planned_machines < machine_breakdown_count:
        raise ValueError(
            "recovery_parameters.planned_machine_count cannot be less than "
            "machine_breakdown_count"
        )

    return config


def count_available_working_days(start: datetime, deadline: datetime) -> int:
    """Count Monday-Friday production days after ``start`` through deadline."""
    if deadline <= start:
        return 0
    current = start + timedelta(days=1)
    count = 0
    while current.date() <= deadline.date():
        if current.weekday() < 5:
            count += 1
        current += timedelta(days=1)
    return count


def _add_working_days(start: datetime, days: int) -> datetime:
    current = start
    added = 0
    while added < days:
        current += timedelta(days=1)
        if current.weekday() < 5:
            added += 1
    return current


def _rounded(value: float) -> float:
    return round(float(value), 2)


def _evaluate_option(
    *,
    option_id: str,
    title: str,
    rationale: str,
    capacity: float,
    current_capacity: float,
    remaining_qty: int,
    production_date: datetime,
    available_days: int,
    overtime_hours: float = 0.0,
    additional_workers: int = 0,
    repaired_machines: int = 0,
    backup_machines: int = 0,
    backup_line_capacity: float = 0.0,
    expected_machine_repair_hours: float = 0.0,
    required_days_override: int | None = None,
) -> dict[str, Any]:
    capacity = max(0.0, capacity)
    required_days = (
        required_days_override
        if required_days_override is not None
        else math.ceil(remaining_qty / capacity) if capacity > 0 else None
    )
    projected = (
        _add_working_days(production_date, required_days).strftime("%Y-%m-%d")
        if required_days is not None
        else None
    )
    margin = available_days - required_days if required_days is not None else None
    feasible = required_days is not None and required_days <= available_days

    return {
        "option_id": option_id,
        "title": title,
        "feasible_before_deadline": feasible,
        "daily_capacity": _rounded(capacity),
        "daily_capacity_gain": _rounded(capacity - current_capacity),
        "required_overtime_hours_per_day": _rounded(overtime_hours),
        "additional_workers": additional_workers,
        "repaired_machines": repaired_machines,
        "expected_machine_repair_hours": _rounded(
            expected_machine_repair_hours
        ),
        "backup_machines": backup_machines,
        "backup_line_daily_capacity_used": _rounded(backup_line_capacity),
        "required_working_days": required_days,
        "projected_completion_date": projected,
        "deadline_margin_working_days": margin,
        "rationale": rationale,
    }


def _required_days_with_delayed_gain(
    *,
    remaining_qty: int,
    base_capacity: float,
    delayed_daily_gain: float,
    delay_hours: float,
    shift_hours: float,
) -> int | None:
    """Estimate completion days when repaired capacity returns mid-shift.

    Repair starts on the next production day. During repair, the line retains
    its current base capacity. The restored machines contribute in proportion
    to the unused part of the shift in which the repair finishes.
    """
    final_capacity = base_capacity + delayed_daily_gain
    if final_capacity <= 0:
        return None

    quantity_left = float(remaining_qty)
    repair_hours_left = float(delay_hours)
    days = 0
    while quantity_left > 0:
        days += 1
        repair_hours_today = min(repair_hours_left, shift_hours)
        repair_hours_left -= repair_hours_today
        recovered_fraction = 1.0 - (repair_hours_today / shift_hours)
        day_capacity = base_capacity + delayed_daily_gain * recovered_fraction
        quantity_left -= day_capacity
    return days


def build_recovery_plan(
    data: dict[str, Any],
    *,
    detected_risk_type: str | None = None,
) -> dict[str, Any]:
    """Build ranked, explainable actions for an at-risk production order."""
    production_date = datetime.strptime(data["production_date"], "%Y-%m-%d")
    deadline = datetime.strptime(data["buyer_required_date"], "%Y-%m-%d")
    remaining_qty = max(
        0, int(data["full_order_qty"]) - int(data["cumulative_completed_qty"])
    )
    current_capacity = float(data["plant_daily_output"])
    daily_commitment = float(data["daily_commitment"])
    worker_shortage = int(data["worker_shortage_count"])
    machine_breakdown = int(data["machine_breakdown_count"])
    damage_exceeded = int(data["daily_damage_qty"]) > int(
        data["max_daily_damage_qty"]
    )

    config = normalize_recovery_parameters(
        data.get("recovery_parameters"),
        worker_shortage_count=worker_shortage,
        machine_breakdown_count=machine_breakdown,
    )
    available_days = count_available_working_days(production_date, deadline)

    triggers = []
    if worker_shortage:
        triggers.append("Worker Shortage")
    if machine_breakdown:
        triggers.append("Machine Breakdown")
    if damage_exceeded:
        triggers.append("Quality Limit Exceeded")
    if detected_risk_type and detected_risk_type not in {"No Issue", *triggers}:
        triggers.append(detected_risk_type)

    missing_parameters = []
    if worker_shortage and config["planned_worker_count"] is None:
        missing_parameters.append("planned_worker_count")
    if machine_breakdown and config["planned_machine_count"] is None:
        missing_parameters.append("planned_machine_count")
    if machine_breakdown and config["expected_machine_repair_hours"] is None:
        missing_parameters.append("expected_machine_repair_hours")

    required_daily_rate = (
        remaining_qty / available_days if available_days > 0 else None
    )
    recovery_gap = (
        max(0.0, required_daily_rate - current_capacity)
        if required_daily_rate is not None
        else None
    )

    if remaining_qty == 0:
        return {
            "engine_version": "v1-rules",
            "status": "completed",
            "triggered_by": triggers,
            "remaining_quantity": 0,
            "available_working_days": available_days,
            "required_daily_rate": 0.0,
            "current_daily_capacity": _rounded(current_capacity),
            "daily_recovery_gap": 0.0,
            "missing_parameters": missing_parameters,
            "recommended_option": None,
            "alternatives": [],
            "manual_escalation_required": False,
            "assumptions": _assumptions(),
        }

    if available_days == 0:
        return {
            "engine_version": "v1-rules",
            "status": "deadline_passed",
            "triggered_by": triggers,
            "remaining_quantity": remaining_qty,
            "available_working_days": 0,
            "required_daily_rate": None,
            "current_daily_capacity": _rounded(current_capacity),
            "daily_recovery_gap": None,
            "missing_parameters": missing_parameters,
            "recommended_option": {
                "option_id": "manual_escalation",
                "title": "Escalate and renegotiate or reallocate the order",
                "feasible_before_deadline": False,
                "external_daily_capacity_required": None,
                "rationale": "No future working day remains before the buyer deadline.",
            },
            "alternatives": [],
            "manual_escalation_required": True,
            "assumptions": _assumptions(),
        }

    options = []
    base = _evaluate_option(
        option_id="current_plan",
        title="Continue current production plan",
        rationale=(
            "Current sustainable output can complete the remaining quantity "
            "within the available working days."
            if current_capacity >= required_daily_rate
            else "Current sustainable output cannot meet the buyer deadline."
        ),
        capacity=current_capacity,
        current_capacity=current_capacity,
        remaining_qty=remaining_qty,
        production_date=production_date,
        available_days=available_days,
    )
    options.append(base)

    gap = recovery_gap or 0.0
    shift_hours = float(config["normal_shift_hours"])
    max_ot = float(config["max_overtime_hours_per_day"])

    if gap > 0 and current_capacity > 0 and max_ot > 0:
        hourly_output = current_capacity / shift_hours
        needed_ot = gap / hourly_output
        used_ot = min(needed_ot, max_ot)
        options.append(
            _evaluate_option(
                option_id="overtime",
                title="Add controlled daily overtime",
                rationale=(
                    f"Add {_rounded(used_ot)} overtime hour(s) per day; the "
                    f"configured limit is {_rounded(max_ot)} hour(s)."
                ),
                capacity=current_capacity + hourly_output * used_ot,
                current_capacity=current_capacity,
                remaining_qty=remaining_qty,
                production_date=production_date,
                available_days=available_days,
                overtime_hours=used_ot,
            )
        )

    planned_workers = config["planned_worker_count"]
    if gap > 0 and worker_shortage and planned_workers is not None:
        per_worker = daily_commitment / float(planned_workers)
        needed_workers = math.ceil(gap / per_worker)
        workers_used = min(
            needed_workers,
            worker_shortage,
            int(config["max_additional_workers"]),
        )
        if workers_used > 0:
            options.append(
                _evaluate_option(
                    option_id="add_workers",
                    title="Reassign or add operators",
                    rationale=(
                        f"Add {workers_used} operator(s); estimated recovery is "
                        f"{_rounded(per_worker)} pieces per operator per day."
                    ),
                    capacity=current_capacity + workers_used * per_worker,
                    current_capacity=current_capacity,
                    remaining_qty=remaining_qty,
                    production_date=production_date,
                    available_days=available_days,
                    additional_workers=workers_used,
                )
            )

    planned_machines = config["planned_machine_count"]
    per_machine = (
        daily_commitment / float(planned_machines)
        if planned_machines is not None
        else 0.0
    )
    repair_hours = config["expected_machine_repair_hours"]
    if (
        gap > 0
        and machine_breakdown
        and planned_machines is not None
        and repair_hours is not None
    ):
        needed_machines = math.ceil(gap / per_machine)
        repaired = min(needed_machines, machine_breakdown)
        if repaired > 0:
            repair_gain = repaired * per_machine
            repair_required_days = _required_days_with_delayed_gain(
                remaining_qty=remaining_qty,
                base_capacity=current_capacity,
                delayed_daily_gain=repair_gain,
                delay_hours=float(repair_hours),
                shift_hours=shift_hours,
            )
            options.append(
                _evaluate_option(
                    option_id="repair_machines",
                    title="Repair and restore failed machines",
                    rationale=(
                        f"Restore {repaired} machine(s) within "
                        f"{_rounded(float(repair_hours))} hour(s); estimated "
                        f"recovery is {_rounded(per_machine)} pieces per machine per day."
                    ),
                    capacity=current_capacity + repair_gain,
                    current_capacity=current_capacity,
                    remaining_qty=remaining_qty,
                    production_date=production_date,
                    available_days=available_days,
                    repaired_machines=repaired,
                    expected_machine_repair_hours=float(repair_hours),
                    required_days_override=repair_required_days,
                )
            )

    available_backups = int(config["available_backup_machines"])
    if gap > 0 and planned_machines is not None and available_backups > 0:
        needed_backups = math.ceil(gap / per_machine)
        backups_used = min(needed_backups, available_backups)
        options.append(
            _evaluate_option(
                option_id="backup_machines",
                title="Activate backup machines",
                rationale=(
                    f"Activate {backups_used} backup machine(s); estimated "
                    f"recovery is {_rounded(per_machine)} pieces per machine per day."
                ),
                capacity=current_capacity + backups_used * per_machine,
                current_capacity=current_capacity,
                remaining_qty=remaining_qty,
                production_date=production_date,
                available_days=available_days,
                backup_machines=backups_used,
            )
        )

    backup_line_capacity = float(config["backup_line_daily_capacity"])
    if gap > 0 and backup_line_capacity > 0:
        line_used = min(gap, backup_line_capacity)
        options.append(
            _evaluate_option(
                option_id="backup_line",
                title="Move part of the order to a backup line",
                rationale=(
                    f"Assign {_rounded(line_used)} pieces per day to the backup line."
                ),
                capacity=current_capacity + line_used,
                current_capacity=current_capacity,
                remaining_qty=remaining_qty,
                production_date=production_date,
                available_days=available_days,
                backup_line_capacity=line_used,
            )
        )

    combined = _build_combined_option(
        config=config,
        worker_shortage=worker_shortage,
        machine_breakdown=machine_breakdown,
        planned_workers=planned_workers,
        planned_machines=planned_machines,
        per_machine=per_machine,
        current_capacity=current_capacity,
        daily_commitment=daily_commitment,
        required_daily_rate=required_daily_rate,
        remaining_qty=remaining_qty,
        production_date=production_date,
        available_days=available_days,
    )
    if combined is not None:
        signature = (
            combined["additional_workers"],
            combined["repaired_machines"],
            combined["backup_machines"],
            combined["backup_line_daily_capacity_used"],
            combined["required_overtime_hours_per_day"],
        )
        single_signatures = {
            (
                option["additional_workers"],
                option["repaired_machines"],
                option["backup_machines"],
                option["backup_line_daily_capacity_used"],
                option["required_overtime_hours_per_day"],
            )
            for option in options
        }
        if signature not in single_signatures:
            options.append(combined)

    priority = {
        "current_plan": 0,
        "add_workers": 1,
        "repair_machines": 1,
        "backup_machines": 2,
        "overtime": 3,
        "backup_line": 4,
        "combined_recovery": 5,
    }
    feasible = [option for option in options if option["feasible_before_deadline"]]
    recommended = min(
        feasible,
        key=lambda option: (
            priority[option["option_id"]],
            option["daily_capacity_gain"],
        ),
    ) if feasible else None

    manual_escalation = recommended is None
    if manual_escalation:
        maximum_capacity = max(option["daily_capacity"] for option in options)
        recommended = {
            "option_id": "manual_escalation",
            "title": "Escalate and reallocate external capacity",
            "feasible_before_deadline": False,
            "external_daily_capacity_required": _rounded(
                max(0.0, required_daily_rate - maximum_capacity)
            ),
            "rationale": (
                "Configured internal recovery limits are insufficient. Reallocate "
                "the remaining daily capacity to another line or plant, or agree "
                "a revised buyer deadline."
            ),
        }

    alternatives = [
        option for option in options if option["option_id"] != recommended["option_id"]
    ]
    return {
        "engine_version": "v1-rules",
        "status": "on_track" if base["feasible_before_deadline"] else "recovery_required",
        "triggered_by": triggers,
        "remaining_quantity": remaining_qty,
        "available_working_days": available_days,
        "required_daily_rate": _rounded(required_daily_rate),
        "current_daily_capacity": _rounded(current_capacity),
        "daily_recovery_gap": _rounded(gap),
        "missing_parameters": missing_parameters,
        "recommended_option": recommended,
        "alternatives": alternatives,
        "manual_escalation_required": manual_escalation,
        "assumptions": _assumptions(),
    }


def _build_combined_option(
    *,
    config: dict[str, int | float | None],
    worker_shortage: int,
    machine_breakdown: int,
    planned_workers: int | float | None,
    planned_machines: int | float | None,
    per_machine: float,
    current_capacity: float,
    daily_commitment: float,
    required_daily_rate: float,
    remaining_qty: int,
    production_date: datetime,
    available_days: int,
) -> dict[str, Any] | None:
    """Use configured internal resources in priority order, then limited OT."""
    capacity = current_capacity
    workers_used = 0
    repaired = 0
    backups_used = 0
    line_used = 0.0
    overtime_used = 0.0

    if capacity < required_daily_rate and worker_shortage and planned_workers:
        per_worker = daily_commitment / float(planned_workers)
        workers_needed = math.ceil((required_daily_rate - capacity) / per_worker)
        workers_used = min(
            workers_needed,
            worker_shortage,
            int(config["max_additional_workers"]),
        )
        capacity += workers_used * per_worker

    if (
        capacity < required_daily_rate
        and machine_breakdown
        and planned_machines
        and config["expected_machine_repair_hours"] is not None
    ):
        machines_needed = math.ceil((required_daily_rate - capacity) / per_machine)
        repaired = min(machines_needed, machine_breakdown)
        capacity += repaired * per_machine

    if capacity < required_daily_rate and planned_machines:
        machines_needed = math.ceil((required_daily_rate - capacity) / per_machine)
        backups_used = min(
            machines_needed, int(config["available_backup_machines"])
        )
        capacity += backups_used * per_machine

    if capacity < required_daily_rate:
        line_used = min(
            required_daily_rate - capacity,
            float(config["backup_line_daily_capacity"]),
        )
        capacity += line_used

    if capacity < required_daily_rate and current_capacity > 0:
        hourly_output = current_capacity / float(config["normal_shift_hours"])
        overtime_used = min(
            (required_daily_rate - capacity) / hourly_output,
            float(config["max_overtime_hours_per_day"]),
        )
        capacity += overtime_used * hourly_output

    used_action_count = sum(
        value > 0
        for value in (workers_used, repaired, backups_used, line_used, overtime_used)
    )
    if used_action_count < 2:
        return None

    return _evaluate_option(
        option_id="combined_recovery",
        title="Use a combined recovery plan",
        rationale=(
            "Combine available internal resources in this order: operators, "
            "machine repair, backup machines, backup line capacity, then overtime."
        ),
        capacity=capacity,
        current_capacity=current_capacity,
        remaining_qty=remaining_qty,
        production_date=production_date,
        available_days=available_days,
        overtime_hours=overtime_used,
        additional_workers=workers_used,
        repaired_machines=repaired,
        backup_machines=backups_used,
        backup_line_capacity=line_used,
        expected_machine_repair_hours=(
            float(config["expected_machine_repair_hours"])
            if repaired and config["expected_machine_repair_hours"] is not None
            else 0.0
        ),
        required_days_override=(
            _required_days_with_delayed_gain(
                remaining_qty=remaining_qty,
                base_capacity=capacity - repaired * per_machine,
                delayed_daily_gain=repaired * per_machine,
                delay_hours=float(config["expected_machine_repair_hours"]),
                shift_hours=float(config["normal_shift_hours"]),
            )
            if repaired and config["expected_machine_repair_hours"] is not None
            else None
        ),
    )


def _assumptions() -> list[str]:
    return [
        "Production runs Monday to Friday; public and factory holidays are not included.",
        "The production_date output is already included in cumulative_completed_qty.",
        "Current plant_daily_output is treated as sustainable daily good output.",
        "Worker and machine capacity gains are linear estimates based on daily_commitment.",
    ]
