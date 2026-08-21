import unittest

from components.component3_early_warning_validation import (
    TARGET_SPECS,
    build_early_warning_validation_report,
)


class Component3EarlyWarningValidationTests(unittest.TestCase):
    @staticmethod
    def record(
        record_id: str,
        *,
        independent: bool,
        actual: tuple[int, int, int],
        predicted: tuple[int, int, int],
    ):
        warnings = []
        for spec, decision in zip(TARGET_SPECS, predicted):
            warnings.append(
                {
                    "target": spec["target"],
                    "probability": 0.8 if decision else 0.2,
                    "warning_predicted": bool(decision),
                }
            )
        return {
            "record_id": record_id,
            "bulk_order_id": f"ORDER_{record_id}",
            "actual_outcome_status": "Verified",
            "actual_emergency": False,
            "label_status": "Ready",
            "machine_breakdown_within_3_days": actual[0],
            "quality_limit_within_3_days": actual[1],
            "output_schedule_risk_within_3_days": actual[2],
            "independent_validation_eligible": independent,
            "analysis": {
                "early_warning": {
                    "status": "available",
                    "warnings": warnings,
                }
            },
        }

    def test_metrics_use_saved_decisions_and_keep_scopes_separate(self):
        snapshot = [
            self.record(
                "A",
                independent=True,
                actual=(1, 0, 1),
                predicted=(1, 0, 0),
            ),
            self.record(
                "B",
                independent=True,
                actual=(0, 1, 0),
                predicted=(1, 0, 0),
            ),
            self.record(
                "R",
                independent=False,
                actual=(1, 0, 1),
                predicted=(1, 0, 1),
            ),
        ]

        report = build_early_warning_validation_report(snapshot)

        self.assertFalse(report["scope_mixing_detected"])
        independent = report["independent_validation"]
        retrospective = report["retrospective_training_reuse"]
        self.assertEqual(independent["ready_warning_rows"], 2)
        self.assertEqual(retrospective["ready_warning_rows"], 1)
        self.assertEqual(independent["status"], "evaluated")
        machine = independent["targets"][0]
        self.assertEqual(machine["metrics"]["accuracy"], 0.5)
        self.assertEqual(machine["metrics"]["macro_f1"], 0.333333)
        self.assertEqual(machine["metrics"]["f1"], 0.666667)
        self.assertEqual(
            set(machine["metrics"]),
            {"accuracy", "macro_f1", "f1"},
        )
        self.assertEqual(
            retrospective["status"],
            "insufficient_class_coverage",
        )

    def test_unverified_or_missing_warning_rows_are_excluded(self):
        unverified = self.record(
            "U",
            independent=True,
            actual=(0, 0, 0),
            predicted=(0, 0, 0),
        )
        unverified["actual_outcome_status"] = "Pending"
        unavailable = self.record(
            "N",
            independent=True,
            actual=(0, 0, 0),
            predicted=(0, 0, 0),
        )
        unavailable["analysis"]["early_warning"]["status"] = (
            "not_applicable_current_emergency"
        )

        report = build_early_warning_validation_report(
            [unverified, unavailable]
        )["independent_validation"]

        self.assertEqual(report["ready_warning_rows"], 0)
        self.assertEqual(report["status"], "awaiting_evaluable_rows")
        self.assertEqual(
            report["excluded_rows_by_reason"],
            {
                "actual_outcome_not_verified": 1,
                "stored_early_warning_not_available": 1,
            },
        )
        self.assertTrue(
            all(target["metrics"] is None for target in report["targets"])
        )


if __name__ == "__main__":
    unittest.main()
