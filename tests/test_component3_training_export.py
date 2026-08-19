import json
import os
import subprocess
import sys
import tempfile
import unittest
from datetime import date, timedelta
from io import BytesIO
from pathlib import Path

import pandas as pd

from app import app
from components.component3_early_warning_data import (
    EARLY_WARNING_FEATURES,
    TARGET_COLUMNS,
)
from components.component3_monitoring import Component3MonitoringStore
from components.component3_training_export import (
    EXPORT_COLUMNS,
    build_verified_training_dataset,
    dataframe_to_csv_bytes,
    dataframe_to_xlsx_bytes,
)


class TrainingExportFixture:
    @staticmethod
    def prediction_input(day: int, order_id: str) -> dict:
        return {
            "bulk_order_id": order_id,
            "style_id": f"STYLE_{order_id}",
            "buyer_name": "Buyer",
            "allocated_bulk_plant": "Plant",
            "plant_location": "Colombo",
            "full_order_qty": 2_000,
            "bulk_order_approved_date": "2026-08-10",
            "buyer_required_date": "2026-09-30",
            "total_working_days": 20,
            "cutting_days": 5,
            "sewing_days": 10,
            "daily_commitment": 100,
            "production_date": (
                date(2026, 8, 17) + timedelta(days=day - 1)
            ).isoformat(),
            "working_day_no": day,
            "plant_daily_output": 100 + day,
            "daily_damage_qty": 1,
            "max_daily_damage_qty": 3,
            "machine_breakdown_count": 0,
            "worker_shortage_count": 0,
            "cumulative_completed_qty": day * 100,
            "recovery_parameters": {},
        }

    @staticmethod
    def analysis(prediction_input: dict, risk_type: str = "No Issue") -> dict:
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

    @classmethod
    def save_order(
        cls,
        store: Component3MonitoringStore,
        order_id: str,
        actual_types: dict[int, str] | None = None,
        *,
        days: tuple[int, ...] = (1, 2, 3, 4),
        leave_unverified: set[int] | None = None,
    ) -> list[dict]:
        actual_types = actual_types or {}
        leave_unverified = leave_unverified or set()
        records = []
        for day in days:
            prediction_input = cls.prediction_input(day, order_id)
            actual_type = actual_types.get(day)
            if actual_type == "Worker Shortage":
                prediction_input["worker_shortage_count"] = 2
            risk_type = "Worker Issue" if actual_type else "No Issue"
            record = store.create_record(
                prediction_input,
                cls.analysis(prediction_input, risk_type),
                recorded_by="Line Supervisor",
            )
            records.append(record)
            if day not in leave_unverified:
                store.verify_record(
                    record["record_id"],
                    actual_emergency=actual_type is not None,
                    actual_emergency_type=actual_type,
                    verified_by="Factory Supervisor",
                )
        return records


class Component3TrainingExportTests(unittest.TestCase, TrainingExportFixture):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.database_path = os.path.join(
            self.temporary_directory.name,
            "training-export.sqlite3",
        )
        self.store = Component3MonitoringStore(self.database_path)

    def tearDown(self):
        self.temporary_directory.cleanup()

    def test_only_verified_ready_sources_are_exported_without_leakage(self):
        self.save_order(
            self.store,
            "ORDER_POSITIVE",
            {2: "Worker Shortage"},
        )
        dataset, audit = build_verified_training_dataset(
            self.store.training_export_snapshot()
        )

        self.assertEqual(len(dataset), 1)
        self.assertEqual(dataset.columns.tolist(), EXPORT_COLUMNS)
        self.assertEqual(dataset.iloc[0]["Bulk_Order_ID"], "ORDER_POSITIVE")
        self.assertEqual(dataset.iloc[0]["Emergency_Within_1_Day"], 1)
        self.assertEqual(dataset.iloc[0]["Emergency_Within_3_Days"], 1)
        self.assertEqual(
            dataset.iloc[0]["First_Emergency_Type_Within_3_Days"],
            "Worker Shortage",
        )
        self.assertTrue(audit["leakage_controls"]["passed"])
        self.assertEqual(
            audit["leakage_controls"]["future_targets_in_model_features"],
            [],
        )
        self.assertEqual(
            audit["leakage_controls"]["identity_columns_in_model_features"],
            [],
        )
        self.assertEqual(
            audit["schema"]["model_feature_count"],
            len(EARLY_WARNING_FEATURES),
        )
        self.assertTrue(set(TARGET_COLUMNS).isdisjoint(EARLY_WARNING_FEATURES))
        self.assertFalse(audit["primary_target"]["training_ready"])

    def test_positive_and_negative_orders_are_reported_separately(self):
        self.save_order(
            self.store,
            "ORDER_POSITIVE",
            {2: "Worker Shortage"},
        )
        self.save_order(self.store, "ORDER_NEGATIVE")
        dataset, audit = build_verified_training_dataset(
            self.store.training_export_snapshot()
        )

        self.assertEqual(len(dataset), 2)
        primary = audit["primary_target"]
        self.assertEqual(primary["positive_rows"], 1)
        self.assertEqual(primary["negative_rows"], 1)
        self.assertEqual(primary["positive_orders"], 1)
        self.assertEqual(primary["negative_orders"], 1)
        self.assertEqual(primary["positive_rate"], 0.5)

    def test_minimum_rows_and_order_groups_unlock_step_5b(self):
        for index in range(3):
            self.save_order(
                self.store,
                f"POSITIVE_GROUP_{index}",
                {
                    4: "Worker Shortage",
                    8: "Worker Shortage",
                    12: "Worker Shortage",
                },
                days=tuple(range(1, 13)),
            )
            self.save_order(
                self.store,
                f"NEGATIVE_GROUP_{index}",
                days=tuple(range(1, 11)),
            )

        dataset, audit = build_verified_training_dataset(
            self.store.training_export_snapshot()
        )
        primary = audit["primary_target"]
        self.assertEqual(len(dataset), 42)
        self.assertEqual(primary["positive_rows"], 21)
        self.assertEqual(primary["negative_rows"], 21)
        self.assertEqual(primary["positive_orders"], 3)
        self.assertEqual(primary["negative_orders"], 3)
        self.assertTrue(primary["training_ready"])
        self.assertIn("Ready for Step 5B", audit["decision"])

    def test_ready_source_with_unverified_prior_history_is_excluded(self):
        records = self.save_order(
            self.store,
            "ORDER_HISTORY",
            days=(1, 2, 3, 4, 5),
            leave_unverified={1},
        )
        day2 = self.store.get_record(records[1]["record_id"])
        self.assertEqual(day2["label_status"], "Ready")

        dataset, audit = build_verified_training_dataset(
            self.store.training_export_snapshot()
        )
        self.assertTrue(dataset.empty)
        self.assertEqual(audit["dataset"]["ready_source_candidates"], 1)
        self.assertEqual(
            audit["dataset"]["excluded_rows_by_reason"][
                "unverified_prior_history"
            ],
            1,
        )

    def test_missing_working_day_transition_is_reported(self):
        self.save_order(
            self.store,
            "ORDER_GAP",
            days=(1, 3, 4, 5, 6),
        )
        dataset, audit = build_verified_training_dataset(
            self.store.training_export_snapshot()
        )

        self.assertEqual(len(dataset), 1)
        self.assertFalse(audit["sequence_quality"]["passed"])
        self.assertEqual(
            audit["sequence_quality"]["working_day_gap_transitions"],
            1,
        )
        self.assertEqual(
            audit["sequence_quality"]["orders_with_working_day_gaps"],
            ["ORDER_GAP"],
        )
        self.assertFalse(audit["primary_target"]["training_ready"])

    def test_csv_and_excel_include_data_audit_and_column_manifest(self):
        self.save_order(self.store, "ORDER_NEGATIVE")
        dataset, audit = build_verified_training_dataset(
            self.store.training_export_snapshot()
        )

        csv_content = dataframe_to_csv_bytes(dataset).decode("utf-8")
        self.assertTrue(csv_content.startswith("Record_ID,Bulk_Order_ID"))
        self.assertNotIn("Verified_By", csv_content.splitlines()[0])
        self.assertNotIn("Actual_Emergency", csv_content.splitlines()[0])

        workbook = pd.ExcelFile(
            BytesIO(dataframe_to_xlsx_bytes(dataset, audit))
        )
        self.assertEqual(
            workbook.sheet_names,
            ["training_data", "audit_summary", "column_manifest"],
        )
        manifest = pd.read_excel(workbook, sheet_name="column_manifest")
        roles = set(manifest["Role"].tolist())
        self.assertEqual(
            roles,
            {"grouping_or_audit_metadata", "model_feature", "future_target"},
        )

    def test_command_line_export_writes_all_requested_artifacts(self):
        self.save_order(self.store, "ORDER_CLI")
        output_directory = Path(self.temporary_directory.name) / "exports"
        csv_path = output_directory / "training.csv"
        xlsx_path = output_directory / "training.xlsx"
        audit_path = output_directory / "audit.json"
        repository_root = Path(__file__).resolve().parents[1]

        result = subprocess.run(
            [
                sys.executable,
                str(repository_root / "export_component3_training_dataset.py"),
                "--database",
                self.database_path,
                "--csv",
                str(csv_path),
                "--xlsx",
                str(xlsx_path),
                "--audit",
                str(audit_path),
            ],
            cwd=repository_root,
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(csv_path.exists())
        self.assertTrue(xlsx_path.exists())
        self.assertTrue(audit_path.exists())
        audit = json.loads(audit_path.read_text(encoding="utf-8"))
        self.assertEqual(audit["dataset"]["exported_rows"], 1)


class Component3TrainingExportApiTests(unittest.TestCase, TrainingExportFixture):
    def setUp(self):
        self.previous_database = app.config.get("COMPONENT3_TRACKING_DB")
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.database_path = os.path.join(
            self.temporary_directory.name,
            "training-export-api.sqlite3",
        )
        app.config["COMPONENT3_TRACKING_DB"] = self.database_path
        self.store = Component3MonitoringStore(self.database_path)
        self.client = app.test_client()

    def tearDown(self):
        self.temporary_directory.cleanup()
        if self.previous_database is None:
            app.config.pop("COMPONENT3_TRACKING_DB", None)
        else:
            app.config["COMPONENT3_TRACKING_DB"] = self.previous_database

    def test_audit_and_csv_and_excel_downloads(self):
        self.save_order(self.store, "ORDER_DOWNLOAD")

        audit_response = self.client.get(
            "/api/component3/training-dataset-audit"
        )
        self.assertEqual(audit_response.status_code, 200)
        self.assertEqual(audit_response.get_json()["dataset"]["exported_rows"], 1)

        csv_response = self.client.get(
            "/api/component3/training-dataset?format=csv"
        )
        self.assertEqual(csv_response.status_code, 200)
        self.assertIn("text/csv", csv_response.content_type)
        self.assertEqual(csv_response.headers["X-Component3-Export-Rows"], "1")
        self.assertIn(
            "component3_verified_training_dataset.csv",
            csv_response.headers["Content-Disposition"],
        )
        self.assertIn(b"Emergency_Within_3_Days", csv_response.data)

        excel_response = self.client.get(
            "/api/component3/training-dataset?format=xlsx"
        )
        self.assertEqual(excel_response.status_code, 200)
        self.assertIn(
            "spreadsheetml.sheet",
            excel_response.content_type,
        )
        workbook = pd.ExcelFile(BytesIO(excel_response.data))
        self.assertIn("audit_summary", workbook.sheet_names)

    def test_empty_and_invalid_download_requests_are_rejected(self):
        response = self.client.get(
            "/api/component3/training-dataset?format=pdf"
        )
        self.assertEqual(response.status_code, 400)
        response = self.client.get(
            "/api/component3/training-dataset?format=csv"
        )
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.get_json()["audit"]["dataset"]["exported_rows"], 0)


if __name__ == "__main__":
    unittest.main()
