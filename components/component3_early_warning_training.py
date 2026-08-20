"""Grouped model comparison for Component 3 three-day subtype warnings.

Step 5B intentionally trains only the binary subtype targets that passed the
Step 5A row- and order-coverage checks.  Every reported score is produced from
a prediction for a bulk order that was absent from that fold's training data.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
from pathlib import Path
from typing import Any, Iterable

import numpy as np
import pandas as pd
from sklearn.base import BaseEstimator, clone
from sklearn.dummy import DummyClassifier
from sklearn.ensemble import RandomForestClassifier
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, f1_score
from sklearn.model_selection import LeaveOneGroupOut
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.utils.class_weight import compute_sample_weight
from xgboost import XGBClassifier

from components.component3_early_warning_data import (
    EARLY_WARNING_FEATURES,
    MIN_ORDERS_PER_CLASS,
    MIN_ROWS_PER_CLASS,
    run_step5a_audit,
)


REPORT_VERSION = "component3-early-warning-step5b-v1"
ARTIFACT_VERSION = "component3-early-warning-model-v1"
RANDOM_STATE = 42

SUPPORTED_TARGETS: dict[str, dict[str, str]] = {
    "Machine_Breakdown_Within_3_Days": {
        "display_name": "Machine breakdown within 3 production days",
        "slug": "machine_breakdown",
    },
    "Quality_Limit_Within_3_Days": {
        "display_name": "Quality-limit issue within 3 production days",
        "slug": "quality_limit",
    },
    "Output_Schedule_Risk_Within_3_Days": {
        "display_name": "Output or schedule risk within 3 production days",
        "slug": "output_schedule_risk",
    },
}


@dataclass(frozen=True)
class CandidateModel:
    """A reproducible candidate and its model-selection role."""

    name: str
    estimator: BaseEstimator
    selectable: bool = True
    balanced_fit_weights: bool = False


def build_candidate_models(
    *,
    random_state: int = RANDOM_STATE,
) -> dict[str, CandidateModel]:
    """Return the fixed Step 5B baseline and candidate model definitions."""
    return {
        "dummy_prior": CandidateModel(
            name="dummy_prior",
            estimator=Pipeline(
                [
                    ("imputer", SimpleImputer(strategy="median")),
                    ("model", DummyClassifier(strategy="prior")),
                ]
            ),
            selectable=False,
        ),
        "logistic_regression": CandidateModel(
            name="logistic_regression",
            estimator=Pipeline(
                [
                    ("imputer", SimpleImputer(strategy="median")),
                    ("scaler", StandardScaler()),
                    (
                        "model",
                        LogisticRegression(
                            class_weight="balanced",
                            max_iter=5_000,
                            random_state=random_state,
                        ),
                    ),
                ]
            ),
        ),
        "random_forest": CandidateModel(
            name="random_forest",
            estimator=Pipeline(
                [
                    ("imputer", SimpleImputer(strategy="median")),
                    (
                        "model",
                        RandomForestClassifier(
                            n_estimators=300,
                            min_samples_leaf=2,
                            class_weight="balanced_subsample",
                            random_state=random_state,
                            n_jobs=1,
                        ),
                    ),
                ]
            ),
        ),
        "xgboost": CandidateModel(
            name="xgboost",
            estimator=Pipeline(
                [
                    ("imputer", SimpleImputer(strategy="median")),
                    (
                        "model",
                        XGBClassifier(
                            n_estimators=250,
                            max_depth=3,
                            learning_rate=0.05,
                            subsample=0.9,
                            colsample_bytree=0.8,
                            eval_metric="logloss",
                            random_state=random_state,
                            n_jobs=1,
                        ),
                    ),
                ]
            ),
            balanced_fit_weights=True,
        ),
    }


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _frame_sha256(data: pd.DataFrame) -> str:
    rendered = data.to_csv(index=False, lineterminator="\n").encode("utf-8")
    return hashlib.sha256(rendered).hexdigest()


def _rounded(value: float) -> float:
    return round(float(value), 6)


def _metrics(actual: pd.Series, predicted: np.ndarray) -> dict[str, float]:
    return {
        "accuracy": _rounded(accuracy_score(actual, predicted)),
        "macro_f1": _rounded(
            f1_score(actual, predicted, average="macro", zero_division=0)
        ),
        "f1": _rounded(f1_score(actual, predicted, zero_division=0)),
    }


def _class_coverage(labelled: pd.DataFrame, target: str) -> dict[str, Any]:
    target_values = labelled[target].astype(int)
    positive = target_values.eq(1)
    negative = target_values.eq(0)
    return {
        "positive_rows": int(positive.sum()),
        "negative_rows": int(negative.sum()),
        "positive_orders": int(
            labelled.loc[positive, "Bulk_Order_ID"].nunique()
        ),
        "negative_orders": int(
            labelled.loc[negative, "Bulk_Order_ID"].nunique()
        ),
    }


def _validate_training_data(labelled: pd.DataFrame, targets: Iterable[str]) -> None:
    required = {"Bulk_Order_ID", *EARLY_WARNING_FEATURES, *targets}
    missing = sorted(required.difference(labelled.columns))
    if missing:
        raise ValueError(f"Step 5B dataset is missing required columns: {missing}")
    if labelled.empty:
        raise ValueError("Step 5B dataset has no eligible stable-day rows")
    if labelled["Bulk_Order_ID"].isna().any():
        raise ValueError("Bulk_Order_ID cannot be missing during grouped evaluation")
    try:
        numeric_features = labelled[EARLY_WARNING_FEATURES].apply(
            pd.to_numeric,
            errors="raise",
        )
    except (TypeError, ValueError) as exc:
        raise ValueError("Step 5B model features must be numeric") from exc
    if numeric_features.isna().all(axis=0).any():
        empty_features = numeric_features.columns[
            numeric_features.isna().all(axis=0)
        ].tolist()
        raise ValueError(f"Model features contain all-null columns: {empty_features}")
    finite_values = numeric_features.to_numpy(dtype=float, na_value=np.nan)
    if np.isinf(finite_values).any():
        raise ValueError("Step 5B model features cannot contain infinite values")

    for target in targets:
        if labelled[target].isna().any():
            raise ValueError(f"{target} cannot contain missing labels")
        values = set(labelled[target].unique().tolist())
        if values != {0, 1}:
            raise ValueError(f"{target} must contain both binary classes")
        coverage = _class_coverage(labelled, target)
        if min(coverage["positive_rows"], coverage["negative_rows"]) < MIN_ROWS_PER_CLASS:
            raise ValueError(
                f"{target} does not meet the minimum {MIN_ROWS_PER_CLASS} rows per class"
            )
        if min(coverage["positive_orders"], coverage["negative_orders"]) < MIN_ORDERS_PER_CLASS:
            raise ValueError(
                f"{target} does not meet the minimum {MIN_ORDERS_PER_CLASS} orders per class"
            )


def _fit_candidate(
    candidate: CandidateModel,
    features: pd.DataFrame,
    target: pd.Series,
) -> BaseEstimator:
    estimator = clone(candidate.estimator)
    if candidate.balanced_fit_weights:
        weights = compute_sample_weight(class_weight="balanced", y=target)
        estimator.fit(features, target, model__sample_weight=weights)
    else:
        estimator.fit(features, target)
    return estimator


def evaluate_candidate(
    labelled: pd.DataFrame,
    target: str,
    candidate: CandidateModel,
) -> tuple[dict[str, float], dict[str, Any]]:
    """Return order-held-out aggregate metrics and validation evidence."""
    features = labelled[EARLY_WARNING_FEATURES].astype(float)
    actual = labelled[target].astype(int).reset_index(drop=True)
    groups = labelled["Bulk_Order_ID"].astype(str).reset_index(drop=True)
    features = features.reset_index(drop=True)
    predicted = np.full(len(labelled), -1, dtype=int)
    test_counts = np.zeros(len(labelled), dtype=int)
    held_out_orders: list[str] = []
    group_overlap_detected = False

    splitter = LeaveOneGroupOut()
    for train_indexes, test_indexes in splitter.split(features, actual, groups):
        train_groups = set(groups.iloc[train_indexes])
        test_groups = set(groups.iloc[test_indexes])
        group_overlap_detected |= bool(train_groups.intersection(test_groups))
        held_out_orders.extend(sorted(test_groups))
        if actual.iloc[train_indexes].nunique() != 2:
            raise ValueError(
                f"{target} has a Leave-One-Order-Out fold with one training class"
            )

        estimator = _fit_candidate(
            candidate,
            features.iloc[train_indexes],
            actual.iloc[train_indexes],
        )
        predicted[test_indexes] = estimator.predict(features.iloc[test_indexes])
        test_counts[test_indexes] += 1

    every_row_evaluated_once = bool(np.all(test_counts == 1))
    if not every_row_evaluated_once or np.any(predicted < 0):
        raise RuntimeError("Grouped evaluation did not produce one prediction per row")
    if group_overlap_detected:
        raise RuntimeError("Bulk order leakage was detected between train and test")

    validation = {
        "fold_count": int(groups.nunique()),
        "held_out_orders": sorted(set(held_out_orders)),
        "every_row_evaluated_once": every_row_evaluated_once,
        "train_test_group_overlap_detected": group_overlap_detected,
    }
    return _metrics(actual, predicted), validation


def train_early_warning_models(
    labelled: pd.DataFrame,
    *,
    target_names: Iterable[str] | None = None,
    candidate_names: Iterable[str] | None = None,
    random_state: int = RANDOM_STATE,
) -> tuple[dict[str, Any], pd.DataFrame, dict[str, dict[str, Any]]]:
    """Compare candidates and refit one research artifact for each target."""
    targets = list(target_names or SUPPORTED_TARGETS)
    unsupported = sorted(set(targets).difference(SUPPORTED_TARGETS))
    if unsupported:
        raise ValueError(f"Unsupported Step 5B targets: {unsupported}")

    all_candidates = build_candidate_models(random_state=random_state)
    names = list(candidate_names or all_candidates)
    unknown_candidates = sorted(set(names).difference(all_candidates))
    if unknown_candidates:
        raise ValueError(f"Unknown Step 5B model candidates: {unknown_candidates}")
    candidates = [all_candidates[name] for name in names]
    if not any(candidate.selectable for candidate in candidates):
        raise ValueError("At least one selectable model candidate is required")

    _validate_training_data(labelled, targets)
    target_reports: dict[str, Any] = {}
    comparison_rows: list[dict[str, Any]] = []
    artifacts: dict[str, dict[str, Any]] = {}

    for target in targets:
        candidate_results: list[dict[str, Any]] = []
        validation_evidence: dict[str, Any] | None = None
        for candidate in candidates:
            metrics, validation = evaluate_candidate(labelled, target, candidate)
            validation_evidence = validation_evidence or validation
            result = {
                "model": candidate.name,
                "selectable": candidate.selectable,
                **metrics,
            }
            candidate_results.append(result)

        selectable_results = [
            result for result in candidate_results if result["selectable"]
        ]
        selected_result = max(
            selectable_results,
            key=lambda result: (
                result["macro_f1"],
                result["f1"],
                result["accuracy"],
                result["model"],
            ),
        )
        selected_name = str(selected_result["model"])
        selected_candidate = all_candidates[selected_name]
        final_estimator = _fit_candidate(
            selected_candidate,
            labelled[EARLY_WARNING_FEATURES].astype(float),
            labelled[target].astype(int),
        )
        target_info = SUPPORTED_TARGETS[target]
        artifact_path = (
            f"models/c3_early_warning_{target_info['slug']}_v1.joblib"
        )
        coverage = _class_coverage(labelled, target)
        target_report = {
            "display_name": target_info["display_name"],
            "class_coverage": coverage,
            "candidate_metrics": candidate_results,
            "selected_model": selected_name,
            "selected_metrics": {
                key: selected_result[key]
                for key in ("accuracy", "macro_f1", "f1")
            },
            "artifact_path": artifact_path,
            "production_approved": False,
            "validation": validation_evidence,
        }
        target_reports[target] = target_report
        artifacts[target] = {
            "artifact_version": ARTIFACT_VERSION,
            "target": target,
            "display_name": target_info["display_name"],
            "horizon_production_days": 3,
            "model_name": selected_name,
            "features": list(EARLY_WARNING_FEATURES),
            "decision_threshold": 0.5,
            "validation_metrics": target_report["selected_metrics"],
            "training_rows": int(len(labelled)),
            "training_orders": int(labelled["Bulk_Order_ID"].nunique()),
            "class_coverage": coverage,
            "production_approved": False,
            "estimator": final_estimator,
        }
        for result in candidate_results:
            comparison_rows.append(
                {
                    "Target": target,
                    "Model": result["model"],
                    "Accuracy": result["accuracy"],
                    "Macro_F1": result["macro_f1"],
                    "F1": result["f1"],
                    "Selected": result["model"] == selected_name,
                    "Baseline": not result["selectable"],
                }
            )

    experiment = {
        "targets": target_reports,
        "selection_rule": (
            "Highest aggregate unseen-order Macro-F1; ties use F1, then Accuracy. "
            "The dummy prior is a non-selectable baseline."
        ),
    }
    comparison = pd.DataFrame.from_records(comparison_rows)
    return experiment, comparison, artifacts


def run_step5b_experiment(
    path: str | Path,
    *,
    candidate_names: Iterable[str] | None = None,
) -> tuple[dict[str, Any], pd.DataFrame, dict[str, dict[str, Any]]]:
    """Build Step 5A labels, run grouped comparison, and return artifacts."""
    source_path = Path(path)
    step5a_report, labelled = run_step5a_audit(source_path)
    supported_by_audit = set(
        step5a_report.get("supported_research_subtype_targets", [])
    )
    targets = [
        target for target in SUPPORTED_TARGETS if target in supported_by_audit
    ]
    if set(targets) != set(SUPPORTED_TARGETS):
        missing = sorted(set(SUPPORTED_TARGETS).difference(targets))
        raise ValueError(
            "Step 5A did not approve all configured Step 5B targets: "
            f"{missing}"
        )

    experiment, comparison, artifacts = train_early_warning_models(
        labelled,
        target_names=targets,
        candidate_names=candidate_names,
    )
    generated_at = datetime.now(timezone.utc).isoformat()
    source_dataset = {
        **step5a_report.get("source_dataset", {}),
        "path": source_path.name,
        "sha256": _file_sha256(source_path),
        "labelled_rows_sha256": _frame_sha256(labelled),
        "synthetic_rows_used": 0,
    }
    for artifact in artifacts.values():
        artifact["trained_at_utc"] = generated_at
        artifact["source_dataset"] = dict(source_dataset)
        artifact["report_version"] = REPORT_VERSION
    report = {
        "report_version": REPORT_VERSION,
        "generated_at_utc": generated_at,
        "scope": "Research-only three-production-day subtype early warnings",
        "production_approved": False,
        "source_dataset": source_dataset,
        "dataset": {
            "eligible_stable_rows": int(len(labelled)),
            "independent_bulk_orders": int(labelled["Bulk_Order_ID"].nunique()),
            "model_feature_count": len(EARLY_WARNING_FEATURES),
            "model_features": list(EARLY_WARNING_FEATURES),
        },
        "protocol": {
            "validation": "Leave-One-Group-Out",
            "group_column": "Bulk_Order_ID",
            "fold_count": int(labelled["Bulk_Order_ID"].nunique()),
            "preprocessing_fitted_inside_each_training_fold": True,
            "test_order_never_used_to_fit_its_prediction": True,
            "decision_threshold": 0.5,
            "reported_metrics": ["accuracy", "macro_f1", "f1"],
            "selection_rule": experiment["selection_rule"],
            "final_refit": (
                "After model selection, the selected pipeline is refit on all "
                "eligible rows for a research artifact."
            ),
        },
        "targets": experiment["targets"],
        "limitations": [
            "The 174 eligible rows come from only 11 independent bulk orders.",
            (
                "The same grouped evaluation is used for model selection, so "
                "these are research comparison scores rather than a locked "
                "final test."
            ),
            (
                "No general emergency or worker-shortage early-warning model "
                "is trained because Step 5A did not approve those targets."
            ),
            (
                "The final refitted artifacts require validation on new, "
                "untouched real orders before production approval."
            ),
        ],
        "decision": (
            "Keep all three artifacts research-only. Integrate them behind an "
            "experimental early-warning response and validate on new real orders."
        ),
    }
    return report, comparison, artifacts
