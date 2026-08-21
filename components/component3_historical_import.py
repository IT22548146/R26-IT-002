"""Safe retrospective import preparation for Component 3 monitoring."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

import pandas as pd

from components.component3_historical_validation import (
    load_historical_workbook,
)


IMPORT_VERSION = "component3-historical-import-v1"

PREDICTION_FIELDS = (
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

INTEGER_FIELDS = {
    "full_order_qty",
    "total_working_days",
    "cutting_days",
    "sewing_days",
    "daily_commitment",
    "working_day_no",
    "plant_daily_output",
    "daily_damage_qty",
    "max_daily_damage_qty",
    "machine_breakdown_count",
    "worker_shortage_count",
    "cumulative_completed_qty",
}

DATE_FIELDS = {
    "bulk_order_approved_date",
    "buyer_required_date",
    "production_date",
}

MASTER_FIELD_MAP = (
    ("Style_ID", "Style_ID", "style_id"),
    ("Buyer_Name", "Buyer_Name", "buyer_name"),
    ("Bulk_Order_Quantity", "Full_Order_Qty", "full_order_qty"),
    (
        "Bulk_Order_Approved_Date",
        "Bulk_Order_Approved_Date",
        "bulk_order_approved_date",
    ),
    ("Buyer_Required_Date", "Buyer_Required_Date", "buyer_required_date"),
    ("Cutting_Days", "Cutting_Days", "cutting_days"),
    ("Sewing_Days", "Sewing_Days", "sewing_days"),
    ("Daily_Commitment", "Daily_Commitment", "daily_commitment"),
    (
        "Allocated_Bulk_Plant",
        "Allocated_Bulk_Plant",
        "allocated_bulk_plant",
    ),
    (
        "Allocated_Bulk_Plant_Location",
        "Plant_Location",
        "plant_location",
    ),
)

RISK_TYPE_TO_ACTUAL = {
    "Worker Issue": "Worker Shortage",
    "Machine Breakdown Issue": "Machine Breakdown",
    "Quality Issue": "Quality Issue",
    "Working Hours Issue": "Output / Schedule Risk",
    "Commitment Too Low": "Output / Schedule Risk",
    "Minor Delay": "Output / Schedule Risk",
    "Production Failure": "Output / Schedule Risk",
}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _date(value: Any) -> str:
    parsed = pd.to_datetime(value, errors="raise")
    return parsed.strftime("%Y-%m-%d")


def _display(value: Any) -> str | int | float | None:
    if pd.isna(value):
        return None
    if isinstance(value, pd.Timestamp):
        return value.strftime("%Y-%m-%d")
    if hasattr(value, "item"):
        value = value.item()
    if isinstance(value, (str, int, float)):
        return value
    return str(value)


def historical_row_to_prediction_input(row: dict[str, Any]) -> dict[str, Any]:
    """Convert one canonical workbook row to the live API input contract."""
    return {
        "bulk_order_id": str(row["Bulk_Order_ID"]).strip(),
        "style_id": str(row["Style_ID"]).strip(),
        "buyer_name": str(row["Buyer_Name"]).strip(),
        "allocated_bulk_plant": str(row["Allocated_Bulk_Plant"]).strip(),
        "plant_location": str(row["Plant_Location"]).strip(),
        "full_order_qty": int(row["Full_Order_Qty"]),
        "bulk_order_approved_date": _date(row["Bulk_Order_Approved_Date"]),
        "buyer_required_date": _date(row["Buyer_Required_Date"]),
        "total_working_days": int(row["Total_Working_Days"]),
        "cutting_days": int(row["Cutting_Days"]),
        "sewing_days": int(row["Sewing_Days"]),
        "daily_commitment": int(row["Daily_Commitment"]),
        "production_date": _date(row["Production_Date"]),
        "working_day_no": int(row["Working_Day_No"]),
        "plant_daily_output": int(row["Plant_Daily_Output"]),
        "daily_damage_qty": int(row["Daily_Damage_Qty"]),
        "max_daily_damage_qty": int(row["Max_Daily_Damage_Qty"]),
        "machine_breakdown_count": int(row["Machine_Breakdown_Count"]),
        "worker_shortage_count": int(row["Worker_Shortage_Count"]),
        "cumulative_completed_qty": int(row["Cumulative_Completed_Qty"]),
        "recovery_parameters": {},
    }


def historical_actual_outcome(
    row: dict[str, Any],
) -> tuple[bool, str | None]:
    """Map a recorded historical event to the monitoring verification types."""
    risk_type = str(row.get("Risk_Type", "No Issue")).strip()
    mapped_type = RISK_TYPE_TO_ACTUAL.get(risk_type)
    if mapped_type:
        return True, mapped_type
    if int(row.get("Machine_Breakdown_Count", 0)) > 0:
        return True, "Machine Breakdown"
    if int(row.get("Worker_Shortage_Count", 0)) > 0:
        return True, "Worker Shortage"
    if int(row.get("Daily_Damage_Qty", 0)) > int(
        row.get("Max_Daily_Damage_Qty", 0)
    ):
        return True, "Quality Issue"
    if risk_type != "No Issue":
        return True, "Other Emergency"
    return False, None


def _comparison_value(value: Any, field: str) -> Any:
    if value is None or pd.isna(value):
        return None
    if field in DATE_FIELDS:
        return _date(value)
    if field in INTEGER_FIELDS:
        return int(value)
    return str(value).strip().casefold()


def prediction_inputs_match(
    first: dict[str, Any],
    second: dict[str, Any],
) -> bool:
    """Compare only the canonical monitoring fields, not recovery defaults."""
    return all(
        _comparison_value(first.get(field), field)
        == _comparison_value(second.get(field), field)
        for field in PREDICTION_FIELDS
    )


def _load_sources(
    component3_path: str | Path,
    component2_path: str | Path,
) -> tuple[pd.DataFrame, dict[str, Any], pd.DataFrame, Path, Path]:
    daily_path = Path(component3_path)
    master_path = Path(component2_path)
    daily, daily_audit = load_historical_workbook(daily_path)
    if not master_path.is_file():
        raise FileNotFoundError(
            f"Component 2 master workbook not found: {master_path}"
        )
    master = pd.read_excel(
        master_path,
        sheet_name="Component2_Bulk_400",
    )
    if "Bulk_Order_ID" not in master.columns:
        raise ValueError("Component 2 master has no Bulk_Order_ID column")
    return daily, daily_audit, master, daily_path, master_path


def _master_comparison(
    daily_first: dict[str, Any],
    master_rows: pd.DataFrame,
) -> dict[str, Any]:
    if master_rows.empty:
        return {
            "status": "not_found",
            "matching_fields": [],
            "conflicting_fields": [],
        }
    if len(master_rows) > 1:
        return {
            "status": "ambiguous",
            "matching_fields": [],
            "conflicting_fields": [],
            "matching_master_rows": int(len(master_rows)),
        }

    master = master_rows.iloc[0].to_dict()
    matching: list[str] = []
    conflicts: list[dict[str, Any]] = []
    for master_field, daily_field, api_field in MASTER_FIELD_MAP:
        master_value = master.get(master_field)
        daily_value = daily_first.get(daily_field)
        if _comparison_value(master_value, api_field) == _comparison_value(
            daily_value,
            api_field,
        ):
            matching.append(api_field)
        else:
            conflicts.append(
                {
                    "field": api_field,
                    "component2_value": _display(master_value),
                    "component3_value": _display(daily_value),
                }
            )
    return {
        "status": "matched_with_conflicts" if conflicts else "matched",
        "matching_fields": matching,
        "conflicting_fields": conflicts,
    }


def load_historical_order(
    component3_path: str | Path,
    component2_path: str | Path,
    bulk_order_id: str,
) -> list[dict[str, Any]]:
    """Return one source order in strict production-day order."""
    daily, _, _, _, _ = _load_sources(component3_path, component2_path)
    selected = daily.loc[
        daily["Bulk_Order_ID"].astype(str).eq(str(bulk_order_id))
    ].sort_values(["Working_Day_No", "Production_Date"])
    if selected.empty:
        raise ValueError(
            f"Historical bulk order {bulk_order_id!r} was not found"
        )
    records: list[dict[str, Any]] = []
    for source_row in selected.to_dict(orient="records"):
        actual_emergency, actual_type = historical_actual_outcome(source_row)
        records.append(
            {
                "prediction_input": historical_row_to_prediction_input(
                    source_row
                ),
                "source_risk_type": str(source_row["Risk_Type"]).strip(),
                "actual_emergency": actual_emergency,
                "actual_emergency_type": actual_type,
            }
        )
    return records


def build_historical_import_preview(
    component3_path: str | Path,
    component2_path: str | Path,
    existing_records: list[dict[str, Any]],
) -> dict[str, Any]:
    """Audit source joins and report exactly what a later import would do."""
    daily, audit, master, daily_path, master_path = _load_sources(
        component3_path,
        component2_path,
    )
    existing_by_order: dict[str, list[dict[str, Any]]] = {}
    for record in existing_records:
        existing_by_order.setdefault(str(record["bulk_order_id"]), []).append(
            record
        )

    orders: list[dict[str, Any]] = []
    total_importable = 0
    total_existing_matching = 0
    total_existing_conflicts = 0
    component2_matches = 0
    for order_id, order_rows in daily.groupby("Bulk_Order_ID", sort=True):
        ordered = order_rows.sort_values(
            ["Working_Day_No", "Production_Date"]
        )
        first = ordered.iloc[0].to_dict()
        master_rows = master.loc[
            master["Bulk_Order_ID"].astype(str).eq(str(order_id))
        ]
        comparison = _master_comparison(first, master_rows)
        if comparison["status"].startswith("matched"):
            component2_matches += 1

        existing_order = existing_by_order.get(str(order_id), [])
        by_day = {
            int(record["working_day_no"]): record for record in existing_order
        }
        by_date = {
            str(record["production_date"]): record for record in existing_order
        }
        importable = 0
        existing_matching = 0
        existing_conflicts = 0
        emergency_days = 0
        for source_row in ordered.to_dict(orient="records"):
            payload = historical_row_to_prediction_input(source_row)
            actual_emergency, _ = historical_actual_outcome(source_row)
            emergency_days += int(actual_emergency)
            existing = by_day.get(payload["working_day_no"]) or by_date.get(
                payload["production_date"]
            )
            if existing is None:
                importable += 1
            elif prediction_inputs_match(
                payload,
                existing["prediction_input"],
            ):
                existing_matching += 1
            else:
                existing_conflicts += 1

        total_importable += importable
        total_existing_matching += existing_matching
        total_existing_conflicts += existing_conflicts
        orders.append(
            {
                "bulk_order_id": str(order_id),
                "style_id": str(first["Style_ID"]),
                "source_rows": int(len(ordered)),
                "production_date_from": _date(ordered["Production_Date"].min()),
                "production_date_to": _date(ordered["Production_Date"].max()),
                "recorded_emergency_days": emergency_days,
                "importable_rows": importable,
                "existing_matching_rows": existing_matching,
                "existing_conflicting_rows": existing_conflicts,
                "component2_master": comparison,
            }
        )

    return {
        "import_version": IMPORT_VERSION,
        "status": "preview",
        "mode": "retrospective_demo",
        "independent_validation": False,
        "production_approved": False,
        "sources": {
            "component3_daily": {
                "filename": daily_path.name,
                "sha256": _sha256(daily_path),
                "rows": int(audit["historical_rows_used"]),
                "orders": int(audit["bulk_orders"]),
                "generated_or_augmented_rows_excluded": int(
                    audit["generated_or_augmented_rows_excluded"]
                ),
                "already_used_for_model_training": True,
            },
            "component2_master": {
                "filename": master_path.name,
                "sha256": _sha256(master_path),
                "rows": int(len(master)),
                "matched_component3_orders": component2_matches,
                "authority": "audit_only",
            },
        },
        "summary": {
            "source_rows": int(len(daily)),
            "source_orders": int(daily["Bulk_Order_ID"].nunique()),
            "importable_rows": total_importable,
            "existing_matching_rows": total_existing_matching,
            "existing_conflicting_rows": total_existing_conflicts,
        },
        "orders": orders,
        "confirmation_required": {
            "confirm_retrospective_training_data_reuse": True,
            "confirm_historical_outcomes_are_actual": (
                "Required only when automatic verification is requested"
            ),
        },
        "rules": [
            "Component 3 daily values remain authoritative.",
            "Component 2 is used only to audit stable order fields.",
            "Existing matching records are not duplicated.",
            "Existing conflicting records are never overwritten.",
            "Predictions are created before the source outcome is verified.",
        ],
        "limitations": [
            "The Component 3 source was used to train the current artifacts.",
            "Imported results demonstrate retrospective workflow only.",
            "They must not be reported as new independent model validation.",
        ],
    }
