import unittest

import pandas as pd

from components.component3_early_warning_data import EARLY_WARNING_FEATURES
from components.component3_model_optimization import (
    build_tunable_estimators,
    run_optimization_experiment,
)


class Component3ModelOptimizationTests(unittest.TestCase):
    @staticmethod
    def labelled_data() -> pd.DataFrame:
        records = []
        for order_number in range(6):
            for row_number in range(8):
                machine_target = (row_number + order_number) % 2
                record = {
                    "Bulk_Order_ID": f"ORDER_{order_number}",
                    "Machine_Breakdown_Within_3_Days": machine_target,
                }
                for feature_number, feature in enumerate(EARLY_WARNING_FEATURES):
                    record[feature] = float((order_number + row_number + feature_number) % 7)
                record[EARLY_WARNING_FEATURES[0]] = float(machine_target * 10)
                record[EARLY_WARNING_FEATURES[1]] = float(machine_target * 5 + order_number)
                records.append(record)
        return pd.DataFrame.from_records(records)

    def test_estimators_include_linear_and_ensemble_tree_models(self):
        estimators = build_tunable_estimators()

        self.assertEqual(
            set(estimators),
            {"tuned_logistic_regression", "tuned_random_forest"},
        )

    def test_nested_group_search_compares_soft_voting_without_leakage(self):
        report, comparison = run_optimization_experiment(
            self.labelled_data(),
            target_names=["Machine_Breakdown_Within_3_Days"],
            logistic_grid={"model__C": [1.0]},
            forest_grid={
                "model__n_estimators": [10],
                "model__max_depth": [None],
                "model__min_samples_leaf": [1],
                "model__max_features": ["sqrt"],
            },
            voting_weights=[(1, 1)],
            inner_splits=2,
        )

        self.assertEqual(report["parameter_search"], "GridSearchCV")
        result = report["targets"]["Machine_Breakdown_Within_3_Days"]
        self.assertEqual(
            set(result["candidates"]),
            {
                "tuned_logistic_regression",
                "tuned_random_forest",
                "soft_voting_logistic_random_forest",
            },
        )
        self.assertEqual(result["validation"]["outer_fold_count"], 6)
        self.assertTrue(result["validation"]["every_row_evaluated_once"])
        self.assertFalse(result["validation"]["train_test_group_overlap_detected"])
        self.assertEqual(len(comparison), 3)
        self.assertEqual(int(comparison["Selected"].sum()), 1)
        for candidate in result["candidates"].values():
            self.assertIn("final_full_data_best_parameters", candidate)
            self.assertGreaterEqual(candidate["macro_f1"], 0.0)
            self.assertLessEqual(candidate["macro_f1"], 1.0)

    def test_unknown_target_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "Unsupported optimization targets"):
            run_optimization_experiment(
                self.labelled_data(),
                target_names=["Worker_Shortage_Within_3_Days"],
            )


if __name__ == "__main__":
    unittest.main()
