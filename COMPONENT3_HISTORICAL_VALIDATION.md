# Component 3 Historical Validation and Calibration Evidence

## Purpose

This step replays the deterministic Emergency Recovery Planning Engine on past
daily risk records and compares each plan with the next recorded production
day. It is an evaluation pipeline, not a new trained model.

The pipeline uses the original workbook by default:

```text
component3_final_preprossed dataset.xlsx
```

Rows explicitly marked or identified as generated or augmented are excluded.
The generated training workbook is therefore not needed for this recovery
validation.

## Run the validation

From the backend project directory:

```bash
python3 validate_component3_recovery.py \
  --data "component3_final_preprossed dataset.xlsx" \
  --json-output reports/component3_recovery_validation/evaluation.json \
  --csv-output reports/component3_recovery_validation/historical_cases.csv
```

The JSON file contains dataset checks, aggregate validation metrics,
calibration evidence and limitations. The CSV file contains one replay record
per historical risk day so that every result can be audited.

## Current original-data result

The checked-in report was produced from 598 daily rows across 11 bulk orders.
It found 405 risk rows with a following production-day outcome. Seven cases
whose next row was the order's final partial day were excluded from capacity
metrics because their output was limited by remaining order quantity.

Key observational results are:

| Evaluation | Result |
| --- | ---: |
| Current output -> next-workday output MAE | 46.312 pieces |
| Current output -> next-workday output WAPE | 13.631% |
| Recommended capacity -> observed output MAE | 43.806 pieces |
| Recommended capacity -> observed output WAPE | 12.539% |
| Projected completion-date MAE | 0.218 calendar days |

The recommended-capacity comparison is observational. It must not be described
as recovery-action effectiveness because the workbook does not say whether the
recommended action was actually implemented.

The completion-date figure also needs caution: the 405 rows come from only 11
orders, so daily cases are repeated observations rather than 405 independent
orders. Ten of the 11 orders complete exactly on the recorded buyer deadline,
and the planner is also solving capacity toward that deadline. Therefore, the
low completion-date error is not independent predictive evidence.

## Why automatic calibration is not applied yet

The historical workbook records `System_Recommendation`, but it does not record
the applied action or the amount of resources actually used. The following
fields are needed to estimate causal gains:

- `Applied_Action`
- `Actual_Overtime_Hours`
- `Actual_Additional_Workers`
- `Actual_Backup_Machines`
- `Actual_Machine_Repair_Hours`
- the actual daily output after the action
- the actual completion date

Without those fields, changing the engine's worker, machine or overtime gains
would create a false causal claim. The validation report therefore exposes
next-workday output multipliers as calibration evidence but leaves
`engine_parameters_updated` set to `false`.

## How the required data will be collected

The Component 3 incident workflow already stores:

1. the full prediction input and recovery parameters;
2. the selected recovery option and approver;
3. daily actual output and cumulative completion;
4. the actual completion date and an audit timeline.

After enough completed incidents are recorded for each action type, those
records can be exported and used to calibrate per-worker, per-machine and
per-overtime-hour capacity gains. Until then, a manager must approve every
recovery recommendation.

## Important metric limitation

All 11 orders in the current workbook met their buyer deadline. Deadline
feasibility accuracy is included for traceability, but it cannot show whether
the engine can distinguish a missed deadline because the negative class has no
examples. Additional real missed-deadline orders are required for that test.
