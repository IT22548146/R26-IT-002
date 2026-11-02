#!/usr/bin/env python3
"""Generate an evidence-backed Component 3 dataset and model-results PDF."""

from __future__ import annotations

import json
import textwrap
from datetime import date
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.backends.backend_pdf import PdfPages
from matplotlib.patches import FancyBboxPatch

ROOT = Path(__file__).resolve().parents[2]
OUTPUT = ROOT / "reports" / "Component3_Dataset_and_ML_Results_Report.pdf"

NAVY = "#12213f"
INDIGO = "#5b5cf6"
TEAL = "#087f75"
GREEN = "#16a66a"
ORANGE = "#e77910"
RED = "#dc3b45"
INK = "#172033"
MUTED = "#5e6b82"
PALE = "#f2f6fb"
LINE = "#dce4ef"
WHITE = "#ffffff"


def load_json(relative_path: str) -> dict:
    return json.loads((ROOT / relative_path).read_text(encoding="utf-8"))


def pct(value: float) -> str:
    return f"{100 * value:.2f}%"


def clean_model_name(name: str) -> str:
    return {
        "dummy_most_frequent": "Dummy baseline",
        "logistic_regression": "Logistic Regression",
        "random_forest": "Random Forest",
        "extra_trees": "Extra Trees",
        "gradient_boosting": "Gradient Boosting",
        "xgboost": "XGBoost",
    }.get(name, name.replace("_", " ").title())


def add_footer(fig: plt.Figure, page_number: int, source: str = "") -> None:
    fig.text(0.04, 0.025, "FabricFlow | Component 3 research evidence", fontsize=7.5, color=MUTED)
    if source:
        fig.text(0.5, 0.025, source, ha="center", fontsize=6.5, color=MUTED)
    fig.text(0.96, 0.025, str(page_number), ha="right", fontsize=7.5, color=MUTED)


def base_page(
    title: str, subtitle: str, page_number: int, source: str = ""
) -> tuple[plt.Figure, plt.Axes]:
    fig = plt.figure(figsize=(11.69, 8.27), facecolor=WHITE)
    ax = fig.add_axes([0, 0, 1, 1])
    ax.set_axis_off()
    ax.add_patch(
        FancyBboxPatch(
            (0.025, 0.89),
            0.95,
            0.085,
            boxstyle="round,pad=0.008,rounding_size=0.012",
            facecolor=NAVY,
            edgecolor=NAVY,
        )
    )
    ax.text(0.05, 0.94, title, fontsize=21, weight="bold", color=WHITE, va="center")
    ax.text(0.05, 0.902, subtitle, fontsize=9.5, color="#cbd7ef", va="center")
    add_footer(fig, page_number, source)
    return fig, ax


def text_block(
    ax: plt.Axes,
    x: float,
    y: float,
    text: str,
    *,
    width: int = 90,
    size: float = 10,
    color: str = INK,
    weight: str = "normal",
    line_height: float = 0.026,
    bullet: bool = False,
) -> float:
    prefix = "• " if bullet else ""
    lines = textwrap.wrap(text, width=width, break_long_words=False, break_on_hyphens=False) or [""]
    for index, line in enumerate(lines):
        ax.text(
            x,
            y,
            (prefix if index == 0 else "  ") + line,
            fontsize=size,
            color=color,
            weight=weight,
            va="top",
        )
        y -= line_height
    return y


def card(
    ax: plt.Axes,
    x: float,
    y: float,
    w: float,
    h: float,
    title: str,
    value: str,
    note: str = "",
    accent: str = INDIGO,
) -> None:
    ax.add_patch(
        FancyBboxPatch(
            (x, y),
            w,
            h,
            boxstyle="round,pad=0.009,rounding_size=0.012",
            facecolor=PALE,
            edgecolor=LINE,
            linewidth=1,
            zorder=2,
        )
    )
    ax.add_patch(
        FancyBboxPatch(
            (x, y),
            0.008,
            h,
            boxstyle="round,pad=0,rounding_size=0.006",
            facecolor=accent,
            edgecolor=accent,
            zorder=3,
        )
    )
    ax.text(
        x + 0.025,
        y + h - 0.028,
        title.upper(),
        fontsize=7.2,
        weight="bold",
        color=MUTED,
        va="top",
        zorder=4,
    )
    value_size = 13.5 if len(value) > 12 else 17
    ax.text(
        x + 0.025,
        y + h - 0.061,
        value,
        fontsize=value_size,
        weight="bold",
        color=INK,
        va="top",
        zorder=4,
    )
    if note:
        ax.text(
            x + 0.025,
            y + 0.014,
            textwrap.fill(note, 34),
            fontsize=6.5,
            color=MUTED,
            va="bottom",
            linespacing=1.15,
            zorder=4,
        )


def info_box(
    ax: plt.Axes,
    x: float,
    y: float,
    w: float,
    h: float,
    title: str,
    body: str,
    accent: str = TEAL,
    face: str = "#f4fbfa",
    *,
    body_size: float = 8.0,
    line_spacing: float = 1.25,
) -> None:
    ax.add_patch(
        FancyBboxPatch(
            (x, y),
            w,
            h,
            boxstyle="round,pad=0.012,rounding_size=0.012",
            facecolor=face,
            edgecolor=accent,
            linewidth=1.1,
        )
    )
    ax.text(x + 0.02, y + h - 0.03, title, fontsize=10, weight="bold", color=accent, va="top")
    wrapped = textwrap.fill(body, max(25, int(w * 100)), break_long_words=False)
    ax.text(
        x + 0.02,
        y + h - 0.068,
        wrapped,
        fontsize=body_size,
        color=INK,
        va="top",
        linespacing=line_spacing,
    )


def styled_table(
    ax: plt.Axes,
    rows: list[list[str]],
    columns: list[str],
    bbox: list[float],
    col_widths: list[float] | None = None,
    font_size: float = 8.5,
) -> None:
    table = ax.table(
        cellText=rows,
        colLabels=columns,
        cellLoc="left",
        colLoc="left",
        colWidths=col_widths,
        bbox=bbox,
    )
    table.auto_set_font_size(False)
    table.set_fontsize(font_size)
    for (row, _col), cell in table.get_celld().items():
        cell.set_edgecolor(LINE)
        cell.set_linewidth(0.8)
        if row == 0:
            cell.set_facecolor(NAVY)
            cell.get_text().set_color(WHITE)
            cell.get_text().set_weight("bold")
        else:
            cell.set_facecolor(WHITE if row % 2 else PALE)
            cell.get_text().set_color(INK)
    return None


def add_bar_chart(
    fig: plt.Figure,
    rect: list[float],
    labels: list[str],
    values: list[float],
    title: str,
    highlight: int | None = None,
    x_max: float = 1.0,
) -> None:
    ax = fig.add_axes(rect)
    colors = ["#aab8ca"] * len(values)
    if highlight is not None:
        colors[highlight] = INDIGO
    positions = np.arange(len(labels))
    ax.barh(positions, values, color=colors, height=0.55)
    ax.set_yticks(positions, labels, fontsize=8)
    ax.invert_yaxis()
    ax.set_xlim(0, x_max)
    ax.set_title(title, loc="left", fontsize=10, weight="bold", color=INK, pad=8)
    ax.grid(axis="x", color=LINE, linewidth=0.7)
    ax.set_axisbelow(True)
    ax.tick_params(axis="x", labelsize=7, colors=MUTED)
    for spine in ax.spines.values():
        spine.set_visible(False)
    for i, value in enumerate(values):
        ax.text(
            min(value + 0.015, x_max - 0.08), i, pct(value), va="center", fontsize=7.5, color=INK
        )


def generate() -> None:
    c3_v2 = load_json("reports/component3_v2/evaluation.json")
    model2_v3 = load_json("reports/component3_model2_v3/evaluation.json")
    readiness = load_json("reports/component3_early_warning_step5a/readiness.json")
    early = load_json("reports/component3_early_warning_step5b_calibrated/evaluation.json")
    recovery = load_json("reports/component3_recovery_validation/evaluation.json")

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    with PdfPages(OUTPUT) as pdf:
        # Page 1: cover and executive summary
        fig = plt.figure(figsize=(11.69, 8.27), facecolor=WHITE)
        ax = fig.add_axes([0, 0, 1, 1])
        ax.set_axis_off()
        ax.add_patch(
            FancyBboxPatch(
                (0, 0.58), 1, 0.42, boxstyle="square,pad=0", facecolor=NAVY, edgecolor=NAVY
            )
        )
        ax.add_patch(
            FancyBboxPatch(
                (0.68, 0.61),
                0.36,
                0.32,
                boxstyle="round,pad=0.02,rounding_size=0.05",
                facecolor="#243c78",
                edgecolor="#243c78",
                alpha=0.9,
            )
        )
        ax.text(
            0.065, 0.91, "FABRICFLOW RESEARCH REPORT", fontsize=10, color="#78e3d4", weight="bold"
        )
        ax.text(0.065, 0.80, "Component 3", fontsize=34, color=WHITE, weight="bold")
        ax.text(0.065, 0.72, "Dataset & ML Model Results", fontsize=28, color=WHITE, weight="bold")
        ax.text(
            0.065,
            0.64,
            "Emergency Situation Detection and Management",
            fontsize=13,
            color="#cbd7ef",
        )
        ax.text(0.065, 0.51, "Student", fontsize=8, color=MUTED, weight="bold")
        ax.text(0.065, 0.475, "Alagiyawanna S.A.M.A.V.P", fontsize=13, color=INK, weight="bold")
        ax.text(0.35, 0.51, "Student ID", fontsize=8, color=MUTED, weight="bold")
        ax.text(0.35, 0.475, "IT22904614", fontsize=13, color=INK, weight="bold")
        ax.text(0.59, 0.51, "Generated", fontsize=8, color=MUTED, weight="bold")
        ax.text(0.59, 0.475, date.today().isoformat(), fontsize=13, color=INK, weight="bold")
        ax.text(0.065, 0.395, "EXECUTIVE SUMMARY", fontsize=10, color=INDIGO, weight="bold")
        y = 0.355
        for item in [
            "598 real historical daily records across 11 independent bulk orders form the evidence base.",
            "Random Forest was selected for current risk type and overall order-risk classification.",
            "Three calibrated next-3-production-day subtype warnings are supported: machine breakdown, quality limit, and output/schedule risk.",
            "Evaluation uses Leave-One-Group-Out validation by Bulk Order ID; augmented rows are used only inside training folds.",
            "Artifacts remain research-only because real-order coverage and minority-class evidence are limited.",
        ]:
            y = text_block(ax, 0.075, y, item, width=100, size=9.7, line_height=0.031, bullet=True)
            y -= 0.006
        ax.text(
            0.065,
            0.075,
            "Evidence source: current repository reports and metadata. No metrics are estimated or invented.",
            fontsize=8.5,
            color=MUTED,
        )
        add_footer(fig, 1)
        pdf.savefig(fig, bbox_inches="tight")
        plt.close(fig)

        # Page 2: dataset inventory
        fig, ax = base_page(
            "Dataset inventory and provenance",
            "What data exists, what was used, and how synthetic rows were controlled",
            2,
            "Sources: data/*.xlsx; reports/component3_v2; reports/component3_model2_v3",
        )
        card(
            ax,
            0.045,
            0.73,
            0.205,
            0.12,
            "Historical rows",
            "598",
            "Real daily records retained for validation",
            TEAL,
        )
        card(
            ax,
            0.275,
            0.73,
            0.205,
            0.12,
            "Independent orders",
            "11",
            "Bulk Order ID is the validation group",
            INDIGO,
        )
        card(ax, 0.505, 0.73, 0.205, 0.12, "Styles", "11", "One style per historical order", GREEN)
        card(
            ax,
            0.735,
            0.73,
            0.22,
            0.12,
            "Eligible warning rows",
            "174",
            "Stable days with a full 3-day horizon",
            ORANGE,
        )

        dataset_rows = [
            [
                "component3_final_preprocessed_dataset.xlsx",
                "598 real rows",
                "11 sheets / orders",
                "Primary historical evidence",
            ],
            [
                "component3_training_augmented.xlsx",
                "1,962 physical rows",
                "479 new augmented rows",
                "Risk-type training; real-only validation",
            ],
            [
                "component3_training_balanced_research_v2.xlsx",
                "2,208 physical rows",
                "725 augmented training rows",
                "Overall-risk training; real-only validation",
            ],
        ]
        styled_table(
            ax,
            dataset_rows,
            ["Dataset", "Size", "Training additions", "Role"],
            [0.045, 0.49, 0.91, 0.18],
            [0.34, 0.16, 0.20, 0.30],
            8.2,
        )

        ax.text(
            0.045, 0.445, "Real risk-type class coverage", fontsize=11, weight="bold", color=INK
        )
        classes = c3_v2["metadata"]["dataset"]["risk_type_real_rows"]
        order_counts = c3_v2["metadata"]["dataset"]["risk_type_real_orders"]
        rows = [[name, str(count), str(order_counts[name])] for name, count in classes.items()]
        styled_table(
            ax,
            rows,
            ["Risk class", "Real rows", "Orders containing class"],
            [0.045, 0.09, 0.48, 0.325],
            [0.54, 0.22, 0.24],
            8.0,
        )
        info_box(
            ax,
            0.56,
            0.25,
            0.395,
            0.16,
            "Data-quality controls",
            "No duplicate order-date rows, no cumulative-output mismatch rows, and no cumulative totals above full-order quantity were reported. Generated rows are identified and excluded from validation.",
            TEAL,
        )
        info_box(
            ax,
            0.56,
            0.09,
            0.395,
            0.12,
            "Important limitation",
            "Minor Delay and Quality Issue have only four real rows each. Model scores for these rare classes must not be interpreted as strong production evidence.",
            ORANGE,
            "#fff8ee",
        )
        pdf.savefig(fig, bbox_inches="tight")
        plt.close(fig)

        # Page 3: preparation and split
        fig, ax = base_page(
            "Data preparation and validation design",
            "Order-level isolation prevents records from the same order leaking across train and test",
            3,
            "Protocol: Leave-One-Group-Out by Bulk_Order_ID",
        )
        ax.text(0.045, 0.835, "VALIDATION PIPELINE", fontsize=10, color=INDIGO, weight="bold")
        pipeline = [
            ("1", "Group by order", "Bulk_Order_ID defines independent groups"),
            ("2", "Hold out one order", "One unseen order becomes the test fold"),
            ("3", "Fit preprocessing", "Transforms are fitted on training folds only"),
            ("4", "Add augmentation", "Synthetic rows enter training folds only"),
            ("5", "Predict held-out order", "Repeat for all 11 orders and combine scores"),
        ]
        x_positions = [0.045, 0.235, 0.425, 0.615, 0.805]
        for idx, ((number, title, body), x) in enumerate(zip(pipeline, x_positions, strict=False)):
            ax.add_patch(
                FancyBboxPatch(
                    (x, 0.62),
                    0.155,
                    0.16,
                    boxstyle="round,pad=0.012,rounding_size=0.012",
                    facecolor=PALE,
                    edgecolor=INDIGO if idx == 4 else LINE,
                    linewidth=1.1,
                )
            )
            ax.text(x + 0.015, 0.75, number, fontsize=17, color=INDIGO, weight="bold", va="top")
            ax.text(x + 0.015, 0.705, title, fontsize=9, color=INK, weight="bold", va="top")
            ax.text(
                x + 0.015,
                0.67,
                textwrap.fill(body, 23),
                fontsize=7.5,
                color=MUTED,
                va="top",
                linespacing=1.3,
            )
            if idx < 4:
                ax.annotate(
                    "",
                    xy=(x + 0.185, 0.70),
                    xytext=(x + 0.158, 0.70),
                    arrowprops=dict(arrowstyle="->", color=INDIGO, lw=1.5),
                )

        info_box(
            ax,
            0.045,
            0.42,
            0.44,
            0.135,
            "Why this is stronger than a random row split",
            "Daily rows from the same bulk order are correlated. A random 80/20 split could expose the test set to the same order seen in training. LOGO instead measures transfer to an unseen order.",
            TEAL,
        )
        info_box(
            ax,
            0.515,
            0.42,
            0.44,
            0.135,
            "Early-warning calibration",
            "Calibrated warning artifacts use nested grouped validation. A sigmoid calibrator and each target-specific decision threshold are learned without using the held-out order.",
            INDIGO,
            "#f5f5ff",
        )

        ax.text(0.045, 0.36, "Feature groups", fontsize=11, weight="bold", color=INK)
        feature_rows = [
            ["Production", "Daily commitment, actual output, output gap, cumulative completed"],
            ["Disruption", "Machine breakdowns, worker shortages, damage quantity and ratio"],
            ["Schedule", "Working day, days remaining, progress %, required daily rate"],
            ["Process", "Cutting/sewing phase indicators and order quantities"],
            [
                "Early-warning history",
                "Previous output, trailing 3-day averages/variation, recent emergency counts",
            ],
        ]
        styled_table(
            ax, feature_rows, ["Group", "Examples"], [0.045, 0.12, 0.91, 0.215], [0.22, 0.78], 8.4
        )
        ax.text(
            0.045,
            0.075,
            "Leakage exclusions include IDs, dates, final outcomes, risk labels, recommendations, completion date, and future warning labels.",
            fontsize=8.5,
            color=MUTED,
        )
        pdf.savefig(fig, bbox_inches="tight")
        plt.close(fig)

        # Page 4: Model 1
        fig, ax = base_page(
            "Model 1 — current risk type",
            "Seven-class classification using real-order LOGO validation",
            4,
            "Source: reports/component3_v2/evaluation.json",
        )
        candidates = c3_v2["all_candidates"]["risk_type"]
        names = list(candidates)
        table_rows = []
        for name in names:
            m = candidates[name]
            selected = "Selected" if name == "random_forest" else ""
            table_rows.append(
                [
                    clean_model_name(name),
                    pct(m["accuracy"]),
                    pct(m["macro_f1"]),
                    pct(m["weighted_f1"]),
                    selected,
                ]
            )
        styled_table(
            ax,
            table_rows,
            ["Candidate", "Accuracy", "Macro-F1", "Weighted-F1", "Decision"],
            [0.045, 0.55, 0.49, 0.27],
            [0.31, 0.16, 0.16, 0.19, 0.18],
            8.5,
        )
        add_bar_chart(
            fig,
            [0.57, 0.55, 0.385, 0.27],
            [clean_model_name(n) for n in names],
            [candidates[n]["macro_f1"] for n in names],
            "Macro-F1 comparison",
            names.index("random_forest"),
        )
        selected = candidates["random_forest"]
        card(
            ax,
            0.045,
            0.35,
            0.205,
            0.13,
            "Selected model",
            "Random Forest",
            "Best unseen-order Macro-F1",
            INDIGO,
        )
        card(
            ax,
            0.275,
            0.35,
            0.205,
            0.13,
            "Accuracy",
            pct(selected["accuracy"]),
            "598 real validation rows",
            TEAL,
        )
        card(
            ax,
            0.505,
            0.35,
            0.205,
            0.13,
            "Macro-F1",
            pct(selected["macro_f1"]),
            "Equal weight across seven classes",
            GREEN,
        )
        card(
            ax,
            0.735,
            0.35,
            0.22,
            0.13,
            "Weighted-F1",
            pct(selected["weighted_f1"]),
            "Weighted by class support",
            ORANGE,
        )
        info_box(
            ax,
            0.045,
            0.14,
            0.44,
            0.14,
            "What the model predicts",
            "The current production-day condition: No Issue, Minor Delay, Working Hours Issue, Worker Issue, Commitment Too Low, Machine Breakdown Issue, or Quality Issue.",
            TEAL,
        )
        info_box(
            ax,
            0.515,
            0.14,
            0.44,
            0.14,
            "Observed error pattern",
            "Most remaining confusion is between Working Hours Issue and Worker Issue. Perfect results for tiny classes are unstable because Minor Delay and Quality Issue each contain only four real rows.",
            ORANGE,
            "#fff8ee",
        )
        pdf.savefig(fig, bbox_inches="tight")
        plt.close(fig)

        # Page 5: Model 2
        fig, ax = base_page(
            "Model 2 — overall order-risk level (v3)",
            "Binary Low Risk / High Risk classification with broader schedule features",
            5,
            "Source: reports/component3_model2_v3/evaluation.json",
        )
        candidates = model2_v3["all_candidates"]
        names = list(candidates)
        rows = []
        for name in names:
            m = candidates[name]
            rows.append(
                [
                    clean_model_name(name),
                    pct(m["accuracy"]),
                    pct(m["macro_f1"]),
                    pct(m["weighted_f1"]),
                    pct(m["roc_auc"]),
                    "Selected" if name == "random_forest" else "",
                ]
            )
        styled_table(
            ax,
            rows,
            ["Candidate", "Accuracy", "Macro-F1", "Weighted-F1", "ROC-AUC", "Decision"],
            [0.045, 0.55, 0.56, 0.27],
            [0.26, 0.14, 0.14, 0.16, 0.14, 0.16],
            8.1,
        )
        add_bar_chart(
            fig,
            [0.64, 0.55, 0.315, 0.27],
            [clean_model_name(n) for n in names],
            [candidates[n]["macro_f1"] for n in names],
            "Macro-F1 comparison",
            names.index("random_forest"),
        )
        selected = candidates["random_forest"]
        card(
            ax,
            0.045,
            0.35,
            0.205,
            0.13,
            "Selected model",
            "Random Forest",
            "Highest Macro-F1; tie broken by ROC-AUC",
            INDIGO,
        )
        card(
            ax,
            0.275,
            0.35,
            0.205,
            0.13,
            "Accuracy",
            pct(selected["accuracy"]),
            "597 of 598 rows classified correctly",
            TEAL,
        )
        card(
            ax,
            0.505,
            0.35,
            0.205,
            0.13,
            "Macro-F1",
            pct(selected["macro_f1"]),
            "Class-balanced summary",
            GREEN,
        )
        card(
            ax,
            0.735,
            0.35,
            0.22,
            0.13,
            "False low-risk rows",
            str(selected["false_low_risk_rows"]),
            "Confusion matrix: [[35, 0], [1, 562]]",
            ORANGE,
        )
        info_box(
            ax,
            0.045,
            0.135,
            0.91,
            0.145,
            "Critical validity limitation",
            "Only one independent real Low Risk order is available, even though it contributes 35 daily rows. Therefore the near-perfect row-level score is research evidence, not proof of generalisation to new low-risk orders. The artifact is explicitly marked production_approved: false.",
            RED,
            "#fff5f6",
        )
        pdf.savefig(fig, bbox_inches="tight")
        plt.close(fig)

        # Page 6: early warning
        fig, ax = base_page(
            "Early warning — next 3 production days",
            "Supported subtype models use calibrated probabilities and target-specific thresholds",
            6,
            "Source: reports/component3_early_warning_step5b_calibrated/evaluation.json",
        )
        target_labels = {
            "Machine_Breakdown_Within_3_Days": "Machine breakdown",
            "Quality_Limit_Within_3_Days": "Quality-limit issue",
            "Output_Schedule_Risk_Within_3_Days": "Output/schedule risk",
        }
        xs = [0.045, 0.355, 0.665]
        accents = [RED, ORANGE, INDIGO]
        for (target, result), x, accent in zip(early["targets"].items(), xs, accents, strict=False):
            cal = result["calibration"]
            metrics = cal["nested_threshold_validation_metrics"]
            ax.add_patch(
                FancyBboxPatch(
                    (x, 0.51),
                    0.29,
                    0.31,
                    boxstyle="round,pad=0.012,rounding_size=0.014",
                    facecolor=PALE,
                    edgecolor=accent,
                    linewidth=1.3,
                )
            )
            ax.text(
                x + 0.02,
                0.785,
                target_labels[target],
                fontsize=12,
                weight="bold",
                color=INK,
                va="top",
            )
            ax.text(
                x + 0.02,
                0.745,
                clean_model_name(result["selected_model"]),
                fontsize=9,
                color=accent,
                weight="bold",
                va="top",
            )
            ax.text(x + 0.02, 0.685, "Accuracy", fontsize=8, color=MUTED)
            ax.text(
                x + 0.17, 0.685, pct(metrics["accuracy"]), fontsize=15, color=INK, weight="bold"
            )
            ax.text(x + 0.02, 0.635, "Macro-F1", fontsize=8, color=MUTED)
            ax.text(
                x + 0.17, 0.635, pct(metrics["macro_f1"]), fontsize=15, color=INK, weight="bold"
            )
            ax.text(x + 0.02, 0.585, "Positive-class F1", fontsize=8, color=MUTED)
            ax.text(x + 0.17, 0.585, pct(metrics["f1"]), fontsize=15, color=INK, weight="bold")
            ax.text(
                x + 0.02,
                0.535,
                f"Decision threshold: {cal['decision_threshold']:.4f}",
                fontsize=8.5,
                color=MUTED,
            )

        coverage = readiness["label_readiness"]
        rows = []
        for target in target_labels:
            item = coverage[target]
            rows.append(
                [
                    target_labels[target],
                    f"{item['positive_rows']} / {item['negative_rows']}",
                    f"{item['positive_orders']} / {item['negative_orders']}",
                    "Ready" if item["ready_for_grouped_modeling"] else "Not ready",
                ]
            )
        ax.text(
            0.045,
            0.455,
            "Target coverage on eligible stable rows",
            fontsize=11,
            weight="bold",
            color=INK,
        )
        styled_table(
            ax,
            rows,
            [
                "Target",
                "Positive / negative rows",
                "Positive / negative orders",
                "Grouped modelling",
            ],
            [0.045, 0.26, 0.91, 0.16],
            [0.29, 0.24, 0.28, 0.19],
            8.4,
        )
        info_box(
            ax,
            0.045,
            0.09,
            0.44,
            0.115,
            "Calibration evidence",
            "Calibration reduced Brier score and expected calibration error for all three targets. Threshold metrics shown above come from nested grouped validation, not the final training fit.",
            TEAL,
        )
        info_box(
            ax,
            0.515,
            0.09,
            0.44,
            0.115,
            "Scope boundary",
            "A general any-emergency warning and a worker-shortage warning are not supported: the eligible stable-day data lacks enough negative rows and independent negative orders.",
            ORANGE,
            "#fff8ee",
        )
        pdf.savefig(fig, bbox_inches="tight")
        plt.close(fig)

        # Page 7: baseline comparison and selection rationale
        fig, ax = base_page(
            "Model selection rationale",
            "Each selected model is compared against a non-predictive baseline and alternative algorithms",
            7,
            "Sources: Component 3 evaluation JSON and model-comparison CSV evidence",
        )
        selection_rows = [
            [
                "Current risk type",
                "Dummy, Logistic Regression, Random Forest, Extra Trees",
                "Random Forest",
                "Macro-F1 90.08%",
            ],
            [
                "Overall order risk v3",
                "Dummy, Logistic Regression, Random Forest, Gradient Boosting",
                "Random Forest",
                "Macro-F1 99.25%*",
            ],
            [
                "Machine warning",
                "Dummy, Logistic Regression, Random Forest, XGBoost",
                "Random Forest",
                "Nested calibrated Macro-F1 84.05%",
            ],
            [
                "Quality warning",
                "Dummy, Logistic Regression, Random Forest, XGBoost",
                "Logistic Regression",
                "Nested calibrated Macro-F1 51.18%",
            ],
            [
                "Output/schedule warning",
                "Dummy, Logistic Regression, Random Forest, XGBoost",
                "Logistic Regression",
                "Nested calibrated Macro-F1 63.75%",
            ],
        ]
        styled_table(
            ax,
            selection_rows,
            ["Prediction task", "Candidates compared", "Selected", "Evidence"],
            [0.045, 0.52, 0.91, 0.30],
            [0.21, 0.40, 0.18, 0.21],
            8.0,
        )
        info_box(
            ax,
            0.045,
            0.33,
            0.44,
            0.135,
            "Why Macro-F1 matters",
            "Accuracy can look high when one class dominates. Macro-F1 gives each class equal weight, so model selection better reflects minority classes such as incidents and low-risk cases.",
            TEAL,
        )
        info_box(
            ax,
            0.515,
            0.33,
            0.44,
            0.135,
            "Why keep the dummy baseline",
            "The dummy classifier shows what can be achieved by always choosing the most frequent class. A useful model should improve materially over this non-predictive reference.",
            INDIGO,
            "#f5f5ff",
        )
        ax.text(0.045, 0.275, "Interpretation notes", fontsize=11, weight="bold", color=INK)
        y = 0.235
        notes = [
            "Model 1: Random Forest improves Macro-F1 from 6.97% (dummy) to 90.08%.",
            "Model 2 v3: the score is high, but only one real Low Risk order exists; the asterisk marks this important limitation.",
            "Early-warning model names come from candidate comparison; displayed warning metrics use calibrated nested thresholds.",
            "Selected .pkl/.joblib artifacts package preprocessing and the fitted estimator for application inference.",
        ]
        for note in notes:
            y = (
                text_block(ax, 0.06, y, note, width=112, size=9.2, line_height=0.028, bullet=True)
                - 0.008
            )
        pdf.savefig(fig, bbox_inches="tight")
        plt.close(fig)

        # Page 8: recovery engine
        fig, ax = base_page(
            "Recovery engine validation",
            "Rule-based recovery planning is evaluated separately from the ML classifiers",
            8,
            "Source: reports/component3_recovery_validation/evaluation.json",
        )
        val = recovery["validation"]
        baseline = val["current_output_as_next_workday_baseline"]
        recommended = val["recommended_capacity_observational_comparison"]
        completion = val["completion_date_forecast"]
        deadline = val["deadline_feasibility"]
        card(
            ax,
            0.045,
            0.67,
            0.205,
            0.15,
            "Current-output WAPE",
            f"{baseline['wape_pct']:.2f}%",
            f"{baseline['case_count']} next-day cases",
            TEAL,
        )
        card(
            ax,
            0.275,
            0.67,
            0.205,
            0.15,
            "Recommended-capacity WAPE",
            f"{recommended['wape_pct']:.2f}%",
            f"{recommended['case_count']} observational cases",
            INDIGO,
        )
        card(
            ax,
            0.505,
            0.67,
            0.205,
            0.15,
            "Completion-date MAE",
            f"{completion['mae_calendar_days']:.3f} d",
            f"{pct(completion['within_3_calendar_days'])} within 3 days",
            GREEN,
        )
        card(
            ax,
            0.735,
            0.67,
            0.22,
            0.15,
            "Deadline accuracy",
            pct(deadline["accuracy"]),
            "Single observed outcome class",
            ORANGE,
        )

        rows = [
            [
                "Current output → next-day baseline",
                str(baseline["case_count"]),
                f"MAE {baseline['mae']:.3f}",
                f"RMSE {baseline['rmse']:.3f}",
                f"Within 10% {pct(baseline['within_10_pct'])}",
            ],
            [
                "Recommended capacity comparison",
                str(recommended["case_count"]),
                f"MAE {recommended['mae']:.3f}",
                f"RMSE {recommended['rmse']:.3f}",
                f"Within 10% {pct(recommended['within_10_pct'])}",
            ],
            [
                "Completion-date forecast",
                str(completion["case_count"]),
                f"MAE {completion['mae_calendar_days']:.3f} days",
                "—",
                f"Within 3 days {pct(completion['within_3_calendar_days'])}",
            ],
        ]
        styled_table(
            ax,
            rows,
            ["Evaluation", "Cases", "Absolute error", "Squared error", "Tolerance result"],
            [0.045, 0.43, 0.91, 0.17],
            [0.30, 0.11, 0.20, 0.18, 0.21],
            8.2,
        )
        info_box(
            ax,
            0.045,
            0.22,
            0.44,
            0.14,
            "Correct interpretation",
            "The engine calculates feasible recovery options from current output, remaining quantity, days available, and optional workforce/machine limits. It is deterministic business logic, not a trained ML model.",
            TEAL,
        )
        info_box(
            ax,
            0.515,
            0.22,
            0.44,
            0.14,
            "Evidence limitation",
            "Historical data records recommendations and outcomes, but not which action was actually applied. Capacity comparisons are observational and must not be described as causal improvements.",
            ORANGE,
            "#fff8ee",
        )
        ax.text(
            0.045,
            0.145,
            "All 405 observed deadline cases met the deadline, so missed-deadline discrimination cannot be measured.",
            fontsize=9.5,
            color=RED,
            weight="bold",
        )
        ax.text(
            0.045,
            0.105,
            "Calendar assumptions: Monday–Friday production; factory/public holidays are not represented.",
            fontsize=8.5,
            color=MUTED,
        )
        pdf.savefig(fig, bbox_inches="tight")
        plt.close(fig)

        # Page 9: research implementation details
        fig, ax = base_page(
            "Research implementation details",
            "How Component 3 is trained, served, integrated, secured, and persisted",
            9,
            "Verified against the current Component 3 source code",
        )
        ax.text(
            0.045, 0.835, "IMPLEMENTATION ARCHITECTURE", fontsize=10, color=INDIGO, weight="bold"
        )
        flow = [
            ("C2 order", "Assigned plant and approved order master data"),
            ("C3 frontend", "Plant-scoped form auto-fills the assigned order"),
            ("Flask API", "Validates the payload and loads saved artifacts"),
            ("ML + rules", "Predicts risk and builds a recovery plan"),
            ("SQLite", "Stores daily records, incidents, decisions, and outcomes"),
        ]
        x_positions = [0.045, 0.235, 0.425, 0.615, 0.805]
        for idx, ((title, body), x) in enumerate(zip(flow, x_positions, strict=False)):
            ax.add_patch(
                FancyBboxPatch(
                    (x, 0.65),
                    0.155,
                    0.13,
                    boxstyle="round,pad=0.012,rounding_size=0.012",
                    facecolor=PALE,
                    edgecolor=INDIGO if idx in {2, 3} else LINE,
                    linewidth=1.1,
                )
            )
            ax.text(x + 0.015, 0.75, title, fontsize=9.2, color=INK, weight="bold", va="top")
            ax.text(
                x + 0.015,
                0.71,
                textwrap.fill(body, 24),
                fontsize=7.2,
                color=MUTED,
                va="top",
                linespacing=1.25,
            )
            if idx < 4:
                ax.annotate(
                    "",
                    xy=(x + 0.185, 0.715),
                    xytext=(x + 0.158, 0.715),
                    arrowprops=dict(arrowstyle="->", color=INDIGO, lw=1.5),
                )

        implementation_rows = [
            [
                "Training",
                "scripts.component3.train_component3_v2; "
                "scripts.component3.train_component3_model2_v3; "
                "scripts.component3.train_component3_early_warning",
            ],
            [
                "Feature engineering",
                "components/component3_features.py; component3_order_risk_features.py; component3_early_warning_data.py",
            ],
            [
                "Runtime inference",
                "components/component3.py; components/component3_early_warning_inference.py",
            ],
            [
                "Recovery planning",
                "components/component3_recovery.py — deterministic, explainable business rules",
            ],
            [
                "Daily persistence",
                "components/component3_monitoring.py → instance/component3_tracking.db",
            ],
            [
                "Incident workflow",
                "components/component3_tracking.py → decisions, status transitions, and actual outcomes",
            ],
            [
                "Frontend",
                "frontends/src/app/(dashboard)/component3/monitoring and recovery-history",
            ],
        ]
        styled_table(
            ax,
            implementation_rows,
            ["Responsibility", "Implementation"],
            [0.045, 0.335, 0.91, 0.255],
            [0.22, 0.78],
            7.8,
        )

        info_box(
            ax,
            0.045,
            0.135,
            0.285,
            0.145,
            "Backend and model serving",
            "Flask registers Component 3 under /api/component3. The default v3 loader reads the risk-type v2 pickle, order-risk v3 pickle, and three calibrated early-warning joblib artifacts lazily.",
            TEAL,
            body_size=7.0,
            line_spacing=1.1,
        )
        info_box(
            ax,
            0.357,
            0.135,
            0.285,
            0.145,
            "Frontend integration",
            "Next.js/TypeScript calls http://127.0.0.1:5001/api/component3 by default. The monitoring screen sends authenticated prediction, monitoring-record, and incident requests.",
            INDIGO,
            "#f5f5ff",
            body_size=7.0,
            line_spacing=1.1,
        )
        info_box(
            ax,
            0.67,
            0.135,
            0.285,
            0.145,
            "Access control",
            "Manager and PlantManager routes require authentication. JWT plant_id scopes Plant Manager data; the API never trusts a browser-supplied plant query parameter.",
            ORANGE,
            "#fff8ee",
            body_size=7.0,
            line_spacing=1.1,
        )
        pdf.savefig(fig, bbox_inches="tight")
        plt.close(fig)

        # Page 10: GitHub and reproducibility
        fig, ax = base_page(
            "GitHub project and reproducibility",
            "Verified repository location, branch, project structure, and repeatable commands",
            10,
            "Remote checked with git remote -v; branch checked with git branch --show-current",
        )
        ax.text(0.045, 0.83, "GITHUB REPOSITORY", fontsize=9, color=INDIGO, weight="bold")
        repository_url = "https://github.com/IT22548146/R26-IT-002"
        ax.text(
            0.045,
            0.785,
            repository_url,
            fontsize=15,
            color=INDIGO,
            weight="bold",
            url=repository_url,
        )
        ax.text(0.045, 0.745, "Active development branch: component3", fontsize=9.5, color=INK)
        ax.text(
            0.045,
            0.715,
            "The URL above is the configured origin of the current local project. Repository visibility depends on GitHub access permissions.",
            fontsize=8.2,
            color=MUTED,
        )

        structure_rows = [
            [
                "components/",
                "Component APIs, feature engineering, monitoring, recovery, validation",
            ],
            ["models/", "Saved .pkl and .joblib inference artifacts plus metadata"],
            ["data/", "Component 3 historical and controlled augmented workbooks"],
            ["reports/", "JSON/CSV evaluation evidence and this generated PDF"],
            ["frontends/", "Integrated Next.js portal and Component 3 user interfaces"],
            ["tests/", "Backend, integration, validation, access-scope, and workflow tests"],
        ]
        styled_table(
            ax,
            structure_rows,
            ["Project path", "Purpose"],
            [0.045, 0.43, 0.53, 0.235],
            [0.25, 0.75],
            8.0,
        )

        ax.text(0.61, 0.655, "REPRODUCIBILITY COMMANDS", fontsize=9, color=INDIGO, weight="bold")
        commands = [
            "python -m scripts.component3.train_component3_v2",
            "python -m scripts.component3.train_component3_model2_v3",
            "python -m scripts.component3.train_component3_early_warning",
            "python -m scripts.component3.generate_component3_ml_report",
            "python main.py                         # backend :5001",
            "cd frontends && npm run dev            # frontend :3000",
        ]
        ax.add_patch(
            FancyBboxPatch(
                (0.61, 0.43),
                0.345,
                0.20,
                boxstyle="round,pad=0.012,rounding_size=0.012",
                facecolor="#101827",
                edgecolor="#101827",
            )
        )
        y = 0.6
        for command in commands:
            ax.text(0.63, y, command, fontsize=7.2, family="monospace", color="#d7e4ff", va="top")
            y -= 0.029

        info_box(
            ax,
            0.045,
            0.18,
            0.44,
            0.18,
            "Runtime configuration",
            "Backend uses Flask on port 5001; frontend uses Next.js on port 3000. NEXT_PUBLIC_COMPONENT3_API_URL can override the C3 API base. COMPONENT3_MODEL_VERSION defaults to v3. COMPONENT3_TRACKING_DB can override the C3 SQLite path.",
            TEAL,
        )
        info_box(
            ax,
            0.515,
            0.18,
            0.44,
            0.18,
            "Repository hygiene",
            "Keep .env, API keys, SMTP passwords, local databases, virtual environments, node_modules, and generated build caches out of Git. Commit source code, approved model artifacts, dataset documentation, evaluation evidence, and reproducible scripts.",
            ORANGE,
            "#fff8ee",
        )
        ax.text(
            0.045,
            0.12,
            "Before sharing: rotate any previously exposed credentials and provide .env.example with placeholder values only.",
            fontsize=9,
            color=RED,
            weight="bold",
        )
        pdf.savefig(fig, bbox_inches="tight")
        plt.close(fig)

        # Page 11: artifact map and conclusion
        fig, ax = base_page(
            "Artifacts, conclusions, and reporting limits",
            "Reproducible evidence map for code review, viva, and final documentation",
            11,
            "All paths are relative to the project root",
        )
        artifact_rows = [
            ["Historical dataset", "data/component3_final_preprocessed_dataset.xlsx"],
            ["Risk-type training data", "data/component3_training_augmented.xlsx"],
            ["Overall-risk v3 data", "data/component3_training_balanced_research_v2.xlsx"],
            ["Current risk model", "models/c3_model1_risk_type_v2.pkl"],
            ["Overall order-risk model", "models/c3_model2_order_risk_v3.pkl"],
            ["Early-warning models", "models/c3_early_warning_*_v2.joblib"],
            ["Model 1 evaluation", "reports/component3_v2/evaluation.json"],
            ["Model 2 v3 evaluation", "reports/component3_model2_v3/evaluation.json"],
            [
                "Warning evaluation",
                "reports/component3_early_warning_step5b_calibrated/evaluation.json",
            ],
            ["Recovery validation", "reports/component3_recovery_validation/evaluation.json"],
        ]
        styled_table(
            ax,
            artifact_rows,
            ["Evidence type", "Repository path"],
            [0.045, 0.44, 0.91, 0.38],
            [0.30, 0.70],
            8.0,
        )
        info_box(
            ax,
            0.045,
            0.235,
            0.285,
            0.14,
            "What is demonstrated",
            "End-to-end model training, grouped evaluation, artifact persistence, calibrated subtype warnings, API inference, and recovery-plan generation.",
            TEAL,
            body_size=7.0,
            line_spacing=1.1,
        )
        info_box(
            ax,
            0.357,
            0.235,
            0.285,
            0.14,
            "What is not claimed",
            "No claim of production approval, causal recovery benefit, general emergency warning, or worker-shortage future warning from the current evidence.",
            ORANGE,
            "#fff8ee",
            body_size=7.0,
            line_spacing=1.1,
        )
        info_box(
            ax,
            0.67,
            0.235,
            0.285,
            0.14,
            "Next evidence needed",
            "More independent orders, more minority-class examples, several real Low Risk orders, applied-action logs, and missed-deadline outcomes.",
            INDIGO,
            "#f5f5ff",
            body_size=7.0,
            line_spacing=1.1,
        )
        ax.text(0.045, 0.17, "CONCLUSION", fontsize=10, color=INDIGO, weight="bold")
        conclusion = (
            "Component 3 has a coherent research pipeline and performs substantially above dummy baselines on the available order-grouped evidence. "
            "The results support a working academic prototype, while the stated data limitations justify retaining research-only status until broader independent validation is collected."
        )
        text_block(ax, 0.045, 0.135, conclusion, width=145, size=10, line_height=0.031)
        pdf.savefig(fig, bbox_inches="tight")
        plt.close(fig)

    print(OUTPUT)


if __name__ == "__main__":
    generate()
