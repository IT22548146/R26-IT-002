import json
import sqlite3
import unittest
from datetime import date, timedelta

from services.sample_planning_service import (
    get_current_plan,
    plan_buyer_queue,
    release_order_reservations,
    reserve_plan_capacity,
    set_priority_order,
)


class SampleOrderPlanningTests(unittest.TestCase):
    def setUp(self):
        self.db = sqlite3.connect(":memory:")
        self.db.row_factory = sqlite3.Row
        self.db.executescript(
            """
            CREATE TABLE organizations (id INTEGER PRIMARY KEY, name TEXT);
            CREATE TABLE users (id INTEGER PRIMARY KEY, org_id INTEGER);
            CREATE TABLE buyers_config (org_id INTEGER, shipment_dow_index INTEGER);
            CREATE TABLE plants (
                id TEXT PRIMARY KEY, name TEXT, location TEXT, quality_rating REAL,
                historical_on_time_rate REAL, plant_type TEXT
            );
            CREATE TABLE plant_monthly_capacity (
                plant_id TEXT, month_year TEXT, total_capacity INTEGER,
                used_capacity INTEGER, UNIQUE(plant_id, month_year)
            );
            CREATE TABLE sample_orders (
                id INTEGER PRIMARY KEY, buyer_id INTEGER, style_number TEXT,
                sample_qty INTEGER, receive_date DATE, buyer_required_date DATE,
                status TEXT, feasibility TEXT, c1_result_json TEXT, created_at DATETIME,
                buyer_priority_rank INTEGER, priority_reason TEXT,
                priority_updated_at DATETIME, priority_locked_at DATETIME
            );
            CREATE TABLE sample_order_plans (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sample_order_id INTEGER, recommended_plant_id TEXT,
                estimated_start_date DATE, estimated_completion_date DATE,
                planned_shipment_date DATE, original_required_date DATE,
                can_meet_original_date INTEGER, delay_days INTEGER,
                planning_action TEXT, plan_status TEXT,
                capacity_snapshot_json TEXT, buyer_message TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE sample_capacity_reservations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sample_order_id INTEGER, plan_id INTEGER, plant_id TEXT,
                capacity_month TEXT, reserved_quantity INTEGER,
                status TEXT, created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                released_at DATETIME, UNIQUE(plan_id)
            );
            """
        )
        self.db.execute("INSERT INTO organizations VALUES (1, 'Tesco')")
        self.db.execute("INSERT INTO users VALUES (10, 1)")
        self.db.execute("INSERT INTO buyers_config VALUES (1, 0)")
        self.db.executemany(
            "INSERT INTO plants VALUES (?,?,?,?,?,?)",
            [
                ("PL01", "Preferred Plant", "A", 4.9, 0.95, "Registered"),
                ("PL02", "Available Plant", "B", 4.5, 0.85, "Registered"),
            ],
        )

    def tearDown(self):
        self.db.close()

    def insert_order(self, order_id, rank, required_date):
        scores = {
            "model2_plant_selection": {
                "all_scores": [
                    {"plant": "Preferred Plant", "composite_score": 0.95},
                    {"plant": "Available Plant", "composite_score": 0.75},
                ]
            }
        }
        self.db.execute(
            """INSERT INTO sample_orders
               (id, buyer_id, style_number, sample_qty, receive_date,
                buyer_required_date, status, feasibility, c1_result_json,
                created_at, buyer_priority_rank)
               VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            (
                order_id,
                10,
                f"STYLE-{order_id}",
                5,
                date.today().isoformat(),
                required_date.isoformat(),
                "Pending",
                "Feasible",
                json.dumps(scores),
                f"2026-01-{order_id:02d}",
                rank,
            ),
        )

    def test_buyer_can_reorder_only_the_complete_editable_queue(self):
        self.insert_order(1, 1, date.today() + timedelta(days=30))
        self.insert_order(2, 2, date.today() + timedelta(days=30))

        result = set_priority_order(self.db, 10, [2, 1])

        self.assertEqual(result, [2, 1])
        ranks = self.db.execute(
            "SELECT id, buyer_priority_rank FROM sample_orders ORDER BY buyer_priority_rank"
        ).fetchall()
        self.assertEqual(
            [(row["id"], row["buyer_priority_rank"]) for row in ranks],
            [(2, 1), (1, 2)],
        )
        with self.assertRaisesRegex(ValueError, "every editable pending"):
            set_priority_order(self.db, 10, [1])

    def test_planner_uses_alternative_plant_when_preferred_capacity_is_full(self):
        required = date.today() + timedelta(days=30)
        self.insert_order(1, 1, required)
        month = date.today().strftime("%Y-%m")
        self.db.executemany(
            "INSERT INTO plant_monthly_capacity VALUES (?,?,?,?)",
            [("PL01", month, 100, 100), ("PL02", month, 100, 0)],
        )

        plans = plan_buyer_queue(self.db, 10)
        plan = get_current_plan(self.db, 1)

        self.assertEqual(len(plans), 1)
        self.assertEqual(plan["recommended_plant_id"], "PL02")
        self.assertEqual(plan["recommended_plant_name"], "Available Plant")
        self.assertTrue(plan["can_meet_original_date"])
        self.assertEqual(plan["capacity_snapshot"]["available_after"], 95)

    def test_planner_proposes_next_shipment_when_original_date_is_impossible(self):
        self.insert_order(1, 1, date.today())

        plan_buyer_queue(self.db, 10)
        plan = get_current_plan(self.db, 1)

        self.assertFalse(plan["can_meet_original_date"])
        self.assertGreater(plan["delay_days"], 0)
        self.assertGreater(plan["planned_shipment_date"], plan["original_required_date"])
        self.assertIn("Propose", plan["planning_action"])

    def test_delayed_plan_capacity_can_be_held_and_released(self):
        self.insert_order(1, 1, date.today())
        plan_buyer_queue(self.db, 10)
        plan = get_current_plan(self.db, 1)

        reservation = reserve_plan_capacity(self.db, 1, plan)
        self.assertEqual(reservation["status"], "Tentative")
        stored = self.db.execute(
            "SELECT status, reserved_quantity FROM sample_capacity_reservations"
        ).fetchone()
        self.assertEqual(stored["reserved_quantity"], 5)
        self.assertEqual(stored["status"], "Tentative")

        release_order_reservations(self.db, 1)
        status = self.db.execute(
            "SELECT status FROM sample_capacity_reservations"
        ).fetchone()["status"]
        self.assertEqual(status, "Released")


if __name__ == "__main__":
    unittest.main()
