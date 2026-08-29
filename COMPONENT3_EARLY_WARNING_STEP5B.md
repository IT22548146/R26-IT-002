# Component 3 Step 5B — Grouped Model Comparison and Probability Calibration

## Outcome

Step 5B trained and compared research-only models for the three subtype targets
that passed the Step 5A data-readiness audit:

- machine breakdown within the next three production days;
- quality-limit issue within the next three production days;
- output or schedule risk within the next three production days.

It did not train a general emergency model or a worker-shortage early-warning
model. Those targets did not pass the Step 5A class-coverage gate.

## Real-data boundary

The experiment uses only the 598 original daily records from
`component3_final_preprossed dataset.xlsx`. No generated, augmented, copied, or
synthetic rows are used. Step 5A produces 174 eligible currently-stable source
days with a complete three-production-day future window across 11 bulk orders.

The live verified-data export introduced in Step 5A.3 remains a separate path
for future general-emergency training and later retraining. Its current local
records are not mixed into this historical experiment.

## Leakage-safe evaluation

The comparison uses all 30 Step 5A current/past-only features. `Bulk_Order_ID`
is grouping metadata and never a model feature. Future outcomes, risk labels,
recommendations, buyer deadlines, completion dates, and identity fields are
also excluded from model inputs.

Validation uses Leave-One-Group-Out with `Bulk_Order_ID` as the group:

1. one complete bulk order is held out;
2. preprocessing and the model are fitted on the other orders;
3. the held-out order is predicted once;
4. the process repeats for all 11 orders;
5. the out-of-fold predictions are combined to calculate Accuracy, Macro-F1,
   and positive-class F1.

This prevents rows from the same order appearing in both the training and test
parts of a fold.

After model selection, probability calibration uses nested
Leave-One-Group-Out validation. In every outer fold, the held-out bulk order is
absent from both the base model and the sigmoid calibration mapping. The final
sigmoid mapping is fitted only from base-model probabilities generated while
each bulk order was held out.

## Models compared

- Dummy prior, used only as a majority-class baseline;
- class-balanced Logistic Regression;
- class-balanced Random Forest;
- XGBoost with balanced training weights.

The selection rule is highest Macro-F1, then positive-class F1, then Accuracy.
Macro-F1 is primary because each target is imbalanced and plain Accuracy can
reward a model that ignores the minority emergency class.

## Results

| Target | Model | Accuracy | Macro-F1 | F1 | Selected |
| --- | --- | ---: | ---: | ---: | --- |
| Machine breakdown | Dummy prior | 0.729885 | 0.421927 | 0.000000 | No |
| Machine breakdown | Logistic Regression | 0.810345 | 0.779586 | 0.697248 | No |
| Machine breakdown | Random Forest | **0.856322** | **0.825630** | **0.752475** | Yes |
| Machine breakdown | XGBoost | 0.833333 | 0.800040 | 0.718447 | No |
| Quality limit | Dummy prior | 0.770115 | 0.435065 | 0.870130 | No |
| Quality limit | Logistic Regression | **0.637931** | **0.531278** | **0.754864** | Yes |
| Quality limit | Random Forest | 0.752874 | 0.489318 | 0.856187 | No |
| Quality limit | XGBoost | 0.706897 | 0.505764 | 0.821053 | No |
| Output/schedule risk | Dummy prior | 0.856322 | 0.461300 | 0.000000 | No |
| Output/schedule risk | Logistic Regression | **0.729885** | **0.628188** | **0.433735** | Yes |
| Output/schedule risk | Random Forest | 0.821839 | 0.451104 | 0.000000 | No |
| Output/schedule risk | XGBoost | 0.758621 | 0.525208 | 0.192308 | No |

The dummy quality F1 is high because the positive class is the majority, while
its Macro-F1 exposes weak performance across both classes. The output/schedule
dummy and Random Forest have high Accuracy but zero positive-class F1. These
examples are why the experiment does not select by Accuracy alone.

## Probability calibration results

Lower Brier score, log-loss, and expected calibration error (ECE) are better.
All three selected models improved after grouped sigmoid calibration.

| Target | Raw Brier | Calibrated Brier | Raw Log-loss | Calibrated Log-loss | Raw ECE | Calibrated ECE | Action threshold |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Machine breakdown | 0.092461 | **0.091659** | 0.294330 | **0.273545** | 0.085892 | **0.066983** | 32.4% |
| Quality limit | 0.232489 | **0.180590** | 0.681831 | **0.556211** | 0.194385 | **0.046808** | 72.6% |
| Output/schedule risk | 0.204189 | **0.128030** | 0.820563 | **0.401751** | 0.209344 | **0.097743** | 19.5% |

The action threshold is target-specific because the three event classes have
different prevalence. It is selected from bulk-order-held-out calibrated
scores by Macro-F1, rather than assuming that 50% is suitable for every event.

## Artifacts

The selected pipelines are refitted on all 174 eligible rows and stored as:

```text
models/c3_early_warning_machine_breakdown_v2.joblib
models/c3_early_warning_quality_limit_v2.joblib
models/c3_early_warning_output_schedule_risk_v2.joblib
```

Each artifact contains the fitted base estimator, grouped sigmoid calibrator,
exact feature order, target, three-day horizon, class coverage, target-specific
decision threshold, classification metrics, probability metrics, and
`production_approved = false`. Raw base-model scores remain available for
audit, while the normal `predict_proba` output is calibrated.

The machine-readable evidence is stored in:

```text
reports/component3_early_warning_step5b_calibrated/evaluation.json
reports/component3_early_warning_step5b_calibrated/model_comparison.csv
```

## Reproduce the experiment

From the backend repository root:

```bash
python3 train_component3_early_warning.py
```

The command rebuilds Step 5A labels from the original workbook, runs all 11
grouped folds for every candidate and target, runs nested grouped calibration,
writes the comparison files, and replaces the three V2 research artifacts.

## Production boundary and next step

These are model-selection scores from only 11 independent orders, not a locked
final production test. The selected models are refitted research artifacts and
must stay experimental until they are validated on new, untouched real orders.

Step 5C now loads the artifacts, builds current/past-only features from saved
same-order history, and exposes the three research scores through the Component
3 Flask API and monitoring frontend. See
[`COMPONENT3_EARLY_WARNING_STEP5C.md`](COMPONENT3_EARLY_WARNING_STEP5C.md).
Worker-shortage recovery continues through the current-day detector and
deterministic recovery engine while more real negative worker-shortage
sequences are collected.
