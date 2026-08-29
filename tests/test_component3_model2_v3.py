import os
import unittest

from app import app
from components import component3
from components.component3_order_risk_features import (
    DEADLINE_FEATURES,
    available_working_days_to_deadline,
    build_order_risk_feature_values,
)


class Component3Model2V3Tests(unittest.TestCase):
    def setUp(self):
        self.previous_version = os.environ.get("COMPONENT3_MODEL_VERSION")
        os.environ["COMPONENT3_MODEL_VERSION"] = "v3"
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
            "bulk_order_id": "V3-SANITY-001",
            "style_id": "V3-STYLE",
            "buyer_name": "Research Buyer",
            "allocated_bulk_plant": "Research Plant",
            "plant_location": "Colombo",
            "full_order_qty": 100,
            "bulk_order_approved_date": "2026-08-18",
            "buyer_required_date": "2026-09-10",
            "total_working_days": 4,
            "cutting_days": 1,
            "sewing_days": 2,
            "daily_commitment": 25,
            "production_date": "2026-08-25",
            "working_day_no": 1,
            "plant_daily_output": 25,
            "daily_damage_qty": 0,
            "max_daily_damage_qty": 1,
            "machine_breakdown_count": 0,
            "worker_shortage_count": 0,
            "cumulative_completed_qty": 25,
        }

    def test_health_reports_v3_configuration(self):
        response = self.client.get("/api/component3/health")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["configured_model_version"], "v3")

    def test_deadline_feature_contract_excludes_actual_completion_date(self):
        self.assertNotIn("Actual_Completion_Date", DEADLINE_FEATURES)
        self.assertEqual(
            available_working_days_to_deadline("2026-08-28", "2026-09-01"),
            2,
        )

    def test_safe_micro_order_is_low_risk(self):
        response = self.client.post(
            "/api/component3/predict",
            json=self.payload(),
        )
        self.assertEqual(response.status_code, 200, response.get_json())
        result = response.get_json()
        risk = result["risk_detection"]
        self.assertEqual(result["model_version"], "v3")
        self.assertEqual(risk["ml_order_risk_level"], "Low")
        self.assertLess(risk["order_risk_probability"], 0.5)

    def test_same_order_with_tight_deadline_is_high_risk(self):
        payload = self.payload()
        payload["buyer_required_date"] = "2026-08-28"
        response = self.client.post(
            "/api/component3/predict",
            json=payload,
        )
        self.assertEqual(response.status_code, 200, response.get_json())
        risk = response.get_json()["risk_detection"]
        self.assertEqual(risk["ml_order_risk_level"], "High")
        self.assertGreaterEqual(risk["order_risk_probability"], 0.5)

    def test_completed_order_remains_actionably_low(self):
        payload = self.payload()
        payload.update(
            {
                "buyer_required_date": "2026-08-28",
                "production_date": "2026-08-28",
                "working_day_no": 4,
                "cumulative_completed_qty": 100,
            }
        )
        response = self.client.post(
            "/api/component3/predict",
            json=payload,
        )
        self.assertEqual(response.status_code, 200, response.get_json())
        result = response.get_json()
        self.assertTrue(result["risk_detection"]["completion_override_applied"])
        self.assertEqual(result["risk_detection"]["order_risk_level"], "Low")
        self.assertEqual(
            result["early_warning"]["status"],
            "not_applicable_order_completed",
        )

    def test_final_required_quantity_does_not_raise_commitment_alert(self):
        payload = self.payload()
        payload.update(
            {
                "bulk_order_id": "V3-FINAL-DAY-001",
                "full_order_qty": 100,
                "bulk_order_approved_date": "2026-08-24",
                "buyer_required_date": "2026-08-29",
                "total_working_days": 5,
                "cutting_days": 1,
                "sewing_days": 4,
                "daily_commitment": 20,
                "production_date": "2026-08-28",
                "working_day_no": 5,
                "plant_daily_output": 10,
                "daily_damage_qty": 0,
                "max_daily_damage_qty": 2,
                "machine_breakdown_count": 0,
                "worker_shortage_count": 0,
                "cumulative_completed_qty": 100,
            }
        )

        response = self.client.post(
            "/api/component3/predict",
            json=payload,
        )

        self.assertEqual(response.status_code, 200, response.get_json())
        result = response.get_json()
        risk = result["risk_detection"]
        self.assertEqual(risk["raw_model_risk_type"], "Commitment Too Low")
        self.assertEqual(risk["raw_model_risk_status"], "Risk")
        self.assertTrue(risk["current_day_completion_override_applied"])
        self.assertEqual(risk["risk_type"], "No Issue")
        self.assertEqual(risk["risk_status"], "No Risk")
        self.assertIsNone(risk["severity"])
        self.assertFalse(result["alert_system"]["alert_generated"])
        self.assertEqual(
            result["action"]["action_required"],
            "Close Completed Order Monitoring",
        )

    def test_feature_values_reflect_deadline_capacity(self):
        payload = self.payload()
        values = build_order_risk_feature_values(
            daily_commitment=payload["daily_commitment"],
            plant_daily_output=payload["plant_daily_output"],
            machine_breakdown_count=payload["machine_breakdown_count"],
            worker_shortage_count=payload["worker_shortage_count"],
            daily_damage_qty=payload["daily_damage_qty"],
            max_daily_damage_qty=payload["max_daily_damage_qty"],
            working_day_no=payload["working_day_no"],
            total_working_days=payload["total_working_days"],
            cutting_days=payload["cutting_days"],
            sewing_days=payload["sewing_days"],
            full_order_qty=payload["full_order_qty"],
            cumulative_completed_qty=payload["cumulative_completed_qty"],
            production_date=payload["production_date"],
            buyer_required_date=payload["buyer_required_date"],
        )
        self.assertEqual(values["Available_Working_Days_To_Deadline"], 12)
        self.assertEqual(values["Required_Daily_Rate_To_Deadline"], 6.25)
        self.assertEqual(values["Commitment_Slack_Pct_To_Deadline"], 75.0)


if __name__ == "__main__":
    unittest.main()
