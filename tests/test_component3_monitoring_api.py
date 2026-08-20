import json
import os
import sqlite3
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

    def verify(
        self,
        record,
        *,
        actual_emergency: bool = False,
        actual_emergency_type: str | None = None,
        notes: str | None = None,
    ):
        return self.store.verify_record(
            record["record_id"],
            actual_emergency=actual_emergency,
            actual_emergency_type=actual_emergency_type,
            verified_by="Factory Supervisor",
            verification_notes=notes,
        )

    def test_three_future_days_automatically_label_stable_source_day(self):
        day1 = self.save(self.prediction_input(1))
        day2 = self.save(
            self.prediction_input(2, worker_shortage=2),
            "Worker Issue",
        )
        day3 = self.save(self.prediction_input(3))
        day4 = self.save(self.prediction_input(4))

        self.verify(day1)
        self.verify(
            day2,
            actual_emergency=True,
            actual_emergency_type="Worker Shortage",
        )
        self.verify(day3)
        self.verify(day4)

        labelled = self.store.get_record(day1["record_id"])
        self.assertEqual(labelled["label_status"], "Ready")
        self.assertEqual(labelled["emergency_within_1_day"], 1)
        self.assertEqual(labelled["emergency_within_3_days"], 1)
        self.assertEqual(
            labelled["first_emergency_type_within_3_days"],
            "Worker Shortage",
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
        records = [source]
        for day in (2, 3, 4):
            records.append(
                self.save(self.prediction_input(day, order_id="ORDER_2"))
            )
        for record in records:
            self.verify(record)

        labelled = self.store.get_record(source["record_id"])
        self.assertEqual(labelled["label_status"], "Ready")
        self.assertEqual(labelled["emergency_within_3_days"], 0)
        self.assertEqual(
            labelled["first_emergency_type_within_3_days"],
            "No Emergency",
        )
        self.assertIsNone(labelled["first_emergency_lead_days"])

    def test_inference_history_returns_only_earlier_order_days(self):
        for day in (1, 2, 3, 4):
            self.save(self.prediction_input(day, order_id="ORDER_HISTORY"))
        self.save(self.prediction_input(1, order_id="OTHER_ORDER"))

        history = self.store.inference_history(
            "ORDER_HISTORY",
            before_working_day=3,
            before_production_date="2026-08-19",
        )

        self.assertEqual(
            [record["working_day_no"] for record in history],
            [1, 2],
        )
        self.assertTrue(
            all(record["bulk_order_id"] == "ORDER_HISTORY" for record in history)
        )
        self.assertTrue(all("prediction_input" in record for record in history))

    def test_current_emergency_is_not_an_early_warning_source(self):
        record = self.save(
            self.prediction_input(1, machine_breakdown=1),
            "Machine Breakdown Issue",
        )

        self.assertTrue(record["is_emergency"])
        self.assertEqual(record["label_status"], "Awaiting Verification")
        verified = self.verify(
            record,
            actual_emergency=True,
            actual_emergency_type="Machine Breakdown",
        )
        self.assertTrue(verified["actual_emergency"])
        self.assertEqual(verified["label_status"], "Not Eligible")

    def test_completed_order_without_full_horizon_is_censored(self):
        day1 = self.save(
            self.prediction_input(
                1,
                order_id="ORDER_3",
                cumulative=900,
                full_order_qty=1_000,
            )
        )
        day2 = self.save(
            self.prediction_input(
                2,
                order_id="ORDER_3",
                cumulative=1_000,
                full_order_qty=1_000,
            )
        )
        self.verify(day1)
        self.verify(day2)

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

    def test_unverified_predictions_never_create_training_labels(self):
        source = self.save(self.prediction_input(1, order_id="ORDER_PENDING"))
        for day in (2, 3, 4):
            self.save(
                self.prediction_input(day, order_id="ORDER_PENDING"),
                "Worker Issue" if day == 2 else "No Issue",
            )

        record = self.store.get_record(source["record_id"])
        self.assertEqual(record["label_status"], "Awaiting Verification")
        self.assertIsNone(record["emergency_within_3_days"])
        readiness = self.store.readiness_summary()
        self.assertEqual(readiness["verified_records"], 0)
        self.assertEqual(readiness["three_day_target"]["ready_rows"], 0)

    def test_verified_actual_outcome_overrides_model_detection(self):
        detected = self.save(
            self.prediction_input(1, order_id="ORDER_OVERRIDE"),
            "Worker Issue",
        )
        verified = self.verify(detected, actual_emergency=False)

        self.assertTrue(verified["is_emergency"])
        self.assertFalse(verified["actual_emergency"])
        self.assertEqual(verified["label_status"], "Waiting")

    def test_reverification_keeps_an_audit_history(self):
        record = self.save(self.prediction_input(1, order_id="ORDER_AUDIT"))
        self.verify(record, notes="No disruption observed")
        corrected = self.verify(
            record,
            actual_emergency=True,
            actual_emergency_type="Other Emergency",
            notes="Corrected after supervisor review",
        )

        self.assertEqual(len(corrected["verification_history"]), 2)
        self.assertTrue(corrected["verification_history"][0]["actual_emergency"])
        self.assertEqual(corrected["label_status"], "Not Eligible")

    def test_existing_monitoring_database_is_migrated_without_data_loss(self):
        database_path = os.path.join(
            self.temporary_directory.name,
            "legacy-monitoring.sqlite3",
        )
        prediction_input = self.prediction_input(1, order_id="LEGACY_ORDER")
        analysis = self.analysis(prediction_input)
        with sqlite3.connect(database_path) as connection:
            connection.executescript(
                """
                CREATE TABLE component3_daily_monitoring (
                    record_id TEXT PRIMARY KEY,
                    bulk_order_id TEXT NOT NULL,
                    style_id TEXT NOT NULL,
                    production_date TEXT NOT NULL,
                    working_day_no INTEGER NOT NULL,
                    risk_status TEXT NOT NULL,
                    risk_type TEXT NOT NULL,
                    severity TEXT,
                    is_emergency INTEGER NOT NULL,
                    prediction_input_json TEXT NOT NULL,
                    analysis_json TEXT NOT NULL,
                    recorded_by TEXT NOT NULL,
                    label_status TEXT NOT NULL DEFAULT 'Waiting',
                    emergency_within_1_day INTEGER,
                    emergency_within_3_days INTEGER,
                    first_emergency_type_within_3_days TEXT,
                    first_emergency_lead_days INTEGER,
                    worker_shortage_within_3_days INTEGER,
                    machine_breakdown_within_3_days INTEGER,
                    quality_limit_within_3_days INTEGER,
                    output_schedule_risk_within_3_days INTEGER,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                """
            )
            connection.execute(
                """
                INSERT INTO component3_daily_monitoring (
                    record_id, bulk_order_id, style_id, production_date,
                    working_day_no, risk_status, risk_type, is_emergency,
                    prediction_input_json, analysis_json, recorded_by,
                    label_status, emergency_within_1_day,
                    emergency_within_3_days,
                    first_emergency_type_within_3_days,
                    worker_shortage_within_3_days,
                    machine_breakdown_within_3_days,
                    quality_limit_within_3_days,
                    output_schedule_risk_within_3_days,
                    created_at, updated_at
                ) VALUES (
                    'legacy-record', 'LEGACY_ORDER', 'STYLE_LEGACY_ORDER',
                    '2026-08-17', 1, 'No Risk', 'No Issue', 0,
                    ?, ?, 'Legacy Supervisor', 'Ready', 0, 0,
                    'No Emergency', 0, 0, 0, 0,
                    '2026-08-17T00:00:00+00:00',
                    '2026-08-17T00:00:00+00:00'
                )
                """,
                (json.dumps(prediction_input), json.dumps(analysis)),
            )

        migrated_store = Component3MonitoringStore(database_path)
        migrated = migrated_store.get_record("legacy-record")
        self.assertEqual(migrated["actual_outcome_status"], "Pending")
        self.assertEqual(migrated["label_status"], "Awaiting Verification")
        self.assertIsNone(migrated["emergency_within_3_days"])
        self.assertEqual(migrated["recorded_by"], "Legacy Supervisor")

        verified = migrated_store.verify_record(
            "legacy-record",
            actual_emergency=False,
            actual_emergency_type=None,
            verified_by="Migration Verifier",
        )
        self.assertEqual(verified["actual_outcome_status"], "Verified")
        self.assertEqual(len(verified["verification_history"]), 1)


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
        self.assertEqual(record["actual_outcome_status"], "Pending")
        self.assertEqual(record["label_status"], "Awaiting Verification")
        self.assertEqual(record["analysis"]["model_version"], "v2")

        response = self.client.get(
            "/api/component3/monitoring-records?risk_status=No%20Risk"
            "&label_status=Awaiting%20Verification"
            "&verification_status=Pending"
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
        self.assertEqual(response.get_json()["verified_records"], 0)
        self.assertEqual(response.get_json()["pending_verification_records"], 1)
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

    def test_next_saved_day_uses_only_earlier_same_order_history(self):
        first = self.client.post(
            "/api/component3/monitoring-records",
            json=self.payload(),
        )
        self.assertEqual(first.status_code, 201, first.get_json())

        second_payload = self.payload()
        second_payload.update(
            {
                "production_date": "2024-07-22",
                "working_day_no": 2,
                "cumulative_completed_qty": 210,
            }
        )
        second = self.client.post(
            "/api/component3/monitoring-records",
            json=second_payload,
        )

        self.assertEqual(second.status_code, 201, second.get_json())
        warning = second.get_json()["monitoring_record"]["analysis"][
            "early_warning"
        ]
        self.assertEqual(warning["status"], "available")
        self.assertEqual(warning["history"]["saved_prior_records"], 1)
        self.assertEqual(warning["history"]["status"], "partial")
        self.assertEqual(
            warning["history"]["future_or_current_saved_rows_used"],
            0,
        )

    def test_supervisor_can_verify_and_correct_actual_outcome(self):
        created = self.client.post(
            "/api/component3/monitoring-records",
            json=self.payload(),
        ).get_json()["monitoring_record"]
        endpoint = (
            f"/api/component3/monitoring-records/{created['record_id']}"
            "/verification"
        )

        response = self.client.put(
            endpoint,
            json={
                "actual_emergency": False,
                "verified_by": "Shift Supervisor",
                "verification_notes": "No actual disruption",
            },
        )
        self.assertEqual(response.status_code, 200, response.get_json())
        record = response.get_json()["monitoring_record"]
        self.assertEqual(record["actual_outcome_status"], "Verified")
        self.assertFalse(record["actual_emergency"])
        self.assertEqual(record["label_status"], "Waiting")
        self.assertEqual(len(record["verification_history"]), 1)

        corrected = self.client.put(
            endpoint,
            json={
                "actual_emergency": True,
                "actual_emergency_type": "Machine Breakdown",
                "verified_by": "Factory Manager",
                "verification_notes": "Maintenance log confirmed failure",
            },
        )
        self.assertEqual(corrected.status_code, 200, corrected.get_json())
        record = corrected.get_json()["monitoring_record"]
        self.assertTrue(record["actual_emergency"])
        self.assertEqual(record["actual_emergency_type"], "Machine Breakdown")
        self.assertEqual(record["label_status"], "Not Eligible")
        self.assertEqual(len(record["verification_history"]), 2)

        readiness = self.client.get(
            "/api/component3/monitoring-readiness"
        ).get_json()
        self.assertEqual(readiness["verified_records"], 1)
        self.assertEqual(readiness["emergency_records"], 1)

    def test_verification_payload_requires_consistent_actual_outcome(self):
        created = self.client.post(
            "/api/component3/monitoring-records",
            json=self.payload(),
        ).get_json()["monitoring_record"]
        endpoint = (
            f"/api/component3/monitoring-records/{created['record_id']}"
            "/verification"
        )

        response = self.client.put(
            endpoint,
            json={"actual_emergency": "yes", "verified_by": "Supervisor"},
        )
        self.assertEqual(response.status_code, 400)
        response = self.client.put(
            endpoint,
            json={"actual_emergency": True, "verified_by": "Supervisor"},
        )
        self.assertEqual(response.status_code, 400)
        response = self.client.put(
            endpoint,
            json={
                "actual_emergency": False,
                "actual_emergency_type": "Quality Issue",
                "verified_by": "Supervisor",
            },
        )
        self.assertEqual(response.status_code, 400)

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
            "/api/component3/monitoring-records?verification_status=Unknown"
        )
        self.assertEqual(response.status_code, 400)
        response = self.client.get(
            "/api/component3/monitoring-records/not-found"
        )
        self.assertEqual(response.status_code, 404)
        response = self.client.put(
            "/api/component3/monitoring-records/not-found/verification",
            json={
                "actual_emergency": False,
                "verified_by": "Supervisor",
            },
        )
        self.assertEqual(response.status_code, 404)


if __name__ == "__main__":
    unittest.main()
