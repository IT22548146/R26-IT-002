"""Deadline-aware features for Component 3 order-risk Model 2.

Only information available on the monitoring day is used. Actual completion
dates are intentionally excluded to avoid target leakage.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta

import pandas as pd

from components.component3_features import FEATURES, build_feature_values


DEADLINE_FEATURES = [
    "Deadline_Calendar_Days",
    "Available_Working_Days_To_Deadline",
    "Required_Daily_Rate_To_Deadline",
    "Commitment_Slack_To_Deadline",
    "Commitment_Slack_Pct_To_Deadline",
    "Is_Order_Complete",
]
ORDER_RISK_FEATURES = [*FEATURES, *DEADLINE_FEATURES]


def _as_date(value: str | date | datetime | pd.Timestamp) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return pd.Timestamp(value).date()


def available_working_days_to_deadline(
    production_date: str | date | datetime | pd.Timestamp,
    buyer_required_date: str | date | datetime | pd.Timestamp,
) -> int:
    """Count Monday-Friday days after the current day through the deadline."""
    start = _as_date(production_date)
    deadline = _as_date(buyer_required_date)
    if deadline <= start:
        return 0
    current = start + timedelta(days=1)
    count = 0
    while current <= deadline:
        if current.weekday() < 5:
            count += 1
        current += timedelta(days=1)
    return count


def build_order_risk_feature_values(
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
    production_date: str | date | datetime | pd.Timestamp,
    buyer_required_date: str | date | datetime | pd.Timestamp,
) -> dict[str, int | float]:
    values = build_feature_values(
        daily_commitment=daily_commitment,
        plant_daily_output=plant_daily_output,
        machine_breakdown_count=machine_breakdown_count,
        worker_shortage_count=worker_shortage_count,
        daily_damage_qty=daily_damage_qty,
        max_daily_damage_qty=max_daily_damage_qty,
        working_day_no=working_day_no,
        total_working_days=total_working_days,
        cutting_days=cutting_days,
        sewing_days=sewing_days,
        full_order_qty=full_order_qty,
        cumulative_completed_qty=cumulative_completed_qty,
    )
    current = _as_date(production_date)
    deadline = _as_date(buyer_required_date)
    if deadline < current:
        raise ValueError("buyer_required_date cannot be before production_date")

    remaining_qty = max(0, full_order_qty - cumulative_completed_qty)
    available_days = available_working_days_to_deadline(current, deadline)
    required_rate = (
        remaining_qty / available_days
        if available_days > 0
        else float(remaining_qty)
    )
    commitment_slack = daily_commitment - required_rate
    values.update(
        {
            "Deadline_Calendar_Days": (deadline - current).days,
            "Available_Working_Days_To_Deadline": available_days,
            "Required_Daily_Rate_To_Deadline": round(required_rate, 4),
            "Commitment_Slack_To_Deadline": round(commitment_slack, 4),
            "Commitment_Slack_Pct_To_Deadline": round(
                commitment_slack / daily_commitment * 100,
                4,
            ),
            "Is_Order_Complete": int(remaining_qty == 0),
        }
    )
    return values


def build_order_risk_feature_row(**values: object) -> pd.DataFrame:
    features = build_order_risk_feature_values(**values)
    return pd.DataFrame([features], columns=ORDER_RISK_FEATURES)


def build_order_risk_feature_frame(data: pd.DataFrame) -> pd.DataFrame:
    records = []
    for row in data.to_dict(orient="records"):
        records.append(
            build_order_risk_feature_values(
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
                production_date=row["Production_Date"],
                buyer_required_date=row["Buyer_Required_Date"],
            )
        )
    return pd.DataFrame(records, columns=ORDER_RISK_FEATURES)
