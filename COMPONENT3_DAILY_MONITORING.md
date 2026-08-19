# Component 3 Daily Monitoring Data Collection

## Purpose

The early-warning readiness audit showed that the original dataset has no
three-day negative examples among eligible stable days. This data-collection
layer stores both stable and emergency daily observations. A supervisor then
confirms the actual outcome so future labels can be calculated from verified
real order sequences rather than the model's own predictions.

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

A newly saved row has `actual_outcome_status = Pending` and cannot contribute
to model-training readiness until it is verified.

Only one record is allowed for the same bulk order and production date or the
same bulk order and working-day number. The store also rejects inconsistent
style, quantity, deadline, date order, or decreasing cumulative production
within an order sequence.

## Verify the actual outcome

```text
PUT /api/component3/monitoring-records/{record_id}/verification
```

Verify a stable day with:

```json
{
  "actual_emergency": false,
  "verified_by": "Shift Supervisor",
  "verification_notes": "No production disruption was recorded"
}
```

Verify an emergency day with:

```json
{
  "actual_emergency": true,
  "actual_emergency_type": "Machine Breakdown",
  "verified_by": "Factory Manager",
  "verification_notes": "Maintenance log confirmed the failure"
}
```

Accepted actual emergency types are `Worker Shortage`, `Machine Breakdown`,
`Quality Issue`, `Output / Schedule Risk`, and `Other Emergency`.

The server supplies `verified_at`. Submitting another verification corrects
the current outcome without deleting the earlier decision: every verification
is retained in `verification_history` on the record-detail response.

## Automatic future labels

For a verified-stable saved day `d`, the store waits for exact records `d+1`,
`d+2`, and `d+3`. The source day and all three future days must have verified
actual outcomes. The source then becomes `Ready` and receives:

- `emergency_within_1_day`
- `emergency_within_3_days`
- `first_emergency_type_within_3_days`
- `first_emergency_lead_days`
- `worker_shortage_within_3_days`
- `machine_breakdown_within_3_days`
- `quality_limit_within_3_days`
- `output_schedule_risk_within_3_days`

The labels are recalculated whenever another day is added or an outcome is
verified or corrected. The prediction's risk result is retained for model
comparison, but it is never used as training ground truth.

Label statuses are:

| Status | Meaning |
| --- | --- |
| `Awaiting Verification` | The source or one of its exact future days has no supervisor-confirmed actual outcome. |
| `Waiting` | A stable source day is waiting for three future records. |
| `Ready` | All three exact future days exist and labels are calculated. |
| `Not Eligible` | A verified actual emergency exists on the source day. |
| `Censored` | The order completed before a full future window became available. |
| `Incomplete` | The future window passed but one or more daily records are missing. |

`Awaiting Verification`, `Not Eligible`, `Censored`, `Incomplete`, and
`Waiting` records are never silently treated as negative training examples.

## Query history

```text
GET /api/component3/monitoring-records
GET /api/component3/monitoring-records?bulk_order_id=BULK0001
GET /api/component3/monitoring-records?risk_status=No%20Risk
GET /api/component3/monitoring-records?label_status=Ready
GET /api/component3/monitoring-records?verification_status=Pending
GET /api/component3/orders/BULK0001/monitoring-records
GET /api/component3/monitoring-records/{record_id}
```

The list supports `limit` from 1 to 100 and a non-negative `offset`.

## Live readiness

```text
GET /api/component3/monitoring-readiness
```

The response reports pending and verified records; verified stable and
emergency outcomes; model-detected outcomes for comparison; label-status
counts; three-day positive and negative examples; independent-order coverage;
and the current grouped-training readiness decision.

The minimum research threshold is 20 ready examples and three independent
orders in each class. Passing this threshold allows Step 5B evaluation to
begin; it is not by itself a production-readiness claim.

## Frontend workflow

1. Open `/dashboard/monitoring` and run the daily analysis.
2. Use **Save daily record** for both stable and emergency results.
3. If the result is an emergency, separately use **Save & track incident** for
   recovery approval and outcome tracking.
4. Open `/dashboard/monitoring-history` and use **Verify** to confirm what
   actually occurred using factory evidence.
5. Review saved sequences, verification status, future labels, filters, and
   live readiness. Use **Correct** if a supervisor-approved outcome changes;
   the audit history remains available.

## Production boundary

SQLite is suitable for the current local research application and a single
backend process. A multi-instance deployment should use PostgreSQL and replace
the client-supplied `recorded_by` and `verified_by` labels with authenticated,
role-authorized user identities.
