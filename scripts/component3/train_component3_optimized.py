"""Run the Component 3 group-safe tuning and soft-voting experiment."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from components.component3_early_warning_data import run_step5a_audit
from components.component3_model_optimization import run_optimization_experiment

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_REPORT_DIR = PROJECT_ROOT / "reports" / "component3_model_optimization"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run nested Bulk-Order-grouped hyperparameter optimization and "
            "an explicit Logistic Regression + Random Forest soft-voting "
            "comparison for Component 3 early-warning targets."
        )
    )
    parser.add_argument(
        "--data",
        type=Path,
        default=PROJECT_ROOT / "data" / "component3_final_preprocessed_dataset.xlsx",
        help="Original Component 3 historical workbook",
    )
    parser.add_argument(
        "--report-dir",
        type=Path,
        default=DEFAULT_REPORT_DIR,
        help="Directory for JSON, CSV, and Markdown research evidence",
    )
    parser.add_argument(
        "--target",
        action="append",
        dest="targets",
        help="Optional target name; repeat to run more than one target",
    )
    return parser.parse_args()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _pct(value: float) -> str:
    return f"{value * 100:.2f}%"


def render_markdown(report: dict) -> str:
    lines = [
        "# Component 3 — Hyperparameter Optimization and Ensemble Evidence",
        "",
        f"**Report version:** `{report['report_version']}`  ",
        f"**Generated:** `{report['generated_at_utc']}`  ",
        "**Research status:** Evidence only; active artifacts are not replaced automatically.",
        "",
        "## Methodology",
        "",
        "- Outer validation: Leave-One-Group-Out using `Bulk_Order_ID`.",
        "- Inner optimization: GroupKFold with GridSearchCV.",
        "- Primary selection metric: Macro-F1.",
        "- Ensemble: probability-based soft voting between tuned Logistic Regression and tuned Random Forest.",
        "- Leakage control: an outer test order is absent from parameter and ensemble-weight selection.",
        "",
        "## Nested unseen-order results",
        "",
        "| Target | Candidate | Accuracy | Macro-F1 | Positive F1 | Selected |",
        "|---|---|---:|---:|---:|:---:|",
    ]
    for target in report["targets"].values():
        for name, candidate in target["candidates"].items():
            lines.append(
                "| "
                + " | ".join(
                    [
                        target["display_name"],
                        name.replace("_", " ").title(),
                        _pct(candidate["accuracy"]),
                        _pct(candidate["macro_f1"]),
                        _pct(candidate["f1"]),
                        "Yes" if candidate["selected"] else "No",
                    ]
                )
                + " |"
            )

    lines.extend(
        [
            "",
            "## Selected parameters after full-data grouped search",
            "",
        ]
    )
    for target in report["targets"].values():
        lines.extend(
            [
                f"### {target['display_name']}",
                "",
                f"Nested-evidence winner: **{target['selected_model'].replace('_', ' ').title()}**",
                "",
            ]
        )
        for name, candidate in target["candidates"].items():
            parameters = json.dumps(
                candidate["final_full_data_best_parameters"],
                sort_keys=True,
            )
            lines.append(
                f"- `{name}`: `{parameters}` "
                f"(inner Macro-F1 {_pct(candidate['final_full_data_inner_macro_f1'])})"
            )
        lines.append("")

    lines.extend(
        [
            "## Parameter justification",
            "",
        ]
    )
    for parameter, rationale in report["parameter_rationale"].items():
        lines.append(f"- **{parameter.replace('_', ' ').title()}:** {rationale}")

    lines.extend(
        [
            "",
            "## Interpretation and promotion rule",
            "",
            report["promotion_policy"],
            "",
            "An ensemble is not selected merely because it is more complex. It must improve nested unseen-order Macro-F1. A simpler tuned model is preferred when the evidence ties.",
            "",
            "## Limitations",
            "",
        ]
    )
    lines.extend(f"- {limitation}" for limitation in report["research_limitations"])
    lines.append("")
    return "\n".join(lines)


def main() -> None:
    args = parse_args()
    source_report, labelled = run_step5a_audit(args.data)
    report, comparison = run_optimization_experiment(
        labelled,
        target_names=args.targets,
    )
    report["source_dataset"] = {
        "path": str(args.data),
        "sha256": _sha256(args.data),
        "eligible_rows": int(len(labelled)),
        "eligible_orders": int(labelled["Bulk_Order_ID"].nunique()),
        "step5a_report_version": source_report.get("report_version"),
    }

    args.report_dir.mkdir(parents=True, exist_ok=True)
    json_path = args.report_dir / "evaluation.json"
    csv_path = args.report_dir / "model_comparison.csv"
    markdown_path = args.report_dir / "README.md"
    json_path.write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    comparison.to_csv(csv_path, index=False)
    markdown_path.write_text(render_markdown(report), encoding="utf-8")

    print(f"Wrote {json_path}")
    print(f"Wrote {csv_path}")
    print(f"Wrote {markdown_path}")
    for target in report["targets"].values():
        winner = target["candidates"][target["selected_model"]]
        print(
            f"{target['display_name']}: {target['selected_model']} "
            f"(Macro-F1={winner['macro_f1']:.4f})"
        )


if __name__ == "__main__":
    main()
