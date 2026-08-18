import unittest

import pandas as pd

from components.component3_early_warning_data import (
    EARLY_WARNING_FEATURES,
    EXCLUDED_FROM_MODEL_FEATURES,
    audit_early_warning_dataset,
    build_early_warning_dataset,
    emergency_mask,
)


class Component3EarlyWarningDataTests(unittest.TestCase):
    @staticmethod
    def sequence() -> pd.DataFrame:
        dates = pd.to_datetime(
            [
                "2026-08-17",
                "2026-08-18",
                "2026-08-19",
                "2026-08-20",
                "2026-08-21",
                "2026-08-24",
            ]
        )
        records = []
        for index, date in enumerate(dates, start=1):
            is_worker_incident = index == 2
            records.append(
                {
                    "Bulk_Order_ID": "BULK_TEST_1",
                    "Style_ID": "STYLE_1",
                    "Buyer_Name": "Buyer",
                    "Allocated_Bulk_Plant": "Plant",
                    "Plant_Location": "Colombo",
                    "Full_Order_Qty": 600,
                    "Bulk_Order_Approved_Date": pd.Timestamp("2026-08-10"),
                    "Buyer_Required_Date": pd.Timestamp("2026-08-24"),
                    "Production_Date": date,
                    "Working_Day_No": index,
                    "Total_Working_Days": 6,
                    "Cutting_Days": 2,
                    "Sewing_Days": 3,
                    "Daily_Commitment": 100,
                    "Plant_Daily_Output": 100,
                    "Daily_Damage_Qty": 1,
                    "Max_Daily_Damage_Qty": 3,
                    "Machine_Breakdown_Count": 0,
                    "Worker_Shortage_Count": 1 if is_worker_incident else 0,
                    "Risk_Type": "Worker Issue"
                    if is_worker_incident
                    else "No Issue",
                    "System_Recommendation": "Test recommendation",
                    "Cumulative_Completed_Qty": index * 100,
                }
            )
        return pd.DataFrame(records)

    def test_labels_are_created_only_for_stable_rows_with_full_horizon(self):
        labelled, preparation = build_early_warning_dataset(self.sequence())

        self.assertEqual(len(labelled), 2)
        self.assertEqual(labelled["Production_Date"].tolist(), [
            "2026-08-17",
            "2026-08-19",
        ])
        self.assertEqual(labelled["Emergency_Within_1_Day"].tolist(), [1, 0])
        self.assertEqual(labelled["Emergency_Within_3_Days"].tolist(), [1, 0])
        self.assertEqual(
            labelled["First_Emergency_Type_Within_3_Days"].tolist(),
            ["Worker Issue", "No Emergency"],
        )
        self.assertEqual(preparation["current_emergency_rows_excluded"], 1)
        self.assertEqual(preparation["stable_rows_without_full_horizon_excluded"], 3)

    def test_current_operational_trigger_is_an_emergency_even_if_label_is_no_issue(self):
        data = self.sequence().iloc[[0]].copy()
        data.loc[:, "Machine_Breakdown_Count"] = 1
        data.loc[:, "Risk_Type"] = "No Issue"

        self.assertTrue(bool(emergency_mask(data).iloc[0]))

    def test_future_and_identity_fields_are_not_model_features(self):
        self.assertFalse(
            set(EARLY_WARNING_FEATURES).intersection(EXCLUDED_FROM_MODEL_FEATURES)
        )
        self.assertNotIn("Risk_Type", EARLY_WARNING_FEATURES)
        self.assertNotIn("Order_Risk_Level", EARLY_WARNING_FEATURES)

    def test_audit_does_not_approve_insufficient_grouped_data(self):
        report, _ = audit_early_warning_dataset(self.sequence())

        self.assertTrue(report["step_5a"]["dataset_preparation_completed"])
        self.assertFalse(
            report["step_5a"]["general_early_warning_training_ready"]
        )
        target = report["label_readiness"]["Emergency_Within_3_Days"]
        self.assertFalse(target["ready_for_grouped_modeling"])

    def test_only_three_day_horizon_is_accepted(self):
        with self.assertRaisesRegex(ValueError, "3-production-day"):
            build_early_warning_dataset(self.sequence(), horizon=2)


if __name__ == "__main__":
    unittest.main()
