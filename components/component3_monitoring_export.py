"""Operational CSV export for plant-scoped Component 3 monitoring history."""

from __future__ import annotations

import csv
from collections.abc import Iterable
from io import StringIO
from typing import Any

MONITORING_EXPORT_COLUMNS = (
    "record_id",
    "bulk_order_id",
    "plant_key",
    "style_id",
    "buyer_name",
    "allocated_bulk_plant",
    "plant_location",
    "production_date",
    "working_day_no",
    "risk_status",
    "risk_type",
    "severity",
    "plant_daily_output",
    "daily_commitment",
    "daily_damage_qty",
    "max_daily_damage_qty",
    "machine_breakdown_count",
    "worker_shortage_count",
    "cumulative_completed_qty",
    "actual_outcome_status",
    "actual_emergency",
    "actual_emergency_type",
    "label_status",
    "recorded_by",
    "created_at",
)


def _safe_csv_value(value: Any) -> Any:
    if value is None:
        return ""
    if isinstance(value, bool):
        return str(value).lower()
    if isinstance(value, str) and value.startswith(("=", "+", "-", "@")):
        return f"'{value}"
    return value


def monitoring_records_to_csv_bytes(records: Iterable[dict[str, Any]]) -> bytes:
    """Render stable columns and neutralize spreadsheet formula prefixes."""
    output = StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=MONITORING_EXPORT_COLUMNS)
    writer.writeheader()
    for record in records:
        writer.writerow(
            {
                column: _safe_csv_value(record.get(column))
                for column in MONITORING_EXPORT_COLUMNS
            }
        )
    return output.getvalue().encode("utf-8-sig")
