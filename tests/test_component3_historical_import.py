import os
import tempfile
import unittest
from pathlib import Path

from app import app
from components import component3
from components.component3_historical_import import (
    build_historical_import_preview,
    historical_actual_outcome,
    load_historical_order,
    prediction_inputs_match,
)


ROOT = Path(__file__).resolve().parents[1]
COMPONENT3_SOURCE = ROOT / "component3_final_preprossed dataset.xlsx"
COMPONENT2_SOURCE = ROOT / "component2_bulk_order_aligned_to.xlsx"


class Component3HistoricalImportServiceTests(unittest.TestCase):
    def test_preview_marks_training_reuse_and_component2_conflicts(self):
        preview = build_historical_import_preview(
            COMPONENT3_SOURCE,
            COMPONENT2_SOURCE,
            [],
        )

        self.assertEqual(preview["mode"], "retrospective_demo")
        self.assertFalse(preview["independent_validation"])
        self.assertEqual(preview["summary"]["source_rows"], 598)
        self.assertEqual(preview["summary"]["source_orders"], 11)
        self.assertEqual(preview["summary"]["importable_rows"], 598)
        self.assertTrue(
            preview["sources"]["component3_daily"][
                "already_used_for_model_training"
            ]
        )
        self.assertEqual(
            preview["sources"]["component2_master"][
                "matched_component3_orders"
            ],
            11,
        )
        self.assertTrue(
            any(
                order["component2_master"]["conflicting_fields"]
                for order in preview["orders"]
            )
        )

    def test_order_rows_are_canonical_and_chronological(self):
        records = load_historical_order(
            COMPONENT3_SOURCE,
            COMPONENT2_SOURCE,
            "BULK0007",
        )

        self.assertEqual(len(records), 21)
        self.assertEqual(
            [row["prediction_input"]["working_day_no"] for row in records],
            list(range(1, 22)),
        )
        self.assertEqual(
            records[0]["prediction_input"]["bulk_order_id"],
            "BULK0007",
        )
        self.assertIn("actual_emergency", records[0])

    def test_input_comparison_ignores_recovery_parameter_defaults(self):
        record = load_historical_order(
            COMPONENT3_SOURCE,
            COMPONENT2_SOURCE,
            "BULK0007",
        )[0]["prediction_input"]
        changed_defaults = dict(record)
        changed_defaults["recovery_parameters"] = {
            "planned_worker_count": 50,
        }

        self.assertTrue(prediction_inputs_match(record, changed_defaults))
        changed_output = dict(record)
        changed_output["plant_daily_output"] += 1
        self.assertFalse(prediction_inputs_match(record, changed_output))

    def test_source_risk_maps_to_supported_actual_outcome(self):
        actual, actual_type = historical_actual_outcome(
            {
                "Risk_Type": "Working Hours Issue",
                "Machine_Breakdown_Count": 0,
                "Worker_Shortage_Count": 0,
                "Daily_Damage_Qty": 1,
                "Max_Daily_Damage_Qty": 3,
            }
        )

        self.assertTrue(actual)
        self.assertEqual(actual_type, "Output / Schedule Risk")


class Component3HistoricalImportApiTests(unittest.TestCase):
    def setUp(self):
        self.previous_version = os.environ.get("COMPONENT3_MODEL_VERSION")
        self.previous_database = app.config.get("COMPONENT3_TRACKING_DB")
        self.previous_component3_source = app.config.get(
            "COMPONENT3_HISTORICAL_IMPORT_SOURCE"
        )
        self.previous_component2_source = app.config.get(
            "COMPONENT3_COMPONENT2_MASTER_SOURCE"
        )
        os.environ["COMPONENT3_MODEL_VERSION"] = "v2"
        component3._models.clear()
        self.temporary_directory = tempfile.TemporaryDirectory()
        app.config["COMPONENT3_TRACKING_DB"] = os.path.join(
            self.temporary_directory.name,
            "historical-import.sqlite3",
        )
        app.config["COMPONENT3_HISTORICAL_IMPORT_SOURCE"] = str(
            COMPONENT3_SOURCE
        )
        app.config["COMPONENT3_COMPONENT2_MASTER_SOURCE"] = str(
            COMPONENT2_SOURCE
        )
        self.client = app.test_client()

    def tearDown(self):
        component3._models.clear()
        self.temporary_directory.cleanup()
        if self.previous_version is None:
            os.environ.pop("COMPONENT3_MODEL_VERSION", None)
        else:
            os.environ["COMPONENT3_MODEL_VERSION"] = self.previous_version
        for key, previous in (
            ("COMPONENT3_TRACKING_DB", self.previous_database),
            (
                "COMPONENT3_HISTORICAL_IMPORT_SOURCE",
                self.previous_component3_source,
            ),
            (
                "COMPONENT3_COMPONENT2_MASTER_SOURCE",
                self.previous_component2_source,
            ),
        ):
            if previous is None:
                app.config.pop(key, None)
            else:
                app.config[key] = previous

    def test_preview_is_read_only(self):
        response = self.client.get(
            "/api/component3/historical-import/preview"
        )

        self.assertEqual(response.status_code, 200, response.get_json())
        preview = response.get_json()
        self.assertEqual(preview["summary"]["importable_rows"], 598)
        self.assertFalse(preview["independent_validation"])
        readiness = self.client.get(
            "/api/component3/monitoring-readiness"
        ).get_json()
        self.assertEqual(readiness["total_records"], 0)

    def test_import_requires_explicit_retrospective_confirmation(self):
        response = self.client.post(
            "/api/component3/historical-import",
            json={"bulk_order_id": "BULK0007"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn(
            "confirm_retrospective_training_data_reuse",
            response.get_json()["error"],
        )

    def test_verified_import_is_idempotent_and_auditable(self):
        payload = {
            "bulk_order_id": "BULK0007",
            "confirm_retrospective_training_data_reuse": True,
            "verify_historical_outcomes": True,
            "confirm_historical_outcomes_are_actual": True,
            "imported_by": "Researcher",
            "verified_by": "Historical Log Reviewer",
        }

        first = self.client.post(
            "/api/component3/historical-import",
            json=payload,
        )

        self.assertEqual(first.status_code, 200, first.get_json())
        result = first.get_json()
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["imported_rows"], 21)
        self.assertEqual(result["verified_rows"], 21)
        self.assertEqual(result["conflicts"], [])
        self.assertEqual(result["processing_errors"], [])
        self.assertFalse(result["independent_validation"])

        history = self.client.get(
            "/api/component3/orders/BULK0007/monitoring-records?limit=100"
        ).get_json()
        self.assertEqual(history["total"], 21)
        self.assertTrue(
            all(
                item["actual_outcome_status"] == "Verified"
                for item in history["items"]
            )
        )
        self.assertTrue(
            all(
                item["data_origin"] == "historical_training_reuse"
                and not item["independent_validation_eligible"]
                for item in history["items"]
            )
        )
        readiness = self.client.get(
            "/api/component3/monitoring-readiness"
        ).get_json()
        self.assertEqual(readiness["total_records"], 21)
        self.assertEqual(
            readiness["retrospective_training_reuse_records"],
            21,
        )
        self.assertEqual(readiness["three_day_target"]["ready_rows"], 0)
        self.assertGreater(
            readiness["three_day_target"][
                "retrospective_ready_rows_excluded"
            ],
            0,
        )
        export_audit = self.client.get(
            "/api/component3/training-dataset-audit"
        ).get_json()
        self.assertEqual(export_audit["dataset"]["exported_rows"], 0)
        self.assertEqual(
            export_audit["dataset"]["retrospective_records_excluded"],
            21,
        )
        detail = self.client.get(
            "/api/component3/monitoring-records/"
            f"{history['items'][0]['record_id']}"
        ).get_json()["monitoring_record"]
        self.assertFalse(
            detail["analysis"]["historical_import"][
                "independent_validation"
            ]
        )
        self.assertFalse(
            detail["analysis"]["historical_import"][
                "outcome_used_during_prediction"
            ]
        )

        second = self.client.post(
            "/api/component3/historical-import",
            json=payload,
        )
        self.assertEqual(second.status_code, 200, second.get_json())
        repeated = second.get_json()
        self.assertEqual(repeated["imported_rows"], 0)
        self.assertEqual(repeated["existing_matching_rows"], 21)
        self.assertEqual(repeated["already_verified_rows"], 21)
        self.assertEqual(repeated["conflicts"], [])


if __name__ == "__main__":
    unittest.main()
