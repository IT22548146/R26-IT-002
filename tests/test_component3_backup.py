import sqlite3
import tempfile
import unittest
from pathlib import Path

from components.component3_backup import (
    Component3BackupError,
    backup_component3_database,
)


class Component3BackupTests(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.directory = Path(self.temporary_directory.name)
        self.source = self.directory / "component3_tracking.db"
        with sqlite3.connect(self.source) as connection:
            connection.execute(
                "CREATE TABLE daily_records (record_id TEXT PRIMARY KEY, output INTEGER)"
            )
            connection.execute("INSERT INTO daily_records VALUES ('record-1', 125)")

    def tearDown(self):
        self.temporary_directory.cleanup()

    def test_online_backup_is_complete_and_verified(self):
        destination = self.directory / "backups" / "component3.db"

        report = backup_component3_database(self.source, destination)

        self.assertEqual(report["status"], "verified")
        self.assertEqual(report["integrity_check"], "ok")
        self.assertEqual(len(report["sha256"]), 64)
        self.assertGreater(report["size_bytes"], 0)
        with sqlite3.connect(destination) as connection:
            row = connection.execute(
                "SELECT record_id, output FROM daily_records"
            ).fetchone()
        self.assertEqual(row, ("record-1", 125))

    def test_existing_destination_is_never_overwritten(self):
        destination = self.directory / "existing.db"
        destination.write_bytes(b"keep this backup")

        with self.assertRaisesRegex(Component3BackupError, "already exists"):
            backup_component3_database(self.source, destination)

        self.assertEqual(destination.read_bytes(), b"keep this backup")

    def test_source_and_destination_must_differ(self):
        with self.assertRaisesRegex(Component3BackupError, "must differ"):
            backup_component3_database(self.source, self.source)


if __name__ == "__main__":
    unittest.main()
