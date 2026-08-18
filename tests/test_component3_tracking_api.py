import os
import tempfile
import unittest

from app import app
from components import component3


class Component3TrackingApiTests(unittest.TestCase):
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
            "bulk_order_id": "BULK0001",
            "style_id": "AH2495",
            "buyer_name": "Hirdaramani",
            "allocated_bulk_plant": "Sunrose Lanka (Pvt) Ltd",
            "plant_location": "Katubedda",
            "full_order_qty": 46_430,
            "bulk_order_approved_date": "2024-06-29",
            "buyer_required_date": "2024-11-27",
            "total_working_days": 108,
            "cutting_days": 25,
            "sewing_days": 30,
            "daily_commitment": 430,
            "production_date": "2024-07-02",
            "working_day_no": 2,
            "plant_daily_output": 407,
            "daily_damage_qty": 10,
            "max_daily_damage_qty": 13,
            "machine_breakdown_count": 0,
            "worker_shortage_count": 3,
            "cumulative_completed_qty": 845,
            "recovery_parameters": {
                "planned_worker_count": 50,
                "max_additional_workers": 3,
            },
            "created_by": "Production Manager",
        }

    def create_incident(self):
        response = self.client.post(
            "/api/component3/incidents",
            json=self.payload(),
        )
        self.assertEqual(response.status_code, 201, response.get_json())
        return response.get_json()["incident"]

    def approve_and_start(self, incident):
        option_id = incident["recommended_option_id"]
        response = self.client.post(
            f"/api/component3/incidents/{incident['incident_id']}/decision",
            json={
                "selected_option_id": option_id,
                "approved_by": "Factory Manager",
                "notes": "Approved for the next production shift.",
            },
        )
        self.assertEqual(response.status_code, 200, response.get_json())
        self.assertEqual(response.get_json()["incident"]["workflow_status"], "Approved")

        response = self.client.patch(
            f"/api/component3/incidents/{incident['incident_id']}/status",
            json={
                "status": "In Progress",
                "updated_by": "Line Supervisor",
            },
        )
        self.assertEqual(response.status_code, 200, response.get_json())
        return response.get_json()["incident"]

    def test_create_incident_persists_canonical_analysis(self):
        incident = self.create_incident()

        self.assertEqual(incident["workflow_status"], "Pending")
        self.assertEqual(incident["bulk_order_id"], "BULK0001")
        self.assertEqual(incident["recommended_option_id"], "add_workers")
        self.assertEqual(incident["analysis"]["model_version"], "v2")
        self.assertEqual(
            incident["analysis"]["recovery_plan"]["recommended_option"][
                "additional_workers"
            ],
            3,
        )
        self.assertEqual(incident["timeline"][0]["event_type"], "Incident Created")
        self.assertEqual(incident["timeline"][0]["actor"], "Production Manager")

    def test_list_and_order_history_return_saved_incident(self):
        incident = self.create_incident()

        response = self.client.get(
            "/api/component3/incidents?bulk_order_id=BULK0001&status=Pending"
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["total"], 1)
        self.assertEqual(
            response.get_json()["items"][0]["incident_id"],
            incident["incident_id"],
        )

        response = self.client.get(
            "/api/component3/orders/BULK0001/incidents"
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["total"], 1)

    def test_duplicate_order_day_incident_is_rejected(self):
        first = self.client.post(
            "/api/component3/incidents",
            json=self.payload(),
        )
        second = self.client.post(
            "/api/component3/incidents",
            json=self.payload(),
        )
        self.assertEqual(first.status_code, 201)
        self.assertEqual(second.status_code, 409)
        self.assertIn("already exists", second.get_json()["error"])

    def test_complete_workflow_records_effectiveness_and_timeline(self):
        incident = self.create_incident()
        incident = self.approve_and_start(incident)

        response = self.client.post(
            f"/api/component3/incidents/{incident['incident_id']}/outcomes",
            json={
                "outcome_date": "2024-07-03",
                "actual_daily_output": 425,
                "cumulative_completed_qty": 1_270,
                "recorded_by": "Line Supervisor",
                "notes": "Three operators were reassigned.",
            },
        )
        self.assertEqual(response.status_code, 201, response.get_json())
        outcome = response.get_json()["outcome"]
        self.assertEqual(outcome["target_daily_output"], 432.8)
        self.assertEqual(outcome["output_variance"], -7.8)
        self.assertEqual(outcome["effectiveness_pct"], 98.2)

        response = self.client.patch(
            f"/api/component3/incidents/{incident['incident_id']}/status",
            json={
                "status": "Completed",
                "updated_by": "Factory Manager",
                "notes": "Recovery action completed.",
            },
        )
        self.assertEqual(response.status_code, 200, response.get_json())
        completed = response.get_json()["incident"]
        self.assertEqual(completed["workflow_status"], "Completed")
        self.assertEqual(len(completed["outcomes"]), 1)
        self.assertEqual(
            [event["event_type"] for event in completed["timeline"]],
            [
                "Incident Created",
                "Recovery Decision Approved",
                "Status Changed",
                "Outcome Recorded",
                "Status Changed",
            ],
        )

    def test_invalid_recovery_option_is_rejected(self):
        incident = self.create_incident()
        response = self.client.post(
            f"/api/component3/incidents/{incident['incident_id']}/decision",
            json={
                "selected_option_id": "invented-option",
                "approved_by": "Factory Manager",
            },
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("selected_option_id", response.get_json()["error"])

    def test_pending_incident_cannot_skip_decision(self):
        incident = self.create_incident()
        response = self.client.patch(
            f"/api/component3/incidents/{incident['incident_id']}/status",
            json={"status": "Approved", "updated_by": "Factory Manager"},
        )
        self.assertEqual(response.status_code, 409)
        self.assertIn("decision endpoint", response.get_json()["error"])

    def test_outcome_requires_in_progress_incident(self):
        incident = self.create_incident()
        response = self.client.post(
            f"/api/component3/incidents/{incident['incident_id']}/outcomes",
            json={
                "outcome_date": "2024-07-03",
                "actual_daily_output": 425,
                "recorded_by": "Line Supervisor",
            },
        )
        self.assertEqual(response.status_code, 409)

    def test_incident_requires_outcome_before_completion(self):
        incident = self.approve_and_start(self.create_incident())
        response = self.client.patch(
            f"/api/component3/incidents/{incident['incident_id']}/status",
            json={"status": "Completed", "updated_by": "Factory Manager"},
        )
        self.assertEqual(response.status_code, 409)
        self.assertIn("actual production outcome", response.get_json()["error"])

    def test_duplicate_daily_outcome_is_rejected(self):
        incident = self.approve_and_start(self.create_incident())
        payload = {
            "outcome_date": "2024-07-03",
            "actual_daily_output": 425,
            "recorded_by": "Line Supervisor",
        }
        first = self.client.post(
            f"/api/component3/incidents/{incident['incident_id']}/outcomes",
            json=payload,
        )
        second = self.client.post(
            f"/api/component3/incidents/{incident['incident_id']}/outcomes",
            json=payload,
        )
        self.assertEqual(first.status_code, 201)
        self.assertEqual(second.status_code, 409)

    def test_unknown_incident_returns_not_found(self):
        response = self.client.get("/api/component3/incidents/not-a-real-id")
        self.assertEqual(response.status_code, 404)

    def test_invalid_list_filter_is_rejected(self):
        response = self.client.get("/api/component3/incidents?status=Unknown")
        self.assertEqual(response.status_code, 400)
        response = self.client.get("/api/component3/incidents?limit=101")
        self.assertEqual(response.status_code, 400)


if __name__ == "__main__":
    unittest.main()
