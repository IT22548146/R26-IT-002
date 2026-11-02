import unittest

import pandas as pd

from components.component3_features import FEATURES, build_feature_frame, build_feature_values


class Component3FeatureTests(unittest.TestCase):
    def base_values(self):
        return {
            "daily_commitment": 430,
            "plant_daily_output": 445,
            "machine_breakdown_count": 0,
            "worker_shortage_count": 0,
            "daily_damage_qty": 8,
            "max_daily_damage_qty": 13,
            "working_day_no": 20,
            "total_working_days": 108,
            "cutting_days": 25,
            "sewing_days": 30,
            "full_order_qty": 46_430,
            "cumulative_completed_qty": 8_830,
        }

    def test_overproduction_preserves_negative_gap(self):
        result = build_feature_values(**self.base_values())
        self.assertEqual(result["Output_Gap"], -15)
        self.assertEqual(result["Gap_Pct"], -3.49)

    def test_order_specific_phase_flags(self):
        values = self.base_values()
        cutting = build_feature_values(**values)
        self.assertEqual(cutting["Is_Cutting_Phase"], 1)
        self.assertEqual(cutting["Is_Sewing_Phase"], 0)

        values["working_day_no"] = 30
        sewing = build_feature_values(**values)
        self.assertEqual(sewing["Is_Cutting_Phase"], 0)
        self.assertEqual(sewing["Is_Sewing_Phase"], 1)

    def test_damage_above_max_sets_quality_flag(self):
        values = self.base_values()
        values["daily_damage_qty"] = 14
        result = build_feature_values(**values)
        self.assertEqual(result["Damage_Ratio"], 1.0)
        self.assertEqual(result["Is_Quality_Issue"], 1)

    def test_frame_uses_canonical_feature_order(self):
        values = self.base_values()
        workbook_row = {
            "Daily_Commitment": values["daily_commitment"],
            "Plant_Daily_Output": values["plant_daily_output"],
            "Machine_Breakdown_Count": values["machine_breakdown_count"],
            "Worker_Shortage_Count": values["worker_shortage_count"],
            "Daily_Damage_Qty": values["daily_damage_qty"],
            "Max_Daily_Damage_Qty": values["max_daily_damage_qty"],
            "Working_Day_No": values["working_day_no"],
            "Total_Working_Days": values["total_working_days"],
            "Cutting_Days": values["cutting_days"],
            "Sewing_Days": values["sewing_days"],
            "Full_Order_Qty": values["full_order_qty"],
            "Cumulative_Completed_Qty": values["cumulative_completed_qty"],
        }
        frame = build_feature_frame(pd.DataFrame([workbook_row]))
        self.assertEqual(list(frame.columns), FEATURES)
        self.assertEqual(frame.iloc[0]["Remaining_Qty"], 37_600)

    def test_zero_commitment_is_rejected(self):
        values = self.base_values()
        values["daily_commitment"] = 0
        with self.assertRaisesRegex(ValueError, "daily_commitment"):
            build_feature_values(**values)


if __name__ == "__main__":
    unittest.main()
