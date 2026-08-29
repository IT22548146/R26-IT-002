import unittest
from datetime import datetime

from components.component3_recovery import (
    build_recovery_plan,
    count_available_working_days,
    normalize_recovery_parameters,
)


class Component3RecoveryTests(unittest.TestCase):
    @staticmethod
    def data(**changes):
        values = {
            "full_order_qty": 1_000,
            "cumulative_completed_qty": 500,
            "production_date": "2026-08-17",
            "buyer_required_date": "2026-08-21",
            "plant_daily_output": 100,
            "daily_commitment": 200,
            "worker_shortage_count": 0,
            "machine_breakdown_count": 0,
            "daily_damage_qty": 2,
            "max_daily_damage_qty": 5,
        }
        values.update(changes)
        return values

    def test_available_days_exclude_weekends_and_current_day(self):
        friday = datetime(2026, 8, 21)
        monday = datetime(2026, 8, 24)
        self.assertEqual(count_available_working_days(friday, monday), 1)

    def test_worker_shortage_calculates_required_additional_workers(self):
        plan = build_recovery_plan(
            self.data(
                worker_shortage_count=5,
                recovery_parameters={
                    "planned_worker_count": 20,
                    "max_additional_workers": 5,
                },
            ),
            detected_risk_type="Worker Issue",
        )

        recommendation = plan["recommended_option"]
        self.assertEqual(plan["status"], "recovery_required")
        self.assertEqual(plan["available_working_days"], 4)
        self.assertEqual(plan["required_daily_rate"], 125.0)
        self.assertEqual(plan["daily_recovery_gap"], 25.0)
        self.assertEqual(recommendation["option_id"], "add_workers")
        self.assertEqual(recommendation["additional_workers"], 3)
        self.assertEqual(recommendation["projected_completion_date"], "2026-08-21")
        self.assertTrue(recommendation["feasible_before_deadline"])

    def test_overtime_option_calculates_required_daily_hours(self):
        plan = build_recovery_plan(
            self.data(
                recovery_parameters={
                    "normal_shift_hours": 8,
                    "max_overtime_hours_per_day": 3,
                }
            )
        )

        recommendation = plan["recommended_option"]
        self.assertEqual(recommendation["option_id"], "overtime")
        self.assertEqual(recommendation["required_overtime_hours_per_day"], 2.0)
        self.assertEqual(recommendation["daily_capacity"], 125.0)

    def test_machine_breakdown_calculates_repair_option(self):
        plan = build_recovery_plan(
            self.data(
                machine_breakdown_count=3,
                recovery_parameters={
                    "planned_machine_count": 20,
                    "expected_machine_repair_hours": 4,
                    "available_backup_machines": 3,
                },
            ),
            detected_risk_type="Machine Breakdown Issue",
        )

        recommendation = plan["recommended_option"]
        self.assertEqual(recommendation["option_id"], "repair_machines")
        self.assertEqual(recommendation["repaired_machines"], 3)
        self.assertEqual(recommendation["daily_capacity"], 130.0)
        self.assertTrue(recommendation["feasible_before_deadline"])

    def test_long_repair_time_is_included_in_deadline_feasibility(self):
        plan = build_recovery_plan(
            self.data(
                machine_breakdown_count=3,
                recovery_parameters={
                    "planned_machine_count": 20,
                    "expected_machine_repair_hours": 8,
                },
            )
        )

        repair_option = next(
            option
            for option in plan["alternatives"]
            if option["option_id"] == "repair_machines"
        )
        self.assertFalse(repair_option["feasible_before_deadline"])
        self.assertEqual(repair_option["required_working_days"], 5)
        self.assertEqual(plan["recommended_option"]["option_id"], "overtime")

    def test_insufficient_internal_capacity_requires_manual_escalation(self):
        plan = build_recovery_plan(
            self.data(
                full_order_qty=1_500,
                plant_daily_output=50,
                recovery_parameters={"max_overtime_hours_per_day": 1},
            )
        )

        self.assertTrue(plan["manual_escalation_required"])
        self.assertEqual(
            plan["recommended_option"]["option_id"], "manual_escalation"
        )
        self.assertEqual(
            plan["recommended_option"]["external_daily_capacity_required"],
            193.75,
        )

    def test_current_plan_is_recommended_when_deadline_is_safe(self):
        plan = build_recovery_plan(
            self.data(cumulative_completed_qty=700)
        )

        self.assertEqual(plan["status"], "on_track")
        self.assertFalse(plan["manual_escalation_required"])
        self.assertEqual(plan["recommended_option"]["option_id"], "current_plan")

    def test_completed_order_requires_no_recovery_action(self):
        plan = build_recovery_plan(
            self.data(cumulative_completed_qty=1_000)
        )

        self.assertEqual(plan["status"], "completed")
        self.assertEqual(plan["remaining_quantity"], 0)
        self.assertEqual(plan["required_daily_rate"], 0.0)
        self.assertIsNone(plan["recommended_option"])
        self.assertFalse(plan["manual_escalation_required"])

    def test_invalid_recovery_parameters_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "planned_worker_count"):
            normalize_recovery_parameters(
                {"planned_worker_count": 2},
                worker_shortage_count=3,
                machine_breakdown_count=0,
            )


if __name__ == "__main__":
    unittest.main()
