"""Train deadline-aware Component 3 Model 2 V3 for research use.

Evaluation holds out complete observed real orders. Explicitly augmented Low
Risk trajectories are used only in training folds and never as validation
evidence.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
from datetime import datetime, timezone
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import sklearn
from sklearn.base import BaseEstimator, clone
from sklearn.metrics import (
    accuracy_score,
    classification_report,
    confusion_matrix,
    f1_score,
    precision_score,
    recall_score,
    roc_auc_score,
)
from sklearn.model_selection import LeaveOneGroupOut

from components.component3_order_risk_features import (
    ORDER_RISK_FEATURES,
    build_order_risk_feature_frame,
)
from train_component3_v2 import (
    json_ready,
    model2_candidates,
    per_order_metrics,
    positive_probabilities,
    select_candidate,
    split_sources,
    validate_dataset,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--data",
        type=Path,
        default=Path("data/component3_training_balanced_research_v2.xlsx"),
    )
    parser.add_argument(
        "--model-output",
        type=Path,
        default=Path("models/c3_model2_order_risk_v3.pkl"),
    )
    parser.add_argument(
        "--metadata-output",
        type=Path,
        default=Path("models/c3_model2_metadata_v3.json"),
    )
    parser.add_argument(
        "--report-output",
        type=Path,
        default=Path("reports/component3_model2_v3/evaluation.json"),
    )
    return parser.parse_args()


def evaluate_candidates(
    candidates: dict[str, BaseEstimator],
    real: pd.DataFrame,
    augmented: pd.DataFrame,
) -> dict[str, dict]:
    real_x = build_order_risk_feature_frame(real)
    augmented_x = build_order_risk_feature_frame(augmented)
    real_y = real["Order_Risk_Level"].eq("High").to_numpy(dtype=int)
    augmented_y = augmented["Order_Risk_Level"].eq("High").to_numpy(dtype=int)
    groups = real["Bulk_Order_ID"].to_numpy()
    splits = list(LeaveOneGroupOut().split(real_x, real_y, groups))
    evaluations: dict[str, dict] = {}

    for name, candidate in candidates.items():
        predictions = np.empty(len(real), dtype=int)
        probabilities = np.empty(len(real), dtype=float)
        for train_indices, test_indices in splits:
            train_x = pd.concat(
                [real_x.iloc[train_indices], augmented_x],
                ignore_index=True,
            )
            train_y = np.concatenate([real_y[train_indices], augmented_y])
            model = clone(candidate)
            model.fit(train_x, train_y)
            predictions[test_indices] = model.predict(real_x.iloc[test_indices])
            probabilities[test_indices] = positive_probabilities(
                model,
                real_x.iloc[test_indices],
            )

        evaluations[name] = {
            "accuracy": float(accuracy_score(real_y, predictions)),
            "macro_f1": float(
                f1_score(real_y, predictions, average="macro", zero_division=0)
            ),
            "weighted_f1": float(
                f1_score(real_y, predictions, average="weighted", zero_division=0)
            ),
            "roc_auc": float(roc_auc_score(real_y, probabilities)),
            "low_risk_precision": float(
                precision_score(real_y, predictions, pos_label=0, zero_division=0)
            ),
            "low_risk_recall": float(
                recall_score(real_y, predictions, pos_label=0, zero_division=0)
            ),
            "high_risk_recall": float(
                recall_score(real_y, predictions, pos_label=1, zero_division=0)
            ),
            "false_low_risk_rows": int(
                ((predictions == 0) & (real_y == 1)).sum()
            ),
            "confusion_matrix": confusion_matrix(
                real_y,
                predictions,
                labels=[0, 1],
            ).tolist(),
            "classification_report": classification_report(
                real_y,
                predictions,
                labels=[0, 1],
                target_names=["Low Risk", "High Risk"],
                output_dict=True,
                zero_division=0,
            ),
            "per_order": per_order_metrics(
                real,
                real_y,
                predictions,
            ),
        }
    return evaluations


def main() -> None:
    args = parse_args()
    data = pd.read_excel(args.data)
    validate_dataset(data)
    real, augmented = split_sources(data)
    evaluations = evaluate_candidates(model2_candidates(), real, augmented)
    selected = select_candidate(evaluations)

    final_data = pd.concat([real, augmented], ignore_index=True)
    final_x = build_order_risk_feature_frame(final_data)
    final_y = final_data["Order_Risk_Level"].eq("High").to_numpy(dtype=int)
    model = clone(model2_candidates()[selected]).fit(final_x, final_y)

    real_low_risk_orders = int(
        real.loc[
            real["Order_Risk_Level"].eq("Low"),
            "Bulk_Order_ID",
        ].nunique()
    )
    metadata = {
        "artifact_version": "3.0.0",
        "trained_at_utc": datetime.now(timezone.utc).isoformat(),
        "production_approved": False,
        "approval_note": (
            "Research-only Model 2: independent real Low Risk order coverage "
            "remains below the configured production minimum."
        ),
        "dataset": {
            "path": str(args.data.resolve()),
            "sha256": hashlib.sha256(args.data.read_bytes()).hexdigest(),
            "real_rows": int(len(real)),
            "real_orders": int(real["Bulk_Order_ID"].nunique()),
            "real_low_risk_orders": real_low_risk_orders,
            "augmented_training_rows": int(len(augmented)),
            "augmented_training_orders": int(
                augmented["Bulk_Order_ID"].nunique()
            ),
            "augmentation_versions": sorted(
                str(value)
                for value in augmented["Augmentation_Version"].dropna().unique()
            ),
        },
        "features": ORDER_RISK_FEATURES,
        "feature_policy": {
            "known_at_prediction_time_only": True,
            "actual_completion_date_excluded": True,
            "augmented_rows_excluded_from_validation": True,
        },
        "evaluation": (
            "LeaveOneGroupOut on observed real Bulk_Order_ID; controlled "
            "augmentation used in training folds only"
        ),
        "selected_model": selected,
        "selected_metrics": evaluations[selected],
        "versions": {
            "python": platform.python_version(),
            "scikit_learn": sklearn.__version__,
            "pandas": pd.__version__,
            "numpy": np.__version__,
            "joblib": joblib.__version__,
        },
    }
    report = {
        "metadata": metadata,
        "all_candidates": evaluations,
    }

    args.model_output.parent.mkdir(parents=True, exist_ok=True)
    args.metadata_output.parent.mkdir(parents=True, exist_ok=True)
    args.report_output.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(model, args.model_output)
    args.metadata_output.write_text(
        json.dumps(json_ready(metadata), indent=2) + "\n",
        encoding="utf-8",
    )
    args.report_output.write_text(
        json.dumps(json_ready(report), indent=2) + "\n",
        encoding="utf-8",
    )

    print(f"Selected Model 2 V3: {selected}")
    print(json.dumps(evaluations[selected], indent=2)[:2_500])
    print(f"Saved: {args.model_output}")
    print(f"Saved: {args.metadata_output}")
    print(f"Saved: {args.report_output}")
    print("Production approved: False (research prototype)")


if __name__ == "__main__":
    main()
