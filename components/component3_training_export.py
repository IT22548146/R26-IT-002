"""Verified, leakage-safe training export for Component 3 early warning."""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from io import BytesIO
from typing import Any

import pandas as pd

from components.component3_early_warning_data import (
    CURRENT_FEATURES,
    EARLY_WARNING_FEATURES,
    EXCLUDED_FROM_MODEL_FEATURES,
    MIN_ORDERS_PER_CLASS,
    MIN_ROWS_PER_CLASS,
    TARGET_COLUMNS,
)
from components.component3_features import build_feature_values
from components.component3_tracking import utc_now


EXPORT_VERSION = "component3-verified-training-export-v1"
METADATA_COLUMNS = [
    "Record_ID",
    "Bulk_Order_ID",
    "Style_ID",
    "Production_Date",
]
EXPORT_COLUMNS = METADATA_COLUMNS + EARLY_WARNING_FEATURES + TARGET_COLUMNS
IDENTITY_COLUMNS = {
    "Record_ID",
    "Bulk_Order_ID",
    "Style_ID",
    "Buyer_Name",
    "Allocated_Bulk_Plant",
    "Plant_Location",
    "Production_Date",
    "Buyer_Required_Date",
}


def _current_features(prediction_input: dict[str, Any]) -> dict[str, int | float]:
    return build_feature_values(
        daily_commitment=int(prediction_input["daily_commitment"]),
        plant_daily_output=int(prediction_input["plant_daily_output"]),
        machine_breakdown_count=int(
            prediction_input["machine_breakdown_count"]
        ),
        worker_shortage_count=int(prediction_input["worker_shortage_count"]),
        daily_damage_qty=int(prediction_input["daily_damage_qty"]),
        max_daily_damage_qty=int(prediction_input["max_daily_damage_qty"]),
        working_day_no=int(prediction_input["working_day_no"]),
        total_working_days=int(prediction_input["total_working_days"]),
        cutting_days=int(prediction_input["cutting_days"]),
        sewing_days=int(prediction_input["sewing_days"]),
        full_order_qty=int(prediction_input["full_order_qty"]),
        cumulative_completed_qty=int(
            prediction_input["cumulative_completed_qty"]
        ),
    )


def _days_since_last_actual_emergency(history: list[dict[str, Any]]) -> int:
    earlier = history[:-1]
    emergency_positions = [
        position
        for position, record in enumerate(earlier)
        if bool(record["actual_emergency"])
    ]
    if not emergency_positions:
        return len(history)
    return (len(history) - 1) - emergency_positions[-1]


def _trailing_features(
    history: list[dict[str, Any]],
) -> dict[str, int | float]:
    trailing = history[-3:]
    current_input = history[-1]["prediction_input"]
    previous_input = (
        history[-2]["prediction_input"] if len(history) > 1 else current_input
    )
    outputs = pd.Series(
        [
            float(record["prediction_input"]["plant_daily_output"])
            for record in trailing
        ],
        dtype="float64",
    )
    gaps = pd.Series(
        [
            float(_current_features(record["prediction_input"])["Gap_Pct"])
            for record in trailing
        ],
        dtype="float64",
    )

    return {
        "History_Days_Available": len(trailing),
        "Previous_Day_Output": float(previous_input["plant_daily_output"]),
        "Output_Change_From_Previous": float(
            current_input["plant_daily_output"]
            - previous_input["plant_daily_output"]
        ),
        "Trailing_3D_Avg_Output": round(float(outputs.mean()), 4),
        "Trailing_3D_Output_Std": round(float(outputs.std(ddof=0)), 4),
        "Trailing_3D_Avg_Gap_Pct": round(float(gaps.mean()), 4),
        "Trailing_3D_Emergency_Days": sum(
            bool(record["actual_emergency"]) for record in trailing
        ),
        "Trailing_3D_Worker_Shortage_Days": sum(
            int(record["prediction_input"]["worker_shortage_count"]) > 0
            for record in trailing
        ),
        "Trailing_3D_Machine_Breakdown_Days": sum(
            int(record["prediction_input"]["machine_breakdown_count"]) > 0
            for record in trailing
        ),
        "Trailing_3D_Quality_Limit_Days": sum(
            int(record["prediction_input"]["daily_damage_qty"])
            > int(record["prediction_input"]["max_daily_damage_qty"])
            for record in trailing
        ),
        "Days_Since_Last_Emergency": _days_since_last_actual_emergency(
            history
        ),
    }


def _targets(record: dict[str, Any]) -> dict[str, Any]:
    values = {
        "Emergency_Within_1_Day": record["emergency_within_1_day"],
        "Emergency_Within_3_Days": record["emergency_within_3_days"],
        "First_Emergency_Type_Within_3_Days": record[
            "first_emergency_type_within_3_days"
        ],
        "First_Emergency_Lead_Days": record["first_emergency_lead_days"],
        "Worker_Shortage_Within_3_Days": record[
            "worker_shortage_within_3_days"
        ],
        "Machine_Breakdown_Within_3_Days": record[
            "machine_breakdown_within_3_days"
        ],
        "Quality_Limit_Within_3_Days": record[
            "quality_limit_within_3_days"
        ],
        "Output_Schedule_Risk_Within_3_Days": record[
            "output_schedule_risk_within_3_days"
        ],
    }
    required = [
        column
        for column in TARGET_COLUMNS
        if column != "First_Emergency_Lead_Days" and values[column] is None
    ]
    if required:
        raise ValueError(f"Ready record has missing targets: {required}")
    return values


def _binary_balance(dataset: pd.DataFrame, target: str) -> dict[str, Any]:
    if dataset.empty:
        positive_rows = 0
        negative_rows = 0
        positive_orders = 0
        negative_orders = 0
    else:
        positive = dataset[target].eq(1)
        negative = dataset[target].eq(0)
        positive_rows = int(positive.sum())
        negative_rows = int(negative.sum())
        positive_orders = int(dataset.loc[positive, "Bulk_Order_ID"].nunique())
        negative_orders = int(dataset.loc[negative, "Bulk_Order_ID"].nunique())
    rows_sufficient = min(positive_rows, negative_rows) >= MIN_ROWS_PER_CLASS
    orders_sufficient = (
        min(positive_orders, negative_orders) >= MIN_ORDERS_PER_CLASS
    )
    return {
        "positive_rows": positive_rows,
        "negative_rows": negative_rows,
        "positive_rate": (
            round(positive_rows / len(dataset), 4) if len(dataset) else None
        ),
        "positive_orders": positive_orders,
        "negative_orders": negative_orders,
        "minimum_rows_per_class_required": MIN_ROWS_PER_CLASS,
        "minimum_orders_per_class_required": MIN_ORDERS_PER_CLASS,
        "row_balance_sufficient": rows_sufficient,
        "group_coverage_sufficient": orders_sufficient,
        "ready_for_grouped_modeling": rows_sufficient and orders_sufficient,
    }


def _sequence_quality(
    records_by_order: dict[str, list[dict[str, Any]]],
) -> dict[str, Any]:
    transitions_with_gaps = 0
    orders_with_gaps: list[str] = []
    for order_id, records in records_by_order.items():
        days = [int(record["working_day_no"]) for record in records]
        order_gaps = sum(
            current - previous != 1
            for previous, current in zip(days, days[1:])
        )
        if order_gaps:
            transitions_with_gaps += order_gaps
            orders_with_gaps.append(order_id)
    return {
        "working_day_gap_transitions": transitions_with_gaps,
        "orders_with_working_day_gaps": sorted(orders_with_gaps),
        "passed": transitions_with_gaps == 0,
    }


def dataframe_to_csv_bytes(dataset: pd.DataFrame) -> bytes:
    return dataset.to_csv(index=False, lineterminator="\n").encode("utf-8")


def _flatten_audit(value: Any, prefix: str = "") -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    if isinstance(value, dict):
        for key, item in value.items():
            path = f"{prefix}.{key}" if prefix else str(key)
            rows.extend(_flatten_audit(item, path))
    elif isinstance(value, list):
        rows.append({"Audit_Field": prefix, "Value": json.dumps(value)})
    else:
        rows.append({"Audit_Field": prefix, "Value": str(value)})
    return rows


def dataframe_to_xlsx_bytes(
    dataset: pd.DataFrame,
    audit: dict[str, Any],
) -> bytes:
    output = BytesIO()
    manifest = pd.DataFrame(
        [
            {
                "Column": column,
                "Role": (
                    "grouping_or_audit_metadata"
                    if column in METADATA_COLUMNS
                    else "model_feature"
                    if column in EARLY_WARNING_FEATURES
                    else "future_target"
                ),
            }
            for column in EXPORT_COLUMNS
        ]
    )
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        dataset.to_excel(writer, sheet_name="training_data", index=False)
        pd.DataFrame(_flatten_audit(audit)).to_excel(
            writer,
            sheet_name="audit_summary",
            index=False,
        )
        manifest.to_excel(writer, sheet_name="column_manifest", index=False)
    return output.getvalue()


def build_verified_training_dataset(
    snapshot: list[dict[str, Any]],
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Build source-day features and verified future targets from monitoring."""
    records_by_order: dict[str, list[dict[str, Any]]] = {}
    for record in snapshot:
        records_by_order.setdefault(str(record["bulk_order_id"]), []).append(
            record
        )
    for records in records_by_order.values():
        records.sort(
            key=lambda item: (
                int(item["working_day_no"]),
                str(item["production_date"]),
            )
        )

    exported: list[dict[str, Any]] = []
    exclusion_counts: Counter[str] = Counter()
    invalid_record_ids: list[str] = []
    for order_records in records_by_order.values():
        for position, record in enumerate(order_records):
            if not record.get("independent_validation_eligible", True):
                exclusion_counts["retrospective_training_reuse"] += 1
                continue
            if record["label_status"] != "Ready":
                exclusion_counts["label_not_ready"] += 1
                continue
            if record["actual_outcome_status"] != "Verified":
                exclusion_counts["source_not_verified"] += 1
                continue
            if bool(record["actual_emergency"]):
                exclusion_counts["source_actual_emergency"] += 1
                continue

            source_history = order_records[: position + 1]
            if any(
                not item.get("independent_validation_eligible", True)
                for item in source_history
            ):
                exclusion_counts["retrospective_prior_history"] += 1
                continue
            if any(
                item["actual_outcome_status"] != "Verified"
                for item in source_history
            ):
                exclusion_counts["unverified_prior_history"] += 1
                continue

            try:
                prediction_input = record["prediction_input"]
                current = _current_features(prediction_input)
                export_record: dict[str, Any] = {
                    "Record_ID": record["record_id"],
                    "Bulk_Order_ID": record["bulk_order_id"],
                    "Style_ID": record["style_id"],
                    "Production_Date": record["production_date"],
                }
                export_record.update(
                    {feature: current[feature] for feature in CURRENT_FEATURES}
                )
                export_record.update(_trailing_features(source_history))
                export_record.update(_targets(record))
                exported.append(export_record)
            except (KeyError, TypeError, ValueError):
                exclusion_counts["invalid_feature_or_target"] += 1
                invalid_record_ids.append(str(record["record_id"]))

    dataset = pd.DataFrame.from_records(exported, columns=EXPORT_COLUMNS)
    csv_bytes = dataframe_to_csv_bytes(dataset)
    target_overlap = sorted(set(EARLY_WARNING_FEATURES) & set(TARGET_COLUMNS))
    identity_overlap = sorted(set(EARLY_WARNING_FEATURES) & IDENTITY_COLUMNS)
    leakage_passed = not target_overlap and not identity_overlap
    primary_balance = _binary_balance(dataset, "Emergency_Within_3_Days")
    exported_record_ids = {
        str(record_id) for record_id in dataset["Record_ID"].tolist()
    }
    exported_sequences: dict[str, list[dict[str, Any]]] = {}
    for order_id, records in records_by_order.items():
        exported_positions = [
            position
            for position, record in enumerate(records)
            if str(record["record_id"]) in exported_record_ids
        ]
        if exported_positions:
            exported_sequences[order_id] = records[
                : max(exported_positions) + 1
            ]
    sequence_quality = _sequence_quality(exported_sequences)
    training_ready = (
        leakage_passed
        and sequence_quality["passed"]
        and bool(primary_balance["ready_for_grouped_modeling"])
    )
    binary_targets = {
        target: _binary_balance(dataset, target)
        for target in (
            "Emergency_Within_1_Day",
            "Emergency_Within_3_Days",
            "Worker_Shortage_Within_3_Days",
            "Machine_Breakdown_Within_3_Days",
            "Quality_Limit_Within_3_Days",
            "Output_Schedule_Risk_Within_3_Days",
        )
    }

    audit = {
        "export_version": EXPORT_VERSION,
        "generated_at": utc_now(),
        "source": "Component 3 verified daily monitoring records",
        "dataset": {
            "all_monitoring_records": len(snapshot),
            "ready_source_candidates": sum(
                record["label_status"] == "Ready"
                and record.get("independent_validation_eligible", True)
                for record in snapshot
            ),
            "retrospective_records_excluded": sum(
                not record.get("independent_validation_eligible", True)
                for record in snapshot
            ),
            "exported_rows": len(dataset),
            "independent_orders": (
                int(dataset["Bulk_Order_ID"].nunique())
                if not dataset.empty
                else 0
            ),
            "excluded_rows_by_reason": dict(sorted(exclusion_counts.items())),
            "invalid_record_ids": invalid_record_ids,
            "sha256_csv": hashlib.sha256(csv_bytes).hexdigest(),
        },
        "sequence_quality": sequence_quality,
        "all_monitoring_sequence_quality": _sequence_quality(
            records_by_order
        ),
        "schema": {
            "metadata_columns": METADATA_COLUMNS,
            "group_validation_column": "Bulk_Order_ID",
            "model_feature_count": len(EARLY_WARNING_FEATURES),
            "model_features": EARLY_WARNING_FEATURES,
            "target_columns": TARGET_COLUMNS,
            "export_columns": EXPORT_COLUMNS,
        },
        "leakage_controls": {
            "verified_ready_sources_only": True,
            "verified_future_outcomes_required": True,
            "current_actual_emergency_sources_excluded": True,
            "unverified_prior_history_excluded": True,
            "retrospective_training_reuse_excluded": True,
            "identity_columns_in_model_features": identity_overlap,
            "future_targets_in_model_features": target_overlap,
            "excluded_from_model_features": sorted(
                set(EXCLUDED_FROM_MODEL_FEATURES)
                | IDENTITY_COLUMNS
                | {
                    "Actual_Emergency",
                    "Actual_Emergency_Type",
                    "Verified_By",
                    "Verification_Notes",
                }
            ),
            "passed": leakage_passed,
        },
        "class_balance": binary_targets,
        "primary_target": {
            "name": "Emergency_Within_3_Days",
            **primary_balance,
            "training_ready": training_ready,
        },
        "decision": (
            "Ready for Step 5B grouped model evaluation."
            if training_ready
            else "Continue collecting and verifying real daily order sequences."
        ),
    }
    return dataset, audit
