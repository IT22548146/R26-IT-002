# Component 3 — Model Comparison Scores

**Student:** Alagiyawanna S.A.M.A.V.P

**Student ID:** IT22904614

**Component:** Emergency Situation Detection and Management

| ML output | Compared model | Accuracy | Macro-F1 | F1 score | Result |
|---|---|---:|---:|---:|---|
| Current risk type | Dummy baseline | 32.27% | 6.97% | 15.75% | Baseline |
| Current risk type | Logistic Regression | 76.42% | 80.44% | 76.94% | Not selected |
| Current risk type | **Random Forest** | **81.77%** | **90.08%** | **81.93%** | **Selected** |
| Current risk type | Extra Trees | 80.10% | 89.24% | 80.17% | Not selected |


| Overall order risk V3 | Dummy baseline | 5.85% | 5.53% | 0.65% | Baseline |
| Overall order risk V3 | Logistic Regression | 99.67% | 98.52% | 99.67% | Not selected |
| Overall order risk V3 | **Random Forest** | **99.83%** | **99.25%** | **99.83%** | **Selected** |
| Overall order risk V3 | Gradient Boosting | 99.83% | 99.25% | 99.83% | Not selected |


| Machine breakdown — next 3 days | Dummy baseline | 72.99% | 42.19% | 0.00% | Baseline |
| Machine breakdown — next 3 days | Logistic Regression | 81.03% | 77.96% | 69.72% | Not selected |
| Machine breakdown — next 3 days | **Random Forest** | **85.63%** | **82.56%** | **75.25%** | **Selected** |
| Machine breakdown — next 3 days | XGBoost | 83.33% | 80.00% | 71.84% | Not selected |


| Quality-limit issue — next 3 days | Dummy baseline | 77.01% | 43.51% | 87.01% | Baseline |
| Quality-limit issue — next 3 days | **Logistic Regression** | **63.79%** | **53.13%** | **75.49%** | **Selected** |
| Quality-limit issue — next 3 days | Random Forest | 75.29% | 48.93% | 85.62% | Not selected |
| Quality-limit issue — next 3 days | XGBoost | 70.69% | 50.58% | 82.11% | Not selected |


| Output/schedule risk — next 3 days | Dummy baseline | 85.63% | 46.13% | 0.00% | Baseline |
| Output/schedule risk — next 3 days | **Logistic Regression** | **72.99%** | **62.82%** | **43.37%** | **Selected** |
| Output/schedule risk — next 3 days | Random Forest | 82.18% | 45.11% | 0.00% | Not selected |
| Output/schedule risk — next 3 days | XGBoost | 75.86% | 52.52% | 19.23% | Not selected |

*For the two current/order-risk models, the F1 column reports Weighted-F1. For the three early-warning models, it reports positive-class F1.*

## Calibrated Early-Warning Scores Used by the Active System

| Selected early-warning model | Accuracy | Macro-F1 | F1 score |
|---|---:|---:|---:|
| Machine breakdown — Random Forest | 86.21% | 84.05% | 78.18% |
| Quality-limit issue — Logistic Regression | 66.67% | 51.18% | 78.68% |
| Output/schedule risk — Logistic Regression | 79.31% | 63.75% | 40.00% |
