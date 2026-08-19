# Component 3 Step 5A.3 — Verified Training Dataset Export

## Purpose

This pipeline converts Component 3 daily monitoring records into an auditable,
leakage-safe dataset for the future Step 5B early-warning experiment. It does
not train a model and does not generate or relabel production observations.

## Export eligibility

A source record is exported only when:

1. its label status is `Ready`;
2. its actual outcome is supervisor-verified and stable;
3. the exact three future working-day outcomes used by the label are verified;
4. every earlier saved record for that order is verified, so trailing emergency
   features do not silently treat an unknown outcome as stable;
5. all feature and target values pass canonical feature calculation.

All other monitoring records remain in the database and are counted in the
audit exclusions. They are not silently converted to negative examples.

## Dataset schema

The export contains four non-feature metadata columns:

- `Record_ID` for traceability;
- `Bulk_Order_ID` for grouped train/test splitting;
- `Style_ID` for audit inspection;
- `Production_Date` for chronological inspection.

The 30 model features are the Step 5A current and trailing features from
`components/component3_early_warning_data.py`. Trailing values use only the
current and past records available for the same order.

The eight future targets include the one-day and three-day general outcomes,
first emergency type and lead time, and worker, machine, quality, and
output/schedule subtype flags.

Order/style identity, buyer/plant identity, model detections, recommendations,
verification names and notes, actual outcome fields, and all future targets are
excluded from the model-feature list. `Bulk_Order_ID` must be used only as the
grouping key in Step 5B.

## API

Inspect the current export before downloading:

```text
GET /api/component3/training-dataset-audit
```

Download the CSV training table:

```text
GET /api/component3/training-dataset?format=csv
```

Download an Excel workbook:

```text
GET /api/component3/training-dataset?format=xlsx
```

The Excel workbook contains:

- `training_data` — exported rows;
- `audit_summary` — flattened audit evidence;
- `column_manifest` — every column and its metadata, feature, or target role.

Downloads are blocked when there are no eligible rows or when leakage controls
fail. A partial, valid dataset can be downloaded for inspection before the
minimum research threshold is reached; the audit will still report
`training_ready = false`.

## Audit evidence

The audit response reports:

- total monitoring records, Ready candidates, exported rows, and orders;
- every exclusion reason;
- missing working-day transitions by order;
- the exact feature, target, metadata, and grouping columns;
- explicit identity/target overlap checks against the feature list;
- positive/negative rows and independent orders for every binary target;
- the primary three-day readiness decision;
- a SHA-256 checksum of the deterministic CSV content.

The primary target is research-ready only when leakage and working-day sequence
checks pass and both classes have at least 20 exported rows across at least
three independent orders per class.

## Command-line export

From the repository root:

```bash
python export_component3_training_dataset.py \
  --database instance/component3_tracking.db \
  --csv reports/component3_training_export/training_data.csv \
  --xlsx reports/component3_training_export/training_data.xlsx \
  --audit reports/component3_training_export/audit.json
```

The command prints the same audit JSON returned by the API. It refuses to write
CSV or Excel files when no verified Ready row is available.

## Frontend workflow

Open `/dashboard/monitoring-history`. The Step 5A.3 card shows exportable rows,
independent-order coverage, feature count, leakage status, and the current
decision. CSV and Excel download buttons appear when at least one valid row is
available.

## Step boundary

Passing the minimum threshold allows Step 5B grouped model evaluation to begin.
It is not a production-readiness claim. A final production claim still requires
substantially more independent orders and a locked, unseen-order test set.
