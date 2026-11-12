import os
import sqlite3
import tempfile
import unittest
from pathlib import Path

from app import app
from components import component3
from middleware.auth_middleware import generate_token


class Component3PlantIsolationTests(unittest.TestCase):
    def setUp(self):
        self.previous_model_version = os.environ.get("COMPONENT3_MODEL_VERSION")
        self.previous_database_path = os.environ.get("DATABASE_PATH")
        self.previous_tracking_database = app.config.get("COMPONENT3_TRACKING_DB")
        self.temporary_directory = tempfile.TemporaryDirectory()
        directory = Path(self.temporary_directory.name)
        self.operational_database = directory / "garment.db"
        self.tracking_database = directory / "component3_tracking.db"
        os.environ["COMPONENT3_MODEL_VERSION"] = "v2"
        os.environ["DATABASE_PATH"] = str(self.operational_database)
        app.config["COMPONENT3_TRACKING_DB"] = str(self.tracking_database)
        component3._models.clear()
        with sqlite3.connect(self.operational_database) as connection:
            connection.execute(
                """CREATE TABLE order_plant_allocations (
                    bulk_order_id INTEGER NOT NULL,
                    plant_id TEXT NOT NULL
                )"""
            )
            connection.executemany(
                "INSERT INTO order_plant_allocations VALUES (?, ?)",
                [(11, "PL01"), (11, "PL02")],
            )
        self.pl01 = self._client("PL01", 101)
        self.pl02 = self._client("PL02", 102)

    def tearDown(self):
        component3._models.clear()
        self.temporary_directory.cleanup()
        if self.previous_model_version is None:
            os.environ.pop("COMPONENT3_MODEL_VERSION", None)
        else:
            os.environ["COMPONENT3_MODEL_VERSION"] = self.previous_model_version
        if self.previous_database_path is None:
            os.environ.pop("DATABASE_PATH", None)
        else:
            os.environ["DATABASE_PATH"] = self.previous_database_path
        if self.previous_tracking_database is None:
            app.config.pop("COMPONENT3_TRACKING_DB", None)
        else:
            app.config["COMPONENT3_TRACKING_DB"] = self.previous_tracking_database

    @staticmethod
    def _client(plant_id: str, user_id: int):
        client = app.test_client()
        client.environ_base["HTTP_AUTHORIZATION"] = (
            f"Bearer {generate_token(user_id, 'PlantManager', plant_id)}"
        )
        return client

    @staticmethod
    def payload(*, output: int) -> dict:
        return {
            "bulk_order_id": "11",
            "style_id": "STYLE-SPLIT",
            "buyer_name": "Buyer",
            "allocated_bulk_plant": "Assignment is replaced by auth scope",
            "plant_location": "Sri Lanka",
            "full_order_qty": 2_000,
            "bulk_order_approved_date": "2024-07-01",
            "buyer_required_date": "2024-09-30",
            "total_working_days": 30,
            "cutting_days": 8,
            "sewing_days": 15,
            "daily_commitment": 100,
            "production_date": "2024-07-08",
            "working_day_no": 1,
            "plant_daily_output": output,
            "daily_damage_qty": 1,
            "max_daily_damage_qty": 3,
            "machine_breakdown_count": 0,
            "worker_shortage_count": 0,
            "cumulative_completed_qty": output,
            "recorded_by": "Plant Manager",
        }

    def test_monitoring_history_and_details_are_isolated_by_authenticated_plant(self):
        pl01_response = self.pl01.post(
            "/api/component3/monitoring-records",
            json=self.payload(output=95),
        )
        pl02_response = self.pl02.post(
            "/api/component3/monitoring-records",
            json=self.payload(output=90),
        )
        self.assertEqual(pl01_response.status_code, 201, pl01_response.get_json())
        self.assertEqual(pl02_response.status_code, 201, pl02_response.get_json())
        pl01_record = pl01_response.get_json()["monitoring_record"]
        pl02_record = pl02_response.get_json()["monitoring_record"]
        self.assertEqual(pl01_record["plant_key"], "PL01")
        self.assertEqual(pl02_record["plant_key"], "PL02")

        pl01_list = self.pl01.get("/api/component3/monitoring-records").get_json()
        pl02_list = self.pl02.get("/api/component3/monitoring-records").get_json()
        self.assertEqual([item["plant_key"] for item in pl01_list["items"]], ["PL01"])
        self.assertEqual([item["plant_key"] for item in pl02_list["items"]], ["PL02"])

        cross_plant_detail = self.pl01.get(
            f"/api/component3/monitoring-records/{pl02_record['record_id']}"
        )
        self.assertEqual(cross_plant_detail.status_code, 404)

    def test_recovery_incidents_are_isolated_by_authenticated_plant(self):
        pl01_payload = self.payload(output=70)
        pl02_payload = self.payload(output=65)
        pl01_payload.pop("recorded_by")
        pl02_payload.pop("recorded_by")
        pl01_payload["created_by"] = "PL01 Manager"
        pl02_payload["created_by"] = "PL02 Manager"

        pl01_response = self.pl01.post("/api/component3/incidents", json=pl01_payload)
        pl02_response = self.pl02.post("/api/component3/incidents", json=pl02_payload)
        self.assertEqual(pl01_response.status_code, 201, pl01_response.get_json())
        self.assertEqual(pl02_response.status_code, 201, pl02_response.get_json())
        pl01_incident = pl01_response.get_json()["incident"]
        pl02_incident = pl02_response.get_json()["incident"]
        self.assertEqual(pl01_incident["plant_key"], "PL01")
        self.assertEqual(pl02_incident["plant_key"], "PL02")

        pl01_list = self.pl01.get("/api/component3/incidents").get_json()
        pl02_list = self.pl02.get("/api/component3/incidents").get_json()
        self.assertEqual([item["plant_key"] for item in pl01_list["items"]], ["PL01"])
        self.assertEqual([item["plant_key"] for item in pl02_list["items"]], ["PL02"])

        cross_plant_detail = self.pl02.get(
            f"/api/component3/incidents/{pl01_incident['incident_id']}"
        )
        self.assertEqual(cross_plant_detail.status_code, 404)


if __name__ == "__main__":
    unittest.main()
