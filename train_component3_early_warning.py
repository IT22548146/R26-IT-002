"""Train and compare Component 3 Step 5B early-warning subtype models."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import joblib

from components.component3_early_warning_training import (
    build_candidate_models,
    run_step5b_experiment,
)


BASE_DIR = Path(__file__).resolve().parent
DEFAULT_REPORT_DIR = BASE_DIR / "reports" / "component3_early_warning_step5b"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run leakage-safe, order-grouped model comparison for the supported "
            "Component 3 three-day early-warning targets."
        )
    )
    parser.add_argument(
        "--data",
        type=Path,
        default=BASE_DIR / "component3_final_preprossed dataset.xlsx",
        help="Original Component 3 historical workbook",
    )
    parser.add_argument(
        "--report",
        type=Path,
        default=DEFAULT_REPORT_DIR / "evaluation.json",
        help="Write the JSON experiment report",
    )
    parser.add_argument(
        "--comparison",
        type=Path,
        default=DEFAULT_REPORT_DIR / "model_comparison.csv",
        help="Write the flat Accuracy/Macro-F1/F1 comparison",
    )
    parser.add_argument(
        "--models-dir",
        type=Path,
        default=BASE_DIR / "models",
        help="Directory for selected research model artifacts",
    )
    parser.add_argument(
        "--candidates",
        nargs="+",
        choices=sorted(build_candidate_models()),
        help="Optional subset of candidates; include at least one non-dummy model",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    report, comparison, artifacts = run_step5b_experiment(
        args.data,
        candidate_names=args.candidates,
    )

    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.comparison.parent.mkdir(parents=True, exist_ok=True)
    args.models_dir.mkdir(parents=True, exist_ok=True)
    args.report.write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    comparison.to_csv(args.comparison, index=False)
    for target, artifact in artifacts.items():
        artifact_name = Path(report["targets"][target]["artifact_path"]).name
        joblib.dump(artifact, args.models_dir / artifact_name)

    print(json.dumps(report, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
