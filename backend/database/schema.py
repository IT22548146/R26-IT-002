"""
database/schema.py
All CREATE TABLE SQL for the Garment Production System.
Run via database/db.py init_db() — do not call directly.
"""

SCHEMA_SQL = """
PRAGMA foreign_keys = ON;

-- ── Organizations (Mother Company + Buyer Companies) ──────────────────────
CREATE TABLE IF NOT EXISTS organizations (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    name          TEXT    UNIQUE NOT NULL,
    type          TEXT    NOT NULL CHECK(type IN ('MotherCompany', 'Buyer')),
    contact_email TEXT,
    phone         TEXT,
    address       TEXT,
    status        TEXT    DEFAULT 'Active' CHECK(status IN ('Active', 'Suspended')),
    created_at    DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- ── Users ─────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS users (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    org_id        INTEGER NOT NULL REFERENCES organizations(id),
    full_name     TEXT    NOT NULL,
    email         TEXT    UNIQUE NOT NULL,
    password_hash TEXT    NOT NULL,
    role          TEXT    NOT NULL CHECK(role IN ('Admin', 'Buyer', 'PlantManager', 'Manager')),
    plant_id      TEXT    REFERENCES plants(id),   -- only for PlantManager
    status        TEXT    DEFAULT 'Pending' CHECK(status IN ('Pending', 'Approved', 'Rejected')),
    approved_by   INTEGER REFERENCES users(id),
    approved_at   DATETIME,
    contact_no       TEXT,                          -- buyer profile (Phase 2)
    country          TEXT,
    address          TEXT,
    profile_pic_path TEXT,
    created_at    DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- ── Plants (pre-seeded from dataset — no UI creation) ─────────────────────
CREATE TABLE IF NOT EXISTS plants (
    id                      TEXT PRIMARY KEY,      -- PL01..PL06
    org_id                  INTEGER REFERENCES organizations(id),
    name                    TEXT    UNIQUE NOT NULL,
    location                TEXT,
    quality_rating          REAL,                  -- C1 PLANT_QUALITY / C4 PLANT_KPI
    historical_on_time_rate REAL,                  -- C1 PLANT_ONTIME_RATES / C4 PLANT_KPI
    historical_miss_rate    REAL,                  -- C2 hist_miss
    utilization_min         REAL,                  -- C1 PLANT_UTIL_RANGE min
    utilization_max         REAL,                  -- C1 PLANT_UTIL_RANGE max
    total_machines          INTEGER,
    employee_count          INTEGER
);

-- ── Buyer Shipment Config (replaces BUYER_SHIPMENT_SCHEDULE + BUYER_DOW) ──
CREATE TABLE IF NOT EXISTS buyers_config (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    org_id              INTEGER REFERENCES organizations(id),
    buyer_name          TEXT    UNIQUE NOT NULL,   -- must match ALL_BUYERS in C1/C2
    shipment_day        TEXT    NOT NULL,           -- 'Monday' or 'Thursday'
    shipment_dow_index  INTEGER NOT NULL            -- 0=Mon, 3=Thu
);

-- ── Plant Capacity History (replaces both Excel files) ────────────────────
CREATE TABLE IF NOT EXISTS plant_capacity_history (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    plant_id            TEXT    NOT NULL REFERENCES plants(id),
    record_date         DATE    NOT NULL,
    utilization_pct     REAL,
    free_machine_ratio  REAL,
    styles_can_do       INTEGER,
    total_machines      INTEGER
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_plant_cap_hist
    ON plant_capacity_history(plant_id, record_date);

-- ── Plant Monthly Capacity (dynamic — decreases as orders are assigned) ───
CREATE TABLE IF NOT EXISTS plant_monthly_capacity (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    plant_id        TEXT    NOT NULL REFERENCES plants(id),
    month_year      TEXT    NOT NULL,              -- 'YYYY-MM'
    total_capacity  INTEGER NOT NULL,
    used_capacity   INTEGER DEFAULT 0
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_plant_monthly
    ON plant_monthly_capacity(plant_id, month_year);

-- ── Allocation Guide (replaces ALLOCATION_GUIDE dict in C2) ──────────────
CREATE TABLE IF NOT EXISTS allocation_guide (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    priority_level    TEXT    NOT NULL,            -- 'High','Normal','Low','No Urgency'
    complexity_level  TEXT    NOT NULL,            -- 'Hard','High','Medium','Low'
    plant_id          TEXT    NOT NULL REFERENCES plants(id),
    preference_order  INTEGER DEFAULT 1            -- 1=first choice, 2=second
);

-- ── Sample Orders (C1 runs here) ─────────────────────────────────────────
CREATE TABLE IF NOT EXISTS sample_orders (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    style_number        TEXT    NOT NULL,
    artwork_number      TEXT,
    buyer_id            INTEGER NOT NULL REFERENCES users(id),
    sample_qty          INTEGER NOT NULL CHECK(sample_qty BETWEEN 5 AND 9),
    receive_date        DATE    NOT NULL,
    buyer_required_date DATE    NOT NULL,
    notes               TEXT,
    -- Buyer-facing lifecycle. Feasibility is tracked separately (admin-only).
    status              TEXT    DEFAULT 'Pending'
        CHECK(status IN ('Pending','Processing','Completed','Cancelled')),
    feasibility         TEXT    CHECK(feasibility IN ('Feasible','Infeasible')),
    assigned_plant_id   TEXT    REFERENCES plants(id),
    assigned_by         INTEGER REFERENCES users(id),
    assigned_at         DATETIME,
    c1_result_json      TEXT,                      -- full C1 JSON response
    style_pdf_path      TEXT,                      -- optional uploaded style PDF (relative path)
    production_stage    TEXT    DEFAULT 'Pending'
        CHECK(production_stage IN ('Pending','Cutting','Embroidery','Sewing','Packing','Shipping','Delivery')),
    -- "Request a new receive date" negotiation (email-based, mirrors the bulk
    -- timeline loop). Status stays 'Pending' during negotiation; the sub-state
    -- is derived from these columns.
    timeline_email_sent_at   DATETIME,             -- when the date-request email went out
    proposed_receive_date    DATE,                 -- new receive date the admin proposed
    customer_response        TEXT,                 -- 'Approved' | 'Rejected' (buyer reply intent)
    customer_message         TEXT,                 -- free-text of the buyer's reply
    extension_days_requested INTEGER,              -- parsed "N days" if buyer asked for more time
    customer_responded_at    DATETIME,
    created_at          DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- ── Bulk Orders (C2 runs here) ────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS bulk_orders (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    sample_order_id     INTEGER REFERENCES sample_orders(id),
    style_number        TEXT    NOT NULL,
    buyer_id            INTEGER NOT NULL REFERENCES users(id),
    bulk_order_quantity INTEGER NOT NULL,
    daily_commitment    INTEGER NOT NULL,
    style_priority      TEXT    NOT NULL
        CHECK(style_priority IN ('High','Normal','Low','No Urgency')),
    design_width        REAL,
    design_length       REAL,
    color_count         INTEGER,
    stitch_count        INTEGER,
    approved_date       DATE    NOT NULL,
    buyer_required_date DATE    NOT NULL,
    damage_pct          REAL    DEFAULT 0.0,
    shipment_days       INTEGER DEFAULT 18,
    notes               TEXT,                          -- optional buyer note
    -- Admin-facing lifecycle: Pending -> CustomerPending -> Processing -> Completed -> Shipped
    -- (Hold is a manual admin pause from any active state).
    status              TEXT    DEFAULT 'Pending'
        CHECK(status IN ('Pending','CustomerPending','Processing','Hold','Completed','Shipped')),
    customer_response   TEXT    CHECK(customer_response IN ('Approved','Rejected')),
    timeline_email_sent_at DATETIME,               -- when the completion-timeline email went out
    assigned_by         INTEGER REFERENCES users(id),
    assigned_at         DATETIME,
    plant_approved_at   DATETIME,                  -- when the plant accepted the assignment
    ready_at            DATETIME,                  -- when plant marks ready
    shipped_at          DATETIME,                  -- when admin confirms shipment
    c2_result_json      TEXT,                      -- full C2 JSON response
    style_pdf_path      TEXT,                      -- optional uploaded style PDF
    production_stage    TEXT    DEFAULT 'Pending'
        CHECK(production_stage IN ('Pending','Cutting','Embroidery','Sewing','Packing','Shipping','Delivery')),
    created_at          DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- ── Order-Plant Allocations (supports split orders from C2) ──────────────
CREATE TABLE IF NOT EXISTS order_plant_allocations (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    bulk_order_id   INTEGER NOT NULL REFERENCES bulk_orders(id),
    plant_id        TEXT    NOT NULL REFERENCES plants(id),
    allocation_type TEXT    DEFAULT 'Primary'
        CHECK(allocation_type IN ('Primary','Secondary')),
    allocated_qty   INTEGER
);

-- ── Daily Production Logs (C3 on each; C4 aggregates all) ────────────────
CREATE TABLE IF NOT EXISTS daily_logs (
    id                          INTEGER PRIMARY KEY AUTOINCREMENT,
    bulk_order_id               INTEGER NOT NULL REFERENCES bulk_orders(id),
    plant_id                    TEXT    NOT NULL REFERENCES plants(id),
    log_date                    DATE    NOT NULL,
    working_day_no              INTEGER NOT NULL,  -- auto-derived: prior log count + 1
    plant_daily_output          INTEGER NOT NULL,
    daily_damage_qty            INTEGER DEFAULT 0,
    max_daily_damage_qty        INTEGER,
    machine_breakdown_count     INTEGER DEFAULT 0,
    worker_shortage_count       INTEGER DEFAULT 0,
    cumulative_completed_qty    INTEGER NOT NULL,
    c3_result_json              TEXT,              -- full C3 risk result
    c4_result_json              TEXT,              -- full C4 analysis result (when run)
    submitted_by                INTEGER REFERENCES users(id),
    created_at                  DATETIME DEFAULT CURRENT_TIMESTAMP
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_daily_log
    ON daily_logs(bulk_order_id, log_date);

-- ── Notifications (persistent in-portal alerts) ───────────────────────────
CREATE TABLE IF NOT EXISTS notifications (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id             INTEGER NOT NULL REFERENCES users(id),
    title               TEXT    NOT NULL,
    message             TEXT    NOT NULL,
    type                TEXT    DEFAULT 'info'
        CHECK(type IN ('info','success','warning','critical')),
    is_read             INTEGER DEFAULT 0,         -- 0=unread, 1=read
    related_order_type  TEXT,                      -- 'sample_order' or 'bulk_order'
    related_order_id    INTEGER,
    created_at          DATETIME DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_notif_user ON notifications(user_id, is_read);

-- ── Style Catalog (Admin / Plant Manager managed) ─────────────────────────
-- Stores technical specs per style so buyers don't have to enter them manually.
-- When a buyer provides a style_number, the system auto-fills C2 fields.
CREATE TABLE IF NOT EXISTS styles (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    style_number    TEXT    UNIQUE NOT NULL,
    style_name      TEXT,
    description     TEXT,
    design_width    REAL    NOT NULL,
    design_length   REAL    NOT NULL,
    color_count     INTEGER NOT NULL,
    stitch_count    INTEGER NOT NULL,
    complexity      TEXT    CHECK(complexity IN ('Low','Medium','High','Hard')),
    garment_type    TEXT,
    added_by        INTEGER REFERENCES users(id),   -- who added / submitted it
    updated_by      INTEGER REFERENCES users(id),
    -- Submission / approval workflow (buyer-submitted styles await review)
    status          TEXT    DEFAULT 'Approved'
        CHECK(status IN ('Pending','Approved','Rejected')),
    style_pdf_path  TEXT,                           -- mandatory PDF for buyer submissions
    reviewed_by     INTEGER REFERENCES users(id),
    reviewed_at     DATETIME,
    reject_reason   TEXT,
    created_at      DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at      DATETIME DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_style_number ON styles(style_number);

-- ── Inbound Emails (IMAP-polled customer replies to timeline messages) ────
CREATE TABLE IF NOT EXISTS inbound_emails (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    message_uid     TEXT    UNIQUE,           -- IMAP UID, prevents reprocessing
    order_id        INTEGER,                  -- matched order id (nullable)
    order_type      TEXT    DEFAULT 'bulk',   -- 'bulk' | 'sample' — which table order_id points at
    from_addr       TEXT,
    subject         TEXT,
    body            TEXT,
    detected_action TEXT,                     -- 'Approved' | 'Rejected' | 'Unclear'
    extension_days  INTEGER,
    applied         INTEGER DEFAULT 0,        -- 1 if it updated the order automatically
    note            TEXT,                     -- why not applied, etc.
    created_at      DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- ── Contact Messages (public "Contact Us" form → admin inbox) ─────────────
CREATE TABLE IF NOT EXISTS contact_messages (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT    NOT NULL,
    email       TEXT    NOT NULL,
    subject     TEXT,
    message     TEXT    NOT NULL,
    is_read     INTEGER DEFAULT 0,          -- 0=unread, 1=read
    created_at  DATETIME DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_contact_unread ON contact_messages(is_read);
-- ── Plant Daily Logs (Component 4 — plant-wide operations, one row per plant/day) ──
-- Plant-level operational reality: machines running, staff present, disruptions.
-- Distinct from daily_logs (which is per bulk order and feeds Component 3).
CREATE TABLE IF NOT EXISTS plant_daily_logs (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    plant_id                TEXT    NOT NULL REFERENCES plants(id),
    log_date                DATE    NOT NULL,
    machines_total          INTEGER NOT NULL,
    machines_active         INTEGER NOT NULL,
    employees_present       INTEGER NOT NULL,
    machine_breakdown_count INTEGER DEFAULT 0,
    worker_shortage_count   INTEGER DEFAULT 0,
    total_output            INTEGER DEFAULT 0,      -- pcs produced plant-wide that day
    total_damage_qty        INTEGER DEFAULT 0,
    urgent_orders_handled   INTEGER DEFAULT 0,
    notes                   TEXT,
    submitted_by            INTEGER REFERENCES users(id),
    created_at              DATETIME DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(plant_id, log_date)
);
CREATE INDEX IF NOT EXISTS idx_pdl_plant_date ON plant_daily_logs(plant_id, log_date);

-- ── Plant Performance (Component 4 result per plant per month) ────────────
CREATE TABLE IF NOT EXISTS plant_performance (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    plant_id           TEXT    NOT NULL REFERENCES plants(id),
    month_year         TEXT    NOT NULL,            -- 'YYYY-MM'
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
"""
