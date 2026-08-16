"""Train and evaluate version-2 Component 3 models.

Evaluation holds out complete real bulk orders. Only the controlled
``Augmented_Low_Risk`` rows are added to training folds; generated rows are never
used as evaluation evidence. Version-1 model files are not modified.
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
from sklearn.dummy import DummyClassifier
from sklearn.ensemble import (
    ExtraTreesClassifier,
    GradientBoostingClassifier,
    RandomForestClassifier,
)
from sklearn.linear_model import LogisticRegression
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
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from components.component3_features import FEATURES, build_feature_frame


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


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--data",
        type=Path,
        default=Path("data/component3_training_augmented.xlsx"),
    )
    parser.add_argument("--models-dir", type=Path, default=Path("models"))
    parser.add_argument("--reports-dir", type=Path, default=Path("reports/component3_v2"))
    return parser.parse_args()


def model1_candidates() -> dict[str, BaseEstimator]:
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


def model2_candidates() -> dict[str, BaseEstimator]:
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
            max_depth=10,
            min_samples_leaf=5,
            class_weight="balanced",
            random_state=RANDOM_SEED,
            n_jobs=-1,
        ),
        "gradient_boosting": GradientBoostingClassifier(
            n_estimators=300,
            learning_rate=0.07,
            max_depth=4,
            min_samples_leaf=5,
            subsample=0.8,
            random_state=RANDOM_SEED,
        ),
    }


def validate_dataset(data: pd.DataFrame) -> None:
    required = {
        "Bulk_Order_ID",
        "Risk_Type",
        "Order_Risk_Level",
        "Synthetic",
        "Data_Origin",
        "Daily_Commitment",
        "Plant_Daily_Output",
        "Machine_Breakdown_Count",
        "Worker_Shortage_Count",
        "Daily_Damage_Qty",
        "Max_Daily_Damage_Qty",
        "Working_Day_No",
        "Total_Working_Days",
        "Full_Order_Qty",
        "Cumulative_Completed_Qty",
    }
    missing = sorted(required.difference(data.columns))
    if missing:
        raise ValueError(f"Dataset is missing required columns: {missing}")
    unknown_risk_types = sorted(set(data["Risk_Type"].dropna()) - set(RISK_LABELS))
    if unknown_risk_types:
        raise ValueError(f"Unknown Risk_Type labels: {unknown_risk_types}")
    unknown_order_risk = sorted(
        set(data["Order_Risk_Level"].dropna()) - {"Low", "High"}
    )
    if unknown_order_risk:
        raise ValueError(f"Unknown Order_Risk_Level labels: {unknown_order_risk}")


def split_sources(data: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    real = data.loc[~data["Synthetic"].fillna(False).astype(bool)].copy()
    augmented = data.loc[data["Data_Origin"].eq("Augmented_Low_Risk")].copy()
    if real.empty:
        raise ValueError("No real rows were found")
    if augmented.empty:
        raise ValueError("No controlled Augmented_Low_Risk rows were found")
    overlap = set(real["Bulk_Order_ID"]) & set(augmented["Bulk_Order_ID"])
    if overlap:
        raise ValueError(f"Real and augmented order IDs overlap: {sorted(overlap)}")
    return real.reset_index(drop=True), augmented.reset_index(drop=True)


def positive_probabilities(model: BaseEstimator, X: pd.DataFrame) -> np.ndarray:
    probabilities = model.predict_proba(X)
    classes = list(model.classes_)
    return probabilities[:, classes.index(1)]


def per_order_metrics(
    real: pd.DataFrame,
    truth: np.ndarray,
    predictions: np.ndarray,
) -> dict[str, dict[str, float | int]]:
    result = real[["Bulk_Order_ID"]].copy()
    result["correct"] = truth == predictions
    summary = result.groupby("Bulk_Order_ID")["correct"].agg(["size", "mean"])
    return {
        str(order_id): {"rows": int(row["size"]), "accuracy": float(row["mean"])}
        for order_id, row in summary.iterrows()
    }


def evaluate_model1(
    candidates: dict[str, BaseEstimator],
    real: pd.DataFrame,
    augmented: pd.DataFrame,
) -> tuple[dict[str, dict], dict[str, np.ndarray]]:
    real_X = build_feature_frame(real)
    augmented_X = build_feature_frame(augmented)
    real_y = real["Risk_Type"].map(RISK_TYPE_MAP).to_numpy(dtype=int)
    augmented_y = augmented["Risk_Type"].map(RISK_TYPE_MAP).to_numpy(dtype=int)
    groups = real["Bulk_Order_ID"].to_numpy()
    splits = list(LeaveOneGroupOut().split(real_X, real_y, groups))
    evaluations: dict[str, dict] = {}
    predictions_by_candidate: dict[str, np.ndarray] = {}

    for name, candidate in candidates.items():
        predictions = np.empty(len(real), dtype=int)
        for train_indices, test_indices in splits:
            X_train = pd.concat(
                [real_X.iloc[train_indices], augmented_X], ignore_index=True
            )
            y_train = np.concatenate([real_y[train_indices], augmented_y])
            model = clone(candidate)
            model.fit(X_train, y_train)
            predictions[test_indices] = model.predict(real_X.iloc[test_indices])

        evaluations[name] = {
            "accuracy": float(accuracy_score(real_y, predictions)),
            "macro_f1": float(
                f1_score(
                    real_y,
                    predictions,
                    labels=range(len(RISK_LABELS)),
                    average="macro",
                    zero_division=0,
                )
            ),
            "weighted_f1": float(
                f1_score(real_y, predictions, average="weighted", zero_division=0)
            ),
            "confusion_matrix": confusion_matrix(
                real_y, predictions, labels=range(len(RISK_LABELS))
            ).tolist(),
            "classification_report": classification_report(
                real_y,
                predictions,
                labels=range(len(RISK_LABELS)),
                target_names=RISK_LABELS,
                output_dict=True,
                zero_division=0,
            ),
            "per_order": per_order_metrics(real, real_y, predictions),
        }
        predictions_by_candidate[name] = predictions
    return evaluations, predictions_by_candidate


def evaluate_model2(
    candidates: dict[str, BaseEstimator],
    real: pd.DataFrame,
    augmented: pd.DataFrame,
) -> tuple[dict[str, dict], dict[str, np.ndarray]]:
    real_X = build_feature_frame(real)
    augmented_X = build_feature_frame(augmented)
    real_y = real["Order_Risk_Level"].eq("High").to_numpy(dtype=int)
    augmented_y = augmented["Order_Risk_Level"].eq("High").to_numpy(dtype=int)
    groups = real["Bulk_Order_ID"].to_numpy()
    splits = list(LeaveOneGroupOut().split(real_X, real_y, groups))
    evaluations: dict[str, dict] = {}
    predictions_by_candidate: dict[str, np.ndarray] = {}

    for name, candidate in candidates.items():
        predictions = np.empty(len(real), dtype=int)
        probabilities = np.empty(len(real), dtype=float)
        for train_indices, test_indices in splits:
            X_train = pd.concat(
                [real_X.iloc[train_indices], augmented_X], ignore_index=True
            )
            y_train = np.concatenate([real_y[train_indices], augmented_y])
            model = clone(candidate)
            model.fit(X_train, y_train)
            predictions[test_indices] = model.predict(real_X.iloc[test_indices])
            probabilities[test_indices] = positive_probabilities(
                model, real_X.iloc[test_indices]
            )

        evaluations[name] = {
            "accuracy": float(accuracy_score(real_y, predictions)),
            "macro_f1": float(f1_score(real_y, predictions, average="macro", zero_division=0)),
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
            "false_low_risk_rows": int(((predictions == 0) & (real_y == 1)).sum()),
            "confusion_matrix": confusion_matrix(real_y, predictions, labels=[0, 1]).tolist(),
            "classification_report": classification_report(
                real_y,
                predictions,
                labels=[0, 1],
                target_names=["Low Risk", "High Risk"],
                output_dict=True,
                zero_division=0,
            ),
            "per_order": per_order_metrics(real, real_y, predictions),
        }
        predictions_by_candidate[name] = predictions
    return evaluations, predictions_by_candidate


def select_candidate(evaluations: dict[str, dict]) -> str:
    eligible = {name: metrics for name, metrics in evaluations.items() if not name.startswith("dummy")}
    return max(
        eligible,
        key=lambda name: (
            eligible[name]["macro_f1"],
            eligible[name]["accuracy"],
        ),
    )


def json_ready(value):
    if isinstance(value, dict):
        return {str(key): json_ready(item) for key, item in value.items()}
    if isinstance(value, list):
        return [json_ready(item) for item in value]
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        return float(value)
    return value


def main() -> None:
    args = parse_args()
    data = pd.read_excel(args.data)
    validate_dataset(data)
    real, augmented = split_sources(data)

    model1_options = model1_candidates()
    model2_options = model2_candidates()
    model1_evaluations, _ = evaluate_model1(model1_options, real, augmented)
    model2_evaluations, _ = evaluate_model2(model2_options, real, augmented)
    selected_model1 = select_candidate(model1_evaluations)
    selected_model2 = select_candidate(model2_evaluations)

    final_data = pd.concat([real, augmented], ignore_index=True)
    final_X = build_feature_frame(final_data)
    final_y1 = final_data["Risk_Type"].map(RISK_TYPE_MAP).to_numpy(dtype=int)
    final_y2 = final_data["Order_Risk_Level"].eq("High").to_numpy(dtype=int)
    final_model1 = clone(model1_options[selected_model1]).fit(final_X, final_y1)
    final_model2 = clone(model2_options[selected_model2]).fit(final_X, final_y2)

    args.models_dir.mkdir(parents=True, exist_ok=True)
    args.reports_dir.mkdir(parents=True, exist_ok=True)
    model1_path = args.models_dir / "c3_model1_risk_type_v2.pkl"
    model2_path = args.models_dir / "c3_model2_order_risk_v2.pkl"
    metadata_path = args.models_dir / "c3_model_metadata_v2.json"
    report_path = args.reports_dir / "evaluation.json"
    joblib.dump(final_model1, model1_path)
    joblib.dump(final_model2, model2_path)

    low_risk_real_orders = int(
        real.loc[real["Order_Risk_Level"].eq("Low"), "Bulk_Order_ID"].nunique()
    )
    risk_type_real_rows = {
        label: int(real["Risk_Type"].eq(label).sum()) for label in RISK_LABELS
    }
    risk_type_real_orders = {
        label: int(
            real.loc[real["Risk_Type"].eq(label), "Bulk_Order_ID"].nunique()
        )
        for label in RISK_LABELS
    }
    risk_type_model_approved = all(
        risk_type_real_rows[label] >= 20 and risk_type_real_orders[label] >= 3
        for label in RISK_LABELS
    )
    order_risk_model_approved = low_risk_real_orders >= 3
    production_approved = risk_type_model_approved and order_risk_model_approved
    approval_notes = []
    if not risk_type_model_approved:
        approval_notes.append(
            "Model 1 is experimental: every risk class needs at least 20 real rows "
            "across at least three real orders."
        )
    if not order_risk_model_approved:
        approval_notes.append(
            "Model 2 is experimental: fewer than three real Low Risk orders are available."
        )
    dataset_hash = hashlib.sha256(args.data.read_bytes()).hexdigest()
    metadata = {
        "artifact_version": "2.0.0",
        "trained_at_utc": datetime.now(timezone.utc).isoformat(),
        "production_approved": production_approved,
        "model_approval": {
            "risk_type": risk_type_model_approved,
            "order_risk": order_risk_model_approved,
        },
        "approval_notes": approval_notes or [
            "Independent real-order coverage meets the configured minimums."
        ],
        "dataset": {
            "path": str(args.data.resolve()),
            "sha256": dataset_hash,
            "real_rows": int(len(real)),
            "real_orders": int(real["Bulk_Order_ID"].nunique()),
            "augmented_training_rows": int(len(augmented)),
            "augmented_training_orders": int(augmented["Bulk_Order_ID"].nunique()),
            "excluded_existing_generated_rows": int(
                data["Data_Origin"].eq("Existing_Generated").sum()
            ),
            "real_low_risk_orders": low_risk_real_orders,
            "risk_type_real_rows": risk_type_real_rows,
            "risk_type_real_orders": risk_type_real_orders,
        },
        "features": FEATURES,
        "feature_engineering": {
            "output_gap": "Daily_Commitment - Plant_Daily_Output (negative values preserved)",
            "gap_pct": "Output_Gap / Daily_Commitment * 100",
        },
        "risk_type_mapping": RISK_TYPE_MAP,
        "order_risk_mapping": {"Low": 0, "High": 1},
        "evaluation": "LeaveOneGroupOut on real Bulk_Order_ID; augmentation used in training folds only",
        "selected_models": {
            "risk_type": selected_model1,
            "order_risk": selected_model2,
        },
        "selected_metrics": {
            "risk_type": model1_evaluations[selected_model1],
            "order_risk": model2_evaluations[selected_model2],
        },
        "versions": {
            "python": platform.python_version(),
            "scikit_learn": sklearn.__version__,
            "pandas": pd.__version__,
            "numpy": np.__version__,
            "joblib": joblib.__version__,
        },
    }
    full_report = {
        "metadata": metadata,
        "all_candidates": {
            "risk_type": model1_evaluations,
            "order_risk": model2_evaluations,
        },
    }
    metadata_path.write_text(json.dumps(json_ready(metadata), indent=2) + "\n", encoding="utf-8")
    report_path.write_text(json.dumps(json_ready(full_report), indent=2) + "\n", encoding="utf-8")

    print(f"Selected Model 1: {selected_model1}")
    print(json.dumps(model1_evaluations[selected_model1], indent=2)[:1_500])
    print(f"Selected Model 2: {selected_model2}")
    print(json.dumps(model2_evaluations[selected_model2], indent=2)[:1_500])
    print(f"Saved: {model1_path}")
    print(f"Saved: {model2_path}")
    print(f"Saved: {metadata_path}")
    print(f"Saved: {report_path}")
    print(f"Production approved: {production_approved}")


if __name__ == "__main__":
    main()
