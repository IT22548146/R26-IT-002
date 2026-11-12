import csv
import unittest
from io import StringIO

from components.component3_monitoring_export import (
    MONITORING_EXPORT_COLUMNS,
    monitoring_records_to_csv_bytes,
)


class Component3MonitoringExportTests(unittest.TestCase):
    def test_export_has_a_stable_schema_and_utf8_bom(self):
        content = monitoring_records_to_csv_bytes(
            [
                {
                    "record_id": "record-1",
                    "bulk_order_id": "11",
                    "plant_key": "PL01",
                    "buyer_name": "Buyer",
                    "production_date": "2026-08-24",
                    "working_day_no": 1,
                    "actual_emergency": False,
                }
            ]
        )

        self.assertTrue(content.startswith(b"\xef\xbb\xbf"))
        rows = list(csv.DictReader(StringIO(content.decode("utf-8-sig"))))
        self.assertEqual(tuple(rows[0]), MONITORING_EXPORT_COLUMNS)
        self.assertEqual(rows[0]["plant_key"], "PL01")
        self.assertEqual(rows[0]["actual_emergency"], "false")

    def test_spreadsheet_formula_prefixes_are_neutralized(self):
        content = monitoring_records_to_csv_bytes(
            [{"record_id": "record-1", "buyer_name": "=DANGEROUS()"}]
        ).decode("utf-8-sig")
        row = next(csv.DictReader(StringIO(content)))
        self.assertEqual(row["buyer_name"], "'=DANGEROUS()")


if __name__ == "__main__":
    unittest.main()
