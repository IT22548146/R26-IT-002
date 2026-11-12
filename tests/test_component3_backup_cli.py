import json
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from datetime import UTC, datetime
from pathlib import Path

from scripts.component3.backup_component3_database import default_backup_path

PROJECT_ROOT = Path(__file__).resolve().parents[1]


class Component3BackupCliTests(unittest.TestCase):
    def test_default_name_contains_a_utc_timestamp(self):
        path = default_backup_path(datetime(2026, 11, 12, 9, 30, tzinfo=UTC))
        self.assertEqual(path.name, "component3_tracking_20261112T093000Z.db")

    def test_cli_creates_a_verified_backup_report(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "source.db"
            destination = Path(directory) / "backup.db"
            with sqlite3.connect(source) as connection:
                connection.execute("CREATE TABLE records (id INTEGER PRIMARY KEY)")
                connection.execute("INSERT INTO records VALUES (1)")

            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "scripts.component3.backup_component3_database",
                    "--database",
                    str(source),
                    "--output",
                    str(destination),
                ],
                cwd=PROJECT_ROOT,
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            report = json.loads(result.stdout)
            self.assertEqual(report["status"], "verified")
            self.assertEqual(report["destination"], str(destination.resolve()))
            self.assertTrue(destination.is_file())


if __name__ == "__main__":
    unittest.main()
