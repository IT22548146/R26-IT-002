# Component 3 — V2 Training and Evaluation

## Reproduce training

```bash
python3 train_component3_v2.py
```

The pipeline uses `data/component3_training_augmented.xlsx` and:

- evaluates on complete held-out real `Bulk_Order_ID` groups;
- adds only `Data_Origin = Augmented_Low_Risk` rows to training folds;
- excludes all 885 `Existing_Generated` rows;
- recomputes every model feature with the same shared code used by the API;
- preserves the version-1 artifacts.

## Selected models

| Target | Selected algorithm | Accuracy | Macro F1 |
|---|---|---:|---:|
| Risk type | Random Forest | 0.818 | 0.901 |
| Order risk | Logistic Regression | 0.973 | 0.900 |

For Model 2:

- Low Risk precision: `0.686`
- Low Risk recall: `1.000`
- High Risk recall: `0.972`
- High Risk rows incorrectly predicted as Low Risk: `16`

Complete candidate results are stored in `reports/component3_v2/evaluation.json`.

## Artifacts

```text
models/c3_model1_risk_type_v2.pkl
models/c3_model2_order_risk_v2.pkl
models/c3_model_metadata_v2.json
```

The metadata records the dataset SHA-256, feature order, label mappings, selected
metrics, training timestamp, and library versions.

## API model selection

Version 1 remains the default. Test v2 with:

```bash
COMPONENT3_MODEL_VERSION=v2 python3 app.py
```

The response includes:

```json
{
  "model_version": "v2"
}
```

The Component 3 health endpoint also reports the configured model version.

## Production decision

Both v2 models remain experimental:

- `Minor Delay` has only 4 real rows from 1 real order.
- `Quality Issue` has only 4 real rows.
- Low Risk has only 1 real order containing 35 daily rows.

Synthetic or augmented performance does not replace independent real-order
coverage. Keep `COMPONENT3_MODEL_VERSION=v1` as the default until the additional
real records are collected and v2 is re-evaluated.

## Tests

```bash
python3 -m unittest discover -s tests -v
```

The tests cover shared feature calculations, negative gaps, damage thresholds,
order-specific production phases, v2 model loading, and Flask API predictions.
