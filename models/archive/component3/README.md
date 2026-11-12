# Archived Component 3 model artifacts

This directory contains superseded Component 3 artifacts retained only for
research reproducibility and explicit legacy compatibility tests.

The default runtime uses `COMPONENT3_MODEL_VERSION=v3` and loads these active
artifacts from the parent `models/` directory:

- `c3_model1_risk_type_v2.pkl`
- `c3_model2_order_risk_v3.pkl`
- `c3_early_warning_machine_breakdown_v2.joblib`
- `c3_early_warning_quality_limit_v2.joblib`
- `c3_early_warning_output_schedule_risk_v2.joblib`

Files in this archive are not loaded by the default runtime. Do not use them
for new production predictions. The v1/v2 backend configurations can still
load the corresponding archived artifacts when an explicit regression test or
research comparison requires them.
