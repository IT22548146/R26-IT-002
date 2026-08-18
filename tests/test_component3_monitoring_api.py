import os
import tempfile
import unittest
from datetime import date, timedelta

from app import app
from components import component3
from components.component3_monitoring import Component3MonitoringStore
from components.component3_tracking import TrackingConflictError


class Component3MonitoringStoreTests(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.store = Component3MonitoringStore(
            os.path.join(self.temporary_directory.name, "monitoring.sqlite3")
        )

    def tearDown(self):
        self.temporary_directory.cleanup()

    @staticmethod
    def prediction_input(
        day: int,
        *,
        order_id: str = "ORDER_1",
        worker_shortage: int = 0,
        machine_breakdown: int = 0,
        damage: int = 1,
        cumulative: int | None = None,
        full_order_qty: int = 2_000,
    ):
        production_date = date(2026, 8, 17) + timedelta(days=day - 1)
        return {
            "bulk_order_id": order_id,
            "style_id": f"STYLE_{order_id}",
            "buyer_name": "Buyer",
            "allocated_bulk_plant": "Plant",
            "plant_location": "Colombo",
            "full_order_qty": full_order_qty,
            "bulk_order_approved_date": "2026-08-10",
            "buyer_required_date": "2026-09-30",
            "total_working_days": 20,
            "cutting_days": 5,
            "sewing_days": 10,
            "daily_commitment": 100,
            "production_date": production_date.isoformat(),
            "working_day_no": day,
            "plant_daily_output": 100,
            "daily_damage_qty": damage,
            "max_daily_damage_qty": 3,
            "machine_breakdown_count": machine_breakdown,
            "worker_shortage_count": worker_shortage,
            "cumulative_completed_qty": cumulative
            if cumulative is not None
            else day * 100,
            "recovery_parameters": {},
        }

    @staticmethod
    def analysis(prediction_input, risk_type: str = "No Issue"):
        return {
            "status": "success",
            "model_version": "test",
            "bulk_order_id": prediction_input["bulk_order_id"],
            "risk_detection": {
                "risk_status": "No Risk" if risk_type == "No Issue" else "Risk",
                "risk_type": risk_type,
                "severity": None if risk_type == "No Issue" else "Moderate",
                "order_risk_level": "Low",
            },
        }

    def save(self, prediction_input, risk_type: str = "No Issue"):
        return self.store.create_record(
            prediction_input,
            self.analysis(prediction_input, risk_type),
            recorded_by="Line Supervisor",
        )

    def test_three_future_days_automatically_label_stable_source_day(self):
        day1 = self.save(self.prediction_input(1))
        self.save(
            self.prediction_input(2, worker_shortage=2),
            "Worker Issue",
        )
        self.save(self.prediction_input(3))
        self.save(self.prediction_input(4))

        labelled = self.store.get_record(day1["record_id"])
        self.assertEqual(labelled["label_status"], "Ready")
        self.assertEqual(labelled["emergency_within_1_day"], 1)
        self.assertEqual(labelled["emergency_within_3_days"], 1)
        self.assertEqual(
            labelled["first_emergency_type_within_3_days"],
            "Worker Issue",
        )
        self.assertEqual(labelled["first_emergency_lead_days"], 1)
        self.assertEqual(labelled["worker_shortage_within_3_days"], 1)

        readiness = self.store.readiness_summary()
        self.assertEqual(readiness["total_records"], 4)
        self.assertEqual(readiness["stable_records"], 3)
        self.assertEqual(readiness["emergency_records"], 1)
        self.assertEqual(readiness["label_status_counts"]["Ready"], 1)

    def test_stable_three_day_window_creates_negative_example(self):
        source = self.save(self.prediction_input(1, order_id="ORDER_2"))
        for day in (2, 3, 4):
            self.save(self.prediction_input(day, order_id="ORDER_2"))

        labelled = self.store.get_record(source["record_id"])
        self.assertEqual(labelled["label_status"], "Ready")
        self.assertEqual(labelled["emergency_within_3_days"], 0)
        self.assertEqual(
            labelled["first_emergency_type_within_3_days"],
            "No Emergency",
        )
        self.assertIsNone(labelled["first_emergency_lead_days"])

    def test_current_emergency_is_not_an_early_warning_source(self):
        record = self.save(
            self.prediction_input(1, machine_breakdown=1),
            "Machine Breakdown Issue",
        )

        self.assertTrue(record["is_emergency"])
        self.assertEqual(record["label_status"], "Not Eligible")

    def test_completed_order_without_full_horizon_is_censored(self):
        day1 = self.save(
            self.prediction_input(
                1,
                order_id="ORDER_3",
                cumulative=900,
                full_order_qty=1_000,
            )
        )
        self.save(
            self.prediction_input(
                2,
                order_id="ORDER_3",
                cumulative=1_000,
                full_order_qty=1_000,
            )
        )

        self.assertEqual(
            self.store.get_record(day1["record_id"])["label_status"],
            "Censored",
        )

    def test_duplicate_and_inconsistent_sequence_are_rejected(self):
        payload = self.prediction_input(1)
        self.save(payload)
        with self.assertRaisesRegex(TrackingConflictError, "already exists"):
            self.save(payload)

        inconsistent = self.prediction_input(2)
        inconsistent["production_date"] = payload["production_date"]
        with self.assertRaisesRegex(TrackingConflictError, "production_date"):
            self.save(inconsistent)


class Component3MonitoringApiTests(unittest.TestCase):
    def setUp(self):
        self.previous_version = os.environ.get("COMPONENT3_MODEL_VERSION")
        self.previous_database = app.config.get("COMPONENT3_TRACKING_DB")
        os.environ["COMPONENT3_MODEL_VERSION"] = "v2"
        component3._models.clear()
        self.temporary_directory = tempfile.TemporaryDirectory()
        app.config["COMPONENT3_TRACKING_DB"] = os.path.join(
            self.temporary_directory.name,
            "tracking.sqlite3",
        )
        self.client = app.test_client()

    def tearDown(self):
        component3._models.clear()
        self.temporary_directory.cleanup()
        if self.previous_version is None:
            os.environ.pop("COMPONENT3_MODEL_VERSION", None)
        else:
            os.environ["COMPONENT3_MODEL_VERSION"] = self.previous_version
        if self.previous_database is None:
            app.config.pop("COMPONENT3_TRACKING_DB", None)
        else:
            app.config["COMPONENT3_TRACKING_DB"] = self.previous_database

    @staticmethod
    def payload():
        return {
            "bulk_order_id": "MONITORING001",
            "style_id": "STYLE001",
            "buyer_name": "Buyer",
            "allocated_bulk_plant": "Plant",
            "plant_location": "Colombo",
            "full_order_qty": 1_000,
            "bulk_order_approved_date": "2024-07-12",
            "buyer_required_date": "2024-10-20",
            "total_working_days": 35,
            "cutting_days": 14,
            "sewing_days": 20,
            "daily_commitment": 100,
            "production_date": "2024-07-19",
            "working_day_no": 1,
            "plant_daily_output": 105,
            "daily_damage_qty": 1,
            "max_daily_damage_qty": 3,
            "machine_breakdown_count": 0,
            "worker_shortage_count": 0,
            "cumulative_completed_qty": 105,
            "recovery_parameters": {
                "planned_worker_count": 20,
                "planned_machine_count": 20,
                "expected_machine_repair_hours": 4,
            },
            "recorded_by": "Line Supervisor",
        }

    def test_create_list_detail_and_readiness(self):
        response = self.client.post(
            "/api/component3/monitoring-records",
            json=self.payload(),
        )
        self.assertEqual(response.status_code, 201, response.get_json())
        record = response.get_json()["monitoring_record"]
        self.assertEqual(record["bulk_order_id"], "MONITORING001")
        self.assertEqual(record["risk_status"], "No Risk")
        self.assertEqual(record["label_status"], "Waiting")
        self.assertEqual(record["analysis"]["model_version"], "v2")

        response = self.client.get(
            "/api/component3/monitoring-records?risk_status=No%20Risk&label_status=Waiting"
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["total"], 1)

        response = self.client.get(
            f"/api/component3/monitoring-records/{record['record_id']}"
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.get_json()["monitoring_record"]["recorded_by"],
            "Line Supervisor",
        )

        response = self.client.get("/api/component3/monitoring-readiness")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["total_records"], 1)
        self.assertFalse(
            response.get_json()["three_day_target"][
                "general_early_warning_training_ready"
            ]
        )

    def test_duplicate_daily_record_is_rejected(self):
        first = self.client.post(
            "/api/component3/monitoring-records",
            json=self.payload(),
        )
        second = self.client.post(
            "/api/component3/monitoring-records",
            json=self.payload(),
        )
        self.assertEqual(first.status_code, 201)
        self.assertEqual(second.status_code, 409)

    def test_invalid_filters_and_unknown_record_are_rejected(self):
        response = self.client.get(
            "/api/component3/monitoring-records?label_status=Unknown"
        )
        self.assertEqual(response.status_code, 400)
        response = self.client.get(
            "/api/component3/monitoring-records?risk_status=Unknown"
        )
        self.assertEqual(response.status_code, 400)
        response = self.client.get(
            "/api/component3/monitoring-records/not-found"
        )
        self.assertEqual(response.status_code, 404)


if __name__ == "__main__":
    unittest.main()
