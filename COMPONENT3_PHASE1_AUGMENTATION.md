# Component 3 — Phase 1 Low Risk Augmentation

## Artifacts

- Generator: `augment_component3_low_risk.py`
- Source workbook: `../component3 (2).xlsx`
- Generated workbook: `data/component3_training_augmented.xlsx`
- Generator version: `component3_low_risk_v1`
- Random seed: `42`

The source workbook is not modified.

## Generation summary

The generator added 12 complete Low Risk order trajectories containing 479 daily
records. Each trajectory has internally consistent business-day dates, cumulative
production, remaining quantity, completion date, buyer deadline, event fields,
and derived model features.

| Origin | Rows |
|---|---:|
| Real data | 598 |
| Pre-existing generated data | 885 |
| New augmented Low Risk data | 479 |
| Total | 1,962 |

The resulting order-risk row distribution is:

| Order risk | Rows |
|---|---:|
| High | 1,077 |
| Low | 885 |

Every new row is marked with:

```text
Synthetic = True
Scenario_Tag = Augmented_Low_Risk
Data_Origin = Augmented_Low_Risk
Augmentation_Version = component3_low_risk_v1
```

## Validation performed

- 12 unique generated bulk orders
- No generated order-ID collisions
- No negative remaining quantities
- Every generated order finishes with `Remaining_Qty = 0`
- Final cumulative output equals full order quantity
- Buyer deadline is later than the style completion date
- `Output_Gap = Daily_Commitment - Plant_Daily_Output`
- All generated order targets are `Low` / encoded as `0`
- Risk types, flags, recommendations, and severity are generated consistently

## Real-only grouped evaluation after augmentation

Evaluation held out one complete real order at a time. Training used the other
real orders plus only the 479 newly generated records. The 885 pre-existing
generated records were excluded from this comparison.

### Model 1

| Candidate | Accuracy | Macro F1 |
|---|---:|---:|
| Random Forest | 0.809 | 0.897 |
| Extra Trees | 0.799 | 0.892 |

The augmented examples allowed both `Minor Delay` and `Quality Issue` to be
recognized in this test, but each still has only four real evaluation rows.

### Model 2

| Metric | Result |
|---|---:|
| Accuracy | 0.915 |
| Macro F1 | 0.766 |
| ROC-AUC | 0.999 |
| Low Risk recall | 1.000 |
| Low Risk precision | 0.407 |
| High Risk recall | 0.909 |

The model correctly classified all 35 rows from the only real Low Risk order, but
it incorrectly classified 51 High Risk rows as Low Risk. Forty-five of those rows
came from one complete High Risk order (`BULK0005`). This order-level failure is
more important than the high ROC-AUC value.

## Limitation and decision

This workbook is suitable for training experiments, not final production proof.
Generated orders improve class coverage but do not replace independent real Low
Risk orders. Model 2 should remain unapproved for production until multiple new
real Low Risk orders are collected and evaluated as untouched groups.

## Reproduce

```bash
python3 augment_component3_low_risk.py \
  --input "../component3 (2).xlsx" \
  --output "data/component3_training_augmented.xlsx" \
  --orders 12 \
  --seed 42
```
