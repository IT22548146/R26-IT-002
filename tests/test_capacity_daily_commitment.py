import sqlite3
import unittest

from services.capacity_service import calculate_assignment_daily_commitment


class AssignmentDailyCommitmentTests(unittest.TestCase):
    def setUp(self):
        self.db = sqlite3.connect(":memory:")
        self.db.row_factory = sqlite3.Row
        self.db.execute(
            """CREATE TABLE plant_monthly_capacity (
                   plant_id TEXT,
                   month_year TEXT,
                   total_capacity INTEGER,
                   used_capacity INTEGER
               )"""
        )

    def tearDown(self):
        self.db.close()

    def seed_capacity(self, total_capacity):
        self.db.executemany(
            """INSERT INTO plant_monthly_capacity
               (plant_id, month_year, total_capacity, used_capacity)
               VALUES ('PL01', ?, ?, 0)""",
            (("2026-08", total_capacity), ("2026-09", total_capacity)),
        )

    def test_uses_c2_phase_days_when_capacity_can_meet_required_rate(self):
        self.seed_capacity(50_000)
        result = calculate_assignment_daily_commitment(
            "PL01",
            1_500,
            "2026-08-20",
            "2026-09-22",
            {"production_days": {"embroidery_days": 6}},
            db=self.db,
        )

        self.assertEqual(result["required_daily_rate"], 250)
        self.assertEqual(result["daily_commitment"], 250)
        self.assertTrue(result["capacity_sufficient"])

    def test_caps_target_at_assigned_plant_daily_capacity(self):
        self.seed_capacity(1_000)
        result = calculate_assignment_daily_commitment(
            "PL01",
            1_500,
            "2026-08-20",
            "2026-09-22",
            {"production_days": {"embroidery_days": 6}},
            db=self.db,
        )

        self.assertEqual(result["plant_daily_capacity"], 40)
        self.assertEqual(result["daily_commitment"], 40)
        self.assertFalse(result["capacity_sufficient"])


if __name__ == "__main__":
    unittest.main()
