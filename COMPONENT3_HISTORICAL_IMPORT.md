# Component 3 Retrospective Historical Import

## Purpose

The importer replays one order from the original Component 3 daily workbook
through the live monitoring API flow. It creates each prediction in production
day order and only attaches the recorded historical outcome afterward when the
user explicitly enables automatic verification.

This is useful for demonstrating monitoring, early-warning history, actual
outcome verification, future-label creation, and repeatable API behaviour
without manually typing every daily row.

## Evidence boundary

The bundled Component 3 workbook contains 598 original daily rows across 11
bulk orders. It is the same workbook used to train and compare the current
research artifacts. Therefore:

- every import is marked `mode = retrospective_demo`;
- every response has `independent_validation = false`;
- every stored row has `data_origin = historical_training_reuse` and
  `independent_validation_eligible = false`;
- retrospective rows are excluded from independent readiness totals and the
  verified training export;
- imported results must not be reported as new prospective or independent
  model-validation evidence;
- the current artifacts remain `production_approved = false`.

Component 3 is authoritative for daily monitoring values. The Component 2
workbook is used only to audit matching bulk-order master fields. Its values do
not overwrite Component 3 fields because cutting days, sewing days, and daily
commitment conflict for several shared orders.

## Preview

Start the Flask API and request:

```text
GET /api/component3/historical-import/preview
```

The read-only response contains source hashes, source row/order counts, existing
database coverage, importable rows, order date ranges, recorded emergency-day
counts, and Component 2 field conflicts. Preview never inserts or verifies a
record.

The default sources are:

```text
component3_final_preprossed dataset.xlsx
component2_bulk_order_aligned_to.xlsx
```

They can be overridden with Flask configuration or environment variables:

```text
COMPONENT3_HISTORICAL_IMPORT_SOURCE
COMPONENT3_COMPONENT2_MASTER_SOURCE
```

## Import one order

```text
POST /api/component3/historical-import
Content-Type: application/json
```

Pending-verification import:

```json
{
  "bulk_order_id": "BULK0007",
  "imported_by": "Researcher name or ID",
  "confirm_retrospective_training_data_reuse": true,
  "verify_historical_outcomes": false
}
```

Import and attach reviewed historical outcomes:

```json
{
  "bulk_order_id": "BULK0007",
  "imported_by": "Researcher name or ID",
  "confirm_retrospective_training_data_reuse": true,
  "verify_historical_outcomes": true,
  "confirm_historical_outcomes_are_actual": true,
  "verified_by": "Historical log reviewer"
}
```

Automatic verification maps the recorded source event into the supported
actual-outcome types: Worker Shortage, Machine Breakdown, Quality Issue, Output
/ Schedule Risk, or Other Emergency. The source outcome is not passed into the
prediction function. Every stored analysis records
`outcome_used_during_prediction = false`.

## Duplicate and conflict rules

- Matching existing order/day records are skipped.
- Repeating the same import does not create duplicates.
- Conflicting existing records are never overwritten.
- A matching pending record is automatically verified on a later import only
  when it was originally created by this historical importer.
- Processing errors and conflicts are returned per production day.

## Frontend workflow

Open:

```text
http://localhost:3000/dashboard/monitoring-history
```

In **Retrospective data loader**:

1. select one bulk order;
2. enter the researcher name or ID;
3. confirm that the source trained the current models;
4. optionally enable automatic historical verification and provide the
   reviewer confirmation;
5. select **Import selected order**;
6. review imported records and derived three-day labels below the importer.

For actual Step 5D independent validation, collect a different daily workbook
containing orders that were never used during training or model selection.

After an order is imported and verified, review its separated retrospective
scores through `GET /api/component3/early-warning-validation` or the Step 5D.1
card on Daily Monitoring History. See
[`COMPONENT3_EARLY_WARNING_STEP5D1.md`](COMPONENT3_EARLY_WARNING_STEP5D1.md).
