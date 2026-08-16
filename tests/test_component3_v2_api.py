import os
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


if __name__ == "__main__":
    unittest.main()
