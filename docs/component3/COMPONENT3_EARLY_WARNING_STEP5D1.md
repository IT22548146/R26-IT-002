# Component 3 Step 5D.1 — Early-Warning Outcome Validation

## Purpose

Step 5D.1 compares each early-warning decision saved before outcome
verification with the later supervisor-verified three-production-day outcome.
It reports only Accuracy, Macro-F1, and positive-class F1 for the three Step 5C
targets:

- machine breakdown within three production days;
- quality-limit issue within three production days;
- output or schedule risk within three production days.

The evaluator reads the stored warning snapshot. It does not reload or rerun a
model against historical rows, so a changed model cannot silently replace the
decision that was actually shown at prediction time.

## Evidence separation

The report always returns two separate scopes:

1. `independent_validation` contains new real orders that were not used for
   training or model selection.
2. `retrospective_training_reuse` contains imported historical rows from data
   already used during model development.

Rows from these scopes are never combined. Both scopes have
`production_approval_supported = false`, and the complete report currently has
`production_approved = false`.

## Endpoint

Start the Flask API and request:

```text
GET /api/component3/early-warning-validation
```

A row is evaluated only when:

- its actual outcome is supervisor-verified;
- its three-production-day future label has status `Ready`;
- the current day is stable, because Step 5C does not issue future warnings
  during a current emergency; and
- its saved analysis contains an available early-warning decision.

For each target, the response includes evaluated row/order counts, positive and
negative actual-class counts, Accuracy, Macro-F1, F1, and a class-coverage
status. These counts are evidence boundaries, not additional model scores.

## Current BULK0007 retrospective result

After importing and verifying all 21 BULK0007 days, five stable source days
have both a saved warning and a ready three-day outcome:

| Target | Actual positive / negative | Accuracy | Macro-F1 | F1 | Interpretation |
| --- | ---: | ---: | ---: | ---: | --- |
| Machine breakdown | 2 / 3 | 100.0% | 100.0% | 100.0% | Both actual classes exist, but only in reused training data. |
| Quality-limit issue | 0 / 5 | 60.0% | 37.5% | 0.0% | One actual class only; insufficient class coverage. |
| Output or schedule risk | 5 / 0 | 40.0% | 28.6% | 57.1% | One actual class only; insufficient class coverage. |

This is retrospective workflow evidence from one order. It is not an
independent test result and cannot justify a production-readiness claim. In
particular, a high or perfect score on reused model-development data can be
optimistic.

## Frontend

Open:

```text
http://localhost:3000/dashboard/monitoring-history
```

The **Step 5D.1 validation report** card displays independent and retrospective
results side by side. It marks targets that contain only one actual class and
does not merge their scores.

## Next evidence required

Continue saving and verifying daily observations from bulk orders that were not
used during training. An independent target becomes meaningfully evaluable only
after its rows include both positive and negative actual outcomes across
multiple unseen orders. Retrospective BULK0007 rows remain useful for checking
the end-to-end workflow, but they remain excluded from that independent scope.
