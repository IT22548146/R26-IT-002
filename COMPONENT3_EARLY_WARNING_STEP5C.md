# Component 3 Step 5C — Experimental Early-Warning API Integration

## Outcome

Step 5C loads the three Step 5B research artifacts and adds an
`early_warning` section to the existing Component 3 prediction responses. It
does not replace current-day emergency detection or the deterministic recovery
planning engine.

The monitoring frontend displays the supported next-three-production-day
warnings, their model thresholds, and a preparation action:

- machine breakdown;
- quality-limit issue;
- output or schedule risk.

A future worker-shortage warning is not available. Current worker shortages
are still detected by the existing current-day model and handled by the
recovery engine.

## Leakage-safe inference boundary

Warnings are calculated only when the current day is stable. The 30-feature
row contains the current request plus, when available, saved earlier monitoring
records for the same bulk order. The backend enforces both:

```text
saved working_day_no < current working_day_no
saved production_date < current production_date
```

Saved current-day or future rows are never used. Future labels, future
production values, recommendations, and recovery outcomes are not model
features. The response includes `history.future_or_current_saved_rows_used = 0`
as auditable evidence of this boundary.

History readiness is reported as:

- `current_only`: no saved earlier day was available;
- `partial`: one saved earlier consecutive day was available;
- `complete`: current day plus two earlier consecutive days were available;
- `gapped`: at least one working-day transition was missing.

The model can return a score with incomplete history because its training data
contains the same `History_Days_Available` feature. Complete consecutive daily
records are nevertheless preferred.

## API behaviour

Start the backend from the repository root:

```bash
COMPONENT3_MODEL_VERSION=v2 python main.py
```

Use the existing endpoints:

```text
POST /api/component3/predict
POST /api/component3/monitoring-records
POST /api/component3/incidents
```

Their normal analysis now includes:

```json
{
  "early_warning": {
    "status": "available",
    "production_approved": false,
    "horizon_production_days": 3,
    "alert_generated": true,
    "highest_warning": {
      "display_name": "Machine breakdown",
      "probability_pct": 72.5
    },
    "warnings": [
      {
        "target": "Machine_Breakdown_Within_3_Days",
        "probability": 0.725,
        "probability_pct": 72.5,
        "decision_threshold": 0.5,
        "warning_predicted": true,
        "model_name": "Random Forest",
        "preparation": "Inspect critical machines..."
      }
    ],
    "history": {
      "status": "complete",
      "saved_prior_records": 2,
      "feature_history_days": 3,
      "future_or_current_saved_rows_used": 0
    }
  }
}
```

The exact score depends on the request and saved earlier records. If a current
emergency is already present, the status is
`not_applicable_current_emergency`, the future warning list is empty, and the
response directs the user to the recovery plan. If an artifact is missing or
invalid, the status is `unavailable`; current detection and recovery remain
available.

Model artifacts are cached after first use. Restart the Flask process after
retraining or replacing an artifact.

## Frontend

Start the frontend from `frontends/`:

```bash
npm run dev
```

Open `http://localhost:3000/dashboard/monitoring`. After **Analyze situation**,
the result panel shows an **Experimental early warning — Next 3 production
days** section. Save every real daily observation in order so later requests
can use a better same-order history window.

## Research and production boundary

The displayed values are uncalibrated research scores selected using only 11
historical orders. They are not guaranteed real-world probabilities and the
artifacts contain `production_approved = false`. A manager must review any
preparation or recovery action.

The next validation step is to collect and verify new, untouched real orders,
compare each saved warning with the actual next-three-production-day outcome,
measure calibration and subtype metrics, and choose production thresholds only
after that prospective evaluation.
