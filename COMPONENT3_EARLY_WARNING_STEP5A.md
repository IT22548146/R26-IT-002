# Component 3 Step 5A — Early-Warning Dataset Readiness

## Decision

Step 5A dataset preparation completed successfully, but the current original
dataset is **not ready to train a general three-production-day early-warning
model**.

No model was trained in this step. Training a binary model with the current
target would produce a misleading result because the target has only one class.

## What counts as a real early warning

The prediction must be made before an emergency begins. The audit therefore:

1. selects a day on which no emergency is currently present;
2. checks only later rows from the same bulk order;
3. requires all three future production days to be available;
4. labels whether an emergency occurs within one or three production days;
5. excludes future labels, recommendations, completion dates and order identity
   from model features;
6. reserves `Bulk_Order_ID` for grouped validation only.

This prevents a model from appearing accurate merely because a worker shortage
or machine breakdown that already started continues on the following day.

## Original-data findings

The audit used the 598 original daily rows from 11 bulk orders. It did not add
new production rows.

| Check | Result |
| --- | ---: |
| Currently stable rows | 193 |
| Currently emergency rows excluded | 405 |
| Stable rows with a complete three-day future window | 174 |
| Emergency within one day — positive | 170 |
| Emergency within one day — negative | 4 |
| Emergency within three days — positive | 174 |
| Emergency within three days — negative | 0 |

The four one-day negative examples also come from only one bulk order. A grouped
train/test evaluation therefore cannot measure how the general early-warning
target behaves on unseen orders.

## Subtype findings

Some narrower three-day outcome labels have both positive and negative examples:

| Target | Positive | Negative | Research-ready for grouped evaluation |
| --- | ---: | ---: | --- |
| Worker shortage | 165 | 9 | No |
| Machine breakdown | 47 | 127 | Yes |
| Quality limit | 134 | 40 | Yes |
| Output/schedule risk | 25 | 149 | Yes |

These subtype targets may be compared in a research experiment, but they do not
make the complete general early-warning objective production-ready. There are
still only 11 independent orders.

## Reproduce the audit

```bash
python3 audit_component3_early_warning.py \
  --data "component3_final_preprossed dataset.xlsx" \
  --json-output reports/component3_early_warning_step5a/readiness.json \
  --csv-output reports/component3_early_warning_step5a/labelled_stable_rows.csv
```

The labelled CSV contains 30 current/past-only candidate features and the
future outcome labels. It is an auditable dataset-preparation output, not a new
source dataset.

## Data needed next

For the general model, collect real daily monitoring sequences containing:

- stable days followed by at least three more stable days;
- stable-to-emergency transitions;
- both outcomes across several independent bulk orders;
- accurate worker, machine, quality and production-output observations.

The minimum audit rule is at least 20 rows and three independent orders in each
class. A production claim will require substantially more orders and a final
unseen-order test set.

Do not fix the missing negative class by copying rows or creating artificial
negative outcomes. That changes class counts but does not provide evidence of
how the system behaves in real stable production periods.
