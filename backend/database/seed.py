"""
database/seed.py
One-time migration script - run ONCE to populate all static tables
and import both Excel capacity files.

Usage (from project root):
    python -m database.seed
"""

import os
import sys
import sqlite3
import hashlib
import secrets
import pandas as pd
from datetime import datetime

# ── Allow running from project root ──────────────────────────────────────
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from database.schema import SCHEMA_SQL

DB_PATH        = os.environ.get("DATABASE_PATH", "garment.db")
MODELS_DIR     = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "models")
CAP_2024_PATH  = os.path.join(MODELS_DIR, "capacity_full_year_2024.xlsx")
CAP_2026_PATH  = os.path.join(MODELS_DIR, "capacity_full_year_2026.xlsx")

MOTHER_COMPANY = os.environ.get("MOTHER_COMPANY_NAME", "FabricFlow International")
ADMIN_EMAIL    = os.environ.get("ADMIN_EMAIL",    "admin@fabricflow.com")
ADMIN_PASSWORD = os.environ.get("ADMIN_DEFAULT_PASSWORD", "Admin@FabricFlow2024")


def _hash(password: str) -> str:
    """Simple SHA-256 password hash - replace with bcrypt in production."""
    return hashlib.sha256(password.encode()).hexdigest()


def seed(conn: sqlite3.Connection):
    cur = conn.cursor()

    # ── 1. Organizations ──────────────────────────────────────────────────
    print("[seed] Organizations ...")
    orgs = [
        (MOTHER_COMPANY, "MotherCompany", ADMIN_EMAIL),
        ("Tesco",        "Buyer",         "buyer@tesco.com"),
        ("George",       "Buyer",         "buyer@george.com"),
        ("M&S",          "Buyer",         "buyer@ms.com"),
        ("Hirdaramani",  "Buyer",         "buyer@hirdaramani.com"),
    ]
    cur.executemany(
        "INSERT OR IGNORE INTO organizations(name, type, contact_email) VALUES (?,?,?)",
        orgs,
    )
    conn.commit()

    # Fetch mother company id
    mc_id = cur.execute(
        "SELECT id FROM organizations WHERE name = ?", (MOTHER_COMPANY,)
    ).fetchone()[0]

    # ── 2. Plants ─────────────────────────────────────────────────────────
    print("[seed] Plants ...")
    # Data sourced from: C1 PLANT_QUALITY/PLANT_LOCATIONS/PLANT_ONTIME_RATES/PLANT_UTIL_RANGE
    #                    C2 hist_miss, C4 PLANT_KPI
    plants = [
        # id,    name,                           location,         quality, on_time, miss,  u_min,  u_max, machines, employees
        ("PL01", "Dinusha Embroidery",            "Weliweriya",      4.8,    0.92,   0.10,  75.00, 100.0,  20,       60),
        ("PL02", "MRC Group",                     "Colombo",         4.5,    0.88,   0.15,  33.33, 100.0,  18,       55),
        ("PL03", "The Bobbin Group",              "Mount Lavinia",   4.4,    0.85,   0.13,  80.00, 100.0,  16,       50),
        ("PL04", "Sunrose Lanka (Pvt) Ltd",       "Katubedda",       4.3,    0.83,   0.14,  33.33, 100.0,  15,       48),
        ("PL05", "Regal Image International",     "Maharagama",      4.6,    0.80,   0.12,  33.33, 100.0,  17,       52),
        ("PL06", "Amsral Lanka Enterprises",      "Boralesgamuwa",   4.2,    0.78,   0.16,  33.33, 100.0,  14,       45),
    ]
    cur.executemany(
        """INSERT OR IGNORE INTO plants
           (id, org_id, name, location, quality_rating, historical_on_time_rate,
            historical_miss_rate, utilization_min, utilization_max,
            total_machines, employee_count)
           VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
        [(p[0], mc_id, *p[1:]) for p in plants],
    )
    conn.commit()

    # ── 3. Buyers Config (replaces BUYER_SHIPMENT_SCHEDULE + BUYER_DOW) ──
    print("[seed] Buyers config ...")
    buyer_org = lambda name: cur.execute(
        "SELECT id FROM organizations WHERE name = ?", (name,)
    ).fetchone()[0]

    buyers_config = [
        ("Tesco",       "Monday",   0, buyer_org("Tesco")),
        ("M&S",         "Monday",   0, buyer_org("M&S")),
        ("George",      "Thursday", 3, buyer_org("George")),
        ("Hirdaramani", "Thursday", 3, buyer_org("Hirdaramani")),
    ]
    cur.executemany(
        "INSERT OR IGNORE INTO buyers_config(buyer_name, shipment_day, shipment_dow_index, org_id) VALUES (?,?,?,?)",
        buyers_config,
    )
    conn.commit()

    # ── 4. Allocation Guide (replaces ALLOCATION_GUIDE dict in C2) ────────
    print("[seed] Allocation guide ...")
    alloc_rows = [
        # (priority,      complexity, plant_name,                       pref)
        ("High",       "Hard",   "Dinusha Embroidery",            1),
        ("High",       "Hard",   "Regal Image International",     2),
        ("High",       "High",   "Dinusha Embroidery",            1),
        ("High",       "High",   "Regal Image International",     2),
        ("High",       "Medium", "Dinusha Embroidery",            1),
        ("High",       "Medium", "The Bobbin Group",              2),
        ("Normal",     "High",   "Dinusha Embroidery",            1),
        ("Normal",     "High",   "Regal Image International",     2),
        ("Normal",     "Medium", "The Bobbin Group",              1),
        ("Normal",     "Medium", "Sunrose Lanka (Pvt) Ltd",       2),
        ("Low",        "Low",    "MRC Group",                     1),
        ("Low",        "Low",    "Amsral Lanka Enterprises",      2),
        ("No Urgency", "Low",    "MRC Group",                     1),
        ("No Urgency", "Low",    "Amsral Lanka Enterprises",      2),
    ]
    # Look up plant IDs
    plant_name_to_id = {
        row[0]: row[1]
        for row in cur.execute("SELECT name, id FROM plants").fetchall()
    }
    for priority, complexity, plant_name, pref in alloc_rows:
        pid = plant_name_to_id.get(plant_name)
        if pid:
            cur.execute(
                """INSERT OR IGNORE INTO allocation_guide
                   (priority_level, complexity_level, plant_id, preference_order)
                   VALUES (?,?,?,?)""",
                (priority, complexity, pid, pref),
            )
    conn.commit()

    # ── 5. Admin User ─────────────────────────────────────────────────────
    print("[seed] Admin user ...")
    cur.execute(
        """INSERT OR IGNORE INTO users(org_id, full_name, email, password_hash, role, status)
           VALUES (?,?,?,?,?,?)""",
        (mc_id, "System Admin", ADMIN_EMAIL, _hash(ADMIN_PASSWORD), "Admin", "Approved"),
    )
    conn.commit()

    admin_id = cur.execute(
        "SELECT id FROM users WHERE email = ?", (ADMIN_EMAIL,)
    ).fetchone()[0]

    # ── 6. Plant Manager Users (one per plant, pre-seeded) ───────────────
    print("[seed] Plant manager accounts ...")
    plant_managers = [
        ("PL01", "Dinusha Embroidery Manager",      "manager.pl01@dinusha.com"),
        ("PL02", "MRC Group Manager",               "manager.pl02@mrc.com"),
        ("PL03", "The Bobbin Group Manager",         "manager.pl03@bobbin.com"),
        ("PL04", "Sunrose Lanka Manager",            "manager.pl04@sunrose.com"),
        ("PL05", "Regal Image Manager",              "manager.pl05@regal.com"),
        ("PL06", "Amsral Lanka Manager",             "manager.pl06@amsral.com"),
    ]
    default_pm_password = "Plant@Manager2024"
    for plant_id, full_name, email in plant_managers:
        cur.execute(
            """INSERT OR IGNORE INTO users
               (org_id, full_name, email, password_hash, role, plant_id, status,
                approved_by, approved_at)
               VALUES (?,?,?,?,?,?,?,?,?)""",
            (mc_id, full_name, email, _hash(default_pm_password),
             "PlantManager", plant_id, "Approved", admin_id, datetime.utcnow()),
        )
    conn.commit()

    # ── 7. Plant Capacity History from Excel files ────────────────────────
    for cap_path, label in [(CAP_2024_PATH, "2024"), (CAP_2026_PATH, "2026")]:
        if not os.path.exists(cap_path):
            print(f"[seed] WARN: {cap_path} not found - skipping {label} capacity data")
            continue
        print(f"[seed] Importing capacity_full_year_{label}.xlsx ...")
        df = pd.read_excel(cap_path)
        df["Date"] = pd.to_datetime(df["Date"]).dt.date

        # Column mapping - adjust if your Excel header names differ
        col_map = {
            "Plant_Name":          "plant_name",
            "Utilization_Pct":     "utilization_pct",
            "Free_Machine_Ratio":  "free_machine_ratio",
            "Styles_Can_Do":       "styles_can_do",
            "Total_Machines":      "total_machines",
        }
        df = df.rename(columns=col_map)

        inserted = 0
        for _, row in df.iterrows():
            plant_name = str(row.get("plant_name", "")).strip()
            pid = plant_name_to_id.get(plant_name)
            if pid is None:
                continue
            try:
                cur.execute(
                    """INSERT OR IGNORE INTO plant_capacity_history
                       (plant_id, record_date, utilization_pct, free_machine_ratio,
                        styles_can_do, total_machines)
                       VALUES (?,?,?,?,?,?)""",
                    (pid, str(row["Date"]),
                     float(row.get("utilization_pct", 85.0)),
                     float(row.get("free_machine_ratio", 0.15)),
                     int(row.get("styles_can_do", 5)),
                     int(row.get("total_machines", 15))),
                )
                inserted += 1
            except Exception as exc:
                print(f"  [warn] row skip: {exc}")
        conn.commit()
        print(f"  >> {inserted} rows imported from {label}")

    print("\n[seed] DONE.")
    print(f"  Admin login : {ADMIN_EMAIL}  /  {ADMIN_PASSWORD}")
    print(f"  Plant mgrs  : manager.pl01@dinusha.com ... (password: {default_pm_password})")
    print(f"  Database    : {DB_PATH}")


if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()

    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(SCHEMA_SQL)   # ensure tables exist first
    conn.commit()
    seed(conn)
    conn.close()
