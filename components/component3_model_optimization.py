"""Nested, order-grouped tuning and ensemble evidence for Component 3.

This module deliberately keeps optimization separate from the active model
artifacts.  It answers the research question "does tuning or an explicit
ensemble improve unseen-order performance?" without silently replacing a
working production-demo model.
"""

from __future__ import annotations

import json
from collections import Counter
from collections.abc import Iterable, Sequence
from datetime import UTC, datetime
from typing import Any

import numpy as np
import pandas as pd
from sklearn.base import BaseEstimator, clone
from sklearn.ensemble import RandomForestClassifier, VotingClassifier
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, f1_score, make_scorer
from sklearn.model_selection import GridSearchCV, GroupKFold, LeaveOneGroupOut
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from components.component3_early_warning_data import EARLY_WARNING_FEATURES
from components.component3_early_warning_training import SUPPORTED_TARGETS

REPORT_VERSION = "component3-grouped-hyperparameter-optimization-v1"
RANDOM_STATE = 42
MACRO_F1_SCORER = make_scorer(
    f1_score,
    average="macro",
    labels=[0, 1],
    zero_division=0,
)

DEFAULT_LOGISTIC_GRID: dict[str, list[Any]] = {
    "model__C": [0.05, 0.2, 1.0, 5.0],
}
DEFAULT_FOREST_GRID: dict[str, list[Any]] = {
    "model__n_estimators": [200, 400],
    "model__max_depth": [None, 8],
    "model__min_samples_leaf": [1, 3],
    "model__max_features": ["sqrt"],
}
DEFAULT_VOTING_WEIGHTS: list[tuple[int, int]] = [
    (1, 1),
    (2, 1),
    (1, 2),
]


def build_tunable_estimators(
    *,
    random_state: int = RANDOM_STATE,
) -> dict[str, BaseEstimator]:
    """Return the two complementary estimators used in the tuning study."""
    return {
        "tuned_logistic_regression": Pipeline(
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
        "tuned_random_forest": Pipeline(
            [
                ("imputer", SimpleImputer(strategy="median")),
                (
                    "model",
                    RandomForestClassifier(
                        class_weight="balanced_subsample",
                        random_state=random_state,
                        n_jobs=1,
                    ),
                ),
            ]
        ),
    }


def _rounded(value: float) -> float:
    return round(float(value), 6)


def _metrics(actual: pd.Series, predicted: np.ndarray) -> dict[str, float]:
    return {
        "accuracy": _rounded(accuracy_score(actual, predicted)),
        "macro_f1": _rounded(
            f1_score(
                actual,
                predicted,
                average="macro",
                labels=[0, 1],
                zero_division=0,
            )
        ),
        "f1": _rounded(f1_score(actual, predicted, zero_division=0)),
    }


def _normalise_params(params: dict[str, Any]) -> dict[str, Any]:
    """Convert NumPy scalar values to JSON-safe Python values."""
    normalised: dict[str, Any] = {}
    for key, value in params.items():
        if isinstance(value, np.generic):
            value = value.item()
        if isinstance(value, tuple):
            value = list(value)
        normalised[key] = value
    return normalised


def _valid_group_splits(
    features: pd.DataFrame,
    actual: pd.Series,
    groups: pd.Series,
    *,
    requested_splits: int,
) -> list[tuple[np.ndarray, np.ndarray]]:
    """Build inner group folds whose training side contains both classes."""
    group_count = int(groups.nunique())
    split_count = min(requested_splits, group_count)
    if split_count < 2:
        raise ValueError("Hyperparameter tuning requires at least two orders")
    splitter = GroupKFold(n_splits=split_count)
    splits = [
        (train_indexes, test_indexes)
        for train_indexes, test_indexes in splitter.split(
            features,
            actual,
            groups,
        )
        if actual.iloc[train_indexes].nunique() == 2
    ]
    if len(splits) < 2:
        raise ValueError(
            "Grouped hyperparameter tuning could not create two valid inner "
            "folds containing both training classes"
        )
    return splits


def _search(
    estimator: BaseEstimator,
    parameter_grid: dict[str, list[Any]],
    features: pd.DataFrame,
    actual: pd.Series,
    groups: pd.Series,
    *,
    inner_splits: int,
) -> GridSearchCV:
    cv = _valid_group_splits(
        features,
        actual,
        groups,
        requested_splits=inner_splits,
    )
    search = GridSearchCV(
        estimator=clone(estimator),
        param_grid=parameter_grid,
        scoring=MACRO_F1_SCORER,
        cv=cv,
        refit=True,
        n_jobs=1,
        error_score="raise",
        return_train_score=False,
    )
    search.fit(features, actual)
    return search


def _voting_search(
    logistic_estimator: BaseEstimator,
    forest_estimator: BaseEstimator,
    features: pd.DataFrame,
    actual: pd.Series,
    groups: pd.Series,
    *,
    voting_weights: Sequence[tuple[int, int]],
    inner_splits: int,
) -> GridSearchCV:
    ensemble = VotingClassifier(
        estimators=[
            ("logistic", clone(logistic_estimator)),
            ("forest", clone(forest_estimator)),
        ],
        voting="soft",
        n_jobs=1,
    )
    return _search(
        ensemble,
        {"weights": list(voting_weights)},
        features,
        actual,
        groups,
        inner_splits=inner_splits,
    )


def _parameter_stability(
    configurations: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    rendered = [
        json.dumps(
            _normalise_params(configuration),
            sort_keys=True,
            separators=(",", ":"),
        )
        for configuration in configurations
    ]
    counts = Counter(rendered)
    return [
        {
            "parameters": json.loads(configuration),
            "selected_in_outer_folds": count,
        }
        for configuration, count in sorted(
            counts.items(),
            key=lambda item: (-item[1], item[0]),
        )
    ]


def _coverage(labelled: pd.DataFrame, target: str) -> dict[str, int]:
    actual = labelled[target].astype(int)
    positive = actual.eq(1)
    negative = actual.eq(0)
    return {
        "rows": int(len(labelled)),
        "orders": int(labelled["Bulk_Order_ID"].nunique()),
        "positive_rows": int(positive.sum()),
        "negative_rows": int(negative.sum()),
        "positive_orders": int(labelled.loc[positive, "Bulk_Order_ID"].nunique()),
        "negative_orders": int(labelled.loc[negative, "Bulk_Order_ID"].nunique()),
    }


def _validate(
    labelled: pd.DataFrame,
    targets: Iterable[str],
) -> None:
    target_names = list(targets)
    unsupported = sorted(set(target_names).difference(SUPPORTED_TARGETS))
    if unsupported:
        raise ValueError(f"Unsupported optimization targets: {unsupported}")
    required = {"Bulk_Order_ID", *EARLY_WARNING_FEATURES, *target_names}
    missing = sorted(required.difference(labelled.columns))
    if missing:
        raise ValueError(f"Optimization dataset is missing columns: {missing}")
    if labelled.empty:
        raise ValueError("Optimization dataset cannot be empty")
    if labelled["Bulk_Order_ID"].nunique() < 3:
        raise ValueError("Optimization requires at least three bulk orders")
    for target in target_names:
        if set(labelled[target].astype(int).unique()) != {0, 1}:
            raise ValueError(f"{target} must contain both binary classes")


def _select_result(candidate_metrics: dict[str, dict[str, float]]) -> str:
    # Prefer a simpler candidate only when all reported metrics tie.  The
    # ensemble must demonstrate a genuine held-out improvement to be selected.
    simplicity = {
        "tuned_logistic_regression": 2,
        "tuned_random_forest": 1,
        "soft_voting_logistic_random_forest": 0,
    }
    return max(
        candidate_metrics,
        key=lambda name: (
            candidate_metrics[name]["macro_f1"],
            candidate_metrics[name]["f1"],
            candidate_metrics[name]["accuracy"],
            simplicity[name],
        ),
    )


def optimize_target(
    labelled: pd.DataFrame,
    target: str,
    *,
    logistic_grid: dict[str, list[Any]] | None = None,
    forest_grid: dict[str, list[Any]] | None = None,
    voting_weights: Sequence[tuple[int, int]] = DEFAULT_VOTING_WEIGHTS,
    inner_splits: int = 3,
    random_state: int = RANDOM_STATE,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Return unbiased nested-group results for one early-warning target."""
    _validate(labelled, [target])
    logistic_grid = logistic_grid or DEFAULT_LOGISTIC_GRID
    forest_grid = forest_grid or DEFAULT_FOREST_GRID
    estimators = build_tunable_estimators(random_state=random_state)

    features = labelled[EARLY_WARNING_FEATURES].astype(float).reset_index(drop=True)
    actual = labelled[target].astype(int).reset_index(drop=True)
    groups = labelled["Bulk_Order_ID"].astype(str).reset_index(drop=True)
    candidate_names = [
        "tuned_logistic_regression",
        "tuned_random_forest",
        "soft_voting_logistic_random_forest",
    ]
    predictions = {name: np.full(len(labelled), -1, dtype=int) for name in candidate_names}
    test_counts = np.zeros(len(labelled), dtype=int)
    fold_parameters: dict[str, list[dict[str, Any]]] = {name: [] for name in candidate_names}
    held_out_orders: list[str] = []
    overlap_detected = False

    outer = LeaveOneGroupOut()
    for train_indexes, test_indexes in outer.split(features, actual, groups):
        train_features = features.iloc[train_indexes].reset_index(drop=True)
        train_actual = actual.iloc[train_indexes].reset_index(drop=True)
        train_groups = groups.iloc[train_indexes].reset_index(drop=True)
        test_features = features.iloc[test_indexes]
        train_order_set = set(train_groups)
        test_order_set = set(groups.iloc[test_indexes])
        overlap_detected |= bool(train_order_set.intersection(test_order_set))
        held_out_orders.extend(sorted(test_order_set))

        if train_actual.nunique() != 2:
            raise ValueError(f"{target} has an outer fold with only one training class")

        logistic_search = _search(
            estimators["tuned_logistic_regression"],
            logistic_grid,
            train_features,
            train_actual,
            train_groups,
            inner_splits=inner_splits,
        )
        forest_search = _search(
            estimators["tuned_random_forest"],
            forest_grid,
            train_features,
            train_actual,
            train_groups,
            inner_splits=inner_splits,
        )
        voting_search = _voting_search(
            logistic_search.best_estimator_,
            forest_search.best_estimator_,
            train_features,
            train_actual,
            train_groups,
            voting_weights=voting_weights,
            inner_splits=inner_splits,
        )

        searches = {
            "tuned_logistic_regression": logistic_search,
            "tuned_random_forest": forest_search,
            "soft_voting_logistic_random_forest": voting_search,
        }
        for name, search in searches.items():
            predictions[name][test_indexes] = search.predict(test_features)
            fold_parameters[name].append(_normalise_params(search.best_params_))
        test_counts[test_indexes] += 1

    if overlap_detected:
        raise RuntimeError("Bulk-order leakage detected in outer validation")
    if not np.all(test_counts == 1):
        raise RuntimeError("Every row must be evaluated by exactly one outer fold")
    if any(np.any(values < 0) for values in predictions.values()):
        raise RuntimeError("Nested optimization did not predict every row")

    candidate_metrics = {name: _metrics(actual, values) for name, values in predictions.items()}
    selected_model = _select_result(candidate_metrics)

    final_logistic = _search(
        estimators["tuned_logistic_regression"],
        logistic_grid,
        features,
        actual,
        groups,
        inner_splits=inner_splits,
    )
    final_forest = _search(
        estimators["tuned_random_forest"],
        forest_grid,
        features,
        actual,
        groups,
        inner_splits=inner_splits,
    )
    final_voting = _voting_search(
        final_logistic.best_estimator_,
        final_forest.best_estimator_,
        features,
        actual,
        groups,
        voting_weights=voting_weights,
        inner_splits=inner_splits,
    )
    final_searches = {
        "tuned_logistic_regression": final_logistic,
        "tuned_random_forest": final_forest,
        "soft_voting_logistic_random_forest": final_voting,
    }

    candidates: dict[str, dict[str, Any]] = {}
    flat_rows: list[dict[str, Any]] = []
    for name in candidate_names:
        search = final_searches[name]
        candidates[name] = {
            **candidate_metrics[name],
            "outer_fold_parameter_stability": _parameter_stability(fold_parameters[name]),
            "final_full_data_best_parameters": _normalise_params(search.best_params_),
            "final_full_data_inner_macro_f1": _rounded(search.best_score_),
            "selected": name == selected_model,
        }
        flat_rows.append(
            {
                "Target": target,
                "Display_Name": SUPPORTED_TARGETS[target]["display_name"],
                "Candidate": name,
                "Accuracy": candidate_metrics[name]["accuracy"],
                "Macro_F1": candidate_metrics[name]["macro_f1"],
                "F1": candidate_metrics[name]["f1"],
                "Selected": name == selected_model,
                "Final_Best_Parameters": json.dumps(
                    _normalise_params(search.best_params_),
                    sort_keys=True,
                ),
            }
        )

    result = {
        "display_name": SUPPORTED_TARGETS[target]["display_name"],
        "class_coverage": _coverage(labelled, target),
        "selected_model": selected_model,
        "selection_rule": (
            "Highest nested unseen-order Macro-F1; ties use positive-class F1, "
            "Accuracy, then the simpler candidate."
        ),
        "candidates": candidates,
        "validation": {
            "outer_strategy": "LeaveOneGroupOut",
            "inner_strategy": f"GroupKFold(n_splits={inner_splits})",
            "group_column": "Bulk_Order_ID",
            "outer_fold_count": int(groups.nunique()),
            "held_out_orders": sorted(set(held_out_orders)),
            "every_row_evaluated_once": bool(np.all(test_counts == 1)),
            "train_test_group_overlap_detected": overlap_detected,
        },
    }
    return result, flat_rows


def run_optimization_experiment(
    labelled: pd.DataFrame,
    *,
    target_names: Iterable[str] | None = None,
    logistic_grid: dict[str, list[Any]] | None = None,
    forest_grid: dict[str, list[Any]] | None = None,
    voting_weights: Sequence[tuple[int, int]] = DEFAULT_VOTING_WEIGHTS,
    inner_splits: int = 3,
    random_state: int = RANDOM_STATE,
) -> tuple[dict[str, Any], pd.DataFrame]:
    """Optimize supported targets and return research evidence, not artifacts."""
    targets = list(target_names or SUPPORTED_TARGETS)
    _validate(labelled, targets)
    target_results: dict[str, Any] = {}
    comparison_rows: list[dict[str, Any]] = []
    for target in targets:
        result, rows = optimize_target(
            labelled,
            target,
            logistic_grid=logistic_grid,
            forest_grid=forest_grid,
            voting_weights=voting_weights,
            inner_splits=inner_splits,
            random_state=random_state,
        )
        target_results[target] = result
        comparison_rows.extend(rows)

    report = {
        "report_version": REPORT_VERSION,
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "scope": (
            "Research-only nested group hyperparameter optimization and "
            "explicit soft-voting ensemble comparison"
        ),
        "primary_metric": "Macro-F1",
        "parameter_search": "GridSearchCV",
        "outer_validation": "LeaveOneGroupOut by Bulk_Order_ID",
        "inner_validation": f"GroupKFold(n_splits={inner_splits})",
        "leakage_control": (
            "Each outer test order is absent from hyperparameter selection, "
            "model fitting, and ensemble-weight selection."
        ),
        "promotion_policy": (
            "Do not replace active artifacts automatically. Promote only if "
            "nested unseen-order evidence improves and integration tests pass."
        ),
        "parameter_rationale": {
            "logistic_regression_C": (
                "Controls regularization strength for a stable linear model "
                "on the small, imbalanced early-warning dataset."
            ),
            "random_forest_n_estimators": (
                "Compares ensemble sizes to balance stability and compute cost."
            ),
            "random_forest_max_depth": (
                "Constrains tree complexity to reduce small-dataset overfitting."
            ),
            "random_forest_min_samples_leaf": (
                "Prevents decisions from depending on very small leaf samples."
            ),
            "soft_voting_weights": (
                "Tests whether emphasizing the linear or nonlinear model "
                "improves order-held-out Macro-F1."
            ),
        },
        "search_spaces": {
            "logistic_regression": logistic_grid or DEFAULT_LOGISTIC_GRID,
            "random_forest": forest_grid or DEFAULT_FOREST_GRID,
            "soft_voting_weights": [list(values) for values in voting_weights],
        },
        "targets": target_results,
        "research_limitations": [
            "The available real dataset contains a limited number of orders.",
            "Nested grouped scores are research evidence, not production approval.",
            "A tuned or ensemble model is retained only when it improves held-out evidence.",
        ],
    }
    return report, pd.DataFrame.from_records(comparison_rows)
