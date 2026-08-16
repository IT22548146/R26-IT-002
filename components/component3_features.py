"""Shared feature engineering for Component 3 training and inference."""

from __future__ import annotations

import pandas as pd


FEATURES = [
    "Daily_Commitment",
    "Plant_Daily_Output",
    "Output_Gap",
    "Gap_Pct",
    "Machine_Breakdown_Count",
    "Worker_Shortage_Count",
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
    "Is_Machine_Breakdown",
    "Is_Worker_Shortage",
    "Is_Quality_Issue",
    "Is_Cutting_Phase",
    "Is_Sewing_Phase",
]


def build_feature_values(
    *,
    daily_commitment: int,
    plant_daily_output: int,
    machine_breakdown_count: int,
    worker_shortage_count: int,
    daily_damage_qty: int,
    max_daily_damage_qty: int,
    working_day_no: int,
    total_working_days: int,
    cutting_days: int,
    sewing_days: int,
    full_order_qty: int,
    cumulative_completed_qty: int,
) -> dict[str, int | float]:
    """Calculate the canonical 24 features expected by Component 3 models."""
    if daily_commitment <= 0:
        raise ValueError("daily_commitment must be > 0")
    if total_working_days <= 0:
        raise ValueError("total_working_days must be > 0")
    if not 1 <= working_day_no <= total_working_days:
        raise ValueError("working_day_no must be between 1 and total_working_days")
    if max_daily_damage_qty < 0:
        raise ValueError("max_daily_damage_qty must be >= 0")
    if cutting_days < 0 or sewing_days < 0:
        raise ValueError("cutting_days and sewing_days must be >= 0")

    output_gap = daily_commitment - plant_daily_output
    gap_pct = round(output_gap / daily_commitment * 100, 2)
    damage_ratio = round(daily_damage_qty / (max_daily_damage_qty + 1), 4)
    days_remaining = total_working_days - working_day_no
    remaining_qty = full_order_qty - cumulative_completed_qty
    required_daily_rate = round(remaining_qty / (days_remaining + 1), 1)

    return {
        "Daily_Commitment": daily_commitment,
        "Plant_Daily_Output": plant_daily_output,
        "Output_Gap": output_gap,
        "Gap_Pct": gap_pct,
        "Machine_Breakdown_Count": machine_breakdown_count,
        "Worker_Shortage_Count": worker_shortage_count,
        "Daily_Damage_Qty": daily_damage_qty,
        "Max_Daily_Damage_Qty": max_daily_damage_qty,
        "Damage_Ratio": damage_ratio,
        "Working_Day_No": working_day_no,
        "Total_Working_Days": total_working_days,
        "Days_Remaining": days_remaining,
        "Day_Progress_Pct": round(working_day_no / total_working_days * 100, 2),
        "Output_vs_Commit_Ratio": round(plant_daily_output / (daily_commitment + 1), 4),
        "Remaining_Qty": remaining_qty,
        "Full_Order_Qty": full_order_qty,
        "Required_Daily_Rate": required_daily_rate,
        "Commitment_Gap_Rate": round(required_daily_rate - daily_commitment, 1),
        "Cumulative_Completed_Qty": cumulative_completed_qty,
        "Is_Machine_Breakdown": int(machine_breakdown_count > 0),
        "Is_Worker_Shortage": int(worker_shortage_count > 0),
        "Is_Quality_Issue": int(
            daily_damage_qty > max_daily_damage_qty
            and machine_breakdown_count == 0
            and worker_shortage_count == 0
        ),
        "Is_Cutting_Phase": int(working_day_no <= cutting_days),
        "Is_Sewing_Phase": int(
            cutting_days < working_day_no <= cutting_days + sewing_days
        ),
    }


def build_feature_row(**values: int) -> tuple[pd.DataFrame, float]:
    """Return one model-ready DataFrame row and its gap percentage."""
    features = build_feature_values(**values)
    return pd.DataFrame([features], columns=FEATURES), float(features["Gap_Pct"])


def build_feature_frame(data: pd.DataFrame) -> pd.DataFrame:
    """Recompute model features from raw workbook fields for every row."""
    records = []
    for row in data.to_dict(orient="records"):
        records.append(
            build_feature_values(
                daily_commitment=int(row["Daily_Commitment"]),
                plant_daily_output=int(row["Plant_Daily_Output"]),
                machine_breakdown_count=int(row["Machine_Breakdown_Count"]),
                worker_shortage_count=int(row["Worker_Shortage_Count"]),
                daily_damage_qty=int(row["Daily_Damage_Qty"]),
                max_daily_damage_qty=int(row["Max_Daily_Damage_Qty"]),
                working_day_no=int(row["Working_Day_No"]),
                total_working_days=int(row["Total_Working_Days"]),
                cutting_days=int(row["Cutting_Days"]),
                sewing_days=int(row["Sewing_Days"]),
                full_order_qty=int(row["Full_Order_Qty"]),
                cumulative_completed_qty=int(row["Cumulative_Completed_Qty"]),
            )
        )
    return pd.DataFrame(records, columns=FEATURES, index=data.index)
