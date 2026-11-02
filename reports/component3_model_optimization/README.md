# Component 3 — Hyperparameter Optimization and Ensemble Evidence

**Report version:** `component3-grouped-hyperparameter-optimization-v1`
**Generated:** `2026-10-17T15:15:06.889862+00:00`
**Research status:** Evidence only; active artifacts are not replaced automatically.

## Methodology

- Outer validation: Leave-One-Group-Out using `Bulk_Order_ID`.
- Inner optimization: GroupKFold with GridSearchCV.
- Primary selection metric: Macro-F1.
- Ensemble: probability-based soft voting between tuned Logistic Regression and tuned Random Forest.
- Leakage control: an outer test order is absent from parameter and ensemble-weight selection.

## Nested unseen-order results

| Target | Candidate | Accuracy | Macro-F1 | Positive F1 | Selected |
|---|---|---:|---:|---:|:---:|
| Machine breakdown within 3 production days | Tuned Logistic Regression | 84.48% | 82.47% | 76.52% | No |
| Machine breakdown within 3 production days | Tuned Random Forest | 85.63% | 82.76% | 75.73% | No |
| Machine breakdown within 3 production days | Soft Voting Logistic Random Forest | 86.21% | 84.20% | 78.57% | Yes |
| Quality-limit issue within 3 production days | Tuned Logistic Regression | 66.09% | 59.76% | 75.72% | Yes |
| Quality-limit issue within 3 production days | Tuned Random Forest | 73.56% | 48.00% | 84.46% | No |
| Quality-limit issue within 3 production days | Soft Voting Logistic Random Forest | 71.26% | 59.42% | 81.34% | No |
| Output or schedule risk within 3 production days | Tuned Logistic Regression | 73.56% | 61.99% | 41.03% | Yes |
| Output or schedule risk within 3 production days | Tuned Random Forest | 81.03% | 44.76% | 0.00% | No |
| Output or schedule risk within 3 production days | Soft Voting Logistic Random Forest | 75.86% | 57.71% | 30.00% | No |

## Selected parameters after full-data grouped search

### Machine breakdown within 3 production days

Nested-evidence winner: **Soft Voting Logistic Random Forest**

- `tuned_logistic_regression`: `{"model__C": 5.0}` (inner Macro-F1 81.52%)
- `tuned_random_forest`: `{"model__max_depth": null, "model__max_features": "sqrt", "model__min_samples_leaf": 1, "model__n_estimators": 400}` (inner Macro-F1 82.96%)
- `soft_voting_logistic_random_forest`: `{"weights": [2, 1]}` (inner Macro-F1 81.52%)

### Quality-limit issue within 3 production days

Nested-evidence winner: **Tuned Logistic Regression**

- `tuned_logistic_regression`: `{"model__C": 0.05}` (inner Macro-F1 60.01%)
- `tuned_random_forest`: `{"model__max_depth": null, "model__max_features": "sqrt", "model__min_samples_leaf": 3, "model__n_estimators": 200}` (inner Macro-F1 53.08%)
- `soft_voting_logistic_random_forest`: `{"weights": [2, 1]}` (inner Macro-F1 56.25%)

### Output or schedule risk within 3 production days

Nested-evidence winner: **Tuned Logistic Regression**

- `tuned_logistic_regression`: `{"model__C": 1.0}` (inner Macro-F1 62.91%)
- `tuned_random_forest`: `{"model__max_depth": null, "model__max_features": "sqrt", "model__min_samples_leaf": 1, "model__n_estimators": 200}` (inner Macro-F1 46.08%)
- `soft_voting_logistic_random_forest`: `{"weights": [1, 1]}` (inner Macro-F1 59.50%)

## Parameter justification

- **Logistic Regression C:** Controls regularization strength for a stable linear model on the small, imbalanced early-warning dataset.
- **Random Forest N Estimators:** Compares ensemble sizes to balance stability and compute cost.
- **Random Forest Max Depth:** Constrains tree complexity to reduce small-dataset overfitting.
- **Random Forest Min Samples Leaf:** Prevents decisions from depending on very small leaf samples.
- **Soft Voting Weights:** Tests whether emphasizing the linear or nonlinear model improves order-held-out Macro-F1.

## Interpretation and promotion rule

Do not replace active artifacts automatically. Promote only if nested unseen-order evidence improves and integration tests pass.

An ensemble is not selected merely because it is more complex. It must improve nested unseen-order Macro-F1. A simpler tuned model is preferred when the evidence ties.

## Limitations

- The available real dataset contains a limited number of orders.
- Nested grouped scores are research evidence, not production approval.
- A tuned or ensemble model is retained only when it improves held-out evidence.
