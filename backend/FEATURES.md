# Garment Production System — Features & Status

## What Was Built

### Project Structure (New Files)
```
garment_new/
├── database/
│   ├── __init__.py
│   ├── db.py              ← SQLite connection helper
│   ├── schema.py          ← All CREATE TABLE definitions
│   └── seed.py            ← One-time migration script
├── middleware/
│   ├── __init__.py
│   └── auth_middleware.py ← JWT auth + role decorators
├── routes/
│   ├── __init__.py
│   ├── auth.py            ← /auth/* endpoints
│   ├── admin.py           ← /admin/* endpoints
│   ├── buyer.py           ← /buyer/* endpoints
│   └── plant.py           ← /plant/* endpoints
├── services/
│   ├── __init__.py
│   ├── email_service.py   ← Gmail SMTP + 9 email templates
│   ├── notification_service.py ← In-portal notifications
│   └── capacity_service.py     ← Dynamic capacity management
├── app.py                 ← Updated — registers all 8 blueprints
├── .env                   ← Updated — all environment variables
└── GarmentProductionAPI.postman_collection.json
```

---

## Database Tables

| Table | Purpose | Seeded From |
|:---|:---|:---|
| `organizations` | Mother company + buyer companies | Hardcoded (FabricFlow + 4 known buyers) |
| `users` | Admin, Buyers, Plant Managers | Hardcoded (1 Admin + 6 Plant Managers pre-seeded) |
| `plants` | All 6 factories with static KPIs | Extracted from `component1.py`, `component2.py`, `component4.py` |
| `buyers_config` | Buyer shipment day lookup | Extracted from `BUYER_SHIPMENT_SCHEDULE` / `BUYER_DOW` in `component1.py` |
| `plant_capacity_history` | Full year capacity timeseries | **1,572 rows** from `capacity_full_year_2024.xlsx` + **1,566 rows** from `capacity_full_year_2026.xlsx` |
| `plant_monthly_capacity` | Live monthly capacity (decreases dynamically on assignment) | Auto-initialised on first query |
| `allocation_guide` | Priority × Complexity → Plant preference rules | Extracted from `ALLOCATION_GUIDE` dict in `component2.py` |
| `sample_orders` | Buyer sample order requests + C1 results | Created at runtime via API |
| `bulk_orders` | Buyer bulk order requests + C2 results | Created at runtime via API |
| `order_plant_allocations` | Which plant(s) handle each bulk order | Created at runtime via API |
| `daily_logs` | Daily production logs + C3/C4 results | Created at runtime via API |
| `notifications` | In-portal alerts for all roles | Created at runtime on key events |

---

## API Endpoints (Implemented & Working)

### Auth (`/auth`)
| Method | Endpoint | Access | Description |
|:---|:---|:---|:---|
| POST | `/auth/register` | Public | Buyer registers (Pending until Admin approves) |
| POST | `/auth/login` | Public | Returns JWT token (valid 24h) |
| GET | `/auth/me` | Any logged-in | Returns current user profile |

### Admin — User Management (`/admin`)
| Method | Endpoint | Description |
|:---|:---|:---|
| GET | `/admin/users/pending` | List all Pending buyer accounts |
| GET | `/admin/users` | List all users |
| POST | `/admin/users/<id>/approve` | Approve buyer → email sent to buyer |
| POST | `/admin/users/<id>/reject` | Reject buyer → email sent to buyer |

### Admin — Sample Orders
| Method | Endpoint | Description |
|:---|:---|:---|
| GET | `/admin/orders/sample` | View all sample orders with C1 results |
| POST | `/admin/orders/sample/<id>/assign` | Assign plant → deducts capacity → emails plant manager |

### Admin — Bulk Orders
| Method | Endpoint | Description |
|:---|:---|:---|
| GET | `/admin/orders/bulk` | View all bulk orders with C2 results |
| POST | `/admin/orders/bulk/<id>/assign` | Assign plant(s), supports split orders → emails plant(s) |
| GET | `/admin/orders/bulk/<id>/analysis` | Aggregates daily logs → runs **Component 4** → returns ★ score + recommendations |
| POST | `/admin/orders/bulk/<id>/confirm-shipment` | Mark shipped → emails buyer |

### Admin — Capacity & Plants
| Method | Endpoint | Description |
|:---|:---|:---|
| GET | `/admin/capacity?month=YYYY-MM` | Live capacity across all plants for a month |
| GET | `/admin/plants` | All plants with static KPIs |
| GET | `/admin/plants/<id>/logs` | Daily logs for any plant |

### Buyer (`/buyer`)
| Method | Endpoint | Description |
|:---|:---|:---|
| POST | `/buyer/orders/sample` | Submit sample order → auto-runs **Component 1** → saves full result |
| GET | `/buyer/orders/sample` | My sample orders |
| GET | `/buyer/orders/sample/<id>` | Order detail with C1 result |
| POST | `/buyer/orders/bulk` | Submit bulk order → reads capacity from DB → auto-runs **Component 2** |
| GET | `/buyer/orders/bulk` | My bulk orders |
| GET | `/buyer/orders/bulk/<id>` | Order detail with C2 result + allocations |
| GET | `/buyer/notifications` | In-portal notification inbox |
| POST | `/buyer/notifications/<id>/read` | Mark notification as read |

### Plant Manager (`/plant`)
| Method | Endpoint | Description |
|:---|:---|:---|
| GET | `/plant/orders` | Orders assigned to my plant |
| GET | `/plant/orders/<id>` | Order detail |
| POST | `/plant/orders/<id>/log` | Submit daily log → auto-runs **Component 3** → triggers critical alert if severity=Critical |
| GET | `/plant/orders/<id>/logs` | All daily logs for an order |
| POST | `/plant/orders/<id>/ready` | Mark order Ready → **emails Buyer AND Admin** |
| GET | `/plant/notifications` | In-portal notification inbox |
| POST | `/plant/notifications/<id>/read` | Mark notification as read |

### ML APIs (Direct — unchanged)
| Method | Endpoint | Description |
|:---|:---|:---|
| POST | `/api/component1/predict` | Sample Planning |
| POST | `/api/component2/predict` | Bulk Order Planning |
| POST | `/api/component3/predict` | Emergency Detection |
| POST | `/api/component4/predict` | Production Analysis |

---

## Email Notifications (All 9 Triggers)

| Trigger | Sent To |
|:---|:---|
| New buyer registers | Admin |
| Admin approves buyer | Buyer |
| Admin rejects buyer | Buyer |
| New sample order submitted | Admin |
| Sample order assigned to plant | Plant Manager |
| New bulk order submitted | Admin |
| Bulk order assigned to plant | Plant Manager |
| C3 detects Critical risk | Admin + Plant Manager |
| Plant marks order Ready | **Buyer + Admin** |
| Admin confirms shipment | Buyer |

---

## How the Dynamic Capacity Works

When a sample or bulk order is assigned to a plant:
1. `capacity_service.deduct_capacity(plant_id, month_year, qty)` runs
2. `plant_monthly_capacity.used_capacity` increases by the order quantity
3. The next buyer who submits an order gets **updated model outputs** because C2 reads the new available capacity from the DB
4. Plants at high utilisation will score lower in plant rankings and may flip from "Single Plant" to "Split" allocation

---

## Remaining Work (Not Yet Done)

### ML Component Refactoring
The portal endpoints already feed DB-sourced data into the components, but the hardcoded dicts inside the component files themselves are not yet removed.

| File | Remaining Task |
|:---|:---|
| `components/component1.py` | Replace `_load_capacity()` Excel load with DB query; replace `BUYER_DOW` dict with DB query |
| `components/component2.py` | Remove `QUALITY_MAP`, `ALLOCATION_GUIDE` dicts — read from DB instead |
| `components/component4.py` | Remove `PLANT_KPI` dict — read from `plants` table instead |

> These are internal cleanups only. The API already works correctly because the portal routes inject DB values.

### Future Enhancements (Not Planned Yet)
- [ ] Next.js frontend portal (Admin, Buyer, Plant dashboards)
- [ ] JWT refresh token mechanism
- [ ] Password reset via email
- [ ] Pagination for list endpoints
- [ ] Webhook/push notifications (currently polling-based)
- [ ] Production WSGI deployment (Gunicorn + Nginx)
- [ ] Rate limiting on Auth endpoints

---

## Pre-Seeded Accounts

| Role | Email | Password |
|:---|:---|:---|
| Admin | admin@fabricflow.com | Admin@FabricFlow2024 |
| Plant Manager (PL01) | manager.pl01@dinusha.com | Plant@Manager2024 |
| Plant Manager (PL02) | manager.pl02@mrc.com | Plant@Manager2024 |
| Plant Manager (PL03) | manager.pl03@bobbin.com | Plant@Manager2024 |
| Plant Manager (PL04) | manager.pl04@sunrose.com | Plant@Manager2024 |
| Plant Manager (PL05) | manager.pl05@regal.com | Plant@Manager2024 |
| Plant Manager (PL06) | manager.pl06@amsral.com | Plant@Manager2024 |

> Buyers must register via `/auth/register` and be approved by Admin before they can log in.

---

## Known Bugs Fixed
- `SyntaxError` in `component1.py` line 555 — nested f-string quotes fixed
- `TypeError: 'datetime.date' object is not subscriptable` in `routes/admin.py` + `routes/buyer.py` — date fields from SQLite now wrapped with `str()` before slicing
