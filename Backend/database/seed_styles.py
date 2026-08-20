"""
database/seed_styles.py
Seed 10-12 approved styles into the catalog. Idempotent — skips style numbers
that already exist. Run:  python -m database.seed_styles
"""
import os
import sqlite3

# Allow running from the project root or the database package.
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _db_path() -> str:
    return os.environ.get("DATABASE_PATH", os.path.join(_ROOT, "garment.db"))


# (style_number, style_name, garment_type, width, length, colours, stitches, complexity, description)
STYLES = [
    ("USAC-001256", "Classic Crew Tee",      "T-Shirt", 12.0, 14.0, 3,  4200,  "Low",    "Everyday crew-neck t-shirt with chest logo embroidery."),
    ("USAC-001301", "Polo Signature",        "Polo",    10.5, 11.0, 4,  6800,  "Medium", "Pique polo with embroidered crest on the left chest."),
    ("TESC-002045", "Oxford Button Down",    "Shirt",   14.0, 16.0, 2,  5200,  "Medium", "Formal oxford shirt with subtle collar stitch detail."),
    ("TESC-002110", "Fleece Hoodie",         "Hoodie",  20.0, 24.0, 5,  9800,  "High",   "Heavyweight fleece hoodie with large back embroidery."),
    ("GEO-003012",  "Denim Trucker Jacket",  "Jacket",  22.0, 26.0, 3,  12500, "Hard",   "Denim jacket with dense chest and sleeve embroidery."),
    ("GEO-003077",  "Chino Shorts",          "Shorts",  15.0, 15.0, 2,  3100,  "Low",    "Tailored chino shorts with small hem branding."),
    ("MS-004500",   "Knit Beanie",           "Cap",     8.0,  8.0,  4,  2600,  "Low",    "Ribbed knit beanie with fold-up embroidered band."),
    ("MS-004560",   "Snapback Cap",          "Cap",     9.5,  7.5,  5,  7400,  "Medium", "Flat-brim snapback with raised front embroidery."),
    ("HIRD-005220", "Performance Leggings",  "Leggings",16.0, 30.0, 3,  4800,  "Medium", "Stretch performance leggings with side-seam logo."),
    ("HIRD-005288", "Varsity Bomber",        "Jacket",  24.0, 27.0, 6,  15200, "Hard",   "Varsity bomber with chenille and thread embroidery."),
    ("USAC-001410", "Canvas Tote",           "Bag",     18.0, 20.0, 2,  3900,  "Low",    "Heavy canvas tote with single-colour front logo."),
    ("TESC-002201", "Quarter-Zip Pullover",  "Pullover",19.0, 23.0, 3,  8600,  "High",   "Mid-layer quarter-zip with sleeve embroidery."),
]


def seed_styles():
    conn = sqlite3.connect(_db_path())
    admin = conn.execute("SELECT id FROM users WHERE role='Admin' ORDER BY id LIMIT 1").fetchone()
    admin_id = admin[0] if admin else None

    added, skipped = 0, 0
    for (num, name, gtype, w, l, colours, stitches, complexity, desc) in STYLES:
        exists = conn.execute("SELECT 1 FROM styles WHERE style_number=?", (num,)).fetchone()
        if exists:
            skipped += 1
            continue
        conn.execute(
            """INSERT INTO styles
               (style_number, style_name, description, design_width, design_length,
                color_count, stitch_count, complexity, garment_type, added_by, status)
               VALUES (?,?,?,?,?,?,?,?,?,?, 'Approved')""",
            (num, name, desc, w, l, colours, stitches, complexity, gtype, admin_id),
        )
        added += 1
    conn.commit()
    conn.close()
    print(f"[seed_styles] added {added}, skipped {skipped} existing. DB: {_db_path()}")


if __name__ == "__main__":
    seed_styles()
