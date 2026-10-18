# Code Quality and Dependency Audit

Audit date: 2026-10-18

## Runtime entry points

- Flask API: `main.py` imports the application created by `app.py` and listens on
  port 5001 by default.
- Main Next.js application: `frontends/` (port 3000 in development).
- Sub-plant Next.js portal: `subplant-portal/` (port 3001 in development).
- Primary integrated database: `garment.db`.
- Component 3 monitoring database: `instance/component3_tracking.db`.
- Active ML artifacts: the registered files loaded from `models/` by
  `components/component1.py` through `components/component4.py`.

## Dependency findings

- Python dependency integrity: `python -m pip check` passes.
- `requirements.txt` now contains direct runtime dependencies instead of a
  copied list of transitive packages.
- The unused OpenAI SDK was removed from the runtime dependency manifests. The
  active C1-C4 implementations do not import it or require an OpenAI API key.
- Development dependencies (`pytest`, `ruff`) remain in the `dev` optional
  dependency group in `pyproject.toml`.
- PDF report generation uses Matplotlib and is isolated in the `report`
  optional dependency group; it is not required to run the application.
- Both Next.js package manifests match their lockfiles. Local `node_modules/`
  directories contain generated/optional packages, are ignored by Git, and
  should be recreated with `npm ci` on a clean device.

## Archived legacy and duplicate artifacts

The following were moved out of the active repository, not permanently deleted:

- `Backend/`: superseded standalone backend copy.
- `Build/`: generated model-training candidate/report output.
- `models/z/`: old unregistered C1-C4 Python implementations.
- `subplant-portal/subplant-portal/`: accidental nested installation containing
  another generated `node_modules/` tree.
- Unregistered/duplicate model files:
  - `c2_model4_alloc.pkl`
  - `c2_model5_deadline.pkl`
  - `c2_model_embroide.pkl`
  - `c2_model_sewing_.pkl`
  - `c4_model1_perf_score.pkl`
  - `c4_model2_star_rating.pkl`
  - `le_process.pkl`
  - `m1_overrun_classifier.pkl`
  - `model1_overrun.pkl`
  - `model3_delay.pkl`
  - `model_C_recommendation.pkl`

Recoverable archive location:

`../FabricFlow_legacy_archive_2026-10-18/`

The archived artifacts are not imported by the current entry points. The full
Python test suite passed after they were moved.

## Data preservation

No application data was moved or deleted. In particular, the audit preserves:

- `garment.db`
- `instance/component3_tracking.db`
- `data/`
- `uploads/`
- active registered files in `models/`
- research reports and datasets

## C3 modularization

- Prediction payload validation and normalization now live in
  `components/component3_validation.py`.
- The Flask blueprint remains the API orchestration layer and imports that
  validator.
- The recovery-option UI now lives in
  `frontends/src/app/(dashboard)/component3/monitoring/RecoveryOptionCard.tsx`.
- Existing C3 feature engineering, recovery, monitoring, tracking, early-warning
  inference, training export, and historical validation modules remain separate.

## Verification completed

- Ruff lint: all Python files and notebook code cells pass.
- Ruff formatting: all checked Python sources are formatted.
- Pytest: 121 tests pass.
- Main frontend: ESLint passes and production build succeeds.
- Sub-plant portal: ESLint passes and production build succeeds.

## Remaining model compatibility note

Some older C2/C4 scikit-learn artifacts were trained with version 1.6.1 while
the integrated environment uses 1.8.0 for current C3 artifacts. Loading those
older files can emit non-blocking compatibility warnings. Globally downgrading
scikit-learn would create a C3 mismatch; the durable solution is to retrain and
version the older artifacts in the common environment.
