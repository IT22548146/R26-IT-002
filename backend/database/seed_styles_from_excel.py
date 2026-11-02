"""
database/seed_styles_from_excel.py

Seeds the styles catalog from the Component 2 bulk-order dataset
(component2_bulk_order_aligned_to.xlsx).

The sheet holds 400 bulk orders; the style specs repeat across rows, so we take
the distinct Style_ID rows and load each one as an Approved catalog style.

Idempotent: existing style_numbers are skipped (never overwritten), so buyer- and
admin-created styles are safe.

Run:
    python -m database.seed_styles_from_excel                       # default path
    python -m database.seed_styles_from_excel "C:/path/to/file.xlsx"
"""
import os
import sqlite3
import sys

DEFAULT_XLSX = os.path.join(
    os.path.expanduser("~"), "Downloads", "component2_bulk_order_aligned_to.xlsx"
)
SHEET = "Component2_Bulk_400"

# Sheet column -> styles column
COLUMNS = {
    "Style_ID": "style_number",
    "Design_Width": "design_width",
    "Design_Length": "design_length",
    "Color_Count": "color_count",
    "Stitch_Count": "stitch_count",
    "Design_Complexity": "complexity",
}

# The styles table CHECKs complexity against this set.
VALID_COMPLEXITY = {"Low", "Medium", "High", "Hard"}


def _db():
    path = os.environ.get("DATABASE_PATH", "garment.db")
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


def seed(xlsx_path=None):
    try:
        import pandas as pd
    except ImportError:
        print("pandas is required: pip install pandas openpyxl")
        return

    xlsx_path = xlsx_path or DEFAULT_XLSX
    if not os.path.exists(xlsx_path):
        print("Excel file not found: %s" % xlsx_path)
        return

    df = pd.read_excel(xlsx_path, sheet_name=SHEET)
    missing = [c for c in COLUMNS if c not in df.columns]
    if missing:
        print("Sheet is missing expected columns: %s" % missing)
        return

    # One row per style; the specs repeat across the 400 orders.
    styles = df[list(COLUMNS)].drop_duplicates(subset=["Style_ID"])

    conn = _db()
    existing = {r["style_number"] for r in conn.execute("SELECT style_number FROM styles")}

    inserted = skipped = invalid = 0
    for _, row in styles.iterrows():
        style_number = str(row["Style_ID"]).strip().upper()
        if not style_number or style_number == "NAN":
            invalid += 1
            continue
        if style_number in existing:
            skipped += 1
            continue

        try:
            design_width = float(row["Design_Width"])
            design_length = float(row["Design_Length"])
            color_count = int(row["Color_Count"])
            stitch_count = int(row["Stitch_Count"])
        except (TypeError, ValueError):
            invalid += 1
            continue

        complexity = str(row["Design_Complexity"]).strip().title()
        if complexity not in VALID_COMPLEXITY:
            complexity = None

        conn.execute(
            """INSERT INTO styles
               (style_number, style_name, description, design_width, design_length,
                color_count, stitch_count, complexity, garment_type, added_by,
                status, style_pdf_path)
               VALUES (?,?,?,?,?,?,?,?,?,?, 'Approved', NULL)""",
            (style_number, None, "Imported from Component 2 dataset",
             design_width, design_length, color_count, stitch_count,
             complexity, None, None),
        )
        existing.add(style_number)
        inserted += 1

    conn.commit()
    total = conn.execute("SELECT COUNT(*) c FROM styles").fetchone()["c"]
    conn.close()
    print("Styles seeded from %s" % os.path.basename(xlsx_path))
    print("  inserted : %d" % inserted)
    print("  skipped  : %d (already in the catalog)" % skipped)
    if invalid:
        print("  invalid  : %d (unreadable specs)" % invalid)
    print("  styles table total: %d" % total)


if __name__ == "__main__":
    seed(sys.argv[1] if len(sys.argv) > 1 else None)
