"""Research-only inference for Component 3 subtype early warnings."""

from __future__ import annotations

from functools import lru_cache
import math
from pathlib import Path
from typing import Any

import joblib
import pandas as pd

from components.component3_early_warning_data import (
    CURRENT_FEATURES,
    EARLY_WARNING_FEATURES,
)
from components.component3_features import build_feature_values


INFERENCE_VERSION = "component3-early-warning-inference-calibrated-v2"

MODEL_SPECS: dict[str, dict[str, str]] = {
    "Machine_Breakdown_Within_3_Days": {
        "display_name": "Machine breakdown",
        "filename": "c3_early_warning_machine_breakdown_v2.joblib",
        "preparation": (
            "Inspect critical machines, confirm maintenance availability, and "
            "reserve feasible backup-machine capacity."
        ),
    },
    "Quality_Limit_Within_3_Days": {
        "display_name": "Quality-limit issue",
        "filename": "c3_early_warning_quality_limit_v2.joblib",
        "preparation": (
            "Increase in-line quality checks and review the latest damage trend "
            "before releasing more pieces."
        ),
    },
    "Output_Schedule_Risk_Within_3_Days": {
        "display_name": "Output or schedule risk",
        "filename": "c3_early_warning_output_schedule_risk_v2.joblib",
        "preparation": (
            "Review the remaining rate, overtime limit, and backup-line capacity "
            "before the schedule gap grows."
        ),
    },
}


class EarlyWarningModelError(RuntimeError):
    """Raised when a research artifact cannot safely serve a prediction."""


def _current_features(prediction_input: dict[str, Any]) -> dict[str, float]:
    canonical = build_feature_values(
        daily_commitment=int(prediction_input["daily_commitment"]),
        plant_daily_output=int(prediction_input["plant_daily_output"]),
        machine_breakdown_count=int(
            prediction_input["machine_breakdown_count"]
        ),
        worker_shortage_count=int(prediction_input["worker_shortage_count"]),
        daily_damage_qty=int(prediction_input["daily_damage_qty"]),
        max_daily_damage_qty=int(prediction_input["max_daily_damage_qty"]),
        working_day_no=int(prediction_input["working_day_no"]),
        total_working_days=int(prediction_input["total_working_days"]),
        cutting_days=int(prediction_input["cutting_days"]),
        sewing_days=int(prediction_input["sewing_days"]),
        full_order_qty=int(prediction_input["full_order_qty"]),
        cumulative_completed_qty=int(
            prediction_input["cumulative_completed_qty"]
        ),
    )
    return {
        feature: float(canonical[feature]) for feature in CURRENT_FEATURES
    }


def _record_is_emergency(record: dict[str, Any]) -> bool:
    prediction_input = record["prediction_input"]
    return bool(
        record.get("is_emergency")
        or str(record.get("risk_type", "No Issue")) != "No Issue"
        or int(prediction_input["worker_shortage_count"]) > 0
        or int(prediction_input["machine_breakdown_count"]) > 0
        or int(prediction_input["daily_damage_qty"])
        > int(prediction_input["max_daily_damage_qty"])
    )


def _prior_history(
    prediction_input: dict[str, Any],
    history: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    order_id = str(prediction_input["bulk_order_id"])
    current_day = int(prediction_input["working_day_no"])
    current_date = str(prediction_input["production_date"])
    earlier = [
        record
        for record in history
        if str(record.get("bulk_order_id")) == order_id
        and int(record.get("working_day_no", 0)) < current_day
        and str(record.get("production_date", "")) < current_date
    ]
    return sorted(
        earlier,
        key=lambda record: (
            int(record["working_day_no"]),
            str(record["production_date"]),
        ),
    )


def _history_evidence(
    prediction_input: dict[str, Any],
    prior: list[dict[str, Any]],
) -> dict[str, Any]:
    current_day = int(prediction_input["working_day_no"])
    day_numbers = [int(record["working_day_no"]) for record in prior]
    day_numbers.append(current_day)
    gap_count = sum(
        current - previous != 1
        for previous, current in zip(day_numbers, day_numbers[1:])
    )
    feature_days = min(len(prior) + 1, 3)
    if gap_count:
        status = "gapped"
    elif feature_days == 3:
        status = "complete"
    elif prior:
        status = "partial"
    else:
        status = "current_only"
    return {
        "source": "Current input plus saved earlier monitoring records",
        "saved_prior_records": len(prior),
        "feature_history_days": feature_days,
        "maximum_feature_history_days": 3,
        "status": status,
        "working_day_gap_detected": bool(gap_count),
        "working_day_gap_transitions": gap_count,
        "latest_prior_working_day": (
            int(prior[-1]["working_day_no"]) if prior else None
        ),
        "future_or_current_saved_rows_used": 0,
    }


def build_inference_feature_row(
    prediction_input: dict[str, Any],
    history: list[dict[str, Any]],
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Build one current/past-only row and its order-history evidence."""
    prior = _prior_history(prediction_input, history)
    current_observation = {
        "prediction_input": prediction_input,
        "risk_type": "No Issue",
        "is_emergency": False,
    }
    observations = [*prior, current_observation]
    trailing = observations[-3:]
    previous_input = (
        prior[-1]["prediction_input"] if prior else prediction_input
    )
    current_input = prediction_input
    outputs = pd.Series(
        [
            float(record["prediction_input"]["plant_daily_output"])
            for record in trailing
        ],
        dtype="float64",
    )
    gaps = pd.Series(
        [
            _current_features(record["prediction_input"])["Gap_Pct"]
            for record in trailing
        ],
        dtype="float64",
    )
    earlier_emergency_positions = [
        position
        for position, record in enumerate(prior)
        if _record_is_emergency(record)
    ]
    days_since_last_emergency = (
        len(prior) - earlier_emergency_positions[-1]
        if earlier_emergency_positions
        else len(prior) + 1
    )

    features: dict[str, float] = _current_features(prediction_input)
    features.update(
        {
            "History_Days_Available": float(len(trailing)),
            "Previous_Day_Output": float(
                previous_input["plant_daily_output"]
            ),
            "Output_Change_From_Previous": float(
                int(current_input["plant_daily_output"])
                - int(previous_input["plant_daily_output"])
            ),
            "Trailing_3D_Avg_Output": round(float(outputs.mean()), 4),
            "Trailing_3D_Output_Std": round(
                float(outputs.std(ddof=0)),
                4,
            ),
            "Trailing_3D_Avg_Gap_Pct": round(float(gaps.mean()), 4),
            "Trailing_3D_Emergency_Days": float(
                sum(_record_is_emergency(record) for record in trailing)
            ),
            "Trailing_3D_Worker_Shortage_Days": float(
                sum(
                    int(record["prediction_input"]["worker_shortage_count"])
                    > 0
                    for record in trailing
                )
            ),
            "Trailing_3D_Machine_Breakdown_Days": float(
                sum(
                    int(record["prediction_input"]["machine_breakdown_count"])
                    > 0
                    for record in trailing
                )
            ),
            "Trailing_3D_Quality_Limit_Days": float(
                sum(
                    int(record["prediction_input"]["daily_damage_qty"])
                    > int(
                        record["prediction_input"]["max_daily_damage_qty"]
                    )
                    for record in trailing
                )
            ),
            "Days_Since_Last_Emergency": float(days_since_last_emergency),
        }
    )
    missing = sorted(set(EARLY_WARNING_FEATURES).difference(features))
    if missing:
        raise EarlyWarningModelError(
            f"Early-warning feature builder is missing columns: {missing}"
        )
    row = pd.DataFrame([features], columns=EARLY_WARNING_FEATURES)
    if row.isna().any(axis=None) or not all(
        math.isfinite(float(value)) for value in row.iloc[0]
    ):
        raise EarlyWarningModelError(
            "Early-warning feature row contains invalid numeric values"
        )
    return row, _history_evidence(prediction_input, prior)


@lru_cache(maxsize=4)
def load_early_warning_artifacts(
    models_directory: str,
) -> dict[str, dict[str, Any]]:
    """Load and validate the three selected research artifacts once."""
    models_path = Path(models_directory)
    artifacts: dict[str, dict[str, Any]] = {}
    for target, spec in MODEL_SPECS.items():
        path = models_path / spec["filename"]
        if not path.is_file():
            raise EarlyWarningModelError(
                f"Missing early-warning model artifact: {path.name}"
            )
        try:
            artifact = joblib.load(path)
        except Exception as exc:
            raise EarlyWarningModelError(
                f"Could not load early-warning model artifact: {path.name}"
            ) from exc
        if not isinstance(artifact, dict):
            raise EarlyWarningModelError(
                f"Invalid early-warning artifact structure: {path.name}"
            )
        if artifact.get("target") != target:
            raise EarlyWarningModelError(
                f"Early-warning target mismatch in {path.name}"
            )
        if artifact.get("features") != EARLY_WARNING_FEATURES:
            raise EarlyWarningModelError(
                f"Early-warning feature contract mismatch in {path.name}"
            )
        if artifact.get("horizon_production_days") != 3:
            raise EarlyWarningModelError(
                f"Early-warning horizon mismatch in {path.name}"
            )
        if artifact.get("production_approved") is not False:
            raise EarlyWarningModelError(
                f"Early-warning approval metadata is invalid in {path.name}"
            )
        if artifact.get("probability_calibrated") is not True:
            raise EarlyWarningModelError(
                f"Early-warning calibration metadata is invalid in {path.name}"
            )
        calibration = artifact.get("calibration")
        if (
            not isinstance(calibration, dict)
            or calibration.get("is_calibrated") is not True
            or calibration.get("method") != "grouped_sigmoid_on_logit"
            or calibration.get("outer_validation")
            != "Nested Leave-One-Group-Out"
        ):
            raise EarlyWarningModelError(
                f"Early-warning calibration evidence is invalid in {path.name}"
            )
        if not isinstance(artifact.get("model_name"), str):
            raise EarlyWarningModelError(
                f"Early-warning model name is invalid in {path.name}"
            )
        metrics = artifact.get("validation_metrics")
        if not isinstance(metrics, dict) or set(metrics) != {
            "accuracy",
            "macro_f1",
            "f1",
        }:
            raise EarlyWarningModelError(
                f"Early-warning validation metrics are invalid in {path.name}"
            )
        if not all(
            isinstance(value, (int, float)) and math.isfinite(float(value))
            for value in metrics.values()
        ):
            raise EarlyWarningModelError(
                f"Early-warning validation scores are invalid in {path.name}"
            )
        estimator = artifact.get("estimator")
        if estimator is None or not hasattr(estimator, "predict_proba"):
            raise EarlyWarningModelError(
                f"Early-warning estimator is invalid in {path.name}"
            )
        threshold = artifact.get("decision_threshold")
        if not isinstance(threshold, (int, float)) or not 0 <= threshold <= 1:
            raise EarlyWarningModelError(
                f"Early-warning threshold is invalid in {path.name}"
            )
        artifacts[target] = artifact
    return artifacts


def clear_early_warning_artifact_cache() -> None:
    """Clear cached artifacts after retraining or during isolated tests."""
    load_early_warning_artifacts.cache_clear()


def _positive_probability(estimator: Any, row: pd.DataFrame) -> float:
    try:
        classes = [int(value) for value in estimator.classes_]
        probabilities = estimator.predict_proba(row)[0]
    except Exception as exc:
        raise EarlyWarningModelError(
            "Early-warning estimator could not produce a score"
        ) from exc
    if 1 not in classes:
        raise EarlyWarningModelError(
            "Early-warning estimator does not contain the positive class"
        )
    try:
        probability = float(probabilities[classes.index(1)])
    except (IndexError, TypeError, ValueError) as exc:
        raise EarlyWarningModelError(
            "Early-warning estimator returned invalid probabilities"
        ) from exc
    if not math.isfinite(probability):
        raise EarlyWarningModelError(
            "Early-warning estimator returned a non-finite probability"
        )
    return min(1.0, max(0.0, probability))


def _raw_positive_probability(estimator: Any, row: pd.DataFrame) -> float:
    if not hasattr(estimator, "raw_predict_proba"):
        raise EarlyWarningModelError(
            "Calibrated early-warning estimator has no raw audit score"
        )
    try:
        classes = [int(value) for value in estimator.classes_]
        probabilities = estimator.raw_predict_proba(row)[0]
        probability = float(probabilities[classes.index(1)])
    except Exception as exc:
        raise EarlyWarningModelError(
            "Early-warning estimator could not produce a raw audit score"
        ) from exc
    if not math.isfinite(probability):
        raise EarlyWarningModelError(
            "Early-warning estimator returned a non-finite raw audit score"
        )
    return min(1.0, max(0.0, probability))


def _not_applicable_response(current_risk_type: str) -> dict[str, Any]:
    return {
        "inference_version": INFERENCE_VERSION,
        "status": "not_applicable_current_emergency",
        "production_approved": False,
        "horizon_production_days": 3,
        "current_risk_type": current_risk_type,
        "alert_generated": False,
        "highest_warning": None,
        "warnings": [],
        "history": None,
        "message": (
            "A current emergency is already detected. Use the recovery plan; "
            "future early warning is evaluated only on currently stable days."
        ),
        "limitations": [
            "Worker-shortage future warning is not available in Step 5C.",
            "The subtype artifacts are research-only and not production approved.",
        ],
    }


def _completed_order_response(current_risk_type: str) -> dict[str, Any]:
    return {
        "inference_version": INFERENCE_VERSION,
        "status": "not_applicable_order_completed",
        "production_approved": False,
        "horizon_production_days": 3,
        "current_risk_type": current_risk_type,
        "alert_generated": False,
        "highest_warning": None,
        "warnings": [],
        "history": None,
        "message": (
            "The full order quantity is complete. No future production-day "
            "warning is required; raw model outputs remain available in the "
            "saved analysis for research audit."
        ),
        "limitations": [
            "Completed orders are excluded from actionable future warnings.",
            "The subtype artifacts are research-only and not production approved.",
        ],
    }


def predict_early_warnings(
    prediction_input: dict[str, Any],
    *,
    current_risk_type: str,
    history: list[dict[str, Any]],
    models_directory: str | Path,
) -> dict[str, Any]:
    """Predict supported three-day subtype outcomes for a stable current day."""
    order_completed = int(
        prediction_input["cumulative_completed_qty"]
    ) >= int(prediction_input["full_order_qty"])
    if order_completed:
        return _completed_order_response(current_risk_type)

    current_emergency = bool(
        current_risk_type != "No Issue"
        or int(prediction_input["worker_shortage_count"]) > 0
        or int(prediction_input["machine_breakdown_count"]) > 0
        or int(prediction_input["daily_damage_qty"])
        > int(prediction_input["max_daily_damage_qty"])
    )
    if current_emergency:
        return _not_applicable_response(current_risk_type)

    row, history_evidence = build_inference_feature_row(
        prediction_input,
        history,
    )
    artifacts = load_early_warning_artifacts(str(Path(models_directory)))
    warnings: list[dict[str, Any]] = []
    for target, spec in MODEL_SPECS.items():
        artifact = artifacts[target]
        estimator = artifact["estimator"]
        raw_probability = _raw_positive_probability(estimator, row)
        probability = _positive_probability(estimator, row)
        threshold = float(artifact["decision_threshold"])
        warnings.append(
            {
                "target": target,
                "display_name": spec["display_name"],
                "probability": round(probability, 6),
                "probability_pct": round(probability * 100, 2),
                "probability_calibrated": True,
                "calibration_method": str(
                    artifact["calibration"]["method"]
                ),
                "raw_probability_audit": round(raw_probability, 6),
                "raw_probability_audit_pct": round(
                    raw_probability * 100,
                    2,
                ),
                "decision_threshold": threshold,
                "warning_predicted": probability >= threshold,
                "model_name": str(artifact["model_name"]),
                "validation_metrics": dict(
                    artifact.get("validation_metrics", {})
                ),
                "preparation": spec["preparation"],
            }
        )

    highest = max(warnings, key=lambda warning: warning["probability"])
    alert_generated = any(
        warning["warning_predicted"] for warning in warnings
    )
    return {
        "inference_version": INFERENCE_VERSION,
        "status": "available",
        "production_approved": False,
        "horizon_production_days": 3,
        "current_risk_type": current_risk_type,
        "alert_generated": alert_generated,
        "highest_warning": {
            "target": highest["target"],
            "display_name": highest["display_name"],
            "probability": highest["probability"],
            "probability_pct": highest["probability_pct"],
        },
        "warnings": warnings,
        "history": history_evidence,
        "message": (
            "At least one experimental subtype warning crossed its model "
            "threshold. Review preparation actions before approval."
            if alert_generated
            else "No supported subtype crossed its experimental threshold."
        ),
        "limitations": [
            (
                "Probabilities use nested order-grouped sigmoid calibration; "
                "raw base-model scores are retained for audit."
            ),
            "Worker-shortage future warning is not available in Step 5C.",
            "A manager must review warnings and approve operational actions.",
        ],
    }
