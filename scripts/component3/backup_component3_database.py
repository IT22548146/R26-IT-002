"""Create a verified, non-overwriting backup of Component 3 tracking data."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path

from components.component3_backup import (
    Component3BackupError,
    backup_component3_database,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def default_backup_path(now: datetime | None = None) -> Path:
    timestamp = (now or datetime.now(UTC)).strftime("%Y%m%dT%H%M%SZ")
    return PROJECT_ROOT / "backups" / "component3" / f"component3_tracking_{timestamp}.db"


def parse_args(arguments: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Create and verify an online backup of Component 3 SQLite data."
    )
    parser.add_argument(
        "--database",
        type=Path,
        default=PROJECT_ROOT / "instance" / "component3_tracking.db",
        help="Source Component 3 tracking database",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="New backup file; existing files are never overwritten",
    )
    return parser.parse_args(arguments)


def main(arguments: Sequence[str] | None = None) -> int:
    args = parse_args(arguments)
    output = args.output or default_backup_path()
    try:
        report = backup_component3_database(args.database, output)
    except Component3BackupError as error:
        print(json.dumps({"status": "failed", "error": str(error)}), file=sys.stderr)
        return 1
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
