"""Prepare and audit the Component 3 Step 5A early-warning dataset."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from components.component3_early_warning_data import run_step5a_audit


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Audit leakage-safe early-warning labels from historical data."
    )
    parser.add_argument("--data", type=Path, required=True, help="Historical .xlsx workbook")
    parser.add_argument("--json-output", type=Path, help="Write the readiness report")
    parser.add_argument("--csv-output", type=Path, help="Write labelled stable-day rows")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    report, labelled = run_step5a_audit(args.data)
    rendered = json.dumps(report, indent=2, ensure_ascii=False)
    print(rendered)

    if args.json_output:
        args.json_output.parent.mkdir(parents=True, exist_ok=True)
        args.json_output.write_text(rendered + "\n", encoding="utf-8")
    if args.csv_output:
        args.csv_output.parent.mkdir(parents=True, exist_ok=True)
        labelled.to_csv(args.csv_output, index=False)


if __name__ == "__main__":
    main()
