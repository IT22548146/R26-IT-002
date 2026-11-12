# Component 3 Operations and Retraining Runbook

This runbook covers the active Component 3 runtime only: current-day risk
detection, experimental three-production-day warnings, daily monitoring,
recovery history, and the C2/C4 integration records.

## Runtime ownership

| Concern | Source of truth |
|---|---|
| Active artifact contract | `models/component3_model_manifest.json` |
| Current-risk and order-risk inference | `components/component3.py` |
| Early-warning inference | `components/component3_early_warning_inference.py` |
| Feature contracts | `components/component3_features.py`, `components/component3_order_risk_features.py`, `components/component3_early_warning_data.py` |
| C3 monitoring and recovery database | `instance/component3_tracking.db` by default |
| Integrated operational logs consumed by C4 | `garment.db` → `daily_logs` |
| Plant-facing pages | `frontends/src/app/(dashboard)/component3/` |

The tracking database path can be changed with `COMPONENT3_TRACKING_DB`. The
operational database path can be changed with `DATABASE_PATH`.

## Pre-deployment checks

Run these commands from the repository root with the Python environment
activated:

```bash
python -m scripts.component3.verify_component3_models
python -m pytest -q tests/test_component3*.py
cd frontends
npm ci
npm run lint
npm exec tsc -- --noEmit
```

The model check must report `status: verified` and five verified artifacts.
Do not start a deployment if a checksum, filename, manifest, or feature
contract check fails.

## Starting the integrated application

Backend:

```bash
cd "/path/to/Garment_model_backend_latest"
source .venv/bin/activate
python main.py
```

Frontend in a second terminal:

```bash
cd "/path/to/Garment_model_backend_latest/frontends"
npm ci
npm run dev
```

The backend uses port `5001`; the frontend uses port `3000`. Keep
`NEXT_PUBLIC_COMPONENT3_API_URL` aligned with
`http://127.0.0.1:5001/api/component3` unless the API is deployed elsewhere.

## Backup procedure

Create a consistent online backup while SQLite is in use:

```bash
python -m scripts.component3.backup_component3_database
```

Specify paths when needed:

```bash
python -m scripts.component3.backup_component3_database \
  --database instance/component3_tracking.db \
  --output backups/component3/component3_tracking_before_release.db
```

The command never overwrites an existing backup. It uses SQLite's online
backup API, runs `PRAGMA integrity_check`, and prints the backup SHA-256.
Retain that JSON output with the release evidence.

## Cross-database reconciliation

The integrated plant workflow stores the canonical C3 record in the tracking
database and a copy of its analysis in `garment.db.daily_logs` for C4. Audit
their common live records with:

```bash
python -m scripts.component3.audit_component3_persistence \
  --tracking-database instance/component3_tracking.db \
  --operational-database garment.db \
  --output reports/component3_persistence_audit.json
```

Exit codes are:

- `0`: consistent;
- `1`: the audit could not read or validate a database; and
- `2`: one or more missing or mismatched records were found.

The audit is read-only. It compares order, plant, production date, daily
quantities, model version, prediction-contract version, and risk type. Resolve
an inconsistency from the original signed production record; do not guess or
silently overwrite either database.

## Monitoring-data export

Plant Managers can download the currently filtered, plant-scoped monitoring
history from **Daily Monitoring History → Download CSV**. The API endpoint is:

```text
GET /api/component3/monitoring-records/export
```

The same risk, verification, label, and bulk-order filters used by the page
can be supplied as query parameters. JWT plant scope is applied server-side;
a Plant Manager cannot export another plant's records. Spreadsheet formula
prefixes in text values are neutralized in the CSV.

## Retraining and artifact promotion

1. Export only verified, leakage-checked data. Keep retrospective training
   reuse separate from independent validation.
2. Train candidates with the documented order-grouped evaluation scripts.
3. Compare candidates using Accuracy, Macro-F1, target-class F1, class/order
   coverage, and calibration evidence. Do not promote a model on Accuracy
   alone.
4. Keep the existing active artifacts unchanged while candidates are being
   reviewed. Give every candidate a new versioned filename.
5. Record the selected parameters, dataset hash, grouped folds, metrics,
   limitations, and approval decision in `reports/`.
6. Copy only approved artifacts into `models/` and update
   `component3_model_manifest.json` with their role, exact filename, and
   SHA-256.
7. Update the runtime and feature-schema versions when the input or output
   contract changes.
8. Run the pre-deployment checks and an end-to-end C2 → C3 → C4 test before
   merging or deploying.

Active artifacts must not be overwritten in place without updating the
manifest. A checksum mismatch intentionally makes inference unavailable.

## Rollback procedure

1. Stop new monitoring submissions.
2. Preserve the current tracking database with the backup command.
3. Deploy the previous reviewed code revision together with its matching
   manifest and artifacts; do not mix model files from two revisions.
4. Run the model-verification command.
5. Start the backend and check `/api/component3/health`.
6. Run the persistence reconciliation before reopening submissions.

Restore a database backup only after separately preserving the current file
and confirming the backup's integrity and SHA-256. Database restoration is a
controlled operator action and is intentionally not automated by this
repository.

## Security and audit expectations

- `/api/component3/predict` requires an Admin, Manager, or Plant Manager JWT.
- Dataset audit/import/export research endpoints require Admin or Manager.
- Operational monitoring and incident endpoints apply authenticated plant
  scope for Plant Managers.
- Prediction responses and saved analyses contain a `request_id`, model
  version, prediction-contract version, and feature-schema versions.
- Internal exceptions are written to server logs; client responses use the
  request ID instead of exposing filesystem paths or stack details.
- Never commit `.env`, credentials, live databases, or backup databases.

## Current limitations

- Early-warning subtype models remain research-only and explicitly report
  `production_approved: false`.
- Worker-shortage early warning is not available in the active subtype set.
- Public holidays are not removed from Monday-to-Friday working-day counts.
- Model quality depends on accurate daily output, damage, machine, worker, and
  verified-outcome entries.
- Evidence is based on the available plants and order groups; broader unseen
  factory validation is required before production approval.
- SQLite supports the current research deployment, but a multi-instance hosted
  deployment should move operational persistence to a managed transactional
  database and retain the same plant-scope and audit contracts.
