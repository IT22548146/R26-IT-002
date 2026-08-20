import tempfile
import unittest
from pathlib import Path

import joblib

from components.component3_early_warning_data import EARLY_WARNING_FEATURES
from components.component3_early_warning_inference import (
    EarlyWarningModelError,
    build_inference_feature_row,
    clear_early_warning_artifact_cache,
    predict_early_warnings,
)


class Component3EarlyWarningInferenceTests(unittest.TestCase):
    def tearDown(self):
        clear_early_warning_artifact_cache()

    @staticmethod
    def prediction_input(
        day: int,
        *,
        output: int = 100,
        worker_shortage: int = 0,
        machine_breakdown: int = 0,
        damage: int = 1,
    ):
        return {
            "bulk_order_id": "ORDER_EW_1",
            "style_id": "STYLE_EW_1",
            "buyer_name": "Buyer",
            "allocated_bulk_plant": "Plant",
            "plant_location": "Colombo",
            "full_order_qty": 2_000,
            "bulk_order_approved_date": "2026-08-10",
            "buyer_required_date": "2026-09-30",
            "total_working_days": 20,
            "cutting_days": 5,
            "sewing_days": 10,
            "daily_commitment": 100,
            "production_date": f"2026-08-{16 + day:02d}",
            "working_day_no": day,
            "plant_daily_output": output,
            "daily_damage_qty": damage,
            "max_daily_damage_qty": 3,
            "machine_breakdown_count": machine_breakdown,
            "worker_shortage_count": worker_shortage,
            "cumulative_completed_qty": day * 100,
            "recovery_parameters": {},
        }

    @classmethod
    def history_record(
        cls,
        day: int,
        *,
        output: int,
        risk_type: str = "No Issue",
        is_emergency: bool = False,
    ):
        prediction_input = cls.prediction_input(day, output=output)
        return {
            "bulk_order_id": prediction_input["bulk_order_id"],
            "working_day_no": day,
            "production_date": prediction_input["production_date"],
            "risk_type": risk_type,
            "is_emergency": is_emergency,
            "prediction_input": prediction_input,
        }

    def test_feature_builder_uses_only_earlier_rows(self):
        current = self.prediction_input(3, output=90)
        history = [
            self.history_record(
                1,
                output=80,
                risk_type="Machine Breakdown Issue",
                is_emergency=True,
            ),
            self.history_record(2, output=100),
            self.history_record(3, output=777),
            self.history_record(4, output=999),
        ]

        row, evidence = build_inference_feature_row(current, history)

        self.assertEqual(row.loc[0, "History_Days_Available"], 3)
        self.assertEqual(row.loc[0, "Previous_Day_Output"], 100)
        self.assertEqual(row.loc[0, "Output_Change_From_Previous"], -10)
        self.assertEqual(row.loc[0, "Trailing_3D_Avg_Output"], 90)
        self.assertEqual(row.loc[0, "Trailing_3D_Emergency_Days"], 1)
        self.assertEqual(row.loc[0, "Days_Since_Last_Emergency"], 2)
        self.assertEqual(evidence["saved_prior_records"], 2)
        self.assertEqual(evidence["future_or_current_saved_rows_used"], 0)
        self.assertEqual(evidence["status"], "complete")

    def test_real_artifacts_return_three_experimental_warnings(self):
        models_directory = Path(__file__).resolve().parents[1] / "models"

        result = predict_early_warnings(
            self.prediction_input(1, output=105),
            current_risk_type="No Issue",
            history=[],
            models_directory=models_directory,
        )

        self.assertEqual(result["status"], "available")
        self.assertFalse(result["production_approved"])
        self.assertEqual(len(result["warnings"]), 3)
        self.assertEqual(result["history"]["status"], "current_only")
        for warning in result["warnings"]:
            self.assertGreaterEqual(warning["probability"], 0)
            self.assertLessEqual(warning["probability"], 1)
            self.assertEqual(
                set(warning["validation_metrics"]),
                {"accuracy", "macro_f1", "f1"},
            )

    def test_current_emergency_is_not_treated_as_future_warning(self):
        current = self.prediction_input(2, worker_shortage=2)

        result = predict_early_warnings(
            current,
            current_risk_type="Worker Issue",
            history=[],
            models_directory="directory-is-not-needed",
        )

        self.assertEqual(
            result["status"],
            "not_applicable_current_emergency",
        )
        self.assertEqual(result["warnings"], [])
        self.assertIn("recovery plan", result["message"])

    def test_missing_artifacts_are_reported(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(
                EarlyWarningModelError,
                "Missing early-warning model artifact",
            ):
                predict_early_warnings(
                    self.prediction_input(1),
                    current_risk_type="No Issue",
                    history=[],
                    models_directory=directory,
                )

    def test_invalid_artifact_approval_metadata_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            joblib.dump(
                {
                    "target": "Machine_Breakdown_Within_3_Days",
                    "features": EARLY_WARNING_FEATURES,
                    "horizon_production_days": 3,
                    "production_approved": True,
                },
                Path(directory)
                / "c3_early_warning_machine_breakdown_v1.joblib",
            )

            with self.assertRaisesRegex(
                EarlyWarningModelError,
                "approval metadata",
            ):
                predict_early_warnings(
                    self.prediction_input(1),
                    current_risk_type="No Issue",
                    history=[],
                    models_directory=directory,
                )


if __name__ == "__main__":
    unittest.main()
