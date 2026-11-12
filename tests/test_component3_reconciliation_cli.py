import json
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]


class Component3ReconciliationCliTests(unittest.TestCase):
    @staticmethod
    def create_tracking_database(path: Path) -> None:
        prediction_input = {
            "integrated_plant_id": "PL01",
            "working_day_no": 1,
            "plant_daily_output": 100,
            "daily_damage_qty": 1,
            "max_daily_damage_qty": 3,
            "machine_breakdown_count": 0,
            "worker_shortage_count": 0,
            "cumulative_completed_qty": 100,
        }
        analysis = {
            "model_version": "v3",
            "prediction_contract_version": "component3-prediction-v1",
            "risk_detection": {"risk_type": "No Issue"},
        }
        with sqlite3.connect(path) as connection:
            connection.execute(
                """CREATE TABLE component3_daily_monitoring (
                    bulk_order_id TEXT, plant_key TEXT, production_date TEXT,
                    prediction_input_json TEXT, analysis_json TEXT, data_origin TEXT
                )"""
            )
            connection.execute(
                "INSERT INTO component3_daily_monitoring VALUES (?, ?, ?, ?, ?, ?)",
                (
                    "11",
                    "PL01",
                    "2026-08-24",
                    json.dumps(prediction_input),
                    json.dumps(analysis),
                    "live_monitoring",
                ),
            )

    @staticmethod
    def create_operational_database(path: Path) -> None:
        analysis = {
            "model_version": "v3",
            "prediction_contract_version": "component3-prediction-v1",
            "risk_detection": {"risk_type": "No Issue"},
        }
        with sqlite3.connect(path) as connection:
            connection.execute(
                """CREATE TABLE daily_logs (
                    bulk_order_id INTEGER, plant_id TEXT, log_date TEXT,
                    working_day_no INTEGER, plant_daily_output INTEGER,
                    daily_damage_qty INTEGER, max_daily_damage_qty INTEGER,
                    machine_breakdown_count INTEGER, worker_shortage_count INTEGER,
                    cumulative_completed_qty INTEGER, c3_result_json TEXT
                )"""
            )
            connection.execute(
                "INSERT INTO daily_logs VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    11,
                    "PL01",
                    "2026-08-24",
                    1,
                    100,
                    1,
                    3,
                    0,
                    0,
                    100,
                    json.dumps(analysis),
                ),
            )

    def test_cli_writes_a_consistent_report(self):
        with tempfile.TemporaryDirectory() as directory:
            tracking = Path(directory) / "tracking.db"
            operational = Path(directory) / "garment.db"
            output = Path(directory) / "report.json"
            self.create_tracking_database(tracking)
            self.create_operational_database(operational)

            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "scripts.component3.audit_component3_persistence",
                    "--tracking-database",
                    str(tracking),
                    "--operational-database",
                    str(operational),
                    "--output",
                    str(output),
                ],
                cwd=PROJECT_ROOT,
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(result.stdout)["status"], "consistent")
            self.assertEqual(json.loads(output.read_text())["summary"]["matched_rows"], 1)


if __name__ == "__main__":
    unittest.main()
