"""Input normalization and validation for Component 3 predictions."""

import math
from datetime import datetime

from components.component3_recovery import normalize_recovery_parameters

PREDICTION_REQUIRED_FIELDS = (
    "bulk_order_id",
    "style_id",
    "buyer_name",
    "allocated_bulk_plant",
    "plant_location",
    "full_order_qty",
    "bulk_order_approved_date",
    "buyer_required_date",
    "total_working_days",
    "cutting_days",
    "sewing_days",
    "daily_commitment",
    "production_date",
    "working_day_no",
    "plant_daily_output",
    "daily_damage_qty",
    "max_daily_damage_qty",
    "machine_breakdown_count",
    "worker_shortage_count",
    "cumulative_completed_qty",
)

PREDICTION_INTEGER_FIELDS = (
    "full_order_qty",
    "daily_commitment",
    "plant_daily_output",
    "daily_damage_qty",
    "max_daily_damage_qty",
    "machine_breakdown_count",
    "worker_shortage_count",
    "cumulative_completed_qty",
    "working_day_no",
    "total_working_days",
    "cutting_days",
    "sewing_days",
)

PREDICTION_TEXT_FIELDS = (
    "bulk_order_id",
    "style_id",
    "buyer_name",
    "allocated_bulk_plant",
    "plant_location",
)


def _normalize_integer(value: object, field: str) -> int:
    """Accept real integer values without silently truncating decimals."""
    if isinstance(value, bool):
        raise ValueError(f"{field} must be an integer")
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        if not math.isfinite(value) or not value.is_integer():
            raise ValueError(f"{field} must be an integer")
        return int(value)
    if isinstance(value, str):
        normalized = value.strip()
        if not normalized or not normalized.lstrip("+-").isdigit():
            raise ValueError(f"{field} must be an integer")
        return int(normalized)
    raise ValueError(f"{field} must be an integer")


def _normalize_text(value: object, field: str, *, maximum_length: int = 200) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a non-empty string")
    normalized = value.strip()
    if len(normalized) > maximum_length:
        raise ValueError(f"{field} must be {maximum_length} characters or fewer")
    return normalized


def validate_prediction_payload(raw_data: object) -> dict:
    """Return a normalized prediction payload or raise a user-facing error."""
    if not isinstance(raw_data, dict) or not raw_data:
        raise ValueError("Request body must be valid JSON")

    data = dict(raw_data)
    missing = [field for field in PREDICTION_REQUIRED_FIELDS if field not in data]
    if missing:
        raise ValueError(f"Missing required fields: {missing}")

    try:
        for field in PREDICTION_TEXT_FIELDS:
            data[field] = _normalize_text(data[field], field)
        for field in PREDICTION_INTEGER_FIELDS:
            data[field] = _normalize_integer(data[field], field)
        production_date = datetime.strptime(data["production_date"], "%Y-%m-%d").date()
        buyer_required_date = datetime.strptime(data["buyer_required_date"], "%Y-%m-%d").date()
        bulk_order_approved_date = datetime.strptime(
            data["bulk_order_approved_date"], "%Y-%m-%d"
        ).date()
    except (ValueError, TypeError) as error:
        raise ValueError(f"Invalid field value: {error}") from error

    if data["daily_commitment"] <= 0:
        raise ValueError("daily_commitment must be > 0")
    if data["full_order_qty"] <= 0:
        raise ValueError("full_order_qty must be > 0")
    if data["total_working_days"] <= 0:
        raise ValueError("total_working_days must be > 0")
    if buyer_required_date < bulk_order_approved_date:
        raise ValueError("buyer_required_date cannot be before bulk_order_approved_date")
    if not bulk_order_approved_date <= production_date <= buyer_required_date:
        raise ValueError(
            "production_date must be between bulk_order_approved_date and buyer_required_date"
        )
    if production_date.weekday() >= 5:
        raise ValueError("production_date must be a Monday-Friday working day")
    if data["cumulative_completed_qty"] > data["full_order_qty"]:
        raise ValueError("cumulative_completed_qty cannot exceed full_order_qty")
    if data["daily_damage_qty"] > data["plant_daily_output"]:
        raise ValueError("daily_damage_qty cannot exceed plant_daily_output")
    if data["plant_daily_output"] > data["cumulative_completed_qty"]:
        raise ValueError("plant_daily_output cannot exceed cumulative_completed_qty")

    non_negative_fields = (
        "plant_daily_output",
        "daily_damage_qty",
        "max_daily_damage_qty",
        "machine_breakdown_count",
        "worker_shortage_count",
        "cumulative_completed_qty",
        "cutting_days",
        "sewing_days",
    )
    negative_fields = [field for field in non_negative_fields if data[field] < 0]
    if negative_fields:
        raise ValueError(f"Fields must be >= 0: {negative_fields}")

    for phase_field in ("cutting_days", "sewing_days"):
        if data[phase_field] > data["total_working_days"]:
            raise ValueError(f"{phase_field} cannot exceed total_working_days")

    if not (1 <= data["working_day_no"] <= data["total_working_days"]):
        raise ValueError("working_day_no must be between 1 and total_working_days")

    try:
        data["recovery_parameters"] = normalize_recovery_parameters(
            data.get("recovery_parameters"),
            worker_shortage_count=data["worker_shortage_count"],
            machine_breakdown_count=data["machine_breakdown_count"],
        )
    except ValueError as error:
        raise ValueError(f"Invalid field value: {error}") from error

    return data
