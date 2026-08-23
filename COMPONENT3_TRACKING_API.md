# Component 3 Recovery Tracking API

## Purpose

This API stores the full emergency-recovery lifecycle:

1. detect the incident and calculate a recovery plan;
2. select and approve one calculated option;
3. start the recovery action;
4. record actual daily production;
5. calculate action effectiveness;
6. complete the incident while retaining an audit timeline.

The default local database is:

```text
instance/component3_tracking.db
```

Override it when required:

```bash
COMPONENT3_TRACKING_DB=/absolute/path/component3_tracking.db \
COMPONENT3_MODEL_VERSION=v2 \
python3 main.py
```

The database file and `instance/` directory are excluded from Git.

## Workflow

```text
Pending --approve decision--> Approved --start--> In Progress
   In Progress --record one or more outcomes--> In Progress
   In Progress --complete--> Completed
```

A Pending incident cannot skip the decision step. At least one actual outcome
must be stored before an incident can be completed.

## Endpoints

### Create and save an incident

```text
POST /api/component3/incidents
```

Send the same production and recovery fields used by
`POST /api/component3/predict`, plus the responsible user:

```json
{
  "bulk_order_id": "BULK0001",
  "style_id": "AH2495",
  "buyer_name": "Hirdaramani",
  "allocated_bulk_plant": "Sunrose Lanka (Pvt) Ltd",
  "plant_location": "Katubedda",
  "full_order_qty": 46430,
  "bulk_order_approved_date": "2024-06-29",
  "buyer_required_date": "2024-11-27",
  "total_working_days": 108,
  "cutting_days": 25,
  "sewing_days": 30,
  "daily_commitment": 430,
  "production_date": "2024-07-02",
  "working_day_no": 2,
  "plant_daily_output": 407,
  "daily_damage_qty": 10,
  "max_daily_damage_qty": 13,
  "machine_breakdown_count": 0,
  "worker_shortage_count": 3,
  "cumulative_completed_qty": 845,
  "recovery_parameters": {
    "planned_worker_count": 50,
    "max_additional_workers": 3
  },
  "created_by": "Production Manager"
}
```

The API reruns the canonical model and recovery-engine calculation before it
saves the record. It does not trust a prediction result supplied by the
browser. The response status is `201 Created` and contains the incident ID,
full analysis, workflow status and initial timeline event.

Only one incident is stored for the same bulk order and production date. A
duplicate save returns `409 Conflict` instead of creating a second daily record.

### List incidents

```text
GET /api/component3/incidents
GET /api/component3/incidents?bulk_order_id=BULK0001
GET /api/component3/incidents?status=In%20Progress&limit=50&offset=0
```

Valid statuses are `Pending`, `Approved`, `In Progress`, and `Completed`.
`limit` must be between 1 and 100.

### Get one incident

```text
GET /api/component3/incidents/{incident_id}
```

The result contains:

- original validated prediction input;
- full risk and recovery analysis;
- selected recovery option;
- daily outcomes and effectiveness;
- complete audit timeline.

### Get an order's recovery history

```text
GET /api/component3/orders/{bulk_order_id}/incidents
```

### Approve a recovery decision

```text
POST /api/component3/incidents/{incident_id}/decision
```

```json
{
  "selected_option_id": "add_workers",
  "approved_by": "Factory Manager",
  "notes": "Three operators approved for reassignment."
}
```

Only an option returned by the saved recovery analysis can be selected. A
successful decision changes the workflow from `Pending` to `Approved`.

### Start or complete the action

```text
PATCH /api/component3/incidents/{incident_id}/status
```

Start:

```json
{
  "status": "In Progress",
  "updated_by": "Line Supervisor",
  "notes": "Operators assigned at shift start."
}
```

Complete after recording an outcome:

```json
{
  "status": "Completed",
  "updated_by": "Factory Manager",
  "notes": "Production recovered and action closed."
}
```

### Record actual production outcome

```text
POST /api/component3/incidents/{incident_id}/outcomes
```

```json
{
  "outcome_date": "2024-07-03",
  "actual_daily_output": 425,
  "cumulative_completed_qty": 1270,
  "recorded_by": "Line Supervisor",
  "notes": "Three operators were reassigned."
}
```

The response includes:

```json
{
  "target_daily_output": 432.8,
  "actual_daily_output": 425,
  "output_variance": -7.8,
  "effectiveness_pct": 98.2,
  "recovery_gap_closed_pct": 78.09
}
```

Formulas:

```text
effectiveness % = actual daily output / selected-plan daily capacity * 100

recovery gap closed % =
  (actual output - original current capacity) /
  (required daily rate - original current capacity) * 100
```

Only one outcome per incident and date is accepted, which prevents accidental
duplicate daily records.

### Resume a saved order's daily monitoring

```text
GET /api/component3/orders/{bulk_order_id}/next-entry-context
```

For a new order, the response suggests working day 1. For an order with daily
monitoring history, it returns the next Monday-Friday date, next working-day
number, and `saved_order_setup`. That setup contains stable order fields and
recovery-capacity parameters from the latest saved Component 3 monitoring
record. It does not read Component 2 master data. Current-day output, damage,
breakdown, shortage, and cumulative values are intentionally excluded so the
client cannot silently reuse yesterday's observations.

## Current persistence boundary

SQLite is appropriate for local research execution and one backend process. A
production deployment with multiple API instances should move the same schema
to PostgreSQL and add authenticated user identities and role-based approval.
The current `approved_by`, `updated_by`, and `recorded_by` values are auditable
labels supplied by the client; authentication is a later production phase.
