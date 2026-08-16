"""Audit Component 3 data and evaluation methodology.

This script deliberately does not overwrite production model artifacts. It reports
row-level and order-grouped evaluation separately so daily records from the same
bulk order cannot silently leak into both training and test sets.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd
import sklearn
from sklearn.dummy import DummyClassifier
from sklearn.ensemble import ExtraTreesClassifier, RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, classification_report, f1_score
from sklearn.model_selection import LeaveOneGroupOut, cross_val_predict, train_test_split
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler


RANDOM_SEED = 42
RISK_LABELS = [
    "No Issue",
    "Minor Delay",
    "Working Hours Issue",
    "Worker Issue",
    "Commitment Too Low",
    "Machine Breakdown Issue",
    "Quality Issue",
]
RISK_TYPE_MAP = {label: index for index, label in enumerate(RISK_LABELS)}

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


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", type=Path, required=True, help="Component 3 .xlsx dataset")
    parser.add_argument("--json-output", type=Path, help="Optional path for the audit report")
    return parser.parse_args()


def synthetic_mask(df: pd.DataFrame) -> pd.Series:
    """Detect explicitly marked and clearly identified generated records."""
    if "Synthetic" in df.columns:
        explicit = df["Synthetic"].fillna(False).astype(bool)
    else:
        explicit = pd.Series(False, index=df.index)

    identifier_mask = pd.Series(False, index=df.index)
    for column in ("Bulk_Order_ID", "Style_ID"):
        if column in df.columns:
            identifier_mask |= df[column].astype(str).str.contains("SYN", case=False, na=False)
    return explicit | identifier_mask


def model1_candidates() -> dict[str, object]:
    return {
        "dummy_most_frequent": DummyClassifier(strategy="most_frequent"),
        "logistic_regression": make_pipeline(
            StandardScaler(),
            LogisticRegression(
                class_weight="balanced",
                max_iter=5_000,
                random_state=RANDOM_SEED,
            ),
        ),
        "random_forest": RandomForestClassifier(
            n_estimators=300,
            max_depth=12,
            min_samples_leaf=3,
            class_weight="balanced",
            random_state=RANDOM_SEED,
            n_jobs=-1,
        ),
        "extra_trees": ExtraTreesClassifier(
            n_estimators=300,
            max_depth=12,
            min_samples_leaf=3,
            class_weight="balanced",
            random_state=RANDOM_SEED,
            n_jobs=-1,
        ),
    }


def validate_schema(df: pd.DataFrame) -> None:
    required = set(FEATURES) | {
        "Bulk_Order_ID",
        "Style_ID",
        "Risk_Type",
        "Order_Risk_Level",
    }
    missing = sorted(required.difference(df.columns))
    if missing:
        raise ValueError(f"Dataset is missing required columns: {missing}")


def evaluate_random_row_split(real_df: pd.DataFrame) -> dict[str, float]:
    """Diagnostic only; this split is not valid as production evidence."""
    indices = np.arange(len(real_df))
    y = real_df["Risk_Type"].map(RISK_TYPE_MAP)
    train_idx, test_idx = train_test_split(
        indices,
        test_size=0.2,
        stratify=y,
        random_state=RANDOM_SEED,
    )
    model = model1_candidates()["random_forest"]
    model.fit(real_df.iloc[train_idx][FEATURES], y.iloc[train_idx])
    predictions = model.predict(real_df.iloc[test_idx][FEATURES])
    return {
        "accuracy": float(accuracy_score(y.iloc[test_idx], predictions)),
        "macro_f1": float(
            f1_score(
                y.iloc[test_idx],
                predictions,
                labels=range(len(RISK_LABELS)),
                average="macro",
                zero_division=0,
            )
        ),
        "shared_orders_between_train_and_test": int(
            len(
                set(real_df.iloc[train_idx]["Bulk_Order_ID"])
                & set(real_df.iloc[test_idx]["Bulk_Order_ID"])
            )
        ),
    }


def evaluate_model1_grouped(real_df: pd.DataFrame) -> tuple[dict[str, dict], dict[str, str]]:
    X = real_df[FEATURES]
    y = real_df["Risk_Type"].map(RISK_TYPE_MAP)
    groups = real_df["Bulk_Order_ID"]
    cv = LeaveOneGroupOut()
    summaries: dict[str, dict] = {}
    reports: dict[str, str] = {}

    for name, model in model1_candidates().items():
        predictions = cross_val_predict(model, X, y, groups=groups, cv=cv, n_jobs=1)
        summaries[name] = {
            "accuracy": float(accuracy_score(y, predictions)),
            "macro_f1": float(
                f1_score(
                    y,
                    predictions,
                    labels=range(len(RISK_LABELS)),
                    average="macro",
                    zero_division=0,
                )
            ),
        }
        reports[name] = classification_report(
            y,
            predictions,
            labels=range(len(RISK_LABELS)),
            target_names=RISK_LABELS,
            zero_division=0,
        )
    return summaries, reports


def audit(data_path: Path) -> dict:
    df = pd.read_excel(data_path)
    validate_schema(df)
    generated = synthetic_mask(df)
    real_df = df.loc[~generated].copy().reset_index(drop=True)

    risk_counts = real_df["Risk_Type"].value_counts().reindex(RISK_LABELS, fill_value=0)
    order_target_by_group = pd.crosstab(real_df["Bulk_Order_ID"], real_df["Order_Risk_Level"])
    low_risk_groups = int((order_target_by_group.get("Low", 0) > 0).sum())
    high_risk_groups = int((order_target_by_group.get("High", 0) > 0).sum())

    grouped_scores, grouped_reports = evaluate_model1_grouped(real_df)
    model2_grouped_evaluation_possible = low_risk_groups >= 2 and high_risk_groups >= 2

    findings = []
    if generated.any():
        findings.append(
            "The consolidated dataset contains records explicitly marked or identified as synthetic."
        )
    findings.append(
        "Daily rows from the same order must be kept in one fold; random row splitting leaks order context."
    )
    if not model2_grouped_evaluation_possible:
        findings.append(
            "Model 2 cannot be validated across unseen orders because one target class occurs in fewer than two real orders."
        )
    rare_classes = risk_counts[risk_counts < 20].to_dict()
    if rare_classes:
        findings.append(f"Real-data risk classes with fewer than 20 rows: {rare_classes}")

    return {
        "data_path": str(data_path.resolve()),
        "versions": {
            "python_note": "Record the exact Python version in the final training environment.",
            "pandas": pd.__version__,
            "scikit_learn": sklearn.__version__,
        },
        "dataset": {
            "total_rows": int(len(df)),
            "real_rows": int(len(real_df)),
            "synthetic_or_generated_rows": int(generated.sum()),
            "real_bulk_orders": int(real_df["Bulk_Order_ID"].nunique()),
            "real_styles": int(real_df["Style_ID"].nunique()),
            "real_risk_type_counts": {key: int(value) for key, value in risk_counts.items()},
            "real_order_risk_counts": {
                key: int(value)
                for key, value in real_df["Order_Risk_Level"].value_counts().items()
            },
            "real_low_risk_order_groups": low_risk_groups,
            "real_high_risk_order_groups": high_risk_groups,
        },
        "diagnostic_random_row_split": evaluate_random_row_split(real_df),
        "model1_leave_one_order_out": grouped_scores,
        "model1_random_forest_classification_report": grouped_reports["random_forest"],
        "model2_grouped_evaluation_possible": model2_grouped_evaluation_possible,
        "production_candidate_approved": False,
        "findings": findings,
    }


def main() -> None:
    args = parse_args()
    report = audit(args.data)
    rendered = json.dumps(report, indent=2)
    print(rendered)
    if args.json_output:
        args.json_output.parent.mkdir(parents=True, exist_ok=True)
        args.json_output.write_text(rendered + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
