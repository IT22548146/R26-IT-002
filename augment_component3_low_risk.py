"""Generate complete augmented Low Risk order trajectories for Component 3.

The input workbook is never modified. Generated rows are explicitly marked with
``Synthetic=True`` and ``Data_Origin=Augmented_Low_Risk``. These rows are for
training only; production evaluation must continue to use unseen real orders.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd


SEED = 42
GENERATOR_VERSION = "component3_low_risk_v1"

RISK_TYPE_MAP = {
    "No Issue": 0,
    "Minor Delay": 1,
    "Working Hours Issue": 2,
    "Worker Issue": 3,
    "Commitment Too Low": 4,
    "Machine Breakdown Issue": 5,
    "Quality Issue": 6,
}

RECOMMENDATIONS = {
    "No Issue": "Continue current production plan.",
    "Minor Delay": "Increase line monitoring and add small overtime to recover the daily gap.",
    "Working Hours Issue": "Increase working hours or add overtime to recover the small output gap.",
    "Worker Issue": "Add operators or reassign workers from another line to recover lost pieces.",
    "Commitment Too Low": "Daily output is below plan; increase plant working hours to reach actual plan.",
    "Machine Breakdown Issue": "Repair machine immediately and shift remaining output to backup machine/line.",
    "Quality Issue": "Check damaged pieces and improve quality inspection before continuing.",
}

PLANTS = [
    ("Amsral Lanka Enterprises", "Boralesgamuwa", 0),
    ("Dinusha Embroidery", "Weliweriya", 1),
    ("MRC Group", "Colombo", 2),
    ("Regal Image International", "Maharagama", 3),
    ("Sunrose Lanka (Pvt) Ltd", "Katubedda", 4),
    ("The Bobbin Group", "Mount Lavinia", 5),
]
BUYERS = [("George", 0), ("Hirdaramani", 1), ("M&S", 2), ("Tesco", 3)]

OUTPUT_COLUMNS = [
    "Bulk_Order_ID",
    "Style_ID",
    "Buyer_Name",
    "Allocated_Bulk_Plant",
    "Plant_Location",
    "Full_Order_Qty",
    "Bulk_Order_Approved_Date",
    "Buyer_Required_Date",
    "Production_Date",
    "Working_Day_No",
    "Total_Working_Days",
    "Cutting_Days",
    "Sewing_Days",
    "Daily_Commitment",
    "Plant_Daily_Output",
    "Output_Gap",
    "Daily_Damage_Qty",
    "Max_Daily_Damage_Qty",
    "Machine_Breakdown_Count",
    "Worker_Shortage_Count",
    "Risk_Status",
    "Risk_Type",
    "System_Recommendation",
    "Cumulative_Completed_Qty",
    "Remaining_Qty",
    "Style_Completion_Date",
    "Order_Risk_Level",
    "Sheet_Name",
    "Gap_Pct",
    "Damage_Pct",
    "Days_Remaining",
    "Required_Daily_Rate",
    "Commitment_Gap_Rate",
    "Progress_Pct",
    "Severity_Level",
    "Is_Quality_Issue",
    "Is_Machine_Breakdown",
    "Is_Worker_Shortage",
    "Plant_Enc",
    "Buyer_Enc",
    "Is_Cutting_Phase",
    "Is_Sewing_Phase",
    "Day_Progress_Pct",
    "Output_vs_Commit_Ratio",
    "Cumulative_Gap",
    "Damage_Ratio",
    "Cum_Machine_Breakdown",
    "Cum_Worker_Shortage",
    "Risk_Type_Enc",
    "Order_Risk_Enc",
    "Synthetic",
    "Scenario_Tag",
    "Data_Origin",
    "Augmentation_Version",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--orders", type=int, default=12)
    parser.add_argument("--seed", type=int, default=SEED)
    return parser.parse_args()


def severity(gap_pct: float) -> str:
    if gap_pct <= 0:
        return "No Risk"
    if gap_pct <= 5:
        return "Minor"
    if gap_pct <= 15:
        return "Moderate"
    return "Critical"


def choose_daily_event(rng: np.random.Generator) -> str:
    return str(
        rng.choice(
            [
                "No Issue",
                "Minor Delay",
                "Working Hours Issue",
                "Worker Issue",
                "Commitment Too Low",
                "Machine Breakdown Issue",
                "Quality Issue",
            ],
            p=[0.55, 0.08, 0.11, 0.10, 0.03, 0.08, 0.05],
        )
    )


def daily_values(
    rng: np.random.Generator,
    risk_type: str,
    commitment: int,
    max_damage: int,
) -> tuple[int, int, int, int]:
    machine_breakdowns = 0
    worker_shortage = 0
    damage = int(rng.integers(0, max_damage + 1))

    if risk_type == "No Issue":
        output = commitment + int(rng.integers(0, max(2, round(commitment * 0.07))))
    elif risk_type == "Minor Delay":
        gap = int(round(commitment * rng.uniform(0.012, 0.048)))
        output = commitment - max(1, gap)
    elif risk_type == "Working Hours Issue":
        gap = int(round(commitment * rng.uniform(0.05, 0.08)))
        output = commitment - max(1, gap)
        worker_shortage = int(rng.integers(1, 4))
    elif risk_type == "Worker Issue":
        gap = int(round(commitment * rng.uniform(0.081, 0.15)))
        output = commitment - max(1, gap)
        worker_shortage = int(rng.integers(2, 6))
    elif risk_type == "Commitment Too Low":
        gap = int(round(commitment * rng.uniform(0.16, 0.24)))
        output = commitment - max(1, gap)
    elif risk_type == "Machine Breakdown Issue":
        gap = int(round(commitment * rng.uniform(0.17, 0.35)))
        output = commitment - max(1, gap)
        machine_breakdowns = int(rng.integers(1, 5))
    elif risk_type == "Quality Issue":
        output = commitment + int(rng.integers(0, max(2, round(commitment * 0.04))))
        damage = max_damage + int(rng.integers(1, max(2, round(max_damage * 0.35))))
    else:
        raise ValueError(f"Unsupported risk type: {risk_type}")

    return max(1, output), damage, machine_breakdowns, worker_shortage


def generate_order(
    order_number: int,
    rng: np.random.Generator,
    start_date: pd.Timestamp,
) -> pd.DataFrame:
    total_days = int(rng.integers(32, 57))
    base_commitment = int(rng.integers(400, 951))
    production_dates = pd.bdate_range(start=start_date, periods=total_days)
    completion_date = production_dates[-1]
    deadline_buffer_days = int(rng.integers(21, 57))
    buyer_required_date = completion_date + pd.Timedelta(days=deadline_buffer_days)
    approved_date = production_dates[0] - pd.Timedelta(days=7)

    plant_name, plant_location, plant_enc = PLANTS[(order_number - 1) % len(PLANTS)]
    buyer_name, buyer_enc = BUYERS[(order_number - 1) % len(BUYERS)]
    bulk_order_id = f"BULK_AUG_LOW_{order_number:04d}"
    style_id = f"AUGLOW{order_number:04d}"
    cutting_days = int(rng.integers(7, min(13, total_days - 15)))
    sewing_days = int(rng.integers(12, min(26, total_days - cutting_days + 1)))

    daily_records: list[dict] = []
    for day_number, production_date in enumerate(production_dates, start=1):
        commitment = max(1, int(round(base_commitment * rng.uniform(0.97, 1.03))))
        max_damage = int(rng.integers(8, 26))
        risk_type = choose_daily_event(rng)
        output, damage, machine_breakdowns, worker_shortage = daily_values(
            rng, risk_type, commitment, max_damage
        )
        daily_records.append(
            {
                "Production_Date": production_date,
                "Working_Day_No": day_number,
                "Daily_Commitment": commitment,
                "Plant_Daily_Output": output,
                "Daily_Damage_Qty": damage,
                "Max_Daily_Damage_Qty": max_damage,
                "Machine_Breakdown_Count": machine_breakdowns,
                "Worker_Shortage_Count": worker_shortage,
                "Risk_Type": risk_type,
            }
        )

    full_order_qty = sum(record["Plant_Daily_Output"] for record in daily_records)
    cumulative_completed = 0
    cumulative_gap = 0
    cumulative_machine_breakdowns = 0
    cumulative_worker_shortage = 0
    rows: list[dict] = []

    for record in daily_records:
        day_number = record["Working_Day_No"]
        commitment = record["Daily_Commitment"]
        output = record["Plant_Daily_Output"]
        output_gap = commitment - output
        gap_pct = round(output_gap / commitment * 100, 2)
        damage_ratio = round(record["Daily_Damage_Qty"] / (record["Max_Daily_Damage_Qty"] + 1), 4)
        days_remaining = total_days - day_number

        cumulative_completed += output
        cumulative_gap += output_gap
        cumulative_machine_breakdowns += record["Machine_Breakdown_Count"]
        cumulative_worker_shortage += record["Worker_Shortage_Count"]
        remaining_qty = full_order_qty - cumulative_completed
        required_daily_rate = round(remaining_qty / (days_remaining + 1), 1)
        risk_type = record["Risk_Type"]

        rows.append(
            {
                "Bulk_Order_ID": bulk_order_id,
                "Style_ID": style_id,
                "Buyer_Name": buyer_name,
                "Allocated_Bulk_Plant": plant_name,
                "Plant_Location": plant_location,
                "Full_Order_Qty": full_order_qty,
                "Bulk_Order_Approved_Date": approved_date,
                "Buyer_Required_Date": buyer_required_date,
                "Production_Date": record["Production_Date"],
                "Working_Day_No": day_number,
                "Total_Working_Days": total_days,
                "Cutting_Days": cutting_days,
                "Sewing_Days": sewing_days,
                "Daily_Commitment": commitment,
                "Plant_Daily_Output": output,
                "Output_Gap": output_gap,
                "Daily_Damage_Qty": record["Daily_Damage_Qty"],
                "Max_Daily_Damage_Qty": record["Max_Daily_Damage_Qty"],
                "Machine_Breakdown_Count": record["Machine_Breakdown_Count"],
                "Worker_Shortage_Count": record["Worker_Shortage_Count"],
                "Risk_Status": "No Risk" if risk_type == "No Issue" else "Risk",
                "Risk_Type": risk_type,
                "System_Recommendation": RECOMMENDATIONS[risk_type],
                "Cumulative_Completed_Qty": cumulative_completed,
                "Remaining_Qty": remaining_qty,
                "Style_Completion_Date": completion_date,
                "Order_Risk_Level": "Low",
                "Sheet_Name": f"AUG_LOW_{order_number:04d}",
                "Gap_Pct": gap_pct,
                "Damage_Pct": round(damage_ratio * 100, 2),
                "Days_Remaining": days_remaining,
                "Required_Daily_Rate": required_daily_rate,
                "Commitment_Gap_Rate": round(required_daily_rate - commitment, 1),
                "Progress_Pct": round(cumulative_completed / full_order_qty * 100, 2),
                "Severity_Level": severity(gap_pct),
                "Is_Quality_Issue": int(risk_type == "Quality Issue"),
                "Is_Machine_Breakdown": int(record["Machine_Breakdown_Count"] > 0),
                "Is_Worker_Shortage": int(record["Worker_Shortage_Count"] > 0),
                "Plant_Enc": plant_enc,
                "Buyer_Enc": buyer_enc,
                "Is_Cutting_Phase": int(day_number <= 10),
                "Is_Sewing_Phase": int(10 < day_number <= 25),
                "Day_Progress_Pct": round(day_number / total_days * 100, 2),
                "Output_vs_Commit_Ratio": round(output / (commitment + 1), 4),
                "Cumulative_Gap": cumulative_gap,
                "Damage_Ratio": damage_ratio,
                "Cum_Machine_Breakdown": cumulative_machine_breakdowns,
                "Cum_Worker_Shortage": cumulative_worker_shortage,
                "Risk_Type_Enc": RISK_TYPE_MAP[risk_type],
                "Order_Risk_Enc": 0,
                "Synthetic": True,
                "Scenario_Tag": "Augmented_Low_Risk",
                "Data_Origin": "Augmented_Low_Risk",
                "Augmentation_Version": GENERATOR_VERSION,
            }
        )

    return pd.DataFrame(rows, columns=OUTPUT_COLUMNS)


def validate_augmented(augmented: pd.DataFrame, expected_orders: int) -> None:
    if augmented["Bulk_Order_ID"].nunique() != expected_orders:
        raise AssertionError("Generated order count does not match the requested count")
    if not augmented["Synthetic"].all():
        raise AssertionError("Every generated row must be marked Synthetic=True")
    if not augmented["Order_Risk_Level"].eq("Low").all():
        raise AssertionError("Every generated order must be labelled Low Risk")
    if not augmented["Order_Risk_Enc"].eq(0).all():
        raise AssertionError("Low Risk encoding must be 0")
    if not (augmented["Buyer_Required_Date"] > augmented["Style_Completion_Date"]).all():
        raise AssertionError("Low Risk deadlines must occur after completion")
    if (augmented["Remaining_Qty"] < 0).any():
        raise AssertionError("Remaining quantity cannot be negative")

    final_rows = augmented.sort_values("Working_Day_No").groupby("Bulk_Order_ID").tail(1)
    if not final_rows["Remaining_Qty"].eq(0).all():
        raise AssertionError("Every generated trajectory must finish the full order")
    if not final_rows["Cumulative_Completed_Qty"].eq(final_rows["Full_Order_Qty"]).all():
        raise AssertionError("Final cumulative output must equal full order quantity")

    expected_gap = augmented["Daily_Commitment"] - augmented["Plant_Daily_Output"]
    if not expected_gap.eq(augmented["Output_Gap"]).all():
        raise AssertionError("Output_Gap formula is inconsistent")


def add_provenance_columns(source: pd.DataFrame) -> pd.DataFrame:
    result = source.copy()
    if "Synthetic" not in result.columns:
        result["Synthetic"] = False
    if "Scenario_Tag" not in result.columns:
        result["Scenario_Tag"] = np.where(result["Synthetic"], "Existing_Generated", "Real_Data")
    if "Data_Origin" not in result.columns:
        result["Data_Origin"] = np.where(result["Synthetic"], "Existing_Generated", "Real_Data")
    if "Augmentation_Version" not in result.columns:
        result["Augmentation_Version"] = ""
    return result


def main() -> None:
    args = parse_args()
    if args.orders < 1:
        raise ValueError("--orders must be at least 1")
    if args.input.resolve() == args.output.resolve():
        raise ValueError("Refusing to overwrite the input dataset")

    source = add_provenance_columns(pd.read_excel(args.input))
    rng = np.random.default_rng(args.seed)
    start_base = pd.Timestamp("2025-01-06")
    generated_orders = [
        generate_order(
            order_number=index,
            rng=rng,
            start_date=start_base + pd.offsets.BDay((index - 1) * 4),
        )
        for index in range(1, args.orders + 1)
    ]
    augmented = pd.concat(generated_orders, ignore_index=True)
    validate_augmented(augmented, args.orders)

    collisions = set(source["Bulk_Order_ID"]) & set(augmented["Bulk_Order_ID"])
    if collisions:
        raise ValueError(f"Generated order IDs already exist: {sorted(collisions)}")

    result = pd.concat([source, augmented], ignore_index=True, sort=False)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    result.to_excel(args.output, index=False)

    print(f"Input rows: {len(source)}")
    print(f"Generated Low Risk orders: {augmented['Bulk_Order_ID'].nunique()}")
    print(f"Generated Low Risk rows: {len(augmented)}")
    print(f"Output rows: {len(result)}")
    print(f"Output: {args.output.resolve()}")
    print("Generated risk distribution:")
    print(augmented["Risk_Type"].value_counts().to_string())


if __name__ == "__main__":
    main()
