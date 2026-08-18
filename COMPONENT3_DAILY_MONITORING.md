# Component 3 Daily Monitoring Data Collection

## Purpose

The early-warning readiness audit showed that the original dataset has no
three-day negative examples among eligible stable days. This data-collection
layer stores both stable and emergency daily observations so future labels can
be calculated from real order sequences.

Daily monitoring records use the same SQLite database as recovery incidents:

```text
instance/component3_tracking.db
```

Override the path with `COMPONENT3_TRACKING_DB` when required. The database is
local application state and is excluded from Git.

## Save a daily record

```text
POST /api/component3/monitoring-records
```

Send the same validated body used by `POST /api/component3/predict`, plus:

```json
{
  "recorded_by": "Line Supervisor"
}
```

The API reruns the configured Component 3 models and recovery engine on the
server. It saves the canonical input and analysis rather than trusting a
prediction supplied by the browser.

Only one record is allowed for the same bulk order and production date or the
same bulk order and working-day number. The store also rejects inconsistent
style, quantity, deadline, date order, or decreasing cumulative production
within an order sequence.

## Automatic future labels

For a stable saved day `d`, the store waits for exact records `d+1`, `d+2`, and
`d+3`. When all three exist, the record becomes `Ready` and receives:

- `emergency_within_1_day`
- `emergency_within_3_days`
- `first_emergency_type_within_3_days`
- `first_emergency_lead_days`
- `worker_shortage_within_3_days`
- `machine_breakdown_within_3_days`
- `quality_limit_within_3_days`
- `output_schedule_risk_within_3_days`

The labels are recalculated whenever another day is added to that order. No
future outcome is entered manually and no new production row is generated.

Label statuses are:

| Status | Meaning |
| --- | --- |
| `Waiting` | A stable source day is waiting for three future records. |
| `Ready` | All three exact future days exist and labels are calculated. |
| `Not Eligible` | An emergency already exists on the source day. |
| `Censored` | The order completed before a full future window became available. |
| `Incomplete` | The future window passed but one or more daily records are missing. |

`Not Eligible`, `Censored`, `Incomplete`, and `Waiting` records are never
silently treated as negative training examples.

## Query history

```text
GET /api/component3/monitoring-records
GET /api/component3/monitoring-records?bulk_order_id=BULK0001
GET /api/component3/monitoring-records?risk_status=No%20Risk
GET /api/component3/monitoring-records?label_status=Ready
GET /api/component3/orders/BULK0001/monitoring-records
GET /api/component3/monitoring-records/{record_id}
```

The list supports `limit` from 1 to 100 and a non-negative `offset`.

## Live readiness

```text
GET /api/component3/monitoring-readiness
```

The response reports total, stable and emergency records; label-status counts;
three-day positive and negative examples; independent-order coverage; and the
current grouped-training readiness decision.

The minimum research threshold is 20 ready examples and three independent
orders in each class. Passing this threshold allows Step 5B evaluation to
begin; it is not by itself a production-readiness claim.

## Frontend workflow

1. Open `/dashboard/monitoring` and run the daily analysis.
2. Use **Save daily record** for both stable and emergency results.
3. If the result is an emergency, separately use **Save & track incident** for
   recovery approval and outcome tracking.
4. Open `/dashboard/monitoring-history` to review saved sequences, label status,
   future outcomes, filters, and live readiness.

## Production boundary

SQLite is suitable for the current local research application and a single
backend process. A multi-instance deployment should use PostgreSQL and replace
the client-supplied `recorded_by` label with an authenticated user identity.
