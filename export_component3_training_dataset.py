"""Export verified Component 3 monitoring rows for Step 5B training."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from components.component3_monitoring import Component3MonitoringStore
from components.component3_training_export import (
    build_verified_training_dataset,
    dataframe_to_csv_bytes,
    dataframe_to_xlsx_bytes,
)


BASE_DIR = Path(__file__).resolve().parent


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Export leakage-safe training rows from verified Component 3 "
            "daily monitoring records."
        )
    )
    parser.add_argument(
        "--database",
        type=Path,
        default=BASE_DIR / "instance" / "component3_tracking.db",
        help="Component 3 SQLite database path",
    )
    parser.add_argument("--csv", type=Path, help="Write the training CSV")
    parser.add_argument("--xlsx", type=Path, help="Write the Excel workbook")
    parser.add_argument("--audit", type=Path, help="Write the JSON audit report")
    return parser.parse_args()


def _write(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)


def main() -> None:
    args = parse_args()
    store = Component3MonitoringStore(str(args.database))
    dataset, audit = build_verified_training_dataset(
        store.training_export_snapshot()
    )
    rendered_audit = json.dumps(audit, indent=2, ensure_ascii=False) + "\n"
    print(rendered_audit, end="")

    if args.audit:
        _write(args.audit, rendered_audit.encode("utf-8"))
    if dataset.empty and (args.csv or args.xlsx):
        raise SystemExit(
            "No verified Ready rows are available for dataset export."
        )
    if args.csv:
        _write(args.csv, dataframe_to_csv_bytes(dataset))
    if args.xlsx:
        _write(args.xlsx, dataframe_to_xlsx_bytes(dataset, audit))


if __name__ == "__main__":
    main()
