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
from sklearn.metrics import (
    accuracy_score,
    brier_score_loss,
    f1_score,
    log_loss,
)
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


REPORT_VERSION = "component3-early-warning-step5b-calibrated-v2"
ARTIFACT_VERSION = "component3-early-warning-model-calibrated-v2"
RANDOM_STATE = 42
CALIBRATION_METHOD = "grouped_sigmoid_on_logit"
CALIBRATION_BINS = 10

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


class GroupedSigmoidCalibratedClassifier:
    """Binary classifier with a grouped out-of-fold sigmoid calibrator.

    The base estimator is fitted on all eligible rows.  The sigmoid mapping is
    fitted separately from probabilities created while each bulk order was
    held out, so no order calibrates its own training prediction.
    """

    def __init__(
        self,
        base_estimator: BaseEstimator,
        calibration_model: LogisticRegression,
    ) -> None:
        self.base_estimator = base_estimator
        self.calibration_model = calibration_model
        self.classes_ = np.asarray([0, 1], dtype=int)

    def raw_predict_proba(self, features: pd.DataFrame) -> np.ndarray:
        positive = _positive_probabilities(self.base_estimator, features)
        return np.column_stack((1.0 - positive, positive))

    def predict_proba(self, features: pd.DataFrame) -> np.ndarray:
        raw_positive = self.raw_predict_proba(features)[:, 1]
        calibrated = _apply_sigmoid_calibrator(
            self.calibration_model,
            raw_positive,
        )
        return np.column_stack((1.0 - calibrated, calibrated))

    def predict(self, features: pd.DataFrame) -> np.ndarray:
        return (self.predict_proba(features)[:, 1] >= 0.5).astype(int)


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


def _positive_probabilities(
    estimator: BaseEstimator,
    features: pd.DataFrame,
) -> np.ndarray:
    """Return a finite positive-class probability vector."""
    classes = [int(value) for value in estimator.classes_]
    if 1 not in classes:
        raise ValueError("Fitted candidate does not contain the positive class")
    probabilities = np.asarray(estimator.predict_proba(features), dtype=float)
    positive = probabilities[:, classes.index(1)]
    if not np.isfinite(positive).all():
        raise ValueError("Fitted candidate returned non-finite probabilities")
    return np.clip(positive, 0.0, 1.0)


def _probability_logits(probabilities: np.ndarray) -> np.ndarray:
    clipped = np.clip(np.asarray(probabilities, dtype=float), 1e-6, 1 - 1e-6)
    return np.log(clipped / (1.0 - clipped)).reshape(-1, 1)


def _fit_sigmoid_calibrator(
    raw_probabilities: np.ndarray,
    actual: pd.Series | np.ndarray,
    *,
    random_state: int = RANDOM_STATE,
) -> LogisticRegression:
    labels = np.asarray(actual, dtype=int)
    if set(np.unique(labels).tolist()) != {0, 1}:
        raise ValueError("Sigmoid calibration requires both binary classes")
    calibrator = LogisticRegression(
        C=1.0,
        max_iter=5_000,
        random_state=random_state,
    )
    calibrator.fit(_probability_logits(raw_probabilities), labels)
    return calibrator


def _apply_sigmoid_calibrator(
    calibrator: LogisticRegression,
    raw_probabilities: np.ndarray,
) -> np.ndarray:
    classes = [int(value) for value in calibrator.classes_]
    if 1 not in classes:
        raise ValueError("Sigmoid calibrator does not contain the positive class")
    calibrated = calibrator.predict_proba(
        _probability_logits(raw_probabilities)
    )[:, classes.index(1)]
    if not np.isfinite(calibrated).all():
        raise ValueError("Sigmoid calibrator returned non-finite probabilities")
    return np.clip(calibrated, 0.0, 1.0)


def _expected_calibration_error(
    actual: np.ndarray,
    probabilities: np.ndarray,
    *,
    bin_count: int = CALIBRATION_BINS,
) -> tuple[float, list[dict[str, Any]]]:
    """Return equal-width ECE and compact reliability-bin evidence."""
    labels = np.asarray(actual, dtype=int)
    scores = np.clip(np.asarray(probabilities, dtype=float), 0.0, 1.0)
    edges = np.linspace(0.0, 1.0, bin_count + 1)
    indexes = np.minimum(np.digitize(scores, edges[1:-1]), bin_count - 1)
    ece = 0.0
    bins: list[dict[str, Any]] = []
    for index in range(bin_count):
        mask = indexes == index
        count = int(mask.sum())
        if count == 0:
            continue
        mean_probability = float(scores[mask].mean())
        observed_rate = float(labels[mask].mean())
        ece += (count / len(labels)) * abs(mean_probability - observed_rate)
        bins.append(
            {
                "lower": _rounded(edges[index]),
                "upper": _rounded(edges[index + 1]),
                "rows": count,
                "mean_probability": _rounded(mean_probability),
                "observed_positive_rate": _rounded(observed_rate),
            }
        )
    return _rounded(ece), bins


def _probability_metrics(
    actual: pd.Series | np.ndarray,
    probabilities: np.ndarray,
) -> dict[str, Any]:
    labels = np.asarray(actual, dtype=int)
    scores = np.clip(np.asarray(probabilities, dtype=float), 1e-6, 1 - 1e-6)
    ece, bins = _expected_calibration_error(labels, scores)
    return {
        "brier_score": _rounded(brier_score_loss(labels, scores)),
        "log_loss": _rounded(log_loss(labels, scores, labels=[0, 1])),
        "expected_calibration_error": ece,
        "reliability_bins": bins,
    }


def _select_decision_threshold(
    actual: pd.Series | np.ndarray,
    probabilities: np.ndarray,
) -> tuple[float, dict[str, float]]:
    """Select a deterministic Macro-F1 threshold from grouped OOF scores."""
    labels = np.asarray(actual, dtype=int)
    scores = np.clip(np.asarray(probabilities, dtype=float), 0.0, 1.0)
    unique_scores = np.unique(scores)
    if len(unique_scores) == 1:
        candidates = np.asarray([0.5, unique_scores[0]], dtype=float)
    else:
        midpoints = (unique_scores[:-1] + unique_scores[1:]) / 2.0
        candidates = np.unique(
            np.concatenate(([0.0, 0.5, 1.0], unique_scores, midpoints))
        )
    best_threshold = 0.5
    best_metrics = _metrics(labels, (scores >= best_threshold).astype(int))
    best_key = (
        best_metrics["macro_f1"],
        best_metrics["f1"],
        best_metrics["accuracy"],
        -abs(best_threshold - 0.5),
        -best_threshold,
    )
    for threshold in candidates:
        predicted = (scores >= threshold).astype(int)
        metrics = _metrics(labels, predicted)
        key = (
            metrics["macro_f1"],
            metrics["f1"],
            metrics["accuracy"],
            -abs(float(threshold) - 0.5),
            -float(threshold),
        )
        if key > best_key:
            best_key = key
            best_threshold = float(threshold)
            best_metrics = metrics
    return _rounded(best_threshold), best_metrics


def _grouped_out_of_fold_probabilities(
    features: pd.DataFrame,
    actual: pd.Series,
    groups: pd.Series,
    candidate: CandidateModel,
) -> np.ndarray:
    probabilities = np.full(len(actual), np.nan, dtype=float)
    test_counts = np.zeros(len(actual), dtype=int)
    splitter = LeaveOneGroupOut()
    for train_indexes, test_indexes in splitter.split(features, actual, groups):
        if actual.iloc[train_indexes].nunique() != 2:
            raise ValueError(
                "Grouped probability calibration found a fold with one "
                "training class"
            )
        estimator = _fit_candidate(
            candidate,
            features.iloc[train_indexes],
            actual.iloc[train_indexes],
        )
        probabilities[test_indexes] = _positive_probabilities(
            estimator,
            features.iloc[test_indexes],
        )
        test_counts[test_indexes] += 1
    if not np.all(test_counts == 1) or not np.isfinite(probabilities).all():
        raise RuntimeError(
            "Grouped calibration did not produce one probability per row"
        )
    return probabilities


def calibrate_selected_candidate(
    labelled: pd.DataFrame,
    target: str,
    candidate: CandidateModel,
    *,
    random_state: int = RANDOM_STATE,
) -> tuple[GroupedSigmoidCalibratedClassifier, dict[str, Any]]:
    """Fit and evaluate a leakage-safe order-grouped sigmoid calibration.

    Reported calibrated probabilities use nested Leave-One-Group-Out: the
    outer order is absent from both the base model and its sigmoid mapping.
    The final sigmoid is then fitted from full-dataset grouped OOF base scores.
    """
    features = labelled[EARLY_WARNING_FEATURES].astype(float).reset_index(drop=True)
    actual = labelled[target].astype(int).reset_index(drop=True)
    groups = labelled["Bulk_Order_ID"].astype(str).reset_index(drop=True)
    outer_raw = np.full(len(actual), np.nan, dtype=float)
    outer_calibrated = np.full(len(actual), np.nan, dtype=float)
    outer_calibrated_predictions = np.full(len(actual), -1, dtype=int)
    outer_counts = np.zeros(len(actual), dtype=int)
    fold_thresholds: list[float] = []
    splitter = LeaveOneGroupOut()

    for train_indexes, test_indexes in splitter.split(features, actual, groups):
        train_features = features.iloc[train_indexes].reset_index(drop=True)
        train_actual = actual.iloc[train_indexes].reset_index(drop=True)
        train_groups = groups.iloc[train_indexes].reset_index(drop=True)
        if train_actual.nunique() != 2:
            raise ValueError(
                f"{target} has a nested calibration fold with one training class"
            )
        inner_raw = _grouped_out_of_fold_probabilities(
            train_features,
            train_actual,
            train_groups,
            candidate,
        )
        fold_calibrator = _fit_sigmoid_calibrator(
            inner_raw,
            train_actual,
            random_state=random_state,
        )
        inner_calibrated = _apply_sigmoid_calibrator(
            fold_calibrator,
            inner_raw,
        )
        fold_threshold, _ = _select_decision_threshold(
            train_actual,
            inner_calibrated,
        )
        fold_thresholds.append(fold_threshold)
        fold_estimator = _fit_candidate(
            candidate,
            train_features,
            train_actual,
        )
        fold_raw = _positive_probabilities(
            fold_estimator,
            features.iloc[test_indexes],
        )
        outer_raw[test_indexes] = fold_raw
        outer_calibrated[test_indexes] = _apply_sigmoid_calibrator(
            fold_calibrator,
            fold_raw,
        )
        outer_calibrated_predictions[test_indexes] = (
            outer_calibrated[test_indexes] >= fold_threshold
        ).astype(int)
        outer_counts[test_indexes] += 1

    if (
        not np.all(outer_counts == 1)
        or not np.isfinite(outer_raw).all()
        or not np.isfinite(outer_calibrated).all()
        or np.any(outer_calibrated_predictions < 0)
    ):
        raise RuntimeError(
            "Nested grouped calibration did not score every held-out row once"
        )

    final_calibrator = _fit_sigmoid_calibrator(
        outer_raw,
        actual,
        random_state=random_state,
    )
    final_oof_calibrated = _apply_sigmoid_calibrator(
        final_calibrator,
        outer_raw,
    )
    final_threshold, final_threshold_training_metrics = (
        _select_decision_threshold(actual, final_oof_calibrated)
    )
    final_base_estimator = _fit_candidate(candidate, features, actual)
    calibrated_estimator = GroupedSigmoidCalibratedClassifier(
        final_base_estimator,
        final_calibrator,
    )
    raw_probability_metrics = _probability_metrics(actual, outer_raw)
    calibrated_probability_metrics = _probability_metrics(
        actual,
        outer_calibrated,
    )
    calibration_report = {
        "is_calibrated": True,
        "method": CALIBRATION_METHOD,
        "group_column": "Bulk_Order_ID",
        "outer_validation": "Nested Leave-One-Group-Out",
        "outer_fold_count": int(groups.nunique()),
        "every_outer_row_evaluated_once": bool(np.all(outer_counts == 1)),
        "calibrator_fit_source": (
            "Base-model probabilities generated while each bulk order was "
            "held out"
        ),
        "raw_probability_metrics": raw_probability_metrics,
        "calibrated_probability_metrics": calibrated_probability_metrics,
        "decision_threshold": final_threshold,
        "threshold_selection": (
            "Maximize Macro-F1 on bulk-order-held-out calibrated scores; ties "
            "use F1, Accuracy, then proximity to 0.5"
        ),
        "nested_threshold_validation_metrics": _metrics(
            actual,
            outer_calibrated_predictions,
        ),
        "final_threshold_training_metrics": final_threshold_training_metrics,
        "nested_fold_thresholds": fold_thresholds,
        "brier_score_change": _rounded(
            calibrated_probability_metrics["brier_score"]
            - raw_probability_metrics["brier_score"]
        ),
        "log_loss_change": _rounded(
            calibrated_probability_metrics["log_loss"]
            - raw_probability_metrics["log_loss"]
        ),
    }
    return calibrated_estimator, calibration_report


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
        final_estimator, calibration_report = calibrate_selected_candidate(
            labelled,
            target,
            selected_candidate,
            random_state=random_state,
        )
        target_info = SUPPORTED_TARGETS[target]
        artifact_path = (
            f"models/c3_early_warning_{target_info['slug']}_v2.joblib"
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
            "calibration": calibration_report,
        }
        target_reports[target] = target_report
        artifacts[target] = {
            "artifact_version": ARTIFACT_VERSION,
            "target": target,
            "display_name": target_info["display_name"],
            "horizon_production_days": 3,
            "model_name": selected_name,
            "features": list(EARLY_WARNING_FEATURES),
            "decision_threshold": calibration_report["decision_threshold"],
            "probability_calibrated": True,
            "calibration": calibration_report,
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
                    "Calibrated": result["model"] == selected_name,
                    "Selected": result["model"] == selected_name,
                    "Baseline": not result["selectable"],
                }
            )

    experiment = {
        "targets": target_reports,
        "selection_rule": (
            "Highest aggregate unseen-order Macro-F1; ties use F1, then Accuracy. "
            "The dummy prior is a non-selectable baseline. The selected model's "
            "probabilities then receive nested order-grouped sigmoid calibration."
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
            "decision_threshold": (
                "Target-specific threshold selected from grouped out-of-fold "
                "calibrated scores"
            ),
            "reported_metrics": ["accuracy", "macro_f1", "f1"],
            "reported_probability_metrics": [
                "brier_score",
                "log_loss",
                "expected_calibration_error",
            ],
            "probability_calibration": CALIBRATION_METHOD,
            "calibration_validation": "Nested Leave-One-Group-Out",
            "calibrator_uses_only_grouped_out_of_fold_base_scores": True,
            "selection_rule": experiment["selection_rule"],
            "final_refit": (
                "After model selection, the selected pipeline is refit on all "
                "eligible rows. Its sigmoid mapping is fitted on probabilities "
                "generated while each bulk order was held out."
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
                "Calibration reliability should be rechecked when additional "
                "new real orders become available."
            ),
        ],
        "decision": (
            "Use grouped sigmoid-calibrated probabilities for the three supported "
            "research early-warning outputs and continue checking them against "
            "new real-order outcomes."
        ),
    }
    return report, comparison, artifacts
