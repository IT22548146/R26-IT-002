"""Audit integrated C3 tracking rows against the operational database."""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections.abc import Sequence
from pathlib import Path

from components.component3_reconciliation import (
    Component3ReconciliationError,
    audit_component3_persistence,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def parse_args(arguments: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Read-only reconciliation of integrated Component 3 monitoring "
            "records and operational daily_logs."
        )
    )
    parser.add_argument(
        "--tracking-database",
        type=Path,
        default=PROJECT_ROOT / "instance" / "component3_tracking.db",
    )
    parser.add_argument(
        "--operational-database",
        type=Path,
        default=Path(os.environ.get("DATABASE_PATH", PROJECT_ROOT / "garment.db")),
    )
    parser.add_argument("--output", type=Path, help="Optional JSON report path")
    return parser.parse_args(arguments)


def main(arguments: Sequence[str] | None = None) -> int:
    args = parse_args(arguments)
    try:
        report = audit_component3_persistence(
            args.tracking_database,
            args.operational_database,
        )
    except Component3ReconciliationError as error:
        print(json.dumps({"status": "failed", "error": str(error)}), file=sys.stderr)
        return 1

    rendered = json.dumps(report, indent=2, sort_keys=True) + "\n"
    print(rendered, end="")
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    return 0 if report["status"] == "consistent" else 2


if __name__ == "__main__":
    raise SystemExit(main())
