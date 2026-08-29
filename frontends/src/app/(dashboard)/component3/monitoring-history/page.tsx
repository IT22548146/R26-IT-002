'use client';

import Link from 'next/link';
import { useCallback, useEffect, useMemo, useState } from 'react';
import styles from './monitoring-history.module.css';

type RiskStatus = 'No Risk' | 'Risk';
type VerificationStatus = 'Pending' | 'Verified';
type ActualEmergencyType =
  | 'Worker Shortage'
  | 'Machine Breakdown'
  | 'Quality Issue'
  | 'Output / Schedule Risk'
  | 'Other Emergency';
type LabelStatus =
  | 'Awaiting Verification'
  | 'Waiting'
  | 'Ready'
  | 'Not Eligible'
  | 'Censored'
  | 'Incomplete';

interface MonitoringRecord {
  record_id: string;
  bulk_order_id: string;
  style_id: string;
  production_date: string;
  working_day_no: number;
  risk_status: RiskStatus;
  risk_type: string;
  severity: string | null;
  is_emergency: boolean;
  actual_outcome_status: VerificationStatus;
  actual_emergency: boolean | null;
  actual_emergency_type: ActualEmergencyType | null;
  verified_by: string | null;
  verification_notes: string | null;
  verified_at: string | null;
  plant_daily_output: number;
  daily_commitment: number;
  worker_shortage_count: number;
  machine_breakdown_count: number;
  daily_damage_qty: number;
  max_daily_damage_qty: number;
  cumulative_completed_qty: number;
  label_status: LabelStatus;
  emergency_within_1_day: number | null;
  emergency_within_3_days: number | null;
  first_emergency_type_within_3_days: string | null;
  first_emergency_lead_days: number | null;
  recorded_by: string;
  data_origin: string;
  independent_validation_eligible: boolean;
  created_at: string;
}

interface MonitoringListResponse {
  items: MonitoringRecord[];
  total: number;
  limit: number;
  offset: number;
}

interface ReadinessResponse {
  total_records: number;
  verified_records: number;
  pending_verification_records: number;
  independent_validation_eligible_records: number;
  retrospective_training_reuse_records: number;
  stable_records: number;
  emergency_records: number;
  detected_stable_records: number;
  detected_emergency_records: number;
  verification_status_counts: Record<VerificationStatus, number>;
  label_status_counts: Record<LabelStatus, number>;
  three_day_target: {
    ready_rows: number;
    retrospective_ready_rows_excluded: number;
    positive_rows: number;
    negative_rows: number;
    positive_orders: number;
    negative_orders: number;
    minimum_rows_per_class_required: number;
    minimum_orders_per_class_required: number;
    row_balance_sufficient: boolean;
    group_coverage_sufficient: boolean;
    general_early_warning_training_ready: boolean;
  };
}

interface TrainingExportAudit {
  export_version: string;
  dataset: {
    all_monitoring_records: number;
    ready_source_candidates: number;
    exported_rows: number;
    independent_orders: number;
    excluded_rows_by_reason: Record<string, number>;
    sha256_csv: string;
  };
  schema: {
    group_validation_column: string;
    model_feature_count: number;
    model_features: string[];
    target_columns: string[];
  };
  sequence_quality: {
    working_day_gap_transitions: number;
    orders_with_working_day_gaps: string[];
    passed: boolean;
  };
  leakage_controls: {
    identity_columns_in_model_features: string[];
    future_targets_in_model_features: string[];
    passed: boolean;
  };
  primary_target: {
    name: string;
    positive_rows: number;
    negative_rows: number;
    positive_orders: number;
    negative_orders: number;
    training_ready: boolean;
  };
  decision: string;
}

interface WarningValidationTarget {
  target: string;
  display_name: string;
  rows_evaluated: number;
  orders_evaluated: number;
  positive_actual_rows: number;
  negative_actual_rows: number;
  positive_predictions: number;
  negative_predictions: number;
  class_coverage_complete: boolean;
  metrics: {
    accuracy: number;
    macro_f1: number;
    f1: number;
  } | null;
  missing_warning_or_outcome_rows: number;
  stored_score_range: {
    minimum: number;
    maximum: number;
  } | null;
  status: 'no_evaluable_rows' | 'single_actual_class' | 'evaluated';
}

interface WarningValidationScope {
  scope: 'independent_validation' | 'retrospective_training_reuse';
  evidence_type: string;
  status:
    | 'awaiting_evaluable_rows'
    | 'insufficient_class_coverage'
    | 'evaluated';
  records_in_scope: number;
  ready_warning_rows: number;
  orders_evaluated: number;
  excluded_rows_by_reason: Record<string, number>;
  targets: WarningValidationTarget[];
  every_target_has_rows: boolean;
  every_target_has_both_actual_classes: boolean;
  production_approval_supported: false;
}

interface WarningValidationReport {
  report_version: string;
  status: 'success';
  prediction_source: string;
  outcome_source: string;
  scope_mixing_detected: false;
  production_approved: false;
  independent_validation: WarningValidationScope;
  retrospective_training_reuse: WarningValidationScope;
  reported_metrics: ['accuracy', 'macro_f1', 'f1'];
  limitations: string[];
}

interface HistoricalMasterConflict {
  field: string;
  component2_value: string | number | null;
  component3_value: string | number | null;
}

interface HistoricalImportOrder {
  bulk_order_id: string;
  style_id: string;
  source_rows: number;
  production_date_from: string;
  production_date_to: string;
  recorded_emergency_days: number;
  importable_rows: number;
  existing_matching_rows: number;
  existing_conflicting_rows: number;
  component2_master: {
    status: 'matched' | 'matched_with_conflicts' | 'not_found' | 'ambiguous';
    matching_fields: string[];
    conflicting_fields: HistoricalMasterConflict[];
  };
}

interface HistoricalImportPreview {
  import_version: string;
  status: 'preview';
  mode: 'retrospective_demo';
  independent_validation: false;
  production_approved: false;
  sources: {
    component3_daily: {
      filename: string;
      sha256: string;
      rows: number;
      orders: number;
      generated_or_augmented_rows_excluded: number;
      already_used_for_model_training: boolean;
    };
    component2_master: {
      filename: string;
      sha256: string;
      rows: number;
      matched_component3_orders: number;
      authority: 'audit_only';
    };
  };
  summary: {
    source_rows: number;
    source_orders: number;
    importable_rows: number;
    existing_matching_rows: number;
    existing_conflicting_rows: number;
  };
  orders: HistoricalImportOrder[];
  rules: string[];
  limitations: string[];
}

interface HistoricalImportResult {
  status: 'success' | 'partial';
  mode: 'retrospective_demo';
  independent_validation: false;
  bulk_order_id: string;
  source_rows: number;
  imported_rows: number;
  existing_matching_rows: number;
  verified_rows: number;
  already_verified_rows: number;
  conflicts: Array<{
    working_day_no: number;
    production_date: string;
    reason: string;
  }>;
  processing_errors: Array<{
    working_day_no: number;
    production_date: string;
    error: string;
  }>;
  limitations: string[];
}

const ACTUAL_EMERGENCY_TYPES: ActualEmergencyType[] = [
  'Worker Shortage',
  'Machine Breakdown',
  'Quality Issue',
  'Output / Schedule Risk',
  'Other Emergency',
];

const API_BASE_URL = (
  process.env.NEXT_PUBLIC_COMPONENT3_API_URL ??
  'http://127.0.0.1:5001/api/component3'
).replace(/\/$/, '');

const NUMBER_FORMATTER = new Intl.NumberFormat('en-US');

function formatMetric(value: number | undefined) {
  return value === undefined ? '—' : `${(value * 100).toFixed(1)}%`;
}

function labelClass(status: LabelStatus) {
  return styles[`label${status.replace(' ', '')}`];
}

function futureOutcome(record: MonitoringRecord) {
  if (record.label_status !== 'Ready') return 'Not available yet';
  if (!record.emergency_within_3_days) return 'No emergency in next 3 days';
  const lead = record.first_emergency_lead_days;
  return `${record.first_emergency_type_within_3_days ?? 'Emergency'}${
    lead ? ` in ${lead} day${lead === 1 ? '' : 's'}` : ''
  }`;
}

export default function MonitoringHistoryPage() {
  const [records, setRecords] = useState<MonitoringRecord[]>([]);
  const [readiness, setReadiness] = useState<ReadinessResponse | null>(null);
  const [exportAudit, setExportAudit] = useState<TrainingExportAudit | null>(
    null,
  );
  const [validationReport, setValidationReport] =
    useState<WarningValidationReport | null>(null);
  const [validationReportError, setValidationReportError] = useState('');
  const [importPreview, setImportPreview] =
    useState<HistoricalImportPreview | null>(null);
  const [total, setTotal] = useState(0);
  const [orderFilter, setOrderFilter] = useState('');
  const [riskFilter, setRiskFilter] = useState('');
  const [labelFilter, setLabelFilter] = useState('');
  const [verificationFilter, setVerificationFilter] = useState('');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [refreshVersion, setRefreshVersion] = useState(0);
  const [selectedRecord, setSelectedRecord] = useState<MonitoringRecord | null>(
    null,
  );
  const [actualEmergency, setActualEmergency] = useState('');
  const [actualEmergencyType, setActualEmergencyType] = useState('');
  const [verifiedBy, setVerifiedBy] = useState('');
  const [verificationNotes, setVerificationNotes] = useState('');
  const [savingVerification, setSavingVerification] = useState(false);
  const [verificationError, setVerificationError] = useState('');
  const [verificationMessage, setVerificationMessage] = useState('');
  const [historicalOrderId, setHistoricalOrderId] = useState('');
  const [historicalImportedBy, setHistoricalImportedBy] = useState('');
  const [confirmRetrospectiveReuse, setConfirmRetrospectiveReuse] =
    useState(false);
  const [verifyHistoricalOutcomes, setVerifyHistoricalOutcomes] =
    useState(false);
  const [confirmHistoricalOutcomes, setConfirmHistoricalOutcomes] =
    useState(false);
  const [historicalVerifiedBy, setHistoricalVerifiedBy] = useState('');
  const [importingHistory, setImportingHistory] = useState(false);
  const [historicalImportError, setHistoricalImportError] = useState('');
  const [historicalImportMessage, setHistoricalImportMessage] = useState('');
  const [historicalPreviewError, setHistoricalPreviewError] = useState('');

  const requestJson = useCallback(async (path: string) => {
    const response = await fetch(`${API_BASE_URL}${path}`);
    const payload: unknown = await response.json();
    if (!response.ok) {
      const apiError = payload as { error?: unknown };
      throw new Error(
        typeof apiError.error === 'string'
          ? apiError.error
          : 'The daily monitoring request failed.',
      );
    }
    return payload;
  }, []);

  const query = useMemo(() => {
    const parameters = new URLSearchParams({ limit: '100' });
    if (orderFilter.trim()) parameters.set('bulk_order_id', orderFilter.trim());
    if (riskFilter) parameters.set('risk_status', riskFilter);
    if (labelFilter) parameters.set('label_status', labelFilter);
    if (verificationFilter) {
      parameters.set('verification_status', verificationFilter);
    }
    return parameters.toString();
  }, [labelFilter, orderFilter, riskFilter, verificationFilter]);

  useEffect(() => {
    let cancelled = false;
    const historicalPreviewRequest = requestJson('/historical-import/preview')
      .then((payload) => ({ payload, error: '' }))
      .catch((previewError: unknown) => ({
        payload: null,
        error:
          previewError instanceof Error
            ? previewError.message
            : 'Historical import preview is unavailable.',
      }));
    const validationReportRequest = requestJson('/early-warning-validation')
      .then((payload) => ({ payload, error: '' }))
      .catch((validationError: unknown) => ({
        payload: null,
        error:
          validationError instanceof Error
            ? validationError.message
            : 'Early-warning validation report is unavailable.',
      }));
    Promise.all([
      requestJson(`/monitoring-records?${query}`),
      requestJson('/monitoring-readiness'),
      requestJson('/training-dataset-audit'),
      historicalPreviewRequest,
      validationReportRequest,
    ])
      .then(
        ([
          listPayload,
          readinessPayload,
          exportAuditPayload,
          historicalPreviewResult,
          validationReportResult,
        ]) => {
          if (cancelled) return;
          const list = listPayload as MonitoringListResponse;
          setRecords(list.items);
          setTotal(list.total);
          setReadiness(readinessPayload as ReadinessResponse);
          setExportAudit(exportAuditPayload as TrainingExportAudit);
          setValidationReportError(validationReportResult.error);
          setValidationReport(
            validationReportResult.payload
              ? (validationReportResult.payload as WarningValidationReport)
              : null,
          );
          setHistoricalPreviewError(historicalPreviewResult.error);
          if (historicalPreviewResult.payload) {
            const historicalPreview =
              historicalPreviewResult.payload as HistoricalImportPreview;
            setImportPreview(historicalPreview);
            setHistoricalOrderId((current) => {
              if (
                current &&
                historicalPreview.orders.some(
                  (order) => order.bulk_order_id === current,
                )
              ) {
                return current;
              }
              return (
                historicalPreview.orders.find(
                  (order) => order.importable_rows > 0,
                )?.bulk_order_id ??
                historicalPreview.orders[0]?.bulk_order_id ??
                ''
              );
            });
          } else {
            setImportPreview(null);
          }
          setError('');
        },
      )
      .catch((requestError: unknown) => {
        if (cancelled) return;
        setError(
          requestError instanceof Error
            ? requestError.message
            : 'Unable to load daily monitoring history.',
        );
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [query, refreshVersion, requestJson]);

  const target = readiness?.three_day_target;
  const canExport = Boolean(
    exportAudit &&
      exportAudit.dataset.exported_rows > 0 &&
      exportAudit.leakage_controls.passed,
  );
  const selectedHistoricalOrder = importPreview?.orders.find(
    (order) => order.bulk_order_id === historicalOrderId,
  );

  const openVerification = (record: MonitoringRecord) => {
    setSelectedRecord(record);
    setActualEmergency(
      record.actual_emergency === null ? '' : String(record.actual_emergency),
    );
    setActualEmergencyType(record.actual_emergency_type ?? '');
    setVerifiedBy(record.verified_by ?? '');
    setVerificationNotes(record.verification_notes ?? '');
    setVerificationError('');
    setVerificationMessage('');
  };

  const closeVerification = () => {
    setSelectedRecord(null);
    setVerificationError('');
  };

  const handleVerification = async (
    event: React.FormEvent<HTMLFormElement>,
  ) => {
    event.preventDefault();
    if (!selectedRecord) return;

    setSavingVerification(true);
    setVerificationError('');
    try {
      const response = await fetch(
        `${API_BASE_URL}/monitoring-records/${selectedRecord.record_id}/verification`,
        {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            actual_emergency: actualEmergency === 'true',
            actual_emergency_type:
              actualEmergency === 'true' ? actualEmergencyType : null,
            verified_by: verifiedBy.trim(),
            verification_notes: verificationNotes.trim() || null,
          }),
        },
      );
      const payload: unknown = await response.json();
      if (!response.ok) {
        const apiError = payload as { error?: unknown };
        throw new Error(
          typeof apiError.error === 'string'
            ? apiError.error
            : 'The actual outcome could not be verified.',
        );
      }

      setSelectedRecord(null);
      setVerificationMessage(
        `Actual outcome verified for ${selectedRecord.bulk_order_id}, working day ${selectedRecord.working_day_no}.`,
      );
      setLoading(true);
      setRefreshVersion((value) => value + 1);
    } catch (requestError: unknown) {
      setVerificationError(
        requestError instanceof Error
          ? requestError.message
          : 'Unable to verify this daily outcome.',
      );
    } finally {
      setSavingVerification(false);
    }
  };

  const handleHistoricalImport = async (
    event: React.FormEvent<HTMLFormElement>,
  ) => {
    event.preventDefault();
    setImportingHistory(true);
    setHistoricalImportError('');
    setHistoricalImportMessage('');
    try {
      const response = await fetch(`${API_BASE_URL}/historical-import`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          bulk_order_id: historicalOrderId,
          confirm_retrospective_training_data_reuse:
            confirmRetrospectiveReuse,
          imported_by: historicalImportedBy.trim(),
          verify_historical_outcomes: verifyHistoricalOutcomes,
          confirm_historical_outcomes_are_actual:
            verifyHistoricalOutcomes && confirmHistoricalOutcomes,
          verified_by: verifyHistoricalOutcomes
            ? historicalVerifiedBy.trim()
            : undefined,
        }),
      });
      const payload: unknown = await response.json();
      if (!response.ok) {
        const apiError = payload as { error?: unknown };
        throw new Error(
          typeof apiError.error === 'string'
            ? apiError.error
            : 'The historical order could not be imported.',
        );
      }
      const result = payload as HistoricalImportResult;
      const conflictText = result.conflicts.length
        ? ` ${result.conflicts.length} conflict(s) were left unchanged.`
        : '';
      setHistoricalImportMessage(
        `${result.bulk_order_id}: ${result.imported_rows} row(s) imported, ` +
          `${result.existing_matching_rows} already present, and ` +
          `${result.verified_rows} verified.${conflictText}`,
      );
      setLoading(true);
      setRefreshVersion((value) => value + 1);
    } catch (requestError: unknown) {
      setHistoricalImportError(
        requestError instanceof Error
          ? requestError.message
          : 'Unable to import the historical order.',
      );
    } finally {
      setImportingHistory(false);
    }
  };

  return (
    <div className={styles.container}>
      <section className={styles.hero}>
        <div>
          <span>Component 3 data collection</span>
          <h1>Daily Monitoring History</h1>
          <p>
            Verify actual factory outcomes, review automatic future labels, and
            track readiness for the three-day early-warning target.
          </p>
        </div>
        <Link href="/component3/monitoring">+ Record another day</Link>
      </section>

      <section className={styles.metrics} aria-label="Monitoring readiness summary">
        <article>
          <span>Total records</span>
          <strong>{NUMBER_FORMATTER.format(readiness?.total_records ?? 0)}</strong>
          <small>All saved Component 3 days</small>
        </article>
        <article>
          <span>Verified records</span>
          <strong>{NUMBER_FORMATTER.format(readiness?.verified_records ?? 0)}</strong>
          <small>Supervisor-confirmed actual outcomes</small>
        </article>
        <article>
          <span>Pending verification</span>
          <strong>
            {NUMBER_FORMATTER.format(
              readiness?.pending_verification_records ?? 0,
            )}
          </strong>
          <small>Cannot be used as training ground truth</small>
        </article>
        <article>
          <span>Ready labels</span>
          <strong>{NUMBER_FORMATTER.format(target?.ready_rows ?? 0)}</strong>
          <small>
            Independent windows;{' '}
            {target?.retrospective_ready_rows_excluded ?? 0} retrospective
            excluded
          </small>
        </article>
      </section>

      <section
        className={`${styles.readinessCard} ${
          target?.general_early_warning_training_ready
            ? styles.readinessReady
            : styles.readinessCollecting
        }`}
      >
        <div>
          <span className={styles.kicker}>General model readiness</span>
          <h2>
            {target?.general_early_warning_training_ready
              ? 'Dataset threshold reached'
              : 'Continue collecting real daily sequences'}
          </h2>
          <p>
            Training uses supervisor-verified actual outcomes only. Model
            detections are retained for comparison, but never become their own
            training labels.
          </p>
        </div>
        <dl>
          <div>
            <dt>Emergency within 3 days</dt>
            <dd>{target?.positive_rows ?? 0}</dd>
          </div>
          <div>
            <dt>No emergency within 3 days</dt>
            <dd>{target?.negative_rows ?? 0}</dd>
          </div>
          <div>
            <dt>Positive orders</dt>
            <dd>{target?.positive_orders ?? 0}</dd>
          </div>
          <div>
            <dt>Negative orders</dt>
            <dd>{target?.negative_orders ?? 0}</dd>
          </div>
        </dl>
      </section>

      <section
        className={`${styles.exportCard} ${
          !exportAudit
            ? styles.exportCollecting
            : exportAudit.leakage_controls.passed
            ? styles.exportPassed
            : styles.exportBlocked
        }`}
      >
        <div className={styles.exportIntro}>
          <span className={styles.kicker}>Step 5A.3 training export</span>
          <h2>
            {exportAudit?.primary_target.training_ready
              ? 'Export is ready for Step 5B evaluation'
              : 'Audited dataset export'}
          </h2>
          <p>
            Only verified Ready source days are exported. Order identity remains
            grouping metadata, while future outcomes and verification fields are
            excluded from model inputs.
          </p>
          <small>
            {exportAudit
              ? `${exportAudit.decision} Sequence check: ${
                  exportAudit.sequence_quality.passed
                    ? 'Passed'
                    : `${exportAudit.sequence_quality.working_day_gap_transitions} gap transition(s)`
                }.`
              : 'Loading export audit...'}
          </small>
        </div>

        <div className={styles.exportMetrics}>
          <div>
            <span>Export rows</span>
            <strong>{exportAudit?.dataset.exported_rows ?? 0}</strong>
          </div>
          <div>
            <span>Independent orders</span>
            <strong>{exportAudit?.dataset.independent_orders ?? 0}</strong>
          </div>
          <div>
            <span>Model features</span>
            <strong>{exportAudit?.schema.model_feature_count ?? 0}</strong>
          </div>
          <div>
            <span>Leakage check</span>
            <strong>
              {exportAudit?.leakage_controls.passed ? 'Passed' : 'Blocked'}
            </strong>
          </div>
        </div>

        <div className={styles.exportActions}>
          {canExport ? (
            <>
              <a href={`${API_BASE_URL}/training-dataset?format=csv`}>
                Download CSV
              </a>
              <a href={`${API_BASE_URL}/training-dataset?format=xlsx`}>
                Download Excel + audit
              </a>
            </>
          ) : (
            <span>
              Verify enough daily sequences to create at least one exportable
              Ready row.
            </span>
          )}
        </div>
      </section>

      <section className={styles.importCard} id="historical-import">
        <div className={styles.importHeader}>
          <div>
            <span className={styles.kicker}>Retrospective data loader</span>
            <h2>Import one historical Component 3 order</h2>
            <p>
              Replays each day in chronological order so the API prediction is
              created before its recorded outcome is attached. Component 2 is
              used only to audit order-master values; Component 3 remains the
              authority when fields disagree.
            </p>
          </div>
          <span className={styles.researchBadge}>
            Demo only · not independent validation
          </span>
        </div>

        <div className={styles.importMetrics}>
          <div>
            <span>Source rows</span>
            <strong>{importPreview?.summary.source_rows ?? 0}</strong>
          </div>
          <div>
            <span>Source orders</span>
            <strong>{importPreview?.summary.source_orders ?? 0}</strong>
          </div>
          <div>
            <span>Importable now</span>
            <strong>{importPreview?.summary.importable_rows ?? 0}</strong>
          </div>
          <div>
            <span>Already present</span>
            <strong>
              {importPreview?.summary.existing_matching_rows ?? 0}
            </strong>
          </div>
        </div>

        <form className={styles.importForm} onSubmit={handleHistoricalImport}>
          {historicalPreviewError && (
            <div className={styles.formError} role="alert">
              Import preview unavailable: {historicalPreviewError}
            </div>
          )}
          <label>
            Historical bulk order
            <select
              value={historicalOrderId}
              onChange={(event) => setHistoricalOrderId(event.target.value)}
              required
            >
              {importPreview?.orders.map((order) => (
                <option key={order.bulk_order_id} value={order.bulk_order_id}>
                  {order.bulk_order_id} · {order.style_id} · {order.source_rows}{' '}
                  days
                </option>
              ))}
            </select>
          </label>
          <label>
            Imported by
            <input
              value={historicalImportedBy}
              onChange={(event) => setHistoricalImportedBy(event.target.value)}
              placeholder="Researcher name or ID"
              maxLength={100}
              required
            />
          </label>

          {selectedHistoricalOrder && (
            <div className={styles.selectedOrderAudit}>
              <span>
                {selectedHistoricalOrder.production_date_from} to{' '}
                {selectedHistoricalOrder.production_date_to}
              </span>
              <span>
                {selectedHistoricalOrder.importable_rows} importable ·{' '}
                {selectedHistoricalOrder.recorded_emergency_days} recorded
                emergency day(s)
              </span>
              <span>
                Component 2 audit:{' '}
                {selectedHistoricalOrder.component2_master.conflicting_fields
                  .length
                  ? `${selectedHistoricalOrder.component2_master.conflicting_fields.length} field conflict(s); Component 3 values will be kept`
                  : 'all compared fields match'}
              </span>
            </div>
          )}

          <label className={styles.importCheck}>
            <input
              type="checkbox"
              checked={confirmRetrospectiveReuse}
              onChange={(event) =>
                setConfirmRetrospectiveReuse(event.target.checked)
              }
            />
            <span>
              I understand this Component 3 workbook trained the current models,
              so the import is a retrospective workflow demo and cannot be
              reported as new independent validation.
            </span>
          </label>

          <label className={styles.importCheck}>
            <input
              type="checkbox"
              checked={verifyHistoricalOutcomes}
              onChange={(event) => {
                setVerifyHistoricalOutcomes(event.target.checked);
                if (!event.target.checked) setConfirmHistoricalOutcomes(false);
              }}
            />
            <span>
              Automatically verify each imported day from the recorded historical
              risk and operational fields.
            </span>
          </label>

          {verifyHistoricalOutcomes && (
            <div className={styles.verificationConsent}>
              <label>
                Historical outcomes reviewed by
                <input
                  value={historicalVerifiedBy}
                  onChange={(event) =>
                    setHistoricalVerifiedBy(event.target.value)
                  }
                  placeholder="Reviewer name or ID"
                  maxLength={120}
                  required
                />
              </label>
              <label className={styles.importCheck}>
                <input
                  type="checkbox"
                  checked={confirmHistoricalOutcomes}
                  onChange={(event) =>
                    setConfirmHistoricalOutcomes(event.target.checked)
                  }
                />
                <span>
                  I confirm the source risk fields are recorded actual historical
                  outcomes and approve their use as retrospective verification.
                </span>
              </label>
            </div>
          )}

          <div className={styles.importActions}>
            <span>
              Existing matching rows are skipped. Conflicting rows are never
              overwritten.
            </span>
            <button
              type="submit"
              disabled={
                importingHistory ||
                !importPreview ||
                !historicalOrderId ||
                !historicalImportedBy.trim() ||
                !confirmRetrospectiveReuse ||
                (verifyHistoricalOutcomes &&
                  (!historicalVerifiedBy.trim() ||
                    !confirmHistoricalOutcomes))
              }
            >
              {importingHistory ? 'Importing order...' : 'Import selected order'}
            </button>
          </div>

          {historicalImportMessage && (
            <div className={styles.success} role="status">
              {historicalImportMessage}
            </div>
          )}
          {historicalImportError && (
            <div className={styles.formError} role="alert">
              {historicalImportError}
            </div>
          )}
        </form>
      </section>

      <section className={styles.validationCard}>
        <div className={styles.validationHeader}>
          <div>
            <span className={styles.kicker}>Step 5D.1 validation report</span>
            <h2>Stored early warnings vs verified outcomes</h2>
            <p>
              Scores use the prediction saved before verification. Independent
              orders and retrospective training-data reuse are reported
              separately and never combined.
            </p>
          </div>
          <span className={styles.validationBadge}>
            Stored predictions only · no rescoring
          </span>
        </div>

        {validationReportError && (
          <div className={styles.formError} role="alert">
            Validation report unavailable: {validationReportError}
          </div>
        )}

        {validationReport && (
          <div className={styles.validationScopes}>
            {[
              {
                title: 'Independent validation',
                note: 'New unseen real orders',
                className: styles.scopeIndependent,
                report: validationReport.independent_validation,
                emptyTitle: 'Independent validation pending',
                emptyDescription:
                  'No new unseen order has completed the verified three-day evaluation window yet.',
                emptySteps: [
                  'Save consecutive daily records from a new order',
                  'Verify the recorded actual outcomes',
                  'Collect both risk and no-risk target outcomes',
                ],
                emptyNote:
                  'Historical imports remain in the retrospective panel and cannot fill independent validation.',
              },
              {
                title: 'Retrospective workflow evidence',
                note: 'Previously used model-development data',
                className: styles.scopeRetrospective,
                report: validationReport.retrospective_training_reuse,
                emptyTitle: 'Retrospective evaluation pending',
                emptyDescription:
                  'No imported historical source day currently has a verified three-day outcome window.',
                emptySteps: [
                  'Import one historical order chronologically',
                  'Verify its recorded historical outcomes',
                  'Complete an eligible three-day label window',
                ],
                emptyNote:
                  'This evidence demonstrates the workflow only and never counts as independent validation.',
              },
            ].map((scope) => (
              <article
                className={`${styles.validationScope} ${scope.className}`}
                key={scope.report.scope}
              >
                <div className={styles.scopeHeader}>
                  <div>
                    <h3>{scope.title}</h3>
                    <p>{scope.note}</p>
                  </div>
                  <span>
                    {scope.report.status === 'evaluated'
                      ? 'Both classes available'
                      : scope.report.status ===
                          'insufficient_class_coverage'
                        ? 'More class coverage needed'
                        : 'Awaiting evaluable rows'}
                  </span>
                </div>

                <div className={styles.scopeMetrics}>
                  <div>
                    <span>Evaluated rows</span>
                    <strong>{scope.report.ready_warning_rows}</strong>
                  </div>
                  <div>
                    <span>Orders</span>
                    <strong>{scope.report.orders_evaluated}</strong>
                  </div>
                  <div>
                    <span>Production approval</span>
                    <strong>No</strong>
                  </div>
                </div>

                {scope.report.ready_warning_rows === 0 ? (
                  <div className={styles.validationEmptyState} role="status">
                    <div className={styles.validationEmptyHeading}>
                      <span aria-hidden="true">○</span>
                      <div>
                        <h4>{scope.emptyTitle}</h4>
                        <p>{scope.emptyDescription}</p>
                      </div>
                    </div>
                    <ol>
                      {scope.emptySteps.map((step) => (
                        <li key={step}>{step}</li>
                      ))}
                    </ol>
                    <small>{scope.emptyNote}</small>
                  </div>
                ) : (
                  <div className={styles.validationTableWrap}>
                    <table>
                      <thead>
                        <tr>
                          <th>Target</th>
                          <th>Actual + / −</th>
                          <th>Accuracy</th>
                          <th>Macro-F1</th>
                          <th>F1</th>
                        </tr>
                      </thead>
                      <tbody>
                        {scope.report.targets.map((targetResult) => (
                          <tr key={targetResult.target}>
                            <td>
                              <strong>{targetResult.display_name}</strong>
                              <small>{targetResult.rows_evaluated} rows</small>
                            </td>
                            <td>
                              {targetResult.positive_actual_rows} /{' '}
                              {targetResult.negative_actual_rows}
                              {!targetResult.class_coverage_complete &&
                                targetResult.rows_evaluated > 0 && (
                                  <small className={styles.classWarning}>
                                    One actual class only
                                  </small>
                                )}
                            </td>
                            <td>
                              {formatMetric(targetResult.metrics?.accuracy)}
                            </td>
                            <td>
                              {formatMetric(targetResult.metrics?.macro_f1)}
                            </td>
                            <td>{formatMetric(targetResult.metrics?.f1)}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </article>
            ))}
          </div>
        )}

        <p className={styles.validationFootnote}>
          A score calculated from one actual class, or from data reused during
          model development, is not independent production evidence. Production
          validation requires new unseen orders containing positive and negative
          outcomes for every target.
        </p>
      </section>

      {selectedRecord && (
        <section className={styles.verificationCard}>
          <div className={styles.verificationHeader}>
            <div>
              <span className={styles.kicker}>Supervisor ground truth</span>
              <h2>
                {selectedRecord.actual_outcome_status === 'Verified'
                  ? 'Correct actual outcome'
                  : 'Verify actual outcome'}
              </h2>
              <p>
                {selectedRecord.bulk_order_id} · {selectedRecord.production_date}{' '}
                · working day {selectedRecord.working_day_no}. The system detected{' '}
                <strong>{selectedRecord.risk_type}</strong>; confirm what actually
                happened in the factory.
              </p>
              {!selectedRecord.independent_validation_eligible && (
                <p>
                  This is a retrospective training-data reuse record. Corrections
                  remain auditable but do not count as independent validation.
                </p>
              )}
            </div>
            <button type="button" onClick={closeVerification}>
              Cancel
            </button>
          </div>

          <form onSubmit={handleVerification}>
            <label>
              Actual emergency
              <select
                value={actualEmergency}
                onChange={(event) => {
                  setActualEmergency(event.target.value);
                  if (event.target.value !== 'true') {
                    setActualEmergencyType('');
                  }
                }}
                required
              >
                <option value="">Select actual outcome</option>
                <option value="false">No actual emergency</option>
                <option value="true">Yes, an emergency occurred</option>
              </select>
            </label>
            <label>
              Actual emergency type
              <select
                value={actualEmergencyType}
                onChange={(event) => setActualEmergencyType(event.target.value)}
                required={actualEmergency === 'true'}
                disabled={actualEmergency !== 'true'}
              >
                <option value="">Select emergency type</option>
                {ACTUAL_EMERGENCY_TYPES.map((emergencyType) => (
                  <option key={emergencyType} value={emergencyType}>
                    {emergencyType}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Verified by
              <input
                value={verifiedBy}
                onChange={(event) => setVerifiedBy(event.target.value)}
                placeholder="Factory supervisor name or ID"
                maxLength={120}
                required
              />
            </label>
            <label className={styles.notesField}>
              Verification notes
              <textarea
                value={verificationNotes}
                onChange={(event) => setVerificationNotes(event.target.value)}
                placeholder="Optional maintenance log, attendance, quality, or shift evidence"
                maxLength={2000}
                rows={3}
              />
            </label>
            <div className={styles.verificationActions}>
              <span>
                {selectedRecord.actual_outcome_status === 'Verified'
                  ? 'This correction will be added to the audit history.'
                  : 'This confirmation controls future training labels.'}
              </span>
              <button
                type="submit"
                disabled={
                  savingVerification ||
                  !actualEmergency ||
                  !verifiedBy.trim() ||
                  (actualEmergency === 'true' && !actualEmergencyType)
                }
              >
                {savingVerification
                  ? 'Saving verification...'
                  : 'Save verified outcome'}
              </button>
            </div>
            {verificationError && (
              <div className={styles.formError} role="alert">
                {verificationError}
              </div>
            )}
          </form>
        </section>
      )}

      <section className={styles.historyCard}>
        <div className={styles.cardHeader}>
          <div>
            <span className={styles.kicker}>Saved observations</span>
            <h2>{total} matching record{total === 1 ? '' : 's'}</h2>
          </div>
          <button
            type="button"
            onClick={() => {
              setLoading(true);
              setRefreshVersion((value) => value + 1);
            }}
          >
            Refresh
          </button>
        </div>

        {verificationMessage && (
          <div className={styles.success} role="status">
            {verificationMessage}
          </div>
        )}

        <div className={styles.filters}>
          <label>
            Bulk order
            <input
              value={orderFilter}
              onChange={(event) => setOrderFilter(event.target.value)}
              placeholder="e.g. BULK0001"
            />
          </label>
          <label>
            Current risk
            <select
              value={riskFilter}
              onChange={(event) => setRiskFilter(event.target.value)}
            >
              <option value="">All</option>
              <option value="No Risk">No Risk</option>
              <option value="Risk">Risk</option>
            </select>
          </label>
          <label>
            Verification
            <select
              value={verificationFilter}
              onChange={(event) => setVerificationFilter(event.target.value)}
            >
              <option value="">All</option>
              <option value="Pending">Pending</option>
              <option value="Verified">Verified</option>
            </select>
          </label>
          <label>
            Label status
            <select
              value={labelFilter}
              onChange={(event) => setLabelFilter(event.target.value)}
            >
              <option value="">All</option>
              <option value="Awaiting Verification">
                Awaiting Verification
              </option>
              <option value="Waiting">Waiting</option>
              <option value="Ready">Ready</option>
              <option value="Not Eligible">Not Eligible</option>
              <option value="Censored">Censored</option>
              <option value="Incomplete">Incomplete</option>
            </select>
          </label>
        </div>

        {error && <div className={styles.error} role="alert">{error}</div>}

        {loading ? (
          <div className={styles.empty}>Loading daily monitoring records...</div>
        ) : records.length === 0 ? (
          <div className={styles.empty}>
            <strong>No monitoring records found.</strong>
            <span>Run an analysis and use Save daily record to start collecting data.</span>
          </div>
        ) : (
          <div className={styles.tableWrap}>
            <table>
              <thead>
                <tr>
                  <th>Production day</th>
                  <th>Order</th>
                  <th>System detection</th>
                  <th>Output</th>
                  <th>Verified actual outcome</th>
                  <th>Label status</th>
                  <th>Future outcome</th>
                  <th>Recorded by</th>
                </tr>
              </thead>
              <tbody>
                {records.map((record) => (
                  <tr key={record.record_id}>
                    <td>
                      <strong>{record.production_date}</strong>
                      <span>Working day {record.working_day_no}</span>
                    </td>
                    <td>
                      <strong>{record.bulk_order_id}</strong>
                      <span>{record.style_id}</span>
                    </td>
                    <td>
                      <span
                        className={`${styles.riskBadge} ${
                          record.is_emergency ? styles.risk : styles.noRisk
                        }`}
                      >
                        {record.risk_status}
                      </span>
                      <small>{record.risk_type}</small>
                    </td>
                    <td>
                      <strong>{NUMBER_FORMATTER.format(record.plant_daily_output)}</strong>
                      <span>of {NUMBER_FORMATTER.format(record.daily_commitment)}</span>
                    </td>
                    <td>
                      <span
                        className={`${styles.verificationBadge} ${
                          record.actual_outcome_status === 'Verified'
                            ? styles.verified
                            : styles.pending
                        }`}
                      >
                        {record.actual_outcome_status}
                      </span>
                      {record.actual_outcome_status === 'Verified' && (
                        <small>
                          {record.actual_emergency
                            ? record.actual_emergency_type
                            : 'No actual emergency'}
                          {' · '}
                          {record.verified_by}
                        </small>
                      )}
                      <button
                        className={styles.verifyButton}
                        type="button"
                        onClick={() => openVerification(record)}
                      >
                        {record.actual_outcome_status === 'Verified'
                          ? 'Correct'
                          : 'Verify'}
                      </button>
                    </td>
                    <td>
                      <span className={`${styles.labelBadge} ${labelClass(record.label_status)}`}>
                        {record.label_status}
                      </span>
                    </td>
                    <td className={styles.futureOutcome}>{futureOutcome(record)}</td>
                    <td>
                      <strong>{record.recorded_by}</strong>
                      <span>{new Date(record.created_at).toLocaleString()}</span>
                      {!record.independent_validation_eligible && (
                        <small className={styles.retrospectiveTag}>
                          Retrospective · excluded from independent validation
                        </small>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </div>
  );
}
