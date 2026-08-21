"""Evaluate stored early warnings against later verified outcomes."""

from __future__ import annotations

from collections import Counter
from typing import Any

from sklearn.metrics import accuracy_score, f1_score


REPORT_VERSION = "component3-early-warning-validation-v1"

TARGET_SPECS = (
    {
        "target": "Machine_Breakdown_Within_3_Days",
        "display_name": "Machine breakdown",
        "outcome_field": "machine_breakdown_within_3_days",
    },
    {
        "target": "Quality_Limit_Within_3_Days",
        "display_name": "Quality-limit issue",
        "outcome_field": "quality_limit_within_3_days",
    },
    {
        "target": "Output_Schedule_Risk_Within_3_Days",
        "display_name": "Output or schedule risk",
        "outcome_field": "output_schedule_risk_within_3_days",
    },
)


def _metrics(actual: list[int], predicted: list[int]) -> dict[str, float] | None:
    if not actual:
        return None
    return {
        "accuracy": round(float(accuracy_score(actual, predicted)), 6),
        "macro_f1": round(
            float(
                f1_score(
                    actual,
                    predicted,
                    labels=[0, 1],
                    average="macro",
                    zero_division=0,
                )
            ),
            6,
        ),
        "f1": round(
            float(f1_score(actual, predicted, zero_division=0)),
            6,
        ),
    }


def _warning_map(record: dict[str, Any]) -> dict[str, dict[str, Any]]:
    analysis = record.get("analysis")
    if not isinstance(analysis, dict):
        return {}
    early_warning = analysis.get("early_warning")
    if not isinstance(early_warning, dict):
        return {}
    if early_warning.get("status") != "available":
        return {}
    warnings = early_warning.get("warnings")
    if not isinstance(warnings, list):
        return {}
    return {
        str(warning["target"]): warning
        for warning in warnings
        if isinstance(warning, dict) and warning.get("target")
    }


def _scope_report(
    records: list[dict[str, Any]],
    *,
    scope: str,
    evidence_type: str,
) -> dict[str, Any]:
    exclusion_counts: Counter[str] = Counter()
    candidates: list[tuple[dict[str, Any], dict[str, dict[str, Any]]]] = []
    for record in records:
        if record.get("actual_outcome_status") != "Verified":
            exclusion_counts["actual_outcome_not_verified"] += 1
            continue
        if record.get("label_status") != "Ready":
            exclusion_counts["next_three_day_window_not_ready"] += 1
            continue
        if bool(record.get("actual_emergency")):
            exclusion_counts["current_day_actual_emergency"] += 1
            continue
        warning_map = _warning_map(record)
        if not warning_map:
            exclusion_counts["stored_early_warning_not_available"] += 1
            continue
        candidates.append((record, warning_map))

    results: list[dict[str, Any]] = []
    evaluated_record_ids: set[str] = set()
    evaluated_order_ids: set[str] = set()
    for spec in TARGET_SPECS:
        actual: list[int] = []
        predicted: list[int] = []
        scores: list[float] = []
        target_records: list[dict[str, Any]] = []
        target_missing = 0
        for record, warning_map in candidates:
            warning = warning_map.get(spec["target"])
            outcome = record.get(spec["outcome_field"])
            if warning is None or outcome not in (0, 1):
                target_missing += 1
                continue
            actual.append(int(outcome))
            predicted.append(int(bool(warning.get("warning_predicted"))))
            scores.append(float(warning.get("probability", 0.0)))
            target_records.append(record)
            evaluated_record_ids.add(str(record["record_id"]))
            evaluated_order_ids.add(str(record["bulk_order_id"]))

        positive_actual = sum(actual)
        negative_actual = len(actual) - positive_actual
        class_coverage_complete = positive_actual > 0 and negative_actual > 0
        results.append(
            {
                "target": spec["target"],
                "display_name": spec["display_name"],
                "rows_evaluated": len(actual),
                "orders_evaluated": len(
                    {str(record["bulk_order_id"]) for record in target_records}
                ),
                "positive_actual_rows": positive_actual,
                "negative_actual_rows": negative_actual,
                "positive_predictions": sum(predicted),
                "negative_predictions": len(predicted) - sum(predicted),
                "class_coverage_complete": class_coverage_complete,
                "metrics": _metrics(actual, predicted),
                "missing_warning_or_outcome_rows": target_missing,
                "stored_score_range": (
                    {
                        "minimum": round(min(scores), 6),
                        "maximum": round(max(scores), 6),
                    }
                    if scores
                    else None
                ),
                "status": (
                    "no_evaluable_rows"
                    if not actual
                    else "single_actual_class"
                    if not class_coverage_complete
                    else "evaluated"
                ),
            }
        )

    every_target_has_rows = all(
        result["rows_evaluated"] > 0 for result in results
    )
    every_target_has_both_classes = all(
        result["class_coverage_complete"] for result in results
    )
    if not every_target_has_rows:
        status = "awaiting_evaluable_rows"
    elif not every_target_has_both_classes:
        status = "insufficient_class_coverage"
    else:
        status = "evaluated"

    return {
        "scope": scope,
        "evidence_type": evidence_type,
        "status": status,
        "records_in_scope": len(records),
        "ready_warning_rows": len(evaluated_record_ids),
        "orders_evaluated": len(evaluated_order_ids),
        "excluded_rows_by_reason": dict(sorted(exclusion_counts.items())),
        "targets": results,
        "every_target_has_rows": every_target_has_rows,
        "every_target_has_both_actual_classes": (
            every_target_has_both_classes
        ),
        "production_approval_supported": False,
    }


def build_early_warning_validation_report(
    snapshot: list[dict[str, Any]],
) -> dict[str, Any]:
    """Build separated reports without recomputing historical predictions."""
    independent = [
        record
        for record in snapshot
        if record.get("independent_validation_eligible", True)
    ]
    retrospective = [
        record
        for record in snapshot
        if not record.get("independent_validation_eligible", True)
    ]
    return {
        "report_version": REPORT_VERSION,
        "status": "success",
        "prediction_source": (
            "Stored early_warning snapshots created before outcome verification"
        ),
        "outcome_source": "Supervisor-verified next-three-production-day labels",
        "scope_mixing_detected": False,
        "production_approved": False,
        "independent_validation": _scope_report(
            independent,
            scope="independent_validation",
            evidence_type="Unseen real-order evidence",
        ),
        "retrospective_training_reuse": _scope_report(
            retrospective,
            scope="retrospective_training_reuse",
            evidence_type=(
                "Workflow evidence from data used during model development"
            ),
        ),
        "reported_metrics": ["accuracy", "macro_f1", "f1"],
        "limitations": [
            "Retrospective and independent records are never combined.",
            "A metric based on one actual class is not production evidence.",
            "Scores use the decision saved at prediction time; models are not rerun.",
            "Production approval requires new unseen orders with both classes.",
        ],
    }
