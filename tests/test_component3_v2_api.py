import os
import tempfile
import unittest

from app import app
from components import component3


class Component3V2ApiTests(unittest.TestCase):
    def setUp(self):
        self.previous_version = os.environ.get("COMPONENT3_MODEL_VERSION")
        os.environ["COMPONENT3_MODEL_VERSION"] = "v2"
        component3._models.clear()
        self.client = app.test_client()

    def tearDown(self):
        component3._models.clear()
        if self.previous_version is None:
            os.environ.pop("COMPONENT3_MODEL_VERSION", None)
        else:
            os.environ["COMPONENT3_MODEL_VERSION"] = self.previous_version

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
        }

    def test_health_reports_v2_configuration(self):
        response = self.client.get("/api/component3/health")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["configured_model_version"], "v2")

    def test_v2_prediction_uses_canonical_gap(self):
        response = self.client.post("/api/component3/predict", json=self.payload())
        self.assertEqual(response.status_code, 200, response.get_json())
        result = response.get_json()
        self.assertEqual(result["model_version"], "v2")
        self.assertEqual(result["daily_production"]["output_gap"], 23)
        self.assertEqual(result["daily_production"]["gap_pct"], 5.35)

    def test_overproduction_gap_remains_negative(self):
        payload = self.payload()
        payload.update(
            {
                "production_date": "2024-07-08",
                "working_day_no": 6,
                "plant_daily_output": 461,
                "daily_damage_qty": 7,
                "machine_breakdown_count": 0,
                "worker_shortage_count": 0,
                "cumulative_completed_qty": 2_469,
            }
        )
        response = self.client.post("/api/component3/predict", json=payload)
        self.assertEqual(response.status_code, 200, response.get_json())
        result = response.get_json()
        self.assertEqual(result["daily_production"]["output_gap"], -31)
        self.assertEqual(result["daily_production"]["gap_pct"], -7.21)

    def test_prediction_returns_complete_management_output(self):
        response = self.client.post("/api/component3/predict", json=self.payload())
        self.assertEqual(response.status_code, 200, response.get_json())
        result = response.get_json()

        expected_sections = {
            "order_summary",
            "daily_production",
            "risk_detection",
            "alert_system",
            "scheduling",
            "order_progress",
            "production_summary",
            "action",
            "planning_output",
            "recovery_plan",
            "early_warning",
        }
        self.assertTrue(expected_sections.issubset(result))
        self.assertIn(
            result["risk_detection"]["risk_type"],
            component3.RISK_TYPE_MAP,
        )
        self.assertIn(
            result["risk_detection"]["order_risk_level"],
            {"Low", "Medium", "High", "Critical"},
        )
        self.assertGreaterEqual(result["risk_detection"]["risk_confidence"], 0)
        self.assertLessEqual(result["risk_detection"]["risk_confidence"], 1)
        self.assertGreaterEqual(
            result["risk_detection"]["order_risk_probability"], 0
        )
        self.assertLessEqual(
            result["risk_detection"]["order_risk_probability"], 1
        )
        self.assertEqual(
            result["early_warning"]["status"],
            "not_applicable_current_emergency",
        )

    def test_stable_day_returns_experimental_three_day_warnings(self):
        payload = self.payload()
        payload.update(
            {
                "production_date": "2024-07-08",
                "working_day_no": 6,
                "plant_daily_output": 461,
                "daily_damage_qty": 7,
                "machine_breakdown_count": 0,
                "worker_shortage_count": 0,
                "cumulative_completed_qty": 2_469,
            }
        )

        response = self.client.post("/api/component3/predict", json=payload)

        self.assertEqual(response.status_code, 200, response.get_json())
        warning = response.get_json()["early_warning"]
        self.assertEqual(warning["status"], "available")
        self.assertFalse(warning["production_approved"])
        self.assertEqual(warning["horizon_production_days"], 3)
        self.assertEqual(len(warning["warnings"]), 3)
        self.assertEqual(
            warning["history"]["future_or_current_saved_rows_used"],
            0,
        )

    def test_missing_early_warning_models_do_not_break_current_prediction(self):
        payload = self.payload()
        payload.update(
            {
                "production_date": "2024-07-08",
                "working_day_no": 6,
                "plant_daily_output": 461,
                "daily_damage_qty": 7,
                "machine_breakdown_count": 0,
                "worker_shortage_count": 0,
                "cumulative_completed_qty": 2_469,
            }
        )
        previous_directory = app.config.get(
            "COMPONENT3_EARLY_WARNING_MODELS_DIR"
        )
        with tempfile.TemporaryDirectory() as directory:
            app.config["COMPONENT3_EARLY_WARNING_MODELS_DIR"] = directory
            try:
                response = self.client.post(
                    "/api/component3/predict",
                    json=payload,
                )
            finally:
                if previous_directory is None:
                    app.config.pop(
                        "COMPONENT3_EARLY_WARNING_MODELS_DIR",
                        None,
                    )
                else:
                    app.config[
                        "COMPONENT3_EARLY_WARNING_MODELS_DIR"
                    ] = previous_directory

        self.assertEqual(response.status_code, 200, response.get_json())
        result = response.get_json()
        self.assertEqual(result["early_warning"]["status"], "unavailable")
        self.assertFalse(result["early_warning"]["production_approved"])
        self.assertIn("recovery_plan", result)

    def test_recovery_parameters_return_an_exact_worker_plan(self):
        payload = self.payload()
        payload["recovery_parameters"] = {
            "planned_worker_count": 50,
            "max_additional_workers": 3,
        }
        response = self.client.post("/api/component3/predict", json=payload)
        self.assertEqual(response.status_code, 200, response.get_json())

        plan = response.get_json()["recovery_plan"]
        self.assertEqual(plan["engine_version"], "v1-rules")
        self.assertIn("Worker Shortage", plan["triggered_by"])
        self.assertEqual(plan["recommended_option"]["option_id"], "add_workers")
        self.assertGreater(plan["recommended_option"]["additional_workers"], 0)
        self.assertTrue(
            plan["recommended_option"]["feasible_before_deadline"]
        )

    def test_invalid_recovery_parameters_return_bad_request(self):
        payload = self.payload()
        payload["recovery_parameters"] = {"planned_worker_count": 2}
        response = self.client.post("/api/component3/predict", json=payload)
        self.assertEqual(response.status_code, 400)
        self.assertIn("planned_worker_count", response.get_json()["error"])

    def test_invalid_json_is_rejected(self):
        response = self.client.post(
            "/api/component3/predict",
            data="not-json",
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.get_json()["error"],
            "Request body must be valid JSON",
        )

    def test_missing_required_field_is_rejected(self):
        payload = self.payload()
        del payload["full_order_qty"]
        response = self.client.post("/api/component3/predict", json=payload)
        self.assertEqual(response.status_code, 400)
        self.assertIn("full_order_qty", response.get_json()["error"])

    def test_invalid_numeric_value_is_rejected(self):
        payload = self.payload()
        payload["plant_daily_output"] = "not-a-number"
        response = self.client.post("/api/component3/predict", json=payload)
        self.assertEqual(response.status_code, 400)
        self.assertIn("Invalid field value", response.get_json()["error"])

    def test_invalid_date_is_rejected(self):
        payload = self.payload()
        payload["production_date"] = "02-07-2024"
        response = self.client.post("/api/component3/predict", json=payload)
        self.assertEqual(response.status_code, 400)
        self.assertIn("Invalid field value", response.get_json()["error"])

    def test_positive_quantities_are_required(self):
        for field in ("daily_commitment", "full_order_qty", "total_working_days"):
            with self.subTest(field=field):
                payload = self.payload()
                payload[field] = 0
                response = self.client.post("/api/component3/predict", json=payload)
                self.assertEqual(response.status_code, 400)
                self.assertIn(f"{field} must be > 0", response.get_json()["error"])

    def test_working_day_must_be_inside_order_schedule(self):
        for working_day in (0, 109):
            with self.subTest(working_day=working_day):
                payload = self.payload()
                payload["working_day_no"] = working_day
                response = self.client.post("/api/component3/predict", json=payload)
                self.assertEqual(response.status_code, 400)
                self.assertIn("working_day_no", response.get_json()["error"])

    def test_completed_quantity_cannot_exceed_order_quantity(self):
        payload = self.payload()
        payload["cumulative_completed_qty"] = payload["full_order_qty"] + 1
        response = self.client.post("/api/component3/predict", json=payload)
        self.assertEqual(response.status_code, 400)
        self.assertIn("cumulative_completed_qty", response.get_json()["error"])

    def test_negative_operational_values_are_rejected(self):
        fields = (
            "plant_daily_output",
            "daily_damage_qty",
            "max_daily_damage_qty",
            "machine_breakdown_count",
            "worker_shortage_count",
            "cumulative_completed_qty",
            "cutting_days",
            "sewing_days",
        )
        for field in fields:
            with self.subTest(field=field):
                payload = self.payload()
                payload[field] = -1
                response = self.client.post("/api/component3/predict", json=payload)
                self.assertEqual(response.status_code, 400)
                self.assertIn(field, response.get_json()["error"])

    def test_unsupported_model_version_returns_service_unavailable(self):
        os.environ["COMPONENT3_MODEL_VERSION"] = "v99"
        component3._models.clear()
        response = self.client.post("/api/component3/predict", json=self.payload())
        self.assertEqual(response.status_code, 503)
        self.assertIn("Unsupported COMPONENT3_MODEL_VERSION", response.get_json()["error"])

    def test_incident_types_receive_operational_severity(self):
        cases = (
            ({"gap_pct": -1, "risk_type": "No Issue"}, "No Risk"),
            (
                {
                    "gap_pct": -1,
                    "risk_type": "Quality Issue",
                    "damage_exceeded": True,
                },
                "Moderate",
            ),
            (
                {
                    "gap_pct": 3,
                    "risk_type": "Machine Breakdown Issue",
                    "machine_breakdown_count": 2,
                },
                "Critical",
            ),
            (
                {
                    "gap_pct": 2,
                    "risk_type": "Worker Issue",
                    "worker_shortage_count": 6,
                },
                "Moderate",
            ),
        )
        for inputs, expected in cases:
            with self.subTest(risk_type=inputs["risk_type"]):
                self.assertEqual(component3._get_severity(**inputs), expected)


if __name__ == "__main__":
    unittest.main()
