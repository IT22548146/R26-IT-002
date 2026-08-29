# Garment Production Management System — API Backend

A Flask-based REST API providing AI-driven decision support for garment production. The system integrates four ML models (XGBoost, Random Forest, Gradient Boosting) with a full stateful portal featuring buyer ordering, admin management, plant monitoring, real-time capacity tracking, and automated email notifications.

---

## Core ML Components

| Component | Endpoint | Purpose |
|:---|:---|:---|
| **Sample Planning** | `/api/component1/predict` | Overrun prediction, plant selection, feasibility scoring |
| **Bulk Order Planning** | `/api/component2/predict` | Production days, allocation strategy (Single vs Split plants) |
| **Emergency Detection** | `/api/component3/predict` | Daily risk monitoring — machine, worker, quality issues |
| **Production Analysis** | `/api/component4/predict` | ★ Star rating + AI recommendations per plant |

---

## User Roles

| Role | What they can do |
|:---|:---|
| **Admin** | Approve buyers, review ML results, assign orders to plants, run C4 analysis, confirm shipments |
| **Buyer** | Register, submit sample & bulk orders, track status, receive email alerts |
| **Plant Manager** | View assigned orders, submit daily logs (C3 runs automatically), mark orders as Ready |

---

## Prerequisites

- **Python 3.11**
- **Windows / Linux / macOS**

---

## Setup & Installation

### 1. Create Virtual Environment
```powershell
py -3.11 -m venv .venv
```

### 2. Activate Virtual Environment
```powershell
# Windows (PowerShell)
.\.venv\Scripts\Activate.ps1
```
> If you get a "Script execution is disabled" error, run:
> `Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope Process`

### 3. Install Dependencies
```powershell
.venv\Scripts\python.exe -m pip install -r requirements.txt
```

---

## Environment Configuration

Edit `.env` before running for the first time:

```env
# ── Application ───────────────────────────
SECRET_KEY=your-secret-jwt-key-change-this
FLASK_ENV=development

# ── Database ──────────────────────────────
DATABASE_PATH=garment.db

# ── Mother Company ────────────────────────
MOTHER_COMPANY_NAME=FabricFlow International
ADMIN_EMAIL=admin@fabricflow.com
ADMIN_DEFAULT_PASSWORD=Admin@FabricFlow2024

# ── Gmail SMTP ────────────────────────────
# Get App Password: myaccount.google.com → Security → App passwords
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=your_gmail@gmail.com
SMTP_PASSWORD=your_16_char_app_password
EMAIL_FROM_NAME=FabricFlow International

# ── JWT ───────────────────────────────────
JWT_EXPIRY_HOURS=24

# ── Capacity Defaults ─────────────────────
DEFAULT_MONTHLY_CAPACITY=150
DEFAULT_SHIPMENT_DAYS=18
```

---

## Database Setup (Run Once)

After installing dependencies, run the seed script to:
- Create all database tables
- Migrate all plant data (from hardcoded constants in component files)
- Migrate buyer shipment schedules
- Import **1,572 rows** from `capacity_full_year_2024.xlsx`
- Import **1,566 rows** from `capacity_full_year_2026.xlsx`
- Create the Admin account and 6 pre-seeded Plant Manager accounts

```powershell
.venv\Scripts\python.exe -m database.seed
```

Expected output:
```
[seed] Organizations ...
[seed] Plants ...
[seed] Buyers config ...
[seed] Allocation guide ...
[seed] Admin user ...
[seed] Plant manager accounts ...
[seed] Importing capacity_full_year_2024.xlsx ...
  >> 1572 rows imported from 2024
[seed] Importing capacity_full_year_2026.xlsx ...
  >> 1566 rows imported from 2026

[seed] DONE.
  Admin login : admin@fabricflow.com  /  Admin@FabricFlow2024
  Plant mgrs  : manager.pl01@dinusha.com ... (password: Plant@Manager2024)
  Database    : garment.db
```

> **WARNING:** Only run the seed script once. Running it again is safe (uses INSERT OR IGNORE) but will not re-import existing data.

---

## Running the Application

```powershell
.venv\Scripts\python.exe app.py
```

- **Server URL:** `http://localhost:5000`
- **Health Check:** `GET http://localhost:5000/health`
- **API Index:** `GET http://localhost:5000/`

---

## Pre-Seeded Accounts

| Role | Email | Password |
|:---|:---|:---|
| Admin | admin@fabricflow.com | Admin@FabricFlow2024 |
| Plant Manager (PL01 — Dinusha) | manager.pl01@dinusha.com | Plant@Manager2024 |
| Plant Manager (PL02 — MRC) | manager.pl02@mrc.com | Plant@Manager2024 |
| Plant Manager (PL03 — Bobbin) | manager.pl03@bobbin.com | Plant@Manager2024 |
| Plant Manager (PL04 — Sunrose) | manager.pl04@sunrose.com | Plant@Manager2024 |
| Plant Manager (PL05 — Regal) | manager.pl05@regal.com | Plant@Manager2024 |
| Plant Manager (PL06 — Amsral) | manager.pl06@amsral.com | Plant@Manager2024 |

> Buyers must register via `POST /auth/register` and be approved by Admin before logging in.

---

## Testing with Postman

Import `GarmentProductionAPI.postman_collection.json` into Postman.

**Full order lifecycle (run in this order):**
1. `Auth → Login Admin` — token auto-saved
2. `Auth → Register (Buyer Company)` — creates Pending account
3. `Admin → Approve Buyer Account`
4. `Auth → Login Buyer` — token auto-saved
5. `Buyer → Submit Sample Order` — runs C1, `sample_order_id` auto-saved
6. `Admin → Assign Sample Order to Plant` — deducts capacity, emails plant
7. `Auth → Login Plant Manager`
8. `Buyer → Submit Bulk Order` — runs C2 with live DB capacity, `bulk_order_id` auto-saved
9. `Admin → Assign Bulk Order` — single or split plant
10. `Plant → Submit Daily Log` — runs C3, critical alerts if needed
11. `Plant → Mark Order as READY` — emails Buyer + Admin
12. `Admin → Run C4 Analysis` — aggregates all logs, returns ★ rating
13. `Admin → Confirm Shipment` — emails buyer, order → Shipped

---

## Project Structure

```
garment_new/
├── app.py                          ← Flask app factory (8 blueprints)
├── .env                            ← Environment variables
├── components/                     ← ML prediction engines (unchanged)
│   ├── component1.py               ← Sample Planning
│   ├── component2.py               ← Bulk Order Planning
│   ├── component3.py               ← Emergency Detection
│   └── component4.py               ← Production Analysis
├── database/                       ← Database layer
│   ├── db.py                       ← Connection helper
│   ├── schema.py                   ← All CREATE TABLE SQL
│   └── seed.py                     ← One-time migration script
├── middleware/
│   └── auth_middleware.py          ← JWT + require_role() decorator
├── routes/
│   ├── auth.py                     ← /auth/*
│   ├── admin.py                    ← /admin/*
│   ├── buyer.py                    ← /buyer/*
│   └── plant.py                    ← /plant/*
├── services/
│   ├── email_service.py            ← Gmail SMTP + 9 email templates
│   ├── notification_service.py     ← In-portal notifications
│   └── capacity_service.py         ← Dynamic capacity deduction
├── models/                         ← ML .pkl files (unchanged)
│   ├── m3_delay_classifier.pkl
│   ├── c2_model_cutting.pkl
│   └── ... (17 model files)
├── FEATURES.md                     ← Full feature docs + remaining work
└── GarmentProductionAPI.postman_collection.json
```

---

## Full Feature Documentation

See [FEATURES.md](./FEATURES.md) for:
- All implemented endpoints in detail
- Email notification trigger map
- How dynamic capacity works
- Remaining refactoring tasks
- Known bugs fixed
