"""Add broad, controlled Low Risk trajectories for Component 3 Model 2.

This research-only augmentation expands order-size and schedule coverage that is
missing from the 11 observed historical orders. The input workbook is never
modified. Every generated row remains explicitly marked as augmented and must
not be reported as independent real-order validation evidence.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

from augment_component3_low_risk import (
    BUYERS,
    OUTPUT_COLUMNS,
    PLANTS,
    RECOMMENDATIONS,
    RISK_TYPE_MAP,
    add_provenance_columns,
    daily_values,
    severity,
)


SEED = 22904614
GENERATOR_VERSION = "component3_model2_broad_low_risk_v2"
PROFILES = (
    ("micro", (4, 6, 8, 10, 12, 14), (10, 25, 50, 80, 120, 160), 3, 14),
    ("small", (15, 18, 21, 24, 27, 31), (80, 140, 200, 260, 330, 400), 7, 28),
    ("medium", (32, 38, 44, 50, 56, 60), (200, 330, 460, 590, 720, 850), 14, 45),
    ("long", (61, 72, 84, 96, 108, 120), (300, 500, 700, 900, 1_100, 1_300), 21, 60),
)
EVENTS = (
    "No Issue",
    "Minor Delay",
    "Working Hours Issue",
    "Worker Issue",
    "Commitment Too Low",
    "Machine Breakdown Issue",
    "Quality Issue",
)
EVENT_PROBABILITIES = (0.72, 0.08, 0.06, 0.04, 0.03, 0.04, 0.03)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--orders", type=int, default=24)
    parser.add_argument("--seed", type=int, default=SEED)
    return parser.parse_args()


def _daily_event(rng: np.random.Generator) -> str:
    return str(rng.choice(EVENTS, p=EVENT_PROBABILITIES))


def generate_order(
    order_number: int,
    rng: np.random.Generator,
    start_date: pd.Timestamp,
) -> pd.DataFrame:
    profile, day_options, commitment_options, min_buffer, max_buffer = (
        PROFILES[(order_number - 1) % len(PROFILES)]
    )
    profile_variant = (order_number - 1) // len(PROFILES)
    total_days = int(day_options[profile_variant % len(day_options)])
    base_commitment = int(
        commitment_options[profile_variant % len(commitment_options)]
    )
    production_dates = pd.bdate_range(start=start_date, periods=total_days)
    completion_date = production_dates[-1]
    buyer_required_date = completion_date + pd.Timedelta(
        days=int(rng.integers(min_buffer, max_buffer + 1))
    )
    approved_date = production_dates[0] - pd.Timedelta(days=7)

    plant_name, plant_location, plant_enc = PLANTS[(order_number - 1) % len(PLANTS)]
    buyer_name, buyer_enc = BUYERS[(order_number - 1) % len(BUYERS)]
    bulk_order_id = f"BULK_AUG_M2V2_{order_number:04d}"
    style_id = f"AUGM2V2{order_number:04d}"
    cutting_days = max(1, min(total_days, int(round(total_days * 0.28))))
    sewing_days = max(
        1,
        min(total_days - cutting_days, int(round(total_days * 0.48))),
    )

    daily_records: list[dict] = []
    for day_number, production_date in enumerate(production_dates, start=1):
        commitment = max(1, int(round(base_commitment * rng.uniform(0.94, 1.06))))
        max_damage = max(1, int(round(commitment * rng.uniform(0.01, 0.035))))
        risk_type = _daily_event(rng)
        output, damage, machine_breakdowns, worker_shortage = daily_values(
            rng,
            risk_type,
            commitment,
            max_damage,
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
        day_number = int(record["Working_Day_No"])
        commitment = int(record["Daily_Commitment"])
        output = int(record["Plant_Daily_Output"])
        output_gap = commitment - output
        gap_pct = round(output_gap / commitment * 100, 2)
        damage_ratio = round(
            int(record["Daily_Damage_Qty"])
            / (int(record["Max_Daily_Damage_Qty"]) + 1),
            4,
        )
        days_remaining = total_days - day_number
        cumulative_completed += output
        cumulative_gap += output_gap
        cumulative_machine_breakdowns += int(record["Machine_Breakdown_Count"])
        cumulative_worker_shortage += int(record["Worker_Shortage_Count"])
        remaining_qty = full_order_qty - cumulative_completed
        required_daily_rate = round(remaining_qty / (days_remaining + 1), 1)
        risk_type = str(record["Risk_Type"])

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
                "Sheet_Name": f"AUG_M2V2_{profile.upper()}_{order_number:04d}",
                "Gap_Pct": gap_pct,
                "Damage_Pct": round(damage_ratio * 100, 2),
                "Days_Remaining": days_remaining,
                "Required_Daily_Rate": required_daily_rate,
                "Commitment_Gap_Rate": round(required_daily_rate - commitment, 1),
                "Progress_Pct": round(
                    cumulative_completed / full_order_qty * 100,
                    2,
                ),
                "Severity_Level": severity(gap_pct),
                "Is_Quality_Issue": int(risk_type == "Quality Issue"),
                "Is_Machine_Breakdown": int(record["Machine_Breakdown_Count"] > 0),
                "Is_Worker_Shortage": int(record["Worker_Shortage_Count"] > 0),
                "Plant_Enc": plant_enc,
                "Buyer_Enc": buyer_enc,
                "Is_Cutting_Phase": int(day_number <= cutting_days),
                "Is_Sewing_Phase": int(
                    cutting_days < day_number <= cutting_days + sewing_days
                ),
                "Day_Progress_Pct": round(day_number / total_days * 100, 2),
                "Output_vs_Commit_Ratio": round(output / (commitment + 1), 4),
                "Cumulative_Gap": cumulative_gap,
                "Damage_Ratio": damage_ratio,
                "Cum_Machine_Breakdown": cumulative_machine_breakdowns,
                "Cum_Worker_Shortage": cumulative_worker_shortage,
                "Risk_Type_Enc": RISK_TYPE_MAP[risk_type],
                "Order_Risk_Enc": 0,
                "Synthetic": True,
                "Scenario_Tag": f"Augmented_Low_Risk_{profile.title()}",
                "Data_Origin": "Augmented_Low_Risk",
                "Augmentation_Version": GENERATOR_VERSION,
            }
        )

    return pd.DataFrame(rows, columns=OUTPUT_COLUMNS)


def validate_generated(generated: pd.DataFrame, expected_orders: int) -> None:
    if generated["Bulk_Order_ID"].nunique() != expected_orders:
        raise AssertionError("Generated order count is inconsistent")
    if not generated["Synthetic"].eq(True).all():
        raise AssertionError("Generated rows must remain Synthetic=True")
    if not generated["Data_Origin"].eq("Augmented_Low_Risk").all():
        raise AssertionError("Generated data origin is inconsistent")
    if not generated["Augmentation_Version"].eq(GENERATOR_VERSION).all():
        raise AssertionError("Generated version is inconsistent")
    if not generated["Order_Risk_Level"].eq("Low").all():
        raise AssertionError("Generated Model 2 labels must be Low")
    if not (
        generated["Buyer_Required_Date"] > generated["Style_Completion_Date"]
    ).all():
        raise AssertionError("Every generated order must finish before its deadline")

    final_rows = (
        generated.sort_values("Working_Day_No")
        .groupby("Bulk_Order_ID", sort=False)
        .tail(1)
    )
    if not final_rows["Remaining_Qty"].eq(0).all():
        raise AssertionError("Every generated order must complete")
    if not final_rows["Cumulative_Completed_Qty"].eq(
        final_rows["Full_Order_Qty"]
    ).all():
        raise AssertionError("Final cumulative quantity is inconsistent")


def main() -> None:
    args = parse_args()
    if args.orders < len(PROFILES):
        raise ValueError(f"--orders must be at least {len(PROFILES)}")
    if args.input.resolve() == args.output.resolve():
        raise ValueError("Refusing to overwrite the input dataset")

    source = add_provenance_columns(pd.read_excel(args.input))
    rng = np.random.default_rng(args.seed)
    start_base = pd.Timestamp("2025-07-07")
    generated = pd.concat(
        [
            generate_order(
                index,
                rng,
                start_base + pd.offsets.BDay((index - 1) * 3),
            )
            for index in range(1, args.orders + 1)
        ],
        ignore_index=True,
    )
    validate_generated(generated, args.orders)

    collisions = set(source["Bulk_Order_ID"]) & set(generated["Bulk_Order_ID"])
    if collisions:
        raise ValueError(f"Generated order IDs already exist: {sorted(collisions)}")

    result = pd.concat([source, generated], ignore_index=True, sort=False)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    result.to_excel(args.output, index=False)

    print(f"Input rows: {len(source)}")
    print(f"Generated broad Low Risk orders: {generated['Bulk_Order_ID'].nunique()}")
    print(f"Generated broad Low Risk rows: {len(generated)}")
    print(f"Output rows: {len(result)}")
    print(f"Output: {args.output.resolve()}")
    print("Profile coverage:")
    print(generated["Scenario_Tag"].value_counts().sort_index().to_string())
    print("Generated range:")
    print(
        generated[["Total_Working_Days", "Daily_Commitment", "Full_Order_Qty"]]
        .agg(["min", "median", "max"])
        .to_string()
    )


if __name__ == "__main__":
    main()
