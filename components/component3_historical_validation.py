"""Historical replay and calibration evidence for Component 3 recovery.

The recovery engine is replayed against the next production-day observation
from each historical risk row.  This measures forecast behaviour without
claiming that the historical recommendation was actually applied.  Causal
calibration remains disabled until applied-action fields are available.
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from components.component3_recovery import build_recovery_plan


REPORT_VERSION = "component3-recovery-historical-v1"

COLUMN_ALIASES = {
    "Assigned_Plant_Name": "Allocated_Bulk_Plant",
    "Assigned_Plant_Location": "Plant_Location",
    "Running_Day_No": "Working_Day_No",
    "Days_Run_For_Style": "Total_Working_Days",
}

REQUIRED_COLUMNS = {
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
    "Daily_Damage_Qty",
    "Max_Daily_Damage_Qty",
    "Machine_Breakdown_Count",
    "Worker_Shortage_Count",
    "Risk_Type",
    "System_Recommendation",
    "Cumulative_Completed_Qty",
}

DATE_COLUMNS = (
    "Bulk_Order_Approved_Date",
    "Buyer_Required_Date",
    "Production_Date",
    "Style_Completion_Date",
)

NUMERIC_COLUMNS = (
    "Full_Order_Qty",
    "Working_Day_No",
    "Total_Working_Days",
    "Cutting_Days",
    "Sewing_Days",
    "Daily_Commitment",
    "Plant_Daily_Output",
    "Daily_Damage_Qty",
    "Max_Daily_Damage_Qty",
    "Machine_Breakdown_Count",
    "Worker_Shortage_Count",
    "Cumulative_Completed_Qty",
)

# A recommendation string is not proof that an action was implemented. These
# are the minimum historical fields needed for causal action calibration.
ACTION_OUTCOME_FIELDS = (
    "Applied_Action",
    "Actual_Overtime_Hours",
    "Actual_Additional_Workers",
    "Actual_Backup_Machines",
    "Actual_Machine_Repair_Hours",
)


def _find_header_row(path: Path, sheet_name: str) -> int:
    preview = pd.read_excel(path, sheet_name=sheet_name, header=None, nrows=20)
    for index, row in preview.iterrows():
        values = {str(value).strip() for value in row.dropna().tolist()}
        if "Bulk_Order_ID" in values and (
            "Production_Date" in values or "Running_Day_No" in values
        ):
            return int(index)
    raise ValueError(
        f"Could not find the Component 3 table header in sheet {sheet_name!r}"
    )


def _boolean_mask(series: pd.Series) -> pd.Series:
    if pd.api.types.is_bool_dtype(series):
        return series.fillna(False)
    return (
        series.fillna("")
        .astype(str)
        .str.strip()
        .str.lower()
        .isin({"true", "1", "yes", "generated", "synthetic"})
    )


def generated_row_mask(data: pd.DataFrame) -> pd.Series:
    """Identify explicitly generated/augmented rows when markers are present."""
    mask = pd.Series(False, index=data.index)
    if "Synthetic" in data.columns:
        mask |= _boolean_mask(data["Synthetic"])
    if "Data_Origin" in data.columns:
        origin = data["Data_Origin"].fillna("").astype(str).str.lower()
        mask |= origin.str.contains("generated|augmented|synthetic", regex=True)
    for column in ("Bulk_Order_ID", "Style_ID"):
        if column in data.columns:
            identifiers = data[column].fillna("").astype(str)
            mask |= identifiers.str.contains(
                r"(?:^|_)SYN(?:_|$)|(?:^|_)AUG(?:_|$)",
                case=False,
                regex=True,
            )
    return mask


def load_historical_workbook(path: str | Path) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Load the original multi-sheet workbook into one canonical frame."""
    workbook_path = Path(path)
    if not workbook_path.exists():
        raise FileNotFoundError(f"Historical workbook not found: {workbook_path}")

    frames: list[pd.DataFrame] = []
    with pd.ExcelFile(workbook_path) as workbook:
        sheet_names = list(workbook.sheet_names)
        for sheet_name in sheet_names:
            header_row = _find_header_row(workbook_path, sheet_name)
            frame = pd.read_excel(
                workbook,
                sheet_name=sheet_name,
                header=header_row,
            )
            frame.columns = [str(column).strip() for column in frame.columns]
            frame = frame.rename(columns=COLUMN_ALIASES)
            if "Bulk_Order_ID" not in frame.columns:
                raise ValueError(f"Sheet {sheet_name!r} has no Bulk_Order_ID column")
            frame = frame.loc[frame["Bulk_Order_ID"].notna()].copy()
            frame["Source_Sheet"] = sheet_name
            frames.append(frame)

    if not frames:
        raise ValueError("The historical workbook contains no worksheets")

    data = pd.concat(frames, ignore_index=True, sort=False)
    missing = sorted(REQUIRED_COLUMNS.difference(data.columns))
    if missing:
        raise ValueError(f"Historical dataset is missing columns: {missing}")

    source_rows = len(data)
    generated = generated_row_mask(data)
    data = data.loc[~generated].copy().reset_index(drop=True)
    if data.empty:
        raise ValueError("No non-generated historical rows remain after filtering")

    for column in DATE_COLUMNS:
        if column in data.columns:
            data[column] = pd.to_datetime(data[column], errors="coerce")
    for column in NUMERIC_COLUMNS:
        data[column] = pd.to_numeric(data[column], errors="coerce")

    critical_columns = sorted(
        REQUIRED_COLUMNS.difference({"Risk_Type", "System_Recommendation"})
    )
    invalid = {
        column: int(data[column].isna().sum())
        for column in critical_columns
        if data[column].isna().any()
    }
    if invalid:
        raise ValueError(f"Historical dataset contains invalid required values: {invalid}")

    duplicates = int(
        data.duplicated(subset=["Bulk_Order_ID", "Production_Date"]).sum()
    )
    if duplicates:
        raise ValueError(
            "Historical dataset contains duplicate bulk-order/production-date rows: "
            f"{duplicates}"
        )

    data = data.sort_values(
        ["Bulk_Order_ID", "Production_Date", "Working_Day_No"]
    ).reset_index(drop=True)

    cumulative_from_output = data.groupby("Bulk_Order_ID")[
        "Plant_Daily_Output"
    ].cumsum()
    cumulative_mismatches = int(
        (~np.isclose(cumulative_from_output, data["Cumulative_Completed_Qty"])).sum()
    )
    cumulative_over_order = int(
        (data["Cumulative_Completed_Qty"] > data["Full_Order_Qty"]).sum()
    )

    summary = {
        "workbook": workbook_path.name,
        "worksheet_count": len(sheet_names),
        "source_rows": source_rows,
        "generated_or_augmented_rows_excluded": int(generated.sum()),
        "historical_rows_used": int(len(data)),
        "bulk_orders": int(data["Bulk_Order_ID"].nunique()),
        "styles": int(data["Style_ID"].nunique()),
        "duplicate_order_date_rows": duplicates,
        "cumulative_output_mismatch_rows": cumulative_mismatches,
        "cumulative_over_order_rows": cumulative_over_order,
    }
    return data, summary


def _actual_completion_dates(data: pd.DataFrame) -> dict[str, pd.Timestamp]:
    result: dict[str, pd.Timestamp] = {}
    for order_id, order_rows in data.groupby("Bulk_Order_ID", sort=False):
        completed = order_rows.loc[
            order_rows["Cumulative_Completed_Qty"] >= order_rows["Full_Order_Qty"]
        ]
        if not completed.empty:
            result[str(order_id)] = pd.Timestamp(completed["Production_Date"].min())
    return result


def _risk_triggers(row: pd.Series) -> list[str]:
    triggers: list[str] = []
    if row["Worker_Shortage_Count"] > 0:
        triggers.append("worker_shortage")
    if row["Machine_Breakdown_Count"] > 0:
        triggers.append("machine_breakdown")
    if row["Daily_Damage_Qty"] > row["Max_Daily_Damage_Qty"]:
        triggers.append("quality_limit")
    if not triggers and str(row["Risk_Type"]).strip() != "No Issue":
        triggers.append("schedule_or_output_risk")
    return triggers


def _is_risk_row(row: pd.Series) -> bool:
    return bool(_risk_triggers(row)) or str(row["Risk_Type"]).strip() != "No Issue"


def _payload_from_row(row: pd.Series) -> dict[str, Any]:
    return {
        "bulk_order_id": str(row["Bulk_Order_ID"]),
        "style_id": str(row["Style_ID"]),
        "buyer_name": str(row["Buyer_Name"]),
        "allocated_bulk_plant": str(row["Allocated_Bulk_Plant"]),
        "plant_location": str(row["Plant_Location"]),
        "full_order_qty": int(row["Full_Order_Qty"]),
        "bulk_order_approved_date": row["Bulk_Order_Approved_Date"].strftime(
            "%Y-%m-%d"
        ),
        "buyer_required_date": row["Buyer_Required_Date"].strftime("%Y-%m-%d"),
        "total_working_days": int(row["Total_Working_Days"]),
        "cutting_days": int(row["Cutting_Days"]),
        "sewing_days": int(row["Sewing_Days"]),
        "daily_commitment": int(row["Daily_Commitment"]),
        "production_date": row["Production_Date"].strftime("%Y-%m-%d"),
        "working_day_no": int(row["Working_Day_No"]),
        "plant_daily_output": int(row["Plant_Daily_Output"]),
        "daily_damage_qty": int(row["Daily_Damage_Qty"]),
        "max_daily_damage_qty": int(row["Max_Daily_Damage_Qty"]),
        "machine_breakdown_count": int(row["Machine_Breakdown_Count"]),
        "worker_shortage_count": int(row["Worker_Shortage_Count"]),
        "cumulative_completed_qty": int(row["Cumulative_Completed_Qty"]),
    }


def _historical_policy_category(value: Any) -> str:
    text = str(value).strip().lower()
    if "continue" in text:
        return "current_plan"
    if "operator" in text or "worker" in text:
        return "add_workers"
    if "machine" in text:
        return "repair_machines"
    if "overtime" in text or "working hours" in text:
        return "overtime"
    if "quality" in text or "damaged" in text:
        return "quality_control"
    if "another plant" in text or "reallocate" in text:
        return "manual_escalation"
    return "unmapped"


def _rounded(value: float | int | None, digits: int = 3) -> float | None:
    if value is None or pd.isna(value):
        return None
    return round(float(value), digits)


def _error_metrics(predicted: pd.Series, actual: pd.Series) -> dict[str, Any]:
    valid = predicted.notna() & actual.notna() & np.isfinite(predicted) & np.isfinite(actual)
    predicted = predicted.loc[valid].astype(float)
    actual = actual.loc[valid].astype(float)
    if predicted.empty:
        return {
            "case_count": 0,
            "mae": None,
            "rmse": None,
            "mean_error": None,
            "wape_pct": None,
            "within_10_pct": None,
        }
    errors = predicted - actual
    absolute_errors = errors.abs()
    relative = absolute_errors / actual.replace(0, np.nan)
    actual_sum = actual.abs().sum()
    return {
        "case_count": int(len(actual)),
        "mae": _rounded(absolute_errors.mean()),
        "rmse": _rounded(math.sqrt(float((errors**2).mean()))),
        "mean_error": _rounded(errors.mean()),
        "wape_pct": _rounded(absolute_errors.sum() / actual_sum * 100)
        if actual_sum
        else None,
        "within_10_pct": _rounded((relative <= 0.10).mean()),
    }


def _ratio_summary(cases: pd.DataFrame) -> dict[str, Any]:
    ratios = (
        cases["actual_next_workday_output"]
        / cases["current_daily_output"].replace(0, np.nan)
    ).replace([np.inf, -np.inf], np.nan).dropna()
    if ratios.empty:
        return {
            "case_count": 0,
            "mean_multiplier": None,
            "median_multiplier": None,
            "q25_multiplier": None,
            "q75_multiplier": None,
        }
    return {
        "case_count": int(len(ratios)),
        "mean_multiplier": _rounded(ratios.mean()),
        "median_multiplier": _rounded(ratios.median()),
        "q25_multiplier": _rounded(ratios.quantile(0.25)),
        "q75_multiplier": _rounded(ratios.quantile(0.75)),
    }


def build_historical_cases(data: pd.DataFrame) -> pd.DataFrame:
    """Replay recovery planning for risk rows that have a later observation."""
    next_rows = data.groupby("Bulk_Order_ID", sort=False).shift(-1)
    completion_dates = _actual_completion_dates(data)
    records: list[dict[str, Any]] = []

    for index, row in data.iterrows():
        next_row = next_rows.loc[index]
        if not _is_risk_row(row) or pd.isna(next_row["Production_Date"]):
            continue

        payload = _payload_from_row(row)
        plan = build_recovery_plan(
            payload,
            detected_risk_type=str(row["Risk_Type"]),
        )
        recommendation = plan.get("recommended_option") or {}
        actual_completion = completion_dates.get(str(row["Bulk_Order_ID"]))
        projected_completion_raw = recommendation.get("projected_completion_date")
        projected_completion = (
            pd.Timestamp(projected_completion_raw)
            if projected_completion_raw
            else pd.NaT
        )
        deadline = pd.Timestamp(row["Buyer_Required_Date"])
        next_completes_order = bool(
            next_row["Cumulative_Completed_Qty"] >= next_row["Full_Order_Qty"]
        )
        triggers = _risk_triggers(row)
        next_worker_shortage = int(next_row["Worker_Shortage_Count"])
        next_machine_breakdown = int(next_row["Machine_Breakdown_Count"])
        next_quality_exceeded = bool(
            next_row["Daily_Damage_Qty"] > next_row["Max_Daily_Damage_Qty"]
        )

        resolved_triggers: list[str] = []
        if (
            row["Worker_Shortage_Count"] > 0
            and next_worker_shortage < row["Worker_Shortage_Count"]
        ):
            resolved_triggers.append("worker_shortage")
        if (
            row["Machine_Breakdown_Count"] > 0
            and next_machine_breakdown < row["Machine_Breakdown_Count"]
        ):
            resolved_triggers.append("machine_breakdown")
        if (
            row["Daily_Damage_Qty"] > row["Max_Daily_Damage_Qty"]
            and not next_quality_exceeded
        ):
            resolved_triggers.append("quality_limit")

        records.append(
            {
                "bulk_order_id": str(row["Bulk_Order_ID"]),
                "style_id": str(row["Style_ID"]),
                "production_date": row["Production_Date"].strftime("%Y-%m-%d"),
                "next_production_date": next_row["Production_Date"].strftime(
                    "%Y-%m-%d"
                ),
                "risk_type": str(row["Risk_Type"]),
                "triggers": "|".join(triggers),
                "resolved_triggers_next_workday": "|".join(resolved_triggers),
                "historical_recommendation_category": _historical_policy_category(
                    row["System_Recommendation"]
                ),
                "engine_recommended_option": recommendation.get("option_id"),
                "engine_status": plan.get("status"),
                "missing_parameters": "|".join(plan.get("missing_parameters", [])),
                "current_daily_output": float(row["Plant_Daily_Output"]),
                "required_daily_rate": plan.get("required_daily_rate"),
                "engine_recommended_daily_capacity": recommendation.get(
                    "daily_capacity"
                ),
                "actual_next_workday_output": float(next_row["Plant_Daily_Output"]),
                "next_workday_completes_order": next_completes_order,
                "projected_completion_date": projected_completion.strftime("%Y-%m-%d")
                if pd.notna(projected_completion)
                else None,
                "actual_completion_date": actual_completion.strftime("%Y-%m-%d")
                if actual_completion is not None
                else None,
                "buyer_required_date": deadline.strftime("%Y-%m-%d"),
                "projected_completion_error_calendar_days": (
                    int((projected_completion - actual_completion).days)
                    if pd.notna(projected_completion) and actual_completion is not None
                    else None
                ),
                "predicted_deadline_feasible": recommendation.get(
                    "feasible_before_deadline"
                ),
                "actual_deadline_met": (
                    bool(actual_completion <= deadline)
                    if actual_completion is not None
                    else None
                ),
            }
        )

    return pd.DataFrame.from_records(records)


def _deadline_metrics(cases: pd.DataFrame) -> dict[str, Any]:
    valid = cases.loc[
        cases["predicted_deadline_feasible"].notna()
        & cases["actual_deadline_met"].notna()
    ]
    if valid.empty:
        return {
            "case_count": 0,
            "accuracy": None,
            "actual_class_counts": {},
            "both_actual_classes_present": False,
        }
    predicted = valid["predicted_deadline_feasible"].astype(bool)
    actual = valid["actual_deadline_met"].astype(bool)
    counts = actual.value_counts().to_dict()
    return {
        "case_count": int(len(valid)),
        "accuracy": _rounded((predicted == actual).mean()),
        "actual_class_counts": {
            "met_deadline": int(counts.get(True, 0)),
            "missed_deadline": int(counts.get(False, 0)),
        },
        "both_actual_classes_present": len(counts) == 2,
    }


def _calibration_evidence(cases: pd.DataFrame) -> dict[str, Any]:
    capacity_cases = cases.loc[~cases["next_workday_completes_order"]].copy()
    groups: dict[str, dict[str, Any]] = {"all_risk_cases": _ratio_summary(capacity_cases)}
    for trigger in (
        "worker_shortage",
        "machine_breakdown",
        "quality_limit",
        "schedule_or_output_risk",
    ):
        selected = capacity_cases.loc[
            capacity_cases["triggers"].str.split("|").apply(
                lambda values: trigger in values
            )
        ]
        groups[trigger] = _ratio_summary(selected)

    resolved: dict[str, dict[str, Any]] = {}
    for trigger in ("worker_shortage", "machine_breakdown", "quality_limit"):
        selected = capacity_cases.loc[
            capacity_cases["resolved_triggers_next_workday"]
            .str.split("|")
            .apply(lambda values: trigger in values)
        ]
        resolved[trigger] = _ratio_summary(selected)

    return {
        "next_workday_output_multipliers": groups,
        "when_trigger_reduces_or_resolves": resolved,
        "interpretation": (
            "These are observational output multipliers, not causal action gains."
        ),
    }


def evaluate_historical_recovery(
    data: pd.DataFrame,
    dataset_summary: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], pd.DataFrame]:
    """Return a JSON-ready report and the row-level replay cases."""
    cases = build_historical_cases(data)
    if cases.empty:
        raise ValueError("No historical risk row has a later production outcome")

    capacity_cases = cases.loc[~cases["next_workday_completes_order"]]
    baseline_metrics = _error_metrics(
        capacity_cases["current_daily_output"],
        capacity_cases["actual_next_workday_output"],
    )
    recommendation_metrics = _error_metrics(
        capacity_cases["engine_recommended_daily_capacity"],
        capacity_cases["actual_next_workday_output"],
    )

    completion_errors = pd.to_numeric(
        cases["projected_completion_error_calendar_days"], errors="coerce"
    ).dropna()
    completion_metrics = {
        "case_count": int(len(completion_errors)),
        "mae_calendar_days": _rounded(completion_errors.abs().mean())
        if len(completion_errors)
        else None,
        "mean_error_calendar_days": _rounded(completion_errors.mean())
        if len(completion_errors)
        else None,
        "within_3_calendar_days": _rounded((completion_errors.abs() <= 3).mean())
        if len(completion_errors)
        else None,
    }

    comparable_policy = cases.loc[
        cases["historical_recommendation_category"] != "unmapped"
    ]
    policy_agreement = (
        comparable_policy["historical_recommendation_category"]
        == comparable_policy["engine_recommended_option"]
    )

    available_action_fields = [
        field for field in ACTION_OUTCOME_FIELDS if field in data.columns
    ]
    missing_action_fields = [
        field for field in ACTION_OUTCOME_FIELDS if field not in data.columns
    ]
    action_labeled_rows = 0
    if available_action_fields:
        action_labeled_rows = int(
            data[list(available_action_fields)].notna().all(axis=1).sum()
        )

    actual_completion_orders = int(
        cases.dropna(subset=["actual_completion_date"])["bulk_order_id"].nunique()
    )
    order_outcomes = cases[
        ["bulk_order_id", "actual_completion_date", "buyer_required_date"]
    ].drop_duplicates(subset=["bulk_order_id"])
    actual_completion = pd.to_datetime(
        order_outcomes["actual_completion_date"], errors="coerce"
    )
    buyer_deadline = pd.to_datetime(
        order_outcomes["buyer_required_date"], errors="coerce"
    )
    dataset = dict(dataset_summary or {})
    dataset.update(
        {
            "risk_rows_with_next_workday_outcome": int(len(cases)),
            "orders_with_inferred_completion_date": actual_completion_orders,
            "capacity_cases_excluding_final_partial_day": int(len(capacity_cases)),
            "final_partial_day_cases_excluded_from_capacity_metrics": int(
                cases["next_workday_completes_order"].sum()
            ),
            "orders_completed_exactly_on_deadline": int(
                (actual_completion == buyer_deadline).sum()
            ),
            "orders_completed_before_deadline": int(
                (actual_completion < buyer_deadline).sum()
            ),
            "orders_completed_after_deadline": int(
                (actual_completion > buyer_deadline).sum()
            ),
        }
    )

    report = {
        "report_version": REPORT_VERSION,
        "scope": {
            "method": "historical next-production-day replay",
            "generated_rows_policy": (
                "Rows explicitly marked or identified as generated/augmented are excluded."
            ),
            "capacity_metric_rule": (
                "A final partial production day is excluded because its output is "
                "limited by remaining order quantity, not line capacity."
            ),
        },
        "dataset": dataset,
        "validation": {
            "current_output_as_next_workday_baseline": baseline_metrics,
            "recommended_capacity_observational_comparison": recommendation_metrics,
            "completion_date_forecast": completion_metrics,
            "deadline_feasibility": _deadline_metrics(cases),
            "historical_policy_category_agreement": {
                "case_count": int(len(comparable_policy)),
                "agreement": _rounded(policy_agreement.mean())
                if len(comparable_policy)
                else None,
                "note": (
                    "This compares recommendation categories only; it does not "
                    "show that the historical action was implemented or successful."
                ),
            },
            "engine_recommendation_counts": {
                str(key): int(value)
                for key, value in cases["engine_recommended_option"]
                .fillna("none")
                .value_counts()
                .items()
            },
            "missing_parameter_counts": {
                parameter: int(cases["missing_parameters"].str.contains(parameter).sum())
                for parameter in (
                    "planned_worker_count",
                    "planned_machine_count",
                    "expected_machine_repair_hours",
                )
            },
        },
        "calibration_evidence": _calibration_evidence(cases),
        "calibration_decision": {
            "status": "observational_only",
            "engine_parameters_updated": False,
            "action_labeled_rows": action_labeled_rows,
            "available_action_outcome_fields": available_action_fields,
            "missing_action_outcome_fields": missing_action_fields,
            "reason": (
                "The workbook records recommendations and daily outputs but not "
                "which recovery action was actually applied or its resource dose."
            ),
            "next_collection_source": (
                "Use Component 3 incident tracking decisions, recovery parameters, "
                "and daily outcomes for future causal calibration."
            ),
        },
        "limitations": [
            "Historical recommendations are prescribed text, not applied-action evidence.",
            "All observed orders in this workbook met their buyer deadline, so missed-deadline discrimination cannot be measured.",
            "The 11 orders are repeated daily observations; case counts are not independent order counts.",
            "Ten of 11 orders complete exactly on the recorded buyer deadline, while the planner also targets that deadline; the low completion-date error is not independent predictive evidence.",
            "The calendar assumes Monday-Friday production and does not include factory holidays.",
        ],
    }
    return report, cases


def run_historical_validation(
    path: str | Path,
) -> tuple[dict[str, Any], pd.DataFrame]:
    data, summary = load_historical_workbook(path)
    return evaluate_historical_recovery(data, summary)
