"""
database/db.py
SQLite connection helper for the Garment Production System.
Usage:
    from database.db import get_db, init_db
"""

import os
import sqlite3
from flask import g
from database.schema import SCHEMA_SQL


def _db_path() -> str:
    return os.environ.get("DATABASE_PATH", "garment.db")


def get_db() -> sqlite3.Connection:
    """
    Return the per-request SQLite connection stored on Flask's g object.
    Creates a new connection if one doesn't exist yet.
    Rows are returned as sqlite3.Row (dict-like access).
    """
    if "db" not in g:
        g.db = sqlite3.connect(
            _db_path(),
            detect_types=sqlite3.PARSE_DECLTYPES | sqlite3.PARSE_COLNAMES,
        )
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
        g.db.execute("PRAGMA journal_mode = WAL")   # better concurrency
    return g.db


def close_db(e=None):
    """Tear down the per-request connection (registered as app teardown)."""
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db():
    """
    Create all tables if they do not already exist.
    Safe to call on every app startup — uses CREATE TABLE IF NOT EXISTS.
    """
    conn = sqlite3.connect(_db_path())
    conn.executescript(SCHEMA_SQL)
    _run_migrations(conn)
    conn.commit()
    conn.close()
    print(f"[DB] Initialised: {_db_path()}")


def _run_migrations(conn: sqlite3.Connection):
    """
    Lightweight, idempotent migrations for columns added after a DB already
    exists (CREATE TABLE IF NOT EXISTS won't add new columns to old tables).
    """
    def _add_column(table: str, column: str, ddl: str):
        cols = {row[1] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}
        if column not in cols:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {ddl}")
            print(f"[DB] Migration: added {table}.{column}")

    _add_column("sample_orders", "style_pdf_path", "style_pdf_path TEXT")

    # Phase 2 — extended buyer profile fields.
    _add_column("users", "contact_no",       "contact_no TEXT")
    _add_column("users", "country",          "country TEXT")
    _add_column("users", "address",          "address TEXT")
    _add_column("users", "profile_pic_path", "profile_pic_path TEXT")

    # Manager role — an admin-panel operator without user/performance access.
    _migrate_users_role(conn)

    # Part B — Local Sub Plant Portal.
    # plant_type separates the company's own registered plants from external
    # local sub plants. Everything that feeds Component 1/2 (network capacity,
    # allocation) must filter to 'Registered' so sub plants never distort them.
    _add_column("plants", "plant_type",
                "plant_type TEXT DEFAULT 'Registered' CHECK(plant_type IN ('Registered','SubPlant'))")
    _add_column("plants", "contact_no", "contact_no TEXT")
    _add_column("plants", "contact_email", "contact_email TEXT")
    _migrate_users_role_subplant(conn)
    conn.executescript(SUBPLANT_SQL)

    # Component 4 (plant-based) — plant-wide daily ops logs + monthly performance.
    # CREATE TABLE IF NOT EXISTS in schema.py handles these, but call explicitly so
    # an already-initialised DB picks them up on the next start.
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS plant_daily_logs (
        id                      INTEGER PRIMARY KEY AUTOINCREMENT,
        plant_id                TEXT    NOT NULL REFERENCES plants(id),
        log_date                DATE    NOT NULL,
        machines_total          INTEGER NOT NULL,
        machines_active         INTEGER NOT NULL,
        employees_present       INTEGER NOT NULL,
        machine_breakdown_count INTEGER DEFAULT 0,
        worker_shortage_count   INTEGER DEFAULT 0,
        total_output            INTEGER DEFAULT 0,
        total_damage_qty        INTEGER DEFAULT 0,
        urgent_orders_handled   INTEGER DEFAULT 0,
        notes                   TEXT,
        submitted_by            INTEGER REFERENCES users(id),
        created_at              DATETIME DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(plant_id, log_date)
    );
    CREATE INDEX IF NOT EXISTS idx_pdl_plant_date ON plant_daily_logs(plant_id, log_date);
    CREATE TABLE IF NOT EXISTS plant_performance (
        id                 INTEGER PRIMARY KEY AUTOINCREMENT,
        plant_id           TEXT    NOT NULL REFERENCES plants(id),
        month_year         TEXT    NOT NULL,
        performance_score  REAL,
        star_rating_num    INTEGER,
        on_time_rate       REAL,
        efficiency         REAL,
        utilization        REAL,
        damage_rate        REAL,
        delay_ratio        REAL,
        daily_commitment   REAL,
        total_workload     INTEGER,
        urgent_handled     INTEGER,
        best_plant_category TEXT,
        c4_result_json     TEXT,
        computed_at        DATETIME DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(plant_id, month_year)
    );
    CREATE INDEX IF NOT EXISTS idx_pp_month ON plant_performance(month_year);
    """)

    # Phase 3 — sample_orders status rework (needs a table rebuild).
    _migrate_sample_status(conn)

    # Phase 5 — bulk_orders status pipeline rework (needs a table rebuild).
    _migrate_bulk_status(conn)

    # Phase 7 — plant must approve an assignment before production; timestamp
    # also drives the "auto-complete after production days elapse" behaviour.
    _add_column("bulk_orders", "plant_approved_at", "plant_approved_at DATETIME")

    # Bulk orders can carry an optional style PDF, same as sample orders.
    _add_column("bulk_orders", "style_pdf_path", "style_pdf_path TEXT")

    # Optional buyer note on bulk orders (sample orders already have one).
    _add_column("bulk_orders", "notes", "notes TEXT")

    # The completion timeline the admin proposed (given/needed/gap days and the
    # resulting date). Previously these lived only in the email body, so the buyer
    # was asked to approve a timeline they could not see in the app.
    _add_column("bulk_orders", "timeline_decision",       "timeline_decision TEXT")
    _add_column("bulk_orders", "timeline_given_days",     "timeline_given_days INTEGER")
    _add_column("bulk_orders", "timeline_needed_days",    "timeline_needed_days INTEGER")
    _add_column("bulk_orders", "timeline_gap_days",       "timeline_gap_days INTEGER")
    _add_column("bulk_orders", "proposed_required_date",  "proposed_required_date DATE")

    # Buyer's in-app reply to the completion-timeline email.
    _add_column("bulk_orders", "customer_message", "customer_message TEXT")
    _add_column("bulk_orders", "extension_days_requested", "extension_days_requested INTEGER")
    _add_column("bulk_orders", "customer_responded_at", "customer_responded_at DATETIME")

    # Granular garment production stage, advanced by plant managers / admin and
    # shown to the buyer as a tracking bar.
    _stage_ddl = ("production_stage TEXT DEFAULT 'Pending' "
                  "CHECK(production_stage IN "
                  "('Pending','Cutting','Embroidery','Sewing','Packing','Shipping','Delivery'))")
    _add_column("bulk_orders",   "production_stage", _stage_ddl)
    _add_column("sample_orders", "production_stage", _stage_ddl)

    # Style submission / approval workflow. Existing + admin-added styles default
    # to Approved; buyer-submitted styles start Pending.
    _add_column("styles", "status",
                "status TEXT DEFAULT 'Approved' CHECK(status IN ('Pending','Approved','Rejected'))")
    _add_column("styles", "style_pdf_path", "style_pdf_path TEXT")
    _add_column("styles", "reviewed_by",    "reviewed_by INTEGER")
    _add_column("styles", "reviewed_at",    "reviewed_at DATETIME")
    _add_column("styles", "reject_reason",  "reject_reason TEXT")


SUBPLANT_SQL = """
-- ── Local Sub Plant Portal (Part B) ───────────────────────────────────────
CREATE TABLE IF NOT EXISTS sub_plant_customers (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    plant_id       TEXT NOT NULL REFERENCES plants(id),
    customer_code  TEXT,
    customer_name  TEXT NOT NULL,
    customer_type  TEXT,
    contact_no     TEXT,
    location       TEXT,
    registered_date DATE,
    is_active      INTEGER DEFAULT 1,
    created_at     DATETIME DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_spc_plant ON sub_plant_customers(plant_id);

CREATE TABLE IF NOT EXISTS sub_plant_orders (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    plant_id        TEXT NOT NULL REFERENCES plants(id),
    order_number    TEXT NOT NULL,
    customer_id     INTEGER REFERENCES sub_plant_customers(id),
    order_date      DATE,
    order_quantity  INTEGER NOT NULL,
    planned_start   DATE,
    planned_finish  DATE,
    actual_finish   DATE,
    completed_qty   INTEGER DEFAULT 0,
    status          TEXT DEFAULT 'Draft'
        CHECK(status IN ('Draft','Confirmed','In Progress','Completed','Cancelled')),
    notes           TEXT,
    created_at      DATETIME DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_spo_plant ON sub_plant_orders(plant_id);

CREATE TABLE IF NOT EXISTS sub_plant_gatepasses (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    plant_id        TEXT NOT NULL REFERENCES plants(id),
    gatepass_number TEXT NOT NULL,
    gatepass_date   DATE NOT NULL,
    order_id        INTEGER REFERENCES sub_plant_orders(id),
    customer_id     INTEGER REFERENCES sub_plant_customers(id),
    style_number    TEXT,
    description     TEXT,
    good_qty        INTEGER DEFAULT 0,
    damage_qty      INTEGER DEFAULT 0,
    dispatch_status TEXT DEFAULT 'Pending'
        CHECK(dispatch_status IN ('Pending','Dispatched','Received')),
    created_at      DATETIME DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_spg_plant_date ON sub_plant_gatepasses(plant_id, gatepass_date);

CREATE TABLE IF NOT EXISTS sub_plant_invoices (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    plant_id        TEXT NOT NULL REFERENCES plants(id),
    invoice_number  TEXT NOT NULL,
    invoice_date    DATE NOT NULL,
    customer_id     INTEGER REFERENCES sub_plant_customers(id),
    description     TEXT,
    amount          REAL NOT NULL DEFAULT 0,
    discount        REAL DEFAULT 0,
    total_price     REAL NOT NULL DEFAULT 0,
    paid_amount     REAL DEFAULT 0,
    due_date        DATE,
    payment_status  TEXT DEFAULT 'Pending'
        CHECK(payment_status IN ('Paid','Partial','Pending','Overdue')),
    created_at      DATETIME DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_spi_plant ON sub_plant_invoices(plant_id);

CREATE TABLE IF NOT EXISTS sub_plant_payments (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    invoice_id    INTEGER NOT NULL REFERENCES sub_plant_invoices(id),
    payment_date  DATE NOT NULL,
    amount        REAL NOT NULL,
    method        TEXT,
    note          TEXT,
    created_at    DATETIME DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_spp_invoice ON sub_plant_payments(invoice_id);
"""


def _migrate_users_role_subplant(conn: sqlite3.Connection):
    """Add 'SubPlant' to users.role. Rebuilds the table (SQLite CHECK limitation)."""
    row = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name='users'"
    ).fetchone()
    if not row or "'SubPlant'" in (row[0] or ""):
        return

    conn.execute("PRAGMA foreign_keys=OFF")
    conn.executescript("""
    CREATE TABLE users_sp_new (
        id            INTEGER PRIMARY KEY AUTOINCREMENT,
        org_id        INTEGER NOT NULL REFERENCES organizations(id),
        full_name     TEXT    NOT NULL,
        email         TEXT    UNIQUE NOT NULL,
        password_hash TEXT    NOT NULL,
        role          TEXT    NOT NULL
            CHECK(role IN ('Admin','Buyer','PlantManager','Manager','SubPlant')),
        plant_id      TEXT    REFERENCES plants(id),
        status        TEXT    DEFAULT 'Pending' CHECK(status IN ('Pending','Approved','Rejected')),
        approved_by   INTEGER REFERENCES users(id),
        approved_at   DATETIME,
        contact_no       TEXT,
        country          TEXT,
        address          TEXT,
        profile_pic_path TEXT,
        created_at    DATETIME DEFAULT CURRENT_TIMESTAMP
    );
    INSERT INTO users_sp_new
        (id, org_id, full_name, email, password_hash, role, plant_id, status,
         approved_by, approved_at, contact_no, country, address, profile_pic_path, created_at)
    SELECT
        id, org_id, full_name, email, password_hash, role, plant_id, status,
        approved_by, approved_at, contact_no, country, address, profile_pic_path, created_at
    FROM users;
    DROP TABLE users;
    ALTER TABLE users_sp_new RENAME TO users;
    """)
    conn.execute("PRAGMA foreign_keys=ON")
    print("[DB] Migration: added 'SubPlant' to users.role")


def _migrate_users_role(conn: sqlite3.Connection):
    """
    Add 'Manager' to the users.role CHECK set (an admin-panel operator role).
    SQLite can't alter a CHECK in place, so rebuild the table. Idempotent —
    keyed on whether the current CHECK already lists Manager.
    """
    row = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name='users'"
    ).fetchone()
    if not row or "'Manager'" in (row[0] or ""):
        return  # already allows Manager (or table missing → schema.py handles it)

    conn.execute("PRAGMA foreign_keys=OFF")
    conn.executescript("""
    CREATE TABLE users_new (
        id            INTEGER PRIMARY KEY AUTOINCREMENT,
        org_id        INTEGER NOT NULL REFERENCES organizations(id),
        full_name     TEXT    NOT NULL,
        email         TEXT    UNIQUE NOT NULL,
        password_hash TEXT    NOT NULL,
        role          TEXT    NOT NULL CHECK(role IN ('Admin','Buyer','PlantManager','Manager')),
        plant_id      TEXT    REFERENCES plants(id),
        status        TEXT    DEFAULT 'Pending' CHECK(status IN ('Pending','Approved','Rejected')),
        approved_by   INTEGER REFERENCES users(id),
        approved_at   DATETIME,
        contact_no       TEXT,
        country          TEXT,
        address          TEXT,
        profile_pic_path TEXT,
        created_at    DATETIME DEFAULT CURRENT_TIMESTAMP
    );
    INSERT INTO users_new
        (id, org_id, full_name, email, password_hash, role, plant_id, status,
         approved_by, approved_at, contact_no, country, address, profile_pic_path, created_at)
    SELECT
        id, org_id, full_name, email, password_hash, role, plant_id, status,
        approved_by, approved_at, contact_no, country, address, profile_pic_path, created_at
    FROM users;
    DROP TABLE users;
    ALTER TABLE users_new RENAME TO users;
    """)
    conn.execute("PRAGMA foreign_keys=ON")
    print("[DB] Migration: added 'Manager' to users.role")


def _migrate_sample_status(conn: sqlite3.Connection):
    """
    Rework sample_orders.status into a buyer-facing lifecycle and move
    feasibility into its own admin-only column. Idempotent — keyed on the
    presence of the `feasibility` column. Proven on a copy before shipping.

      old status  -> new status , feasibility
      Pending     -> Pending    , NULL
      Feasible    -> Pending    , Feasible
      Infeasible  -> Pending    , Infeasible
      Assigned    -> Processing , Feasible
      Completed   -> Completed  , Feasible
    """
    cols = {r[1] for r in conn.execute("PRAGMA table_info(sample_orders)")}
    if "feasibility" in cols:
        return  # already migrated

    conn.execute("PRAGMA foreign_keys=OFF")
    conn.executescript("""
    CREATE TABLE sample_orders_new (
        id                  INTEGER PRIMARY KEY AUTOINCREMENT,
        style_number        TEXT    NOT NULL,
        artwork_number      TEXT,
        buyer_id            INTEGER NOT NULL REFERENCES users(id),
        sample_qty          INTEGER NOT NULL CHECK(sample_qty BETWEEN 5 AND 9),
        receive_date        DATE    NOT NULL,
        buyer_required_date DATE    NOT NULL,
        notes               TEXT,
        status              TEXT    DEFAULT 'Pending'
            CHECK(status IN ('Pending','Processing','Completed','Cancelled')),
        feasibility         TEXT    CHECK(feasibility IN ('Feasible','Infeasible')),
        assigned_plant_id   TEXT    REFERENCES plants(id),
        assigned_by         INTEGER REFERENCES users(id),
        assigned_at         DATETIME,
        c1_result_json      TEXT,
        style_pdf_path      TEXT,
        created_at          DATETIME DEFAULT CURRENT_TIMESTAMP
    );

    INSERT INTO sample_orders_new
        (id, style_number, artwork_number, buyer_id, sample_qty, receive_date,
         buyer_required_date, notes, status, feasibility, assigned_plant_id,
         assigned_by, assigned_at, c1_result_json, style_pdf_path, created_at)
    SELECT
        id, style_number, artwork_number, buyer_id,
        MIN(MAX(sample_qty,5),9),
        receive_date, buyer_required_date, notes,
        CASE status
            WHEN 'Assigned'  THEN 'Processing'
            WHEN 'Completed' THEN 'Completed'
            ELSE 'Pending'
        END,
        CASE status
            WHEN 'Feasible'   THEN 'Feasible'
            WHEN 'Infeasible' THEN 'Infeasible'
            WHEN 'Assigned'   THEN 'Feasible'
            WHEN 'Completed'  THEN 'Feasible'
            ELSE NULL
        END,
        assigned_plant_id, assigned_by, assigned_at, c1_result_json,
        style_pdf_path, created_at
    FROM sample_orders;

    DROP TABLE sample_orders;
    ALTER TABLE sample_orders_new RENAME TO sample_orders;
    """)
    conn.execute("PRAGMA foreign_keys=ON")
    print("[DB] Migration: reworked sample_orders status + feasibility")


def _migrate_bulk_status(conn: sqlite3.Connection):
    """
    Rework bulk_orders.status into the admin workflow pipeline and add
    customer_response + timeline_email_sent_at. Idempotent — keyed on the
    presence of the customer_response column. Proven on a copy before shipping.

      old status    -> new status
      Pending       -> Pending
      Analyzing     -> Pending
      Assigned      -> Processing
      In-Production -> Processing
      Ready         -> Completed
      Shipped       -> Shipped
    """
    cols = {r[1] for r in conn.execute("PRAGMA table_info(bulk_orders)")}
    if "customer_response" in cols:
        return

    conn.execute("PRAGMA foreign_keys=OFF")
    conn.executescript("""
    CREATE TABLE bulk_orders_new (
        id                  INTEGER PRIMARY KEY AUTOINCREMENT,
        sample_order_id     INTEGER REFERENCES sample_orders(id),
        style_number        TEXT    NOT NULL,
        buyer_id            INTEGER NOT NULL REFERENCES users(id),
        bulk_order_quantity INTEGER NOT NULL,
        daily_commitment    INTEGER NOT NULL,
        style_priority      TEXT    NOT NULL
            CHECK(style_priority IN ('High','Normal','Low','No Urgency')),
        design_width        REAL, design_length REAL, color_count INTEGER, stitch_count INTEGER,
        approved_date       DATE    NOT NULL,
        buyer_required_date DATE    NOT NULL,
        damage_pct          REAL    DEFAULT 0.0,
        shipment_days       INTEGER DEFAULT 18,
        status              TEXT    DEFAULT 'Pending'
            CHECK(status IN ('Pending','CustomerPending','Processing','Hold','Completed','Shipped')),
        customer_response   TEXT    CHECK(customer_response IN ('Approved','Rejected')),
        timeline_email_sent_at DATETIME,
        assigned_by         INTEGER REFERENCES users(id),
        assigned_at         DATETIME,
        ready_at            DATETIME,
        shipped_at          DATETIME,
        c2_result_json      TEXT,
        created_at          DATETIME DEFAULT CURRENT_TIMESTAMP
    );
    INSERT INTO bulk_orders_new
        (id, sample_order_id, style_number, buyer_id, bulk_order_quantity, daily_commitment,
         style_priority, design_width, design_length, color_count, stitch_count,
         approved_date, buyer_required_date, damage_pct, shipment_days, status,
         assigned_by, assigned_at, ready_at, shipped_at, c2_result_json, created_at)
    SELECT
        id, sample_order_id, style_number, buyer_id, bulk_order_quantity, daily_commitment,
        style_priority, design_width, design_length, color_count, stitch_count,
        approved_date, buyer_required_date, damage_pct, shipment_days,
        CASE status
            WHEN 'Analyzing'     THEN 'Pending'
            WHEN 'Assigned'      THEN 'Processing'
            WHEN 'In-Production' THEN 'Processing'
            WHEN 'Ready'         THEN 'Completed'
            WHEN 'Shipped'       THEN 'Shipped'
            ELSE 'Pending'
        END,
        assigned_by, assigned_at, ready_at, shipped_at, c2_result_json, created_at
    FROM bulk_orders;
    DROP TABLE bulk_orders;
    ALTER TABLE bulk_orders_new RENAME TO bulk_orders;
    """)
    conn.execute("PRAGMA foreign_keys=ON")
    print("[DB] Migration: reworked bulk_orders status pipeline")


def register_db(app):
    """
    Bind init_db + close_db to a Flask app instance.
    Call once in app.py: register_db(app)
    """
    app.teardown_appcontext(close_db)
    with app.app_context():
        init_db()
