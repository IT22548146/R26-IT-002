import tempfile
import unittest
from pathlib import Path

import pandas as pd

from components.component3_historical_validation import (
    evaluate_historical_recovery,
    generated_row_mask,
    load_historical_workbook,
)


class Component3HistoricalValidationTests(unittest.TestCase):
    @staticmethod
    def historical_rows() -> pd.DataFrame:
        common = {
            "Bulk_Order_ID": "BULK_TEST_1",
            "Style_ID": "STYLE_1",
            "Buyer_Name": "Buyer",
            "Allocated_Bulk_Plant": "Plant",
            "Plant_Location": "Colombo",
            "Full_Order_Qty": 300,
            "Bulk_Order_Approved_Date": pd.Timestamp("2026-08-14"),
            "Buyer_Required_Date": pd.Timestamp("2026-08-21"),
            "Total_Working_Days": 5,
            "Cutting_Days": 1,
            "Sewing_Days": 2,
            "Daily_Commitment": 100,
            "Daily_Damage_Qty": 1,
            "Max_Daily_Damage_Qty": 3,
            "Machine_Breakdown_Count": 0,
            "System_Recommendation": (
                "Add operators or reassign workers from another line to recover lost pieces."
            ),
        }
        return pd.DataFrame(
            [
                {
                    **common,
                    "Production_Date": pd.Timestamp("2026-08-17"),
                    "Working_Day_No": 1,
                    "Plant_Daily_Output": 80,
                    "Worker_Shortage_Count": 2,
                    "Risk_Type": "Worker Issue",
                    "Cumulative_Completed_Qty": 80,
                },
                {
                    **common,
                    "Production_Date": pd.Timestamp("2026-08-18"),
                    "Working_Day_No": 2,
                    "Plant_Daily_Output": 110,
                    "Worker_Shortage_Count": 1,
                    "Risk_Type": "Worker Issue",
                    "Cumulative_Completed_Qty": 190,
                },
                {
                    **common,
                    "Production_Date": pd.Timestamp("2026-08-19"),
                    "Working_Day_No": 3,
                    "Plant_Daily_Output": 110,
                    "Worker_Shortage_Count": 0,
                    "Risk_Type": "No Issue",
                    "System_Recommendation": "Continue current production plan.",
                    "Cumulative_Completed_Qty": 300,
                },
            ]
        )

    def test_replay_uses_next_workday_and_excludes_final_partial_day(self):
        report, cases = evaluate_historical_recovery(self.historical_rows())

        self.assertEqual(len(cases), 2)
        self.assertEqual(cases.iloc[0]["actual_next_workday_output"], 110)
        self.assertEqual(
            report["dataset"]["capacity_cases_excluding_final_partial_day"], 1
        )
        self.assertEqual(
            report["dataset"][
                "final_partial_day_cases_excluded_from_capacity_metrics"
            ],
            1,
        )
        self.assertEqual(
            report["validation"]["current_output_as_next_workday_baseline"][
                "mae"
            ],
            30.0,
        )
        self.assertEqual(report["dataset"]["orders_completed_before_deadline"], 1)
        self.assertEqual(report["dataset"]["orders_completed_after_deadline"], 0)

    def test_missing_action_fields_prevent_causal_calibration(self):
        report, _ = evaluate_historical_recovery(self.historical_rows())

        decision = report["calibration_decision"]
        self.assertEqual(decision["status"], "observational_only")
        self.assertFalse(decision["engine_parameters_updated"])
        self.assertEqual(decision["action_labeled_rows"], 0)
        self.assertIn("Applied_Action", decision["missing_action_outcome_fields"])

    def test_generated_row_mask_uses_explicit_and_identifier_markers(self):
        data = pd.DataFrame(
            {
                "Bulk_Order_ID": ["BULK0001", "BULK_SYN_1", "BULK_AUG_LOW_1"],
                "Style_ID": ["A", "B", "C"],
                "Synthetic": [False, False, True],
                "Data_Origin": ["Real_Data", "Existing_Generated", "Real_Data"],
            }
        )

        self.assertEqual(generated_row_mask(data).tolist(), [False, True, True])

    def test_loader_finds_offset_header_and_preserves_original_rows(self):
        frame = self.historical_rows()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "history.xlsx"
            with pd.ExcelWriter(path, engine="openpyxl") as writer:
                frame.to_excel(writer, sheet_name="STYLE_1", startrow=6, index=False)

            loaded, summary = load_historical_workbook(path)

        self.assertEqual(len(loaded), 3)
        self.assertEqual(summary["historical_rows_used"], 3)
        self.assertEqual(summary["generated_or_augmented_rows_excluded"], 0)
        self.assertEqual(summary["cumulative_output_mismatch_rows"], 0)


if __name__ == "__main__":
    unittest.main()
