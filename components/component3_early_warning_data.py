"""Leakage-safe dataset preparation for Component 3 early warning.

An early warning must be evaluated before an emergency starts.  This module
therefore creates targets only from rows that are currently stable and have a
complete future production-day horizon inside the same bulk order.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from components.component3_features import build_feature_frame
from components.component3_historical_validation import load_historical_workbook


REPORT_VERSION = "component3-early-warning-step5a-v1"
DEFAULT_HORIZON = 3
MIN_ROWS_PER_CLASS = 20
MIN_ORDERS_PER_CLASS = 3

CURRENT_FEATURES = [
    "Daily_Commitment",
    "Plant_Daily_Output",
    "Output_Gap",
    "Gap_Pct",
    "Daily_Damage_Qty",
    "Max_Daily_Damage_Qty",
    "Damage_Ratio",
    "Working_Day_No",
    "Total_Working_Days",
    "Days_Remaining",
    "Day_Progress_Pct",
    "Output_vs_Commit_Ratio",
    "Remaining_Qty",
    "Full_Order_Qty",
    "Required_Daily_Rate",
    "Commitment_Gap_Rate",
    "Cumulative_Completed_Qty",
    "Is_Cutting_Phase",
    "Is_Sewing_Phase",
]

TRAILING_FEATURES = [
    "History_Days_Available",
    "Previous_Day_Output",
    "Output_Change_From_Previous",
    "Trailing_3D_Avg_Output",
    "Trailing_3D_Output_Std",
    "Trailing_3D_Avg_Gap_Pct",
    "Trailing_3D_Emergency_Days",
    "Trailing_3D_Worker_Shortage_Days",
    "Trailing_3D_Machine_Breakdown_Days",
    "Trailing_3D_Quality_Limit_Days",
    "Days_Since_Last_Emergency",
]

EARLY_WARNING_FEATURES = CURRENT_FEATURES + TRAILING_FEATURES

TARGET_COLUMNS = [
    "Emergency_Within_1_Day",
    "Emergency_Within_3_Days",
    "First_Emergency_Type_Within_3_Days",
    "First_Emergency_Lead_Days",
    "Worker_Shortage_Within_3_Days",
    "Machine_Breakdown_Within_3_Days",
    "Quality_Limit_Within_3_Days",
    "Output_Schedule_Risk_Within_3_Days",
]

# These values are useful metadata or labels, but using them as model inputs
# would leak future outcomes or order identity into validation.
EXCLUDED_FROM_MODEL_FEATURES = [
    "Bulk_Order_ID",
    "Style_ID",
    "Buyer_Name",
    "Allocated_Bulk_Plant",
    "Production_Date",
    "Buyer_Required_Date",
    "Risk_Status",
    "Risk_Type",
    "System_Recommendation",
    "Order_Risk_Level",
    "Style_Completion_Date",
    *TARGET_COLUMNS,
]


def emergency_mask(data: pd.DataFrame) -> pd.Series:
    """Return true for any observed operational, quality, or output risk."""
    operational = (
        data["Worker_Shortage_Count"].gt(0)
        | data["Machine_Breakdown_Count"].gt(0)
        | data["Daily_Damage_Qty"].gt(data["Max_Daily_Damage_Qty"])
    )
    labelled_risk = data["Risk_Type"].fillna("").astype(str).str.strip().ne(
        "No Issue"
    )
    return operational | labelled_risk


def _first_emergency_type(row: pd.Series) -> str:
    risk_type = str(row["Risk_Type"]).strip()
    if risk_type and risk_type != "No Issue":
        return risk_type
    if row["Machine_Breakdown_Count"] > 0:
        return "Machine Breakdown Issue"
    if row["Worker_Shortage_Count"] > 0:
        return "Worker Issue"
    if row["Daily_Damage_Qty"] > row["Max_Daily_Damage_Qty"]:
        return "Quality Issue"
    return "No Emergency"


def _days_since_last_emergency(mask: pd.Series, position: int) -> int:
    earlier = mask.iloc[:position]
    emergency_positions = [
        index for index, occurred in enumerate(earlier.tolist()) if occurred
    ]
    if not emergency_positions:
        return position + 1
    return position - emergency_positions[-1]


def _sequence_quality(data: pd.DataFrame) -> dict[str, int]:
    working_day_jumps = 0
    non_increasing_dates = 0
    for _, order_rows in data.groupby("Bulk_Order_ID", sort=False):
        ordered = order_rows.sort_values(
            ["Production_Date", "Working_Day_No"]
        ).reset_index(drop=True)
        working_day_jumps += int(
            ordered["Working_Day_No"].diff().dropna().ne(1).sum()
        )
        non_increasing_dates += int(
            ordered["Production_Date"].diff().dropna().le(pd.Timedelta(0)).sum()
        )
    return {
        "working_day_sequence_violations": working_day_jumps,
        "non_increasing_date_transitions": non_increasing_dates,
    }


def build_early_warning_dataset(
    data: pd.DataFrame,
    *,
    horizon: int = DEFAULT_HORIZON,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Build stable-day features and future labels within each bulk order."""
    if horizon != DEFAULT_HORIZON:
        raise ValueError("Step 5A currently supports a 3-production-day horizon")

    canonical_features = build_feature_frame(data)
    labelled_records: list[dict[str, Any]] = []
    stable_rows = 0
    stable_rows_without_full_horizon = 0
    complete_horizon_rows_all_states = 0

    for _, positions in data.groupby("Bulk_Order_ID", sort=False).groups.items():
        order = data.loc[list(positions)].sort_values(
            ["Production_Date", "Working_Day_No"]
        )
        order_features = canonical_features.loc[order.index]
        current_emergencies = emergency_mask(order)

        for position in range(len(order)):
            row = order.iloc[position]
            if position + horizon < len(order):
                complete_horizon_rows_all_states += 1
            if current_emergencies.iloc[position]:
                continue

            stable_rows += 1
            if position + horizon >= len(order):
                stable_rows_without_full_horizon += 1
                continue

            current_features = order_features.iloc[position]
            future = order.iloc[position + 1 : position + horizon + 1]
            future_emergencies = emergency_mask(future)
            trailing_start = max(0, position - 2)
            trailing = order.iloc[trailing_start : position + 1]
            trailing_features = order_features.iloc[trailing_start : position + 1]
            trailing_emergencies = current_emergencies.iloc[
                trailing_start : position + 1
            ]

            first_type = "No Emergency"
            first_lead: int | None = None
            for lead, (_, future_row) in enumerate(future.iterrows(), start=1):
                if bool(future_emergencies.loc[future_row.name]):
                    first_type = _first_emergency_type(future_row)
                    first_lead = lead
                    break

            future_physical = (
                future["Worker_Shortage_Count"].gt(0)
                | future["Machine_Breakdown_Count"].gt(0)
                | future["Daily_Damage_Qty"].gt(future["Max_Daily_Damage_Qty"])
            )
            schedule_only = future["Risk_Type"].ne("No Issue") & ~future_physical
            previous_output = (
                float(order.iloc[position - 1]["Plant_Daily_Output"])
                if position > 0
                else float(row["Plant_Daily_Output"])
            )

            record: dict[str, Any] = {
                "Bulk_Order_ID": str(row["Bulk_Order_ID"]),
                "Style_ID": str(row["Style_ID"]),
                "Production_Date": row["Production_Date"].strftime("%Y-%m-%d"),
            }
            record.update(
                {
                    feature: float(current_features[feature])
                    for feature in CURRENT_FEATURES
                }
            )
            record.update(
                {
                    "History_Days_Available": int(len(trailing)),
                    "Previous_Day_Output": previous_output,
                    "Output_Change_From_Previous": float(
                        row["Plant_Daily_Output"] - previous_output
                    ),
                    "Trailing_3D_Avg_Output": round(
                        float(trailing["Plant_Daily_Output"].mean()), 4
                    ),
                    "Trailing_3D_Output_Std": round(
                        float(trailing["Plant_Daily_Output"].std(ddof=0)), 4
                    ),
                    "Trailing_3D_Avg_Gap_Pct": round(
                        float(trailing_features["Gap_Pct"].mean()), 4
                    ),
                    "Trailing_3D_Emergency_Days": int(
                        trailing_emergencies.sum()
                    ),
                    "Trailing_3D_Worker_Shortage_Days": int(
                        trailing["Worker_Shortage_Count"].gt(0).sum()
                    ),
                    "Trailing_3D_Machine_Breakdown_Days": int(
                        trailing["Machine_Breakdown_Count"].gt(0).sum()
                    ),
                    "Trailing_3D_Quality_Limit_Days": int(
                        trailing["Daily_Damage_Qty"]
                        .gt(trailing["Max_Daily_Damage_Qty"])
                        .sum()
                    ),
                    "Days_Since_Last_Emergency": _days_since_last_emergency(
                        current_emergencies, position
                    ),
                    "Emergency_Within_1_Day": int(future_emergencies.iloc[0]),
                    "Emergency_Within_3_Days": int(future_emergencies.any()),
                    "First_Emergency_Type_Within_3_Days": first_type,
                    "First_Emergency_Lead_Days": first_lead,
                    "Worker_Shortage_Within_3_Days": int(
                        future["Worker_Shortage_Count"].gt(0).any()
                    ),
                    "Machine_Breakdown_Within_3_Days": int(
                        future["Machine_Breakdown_Count"].gt(0).any()
                    ),
                    "Quality_Limit_Within_3_Days": int(
                        future["Daily_Damage_Qty"]
                        .gt(future["Max_Daily_Damage_Qty"])
                        .any()
                    ),
                    "Output_Schedule_Risk_Within_3_Days": int(
                        schedule_only.any()
                    ),
                }
            )
            labelled_records.append(record)

    labelled = pd.DataFrame.from_records(labelled_records)
    preparation = {
        "horizon_production_days": horizon,
        "all_rows": int(len(data)),
        "current_stable_rows": stable_rows,
        "current_emergency_rows_excluded": int(len(data) - stable_rows),
        "stable_rows_without_full_horizon_excluded": stable_rows_without_full_horizon,
        "eligible_stable_rows": int(len(labelled)),
        "complete_horizon_rows_if_current_emergencies_were_included": (
            complete_horizon_rows_all_states
        ),
    }
    return labelled, preparation


def _binary_readiness(
    labelled: pd.DataFrame,
    target: str,
) -> dict[str, Any]:
    counts = labelled[target].value_counts().to_dict()
    positive_rows = int(counts.get(1, 0))
    negative_rows = int(counts.get(0, 0))
    positive_orders = int(
        labelled.loc[labelled[target].eq(1), "Bulk_Order_ID"].nunique()
    )
    negative_orders = int(
        labelled.loc[labelled[target].eq(0), "Bulk_Order_ID"].nunique()
    )
    rows_sufficient = min(positive_rows, negative_rows) >= MIN_ROWS_PER_CLASS
    orders_sufficient = (
        min(positive_orders, negative_orders) >= MIN_ORDERS_PER_CLASS
    )
    return {
        "positive_rows": positive_rows,
        "negative_rows": negative_rows,
        "positive_rate": round(positive_rows / len(labelled), 4)
        if len(labelled)
        else None,
        "positive_orders": positive_orders,
        "negative_orders": negative_orders,
        "minimum_rows_per_class_required": MIN_ROWS_PER_CLASS,
        "minimum_orders_per_class_required": MIN_ORDERS_PER_CLASS,
        "row_balance_sufficient": rows_sufficient,
        "group_coverage_sufficient": orders_sufficient,
        "ready_for_grouped_modeling": rows_sufficient and orders_sufficient,
    }


def _type_readiness(labelled: pd.DataFrame) -> dict[str, Any]:
    target = "First_Emergency_Type_Within_3_Days"
    counts = labelled[target].value_counts().to_dict()
    order_counts = labelled.groupby(target)["Bulk_Order_ID"].nunique().to_dict()
    insufficient = sorted(
        label
        for label in counts
        if counts[label] < MIN_ROWS_PER_CLASS
        or order_counts.get(label, 0) < MIN_ORDERS_PER_CLASS
    )
    return {
        "class_rows": {str(key): int(value) for key, value in counts.items()},
        "class_orders": {
            str(key): int(value) for key, value in order_counts.items()
        },
        "insufficient_classes": insufficient,
        "ready_for_grouped_multiclass_modeling": not insufficient
        and len(counts) >= 2,
    }


def audit_early_warning_dataset(
    data: pd.DataFrame,
    dataset_summary: dict[str, Any] | None = None,
    *,
    horizon: int = DEFAULT_HORIZON,
) -> tuple[dict[str, Any], pd.DataFrame]:
    labelled, preparation = build_early_warning_dataset(data, horizon=horizon)
    if labelled.empty:
        raise ValueError("No stable rows have a complete future warning horizon")

    targets = {
        target: _binary_readiness(labelled, target)
        for target in (
            "Emergency_Within_1_Day",
            "Emergency_Within_3_Days",
            "Worker_Shortage_Within_3_Days",
            "Machine_Breakdown_Within_3_Days",
            "Quality_Limit_Within_3_Days",
            "Output_Schedule_Risk_Within_3_Days",
        )
    }
    primary_ready = targets["Emergency_Within_3_Days"][
        "ready_for_grouped_modeling"
    ]
    subtype_candidates = [
        target
        for target in (
            "Worker_Shortage_Within_3_Days",
            "Machine_Breakdown_Within_3_Days",
            "Quality_Limit_Within_3_Days",
            "Output_Schedule_Risk_Within_3_Days",
        )
        if targets[target]["ready_for_grouped_modeling"]
    ]

    report = {
        "report_version": REPORT_VERSION,
        "step_5a": {
            "dataset_preparation_completed": True,
            "general_early_warning_training_ready": primary_ready,
            "status": "ready" if primary_ready else "not_ready",
            "reason": (
                "The three-day general target has no usable negative class on "
                "currently stable rows."
                if not primary_ready
                else "The primary target meets row and order-group requirements."
            ),
            "model_training_started": False,
        },
        "source_dataset": dict(dataset_summary or {}),
        "sequence_quality": _sequence_quality(data),
        "preparation": preparation,
        "label_readiness": targets,
        "future_type_readiness": _type_readiness(labelled),
        "leakage_controls": {
            "current_emergency_rows_excluded": True,
            "future_window_stays_inside_bulk_order": True,
            "complete_three_day_horizon_required": True,
            "group_for_future_validation": "Bulk_Order_ID",
            "model_feature_count": len(EARLY_WARNING_FEATURES),
            "model_features": EARLY_WARNING_FEATURES,
            "excluded_from_model_features": EXCLUDED_FROM_MODEL_FEATURES,
        },
        "supported_research_subtype_targets": subtype_candidates,
        "required_next_data": [
            "More stable production days followed by at least three stable days",
            "More negative examples distributed across several independent bulk orders",
            "Machine, worker, quality, and output-risk outcomes from additional orders",
        ],
        "decision": (
            "Do not train or report a general three-day emergency model from the "
            "current dataset. Continue collecting real stable and incident sequences."
        ),
    }
    return report, labelled


def run_step5a_audit(
    path: str | Path,
    *,
    horizon: int = DEFAULT_HORIZON,
) -> tuple[dict[str, Any], pd.DataFrame]:
    data, summary = load_historical_workbook(path)
    return audit_early_warning_dataset(data, summary, horizon=horizon)
