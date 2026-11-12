import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from components.component3_monitoring import Component3MonitoringStore
from components.component3_reconciliation import audit_component3_persistence


class Component3ReconciliationTests(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.directory = Path(self.temporary_directory.name)
        self.tracking_database = self.directory / "tracking.db"
        self.operational_database = self.directory / "garment.db"
        self.store = Component3MonitoringStore(str(self.tracking_database))
        with sqlite3.connect(self.operational_database) as connection:
            connection.execute(
                """CREATE TABLE daily_logs (
                    bulk_order_id INTEGER,
                    plant_id TEXT,
                    log_date TEXT,
                    working_day_no INTEGER,
                    plant_daily_output INTEGER,
                    daily_damage_qty INTEGER,
                    max_daily_damage_qty INTEGER,
                    machine_breakdown_count INTEGER,
                    worker_shortage_count INTEGER,
                    cumulative_completed_qty INTEGER,
                    c3_result_json TEXT
                )"""
            )

    def tearDown(self):
        self.temporary_directory.cleanup()

    @staticmethod
    def prediction_input() -> dict:
        return {
            "bulk_order_id": "11",
            "integrated_plant_id": "PL01",
            "style_id": "STYLE-1",
            "buyer_name": "Buyer",
            "allocated_bulk_plant": "Dinusha",
            "plant_location": "Weliveriya",
            "full_order_qty": 1_000,
            "bulk_order_approved_date": "2026-08-20",
            "buyer_required_date": "2026-09-22",
            "total_working_days": 20,
            "cutting_days": 5,
            "sewing_days": 10,
            "daily_commitment": 100,
            "production_date": "2026-08-24",
            "working_day_no": 1,
            "plant_daily_output": 95,
            "daily_damage_qty": 1,
            "max_daily_damage_qty": 3,
            "machine_breakdown_count": 0,
            "worker_shortage_count": 0,
            "cumulative_completed_qty": 95,
            "recovery_parameters": {},
        }

    @staticmethod
    def analysis() -> dict:
        return {
            "model_version": "v3",
            "prediction_contract_version": "component3-prediction-v1",
            "risk_detection": {"risk_type": "No Issue"},
        }

    def save_tracking(self) -> None:
        self.store.create_record(
            self.prediction_input(),
            self.analysis(),
            recorded_by="Plant Manager",
        )

    def save_operational(self, *, output: int = 95) -> None:
        payload = self.prediction_input()
        with sqlite3.connect(self.operational_database) as connection:
            connection.execute(
                """INSERT INTO daily_logs VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    11,
                    "PL01",
                    payload["production_date"],
                    payload["working_day_no"],
                    output,
                    payload["daily_damage_qty"],
                    payload["max_daily_damage_qty"],
                    payload["machine_breakdown_count"],
                    payload["worker_shortage_count"],
                    payload["cumulative_completed_qty"],
                    json.dumps(self.analysis()),
                ),
            )

    def test_matching_integrated_records_are_consistent(self):
        self.save_tracking()
        self.save_operational()

        report = audit_component3_persistence(
            self.tracking_database,
            self.operational_database,
        )

        self.assertEqual(report["status"], "consistent")
        self.assertTrue(report["read_only"])
        self.assertEqual(report["summary"]["matched_rows"], 1)
        self.assertEqual(report["summary"]["issue_count"], 0)

    def test_value_mismatch_is_reported_by_order_plant_and_date(self):
        self.save_tracking()
        self.save_operational(output=90)

        report = audit_component3_persistence(
            self.tracking_database,
            self.operational_database,
        )

        self.assertEqual(report["status"], "inconsistent")
        mismatch = report["mismatches"][0]
        self.assertEqual(mismatch["bulk_order_id"], "11")
        self.assertEqual(mismatch["plant_id"], "PL01")
        self.assertEqual(mismatch["production_date"], "2026-08-24")
        self.assertEqual(
            mismatch["differing_fields"]["plant_daily_output"],
            {"tracking": 95, "operational": 90},
        )

    def test_missing_side_is_reported(self):
        self.save_tracking()
        report = audit_component3_persistence(
            self.tracking_database,
            self.operational_database,
        )
        self.assertEqual(report["summary"]["missing_in_operational"], 1)


if __name__ == "__main__":
    unittest.main()
