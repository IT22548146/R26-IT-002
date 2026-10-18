"""Run Component 3 recovery validation against a historical workbook."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from components.component3_historical_validation import run_historical_validation


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Replay the Component 3 recovery engine on historical rows."
    )
    parser.add_argument("--data", type=Path, required=True, help="Historical .xlsx workbook")
    parser.add_argument("--json-output", type=Path, help="Write the summary report")
    parser.add_argument("--csv-output", type=Path, help="Write row-level replay cases")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    report, cases = run_historical_validation(args.data)
    rendered = json.dumps(report, indent=2, ensure_ascii=False)
    print(rendered)

    if args.json_output:
        args.json_output.parent.mkdir(parents=True, exist_ok=True)
        args.json_output.write_text(rendered + "\n", encoding="utf-8")
    if args.csv_output:
        args.csv_output.parent.mkdir(parents=True, exist_ok=True)
        cases.to_csv(args.csv_output, index=False)


if __name__ == "__main__":
    main()
