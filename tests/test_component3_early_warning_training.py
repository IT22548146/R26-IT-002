import tempfile
import unittest
from pathlib import Path

import joblib
import pandas as pd

from components.component3_early_warning_data import EARLY_WARNING_FEATURES
from components.component3_early_warning_training import (
    SUPPORTED_TARGETS,
    build_candidate_models,
    train_early_warning_models,
)


class Component3EarlyWarningTrainingTests(unittest.TestCase):
    @staticmethod
    def labelled_data() -> pd.DataFrame:
        records = []
        for order_number in range(6):
            for row_number in range(8):
                machine_target = row_number % 2
                quality_target = (row_number // 2) % 2
                output_target = (row_number // 4 + order_number) % 2
                record = {
                    "Bulk_Order_ID": f"ORDER_{order_number}",
                    "Machine_Breakdown_Within_3_Days": machine_target,
                    "Quality_Limit_Within_3_Days": quality_target,
                    "Output_Schedule_Risk_Within_3_Days": output_target,
                }
                for feature_number, feature in enumerate(EARLY_WARNING_FEATURES):
                    record[feature] = float(
                        (order_number + row_number + feature_number) % 7
                    )
                record[EARLY_WARNING_FEATURES[0]] = float(machine_target * 10)
                record[EARLY_WARNING_FEATURES[1]] = float(quality_target * 10)
                record[EARLY_WARNING_FEATURES[2]] = float(output_target * 10)
                records.append(record)
        return pd.DataFrame.from_records(records)

    def test_default_candidates_include_baseline_and_advanced_models(self):
        candidates = build_candidate_models()

        self.assertEqual(
            set(candidates),
            {
                "dummy_prior",
                "logistic_regression",
                "random_forest",
                "xgboost",
            },
        )
        self.assertFalse(candidates["dummy_prior"].selectable)
        self.assertTrue(candidates["xgboost"].balanced_fit_weights)

    def test_grouped_comparison_selects_non_baseline_and_builds_artifacts(self):
        data = self.labelled_data()

        experiment, comparison, artifacts = train_early_warning_models(
            data,
            candidate_names=["dummy_prior", "logistic_regression"],
        )

        self.assertEqual(set(experiment["targets"]), set(SUPPORTED_TARGETS))
        self.assertEqual(len(comparison), 6)
        self.assertEqual(set(artifacts), set(SUPPORTED_TARGETS))
        for target, result in experiment["targets"].items():
            self.assertEqual(result["selected_model"], "logistic_regression")
            self.assertEqual(
                set(result["selected_metrics"]),
                {"accuracy", "macro_f1", "f1"},
            )
            self.assertEqual(result["validation"]["fold_count"], 6)
            self.assertTrue(
                result["validation"]["every_row_evaluated_once"]
            )
            self.assertFalse(
                result["validation"]["train_test_group_overlap_detected"]
            )
            self.assertFalse(artifacts[target]["production_approved"])
            self.assertTrue(artifacts[target]["probability_calibrated"])
            self.assertEqual(artifacts[target]["features"], EARLY_WARNING_FEATURES)
            calibration = artifacts[target]["calibration"]
            self.assertTrue(calibration["is_calibrated"])
            self.assertEqual(
                calibration["method"],
                "grouped_sigmoid_on_logit",
            )
            self.assertEqual(calibration["outer_fold_count"], 6)
            self.assertTrue(
                calibration["every_outer_row_evaluated_once"]
            )
            self.assertIn(
                "brier_score",
                calibration["calibrated_probability_metrics"],
            )

    def test_artifact_round_trip_preserves_fitted_pipeline(self):
        data = self.labelled_data()
        _, _, artifacts = train_early_warning_models(
            data,
            target_names=["Machine_Breakdown_Within_3_Days"],
            candidate_names=["logistic_regression"],
        )
        artifact = artifacts["Machine_Breakdown_Within_3_Days"]

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "model.joblib"
            joblib.dump(artifact, path)
            restored = joblib.load(path)

        predictions = restored["estimator"].predict(
            data[EARLY_WARNING_FEATURES].iloc[:4]
        )
        probabilities = restored["estimator"].predict_proba(
            data[EARLY_WARNING_FEATURES].iloc[:4]
        )
        self.assertEqual(len(predictions), 4)
        self.assertEqual(probabilities.shape, (4, 2))
        self.assertTrue(
            ((probabilities >= 0) & (probabilities <= 1)).all()
        )
        self.assertEqual(restored["target"], "Machine_Breakdown_Within_3_Days")

    def test_missing_feature_is_rejected(self):
        data = self.labelled_data().drop(columns=[EARLY_WARNING_FEATURES[-1]])

        with self.assertRaisesRegex(ValueError, "missing required columns"):
            train_early_warning_models(
                data,
                target_names=["Machine_Breakdown_Within_3_Days"],
                candidate_names=["logistic_regression"],
            )

    def test_single_class_target_is_rejected(self):
        data = self.labelled_data()
        data["Machine_Breakdown_Within_3_Days"] = 1

        with self.assertRaisesRegex(ValueError, "both binary classes"):
            train_early_warning_models(
                data,
                target_names=["Machine_Breakdown_Within_3_Days"],
                candidate_names=["logistic_regression"],
            )

    def test_unapproved_target_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "Unsupported Step 5B targets"):
            train_early_warning_models(
                self.labelled_data(),
                target_names=["Worker_Shortage_Within_3_Days"],
                candidate_names=["logistic_regression"],
            )


if __name__ == "__main__":
    unittest.main()
