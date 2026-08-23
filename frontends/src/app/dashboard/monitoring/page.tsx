'use client';

import { useState } from 'react';
import Link from 'next/link';
import styles from './monitoring.module.css';

type NumericValue = number | '';

interface MonitoringFormData {
  bulk_order_id: string;
  style_id: string;
  buyer_name: string;
  allocated_bulk_plant: string;
  plant_location: string;
  full_order_qty: NumericValue;
  bulk_order_approved_date: string;
  buyer_required_date: string;
  total_working_days: NumericValue;
  cutting_days: NumericValue;
  sewing_days: NumericValue;
  daily_commitment: NumericValue;
  production_date: string;
  working_day_no: NumericValue;
  plant_daily_output: NumericValue;
  daily_damage_qty: NumericValue;
  max_daily_damage_qty: NumericValue;
  machine_breakdown_count: NumericValue;
  worker_shortage_count: NumericValue;
  cumulative_completed_qty: NumericValue;
}

interface RecoveryFormData {
  planned_worker_count: NumericValue;
  planned_machine_count: NumericValue;
  normal_shift_hours: NumericValue;
  max_overtime_hours_per_day: NumericValue;
  max_additional_workers: NumericValue;
  available_backup_machines: NumericValue;
  backup_line_daily_capacity: NumericValue;
  expected_machine_repair_hours: NumericValue;
}

interface RecoveryOption {
  option_id: string;
  title: string;
  feasible_before_deadline: boolean;
  rationale: string;
  daily_capacity?: number;
  daily_capacity_gain?: number;
  required_overtime_hours_per_day?: number;
  additional_workers?: number;
  repaired_machines?: number;
  expected_machine_repair_hours?: number;
  backup_machines?: number;
  backup_line_daily_capacity_used?: number;
  required_working_days?: number | null;
  projected_completion_date?: string | null;
  deadline_margin_working_days?: number | null;
  external_daily_capacity_required?: number | null;
}

interface RecoveryPlan {
  engine_version: string;
  status: 'completed' | 'deadline_passed' | 'on_track' | 'recovery_required';
  triggered_by: string[];
  remaining_quantity: number;
  available_working_days: number;
  required_daily_rate: number | null;
  current_daily_capacity: number;
  daily_recovery_gap: number | null;
  missing_parameters: string[];
  recommended_option: RecoveryOption | null;
  alternatives: RecoveryOption[];
  manual_escalation_required: boolean;
  assumptions: string[];
}

type EarlyWarningStatus =
  | 'available'
  | 'not_applicable_current_emergency'
  | 'unavailable';

interface EarlyWarningItem {
  target: string;
  display_name: string;
  probability: number;
  probability_pct: number;
  decision_threshold: number;
  warning_predicted: boolean;
  model_name: string;
  validation_metrics: {
    accuracy: number;
    macro_f1: number;
    f1: number;
  };
  preparation: string;
}

interface EarlyWarningResult {
  inference_version: string;
  status: EarlyWarningStatus;
  production_approved: boolean;
  horizon_production_days: number;
  current_risk_type: string;
  alert_generated: boolean;
  highest_warning: {
    target: string;
    display_name: string;
    probability: number;
    probability_pct: number;
  } | null;
  warnings: EarlyWarningItem[];
  history: {
    source: string;
    saved_prior_records: number;
    feature_history_days: number;
    maximum_feature_history_days: number;
    status: 'complete' | 'partial' | 'current_only' | 'gapped';
    working_day_gap_detected: boolean;
    working_day_gap_transitions: number;
    latest_prior_working_day: number | null;
    future_or_current_saved_rows_used: number;
  } | null;
  message: string;
  limitations: string[];
}

interface MonitoringResponse {
  status: string;
  model_version: string;
  bulk_order_id: string;
  style_id: string;
  buyer_name: string;
  allocated_bulk_plant: string;
  plant_location: string;
  production_date: string;
  working_day_no: number;
  order_summary: {
    full_order_qty: number;
    daily_commitment: number;
    cumulative_completed_qty: number;
    remaining_qty: number;
    completion_pct: number;
    total_working_days: number;
    cutting_days: number;
    sewing_days: number;
  };
  daily_production: {
    plant_daily_output: number;
    daily_commitment: number;
    output_gap: number;
    gap_pct: number;
    daily_damage_qty: number;
    max_daily_damage_qty: number;
    damage_exceeded: boolean;
    damage_pct_of_commitment: number;
    machine_breakdown_count: number;
    worker_shortage_count: number;
  };
  risk_detection: {
    risk_status: string;
    risk_type: string;
    risk_confidence: number;
    severity: string | null;
    alert_colour: string;
    gap_severity_label: string;
    order_risk_level: string;
    ml_order_risk_level: string;
    schedule_order_risk_level: string;
    order_risk_probability: number;
    recommendation: string;
  };
  alert_system: {
    alert_generated: boolean;
    alert_targets: string[];
    notify_via: string[];
    display_on: string[];
  };
  scheduling: {
    bulk_order_approved_date: string;
    bulk_start_date: string;
    buyer_required_date: string;
    projected_completion_date: string;
    days_to_deadline: number;
    working_days_remaining: number;
    on_track: boolean;
  };
  order_progress: {
    order_risk_level: string;
    ml_order_risk_level: string;
    schedule_order_risk_level: string;
    completion_pct: number;
    days_elapsed_pct: number;
    progress_gap_pct: number;
    progress_summary: string;
  };
  production_summary: {
    daily_commitment: number;
    actual_output: number;
    output_gap: number;
    gap_pct: number;
    required_daily_rate: number;
    cumulative_completed: number;
    remaining_qty: number;
  };
  action: {
    recommendation: string;
    action_required: string;
    escalation_needed: boolean;
    alert_recipients: string[];
    notify_channels: string[];
    next_step: string;
    store_for_ml_training: boolean;
  };
  recovery_plan: RecoveryPlan;
  early_warning: EarlyWarningResult;
}

interface FieldDefinition {
  name: keyof MonitoringFormData;
  label: string;
  type?: 'text' | 'number' | 'date';
  min?: number;
  step?: number;
  helper?: string;
  readOnly?: boolean;
}

interface RecoveryFieldDefinition {
  name: keyof RecoveryFormData;
  label: string;
  min: number;
  step?: number;
  helper: string;
}

const API_BASE_URL = (
  process.env.NEXT_PUBLIC_COMPONENT3_API_URL ??
  'http://127.0.0.1:5001/api/component3'
).replace(/\/$/, '');

function countWorkingDaysInclusive(start: string, end: string): NumericValue {
  if (!start || !end) return '';

  const startDate = new Date(`${start}T00:00:00Z`);
  const endDate = new Date(`${end}T00:00:00Z`);
  if (
    Number.isNaN(startDate.getTime()) ||
    Number.isNaN(endDate.getTime()) ||
    endDate < startDate
  ) {
    return '';
  }

  let workingDays = 0;
  const cursor = new Date(startDate);
  while (cursor <= endDate) {
    const day = cursor.getUTCDay();
    if (day !== 0 && day !== 6) workingDays += 1;
    cursor.setUTCDate(cursor.getUTCDate() + 1);
  }
  return workingDays;
}

function validateTimeline(data: MonitoringFormData): string | null {
  const approved = new Date(`${data.bulk_order_approved_date}T00:00:00Z`);
  const production = new Date(`${data.production_date}T00:00:00Z`);
  const required = new Date(`${data.buyer_required_date}T00:00:00Z`);
  if (
    Number.isNaN(approved.getTime()) ||
    Number.isNaN(production.getTime()) ||
    Number.isNaN(required.getTime())
  ) {
    return 'Enter all three timeline dates.';
  }
  if (required < approved) {
    return 'Buyer-required date cannot be before the order-approved date.';
  }
  if (production < approved || production > required) {
    return 'Production date must be between the approved and buyer-required dates.';
  }
  if (production.getUTCDay() === 0 || production.getUTCDay() === 6) {
    return 'Production date must be a Monday-Friday factory working day.';
  }
  if (data.total_working_days === '' || data.total_working_days < 1) {
    return 'The selected date range contains no Monday-Friday working days.';
  }
  if (data.cutting_days !== '' && data.cutting_days > data.total_working_days) {
    return 'Cutting days cannot exceed total working days.';
  }
  if (data.sewing_days !== '' && data.sewing_days > data.total_working_days) {
    return 'Sewing days cannot exceed total working days.';
  }
  return null;
}

const INITIAL_FORM: MonitoringFormData = {
  bulk_order_id: 'BULK0015',
  style_id: 'KM327296',
  buyer_name: 'Tesco',
  allocated_bulk_plant: 'Dinusha Embroidery',
  plant_location: 'Weliweriya',
  full_order_qty: 26_499,
  bulk_order_approved_date: '2024-07-12',
  buyer_required_date: '2024-10-20',
  total_working_days: 71,
  cutting_days: 14,
  sewing_days: 20,
  daily_commitment: 750,
  production_date: '2024-07-19',
  working_day_no: 1,
  plant_daily_output: 750,
  daily_damage_qty: 22,
  max_daily_damage_qty: 23,
  machine_breakdown_count: 0,
  worker_shortage_count: 0,
  cumulative_completed_qty: 770,
};

const INITIAL_RECOVERY_FORM: RecoveryFormData = {
  planned_worker_count: 50,
  planned_machine_count: 40,
  normal_shift_hours: 8,
  max_overtime_hours_per_day: 2,
  max_additional_workers: 5,
  available_backup_machines: 2,
  backup_line_daily_capacity: 150,
  expected_machine_repair_hours: 4,
};

const EMPTY_RECOVERY_FORM: RecoveryFormData = {
  planned_worker_count: '',
  planned_machine_count: '',
  normal_shift_hours: '',
  max_overtime_hours_per_day: '',
  max_additional_workers: '',
  available_backup_machines: '',
  backup_line_daily_capacity: '',
  expected_machine_repair_hours: '',
};

function localWorkingIsoDate() {
  const now = new Date();
  const localTime = new Date(now.getTime() - now.getTimezoneOffset() * 60_000);
  if (localTime.getUTCDay() === 6) {
    localTime.setUTCDate(localTime.getUTCDate() - 1);
  } else if (localTime.getUTCDay() === 0) {
    localTime.setUTCDate(localTime.getUTCDate() - 2);
  }
  return localTime.toISOString().slice(0, 10);
}

function createCurrentOrderForm(): MonitoringFormData {
  return {
    bulk_order_id: '',
    style_id: '',
    buyer_name: '',
    allocated_bulk_plant: '',
    plant_location: '',
    full_order_qty: '',
    bulk_order_approved_date: '',
    buyer_required_date: '',
    total_working_days: '',
    cutting_days: '',
    sewing_days: '',
    daily_commitment: '',
    production_date: localWorkingIsoDate(),
    working_day_no: 1,
    plant_daily_output: '',
    daily_damage_qty: 0,
    max_daily_damage_qty: '',
    machine_breakdown_count: 0,
    worker_shortage_count: 0,
    cumulative_completed_qty: '',
  };
}

const BULK_1_ORDER = {
  bulk_order_id: 'BULK0001',
  style_id: 'AH2495',
  buyer_name: 'Hirdaramani',
  allocated_bulk_plant: 'Sunrose Lanka (Pvt) Ltd',
  plant_location: 'Katubedda',
  full_order_qty: 46_430,
  bulk_order_approved_date: '2024-06-29',
  buyer_required_date: '2024-11-27',
  total_working_days: 108,
  cutting_days: 25,
  sewing_days: 30,
  daily_commitment: 430,
};

const SCENARIOS: Array<{
  label: string;
  description: string;
  values: MonitoringFormData;
  recoveryValues: RecoveryFormData;
}> = [
  {
    label: 'Healthy line',
    description: 'Output is above commitment with stable resources.',
    values: INITIAL_FORM,
    recoveryValues: INITIAL_RECOVERY_FORM,
  },
  {
    label: 'Worker pressure',
    description: 'A staffing shortage is reducing daily output.',
    values: {
      ...INITIAL_FORM,
      ...BULK_1_ORDER,
      production_date: '2024-07-02',
      working_day_no: 2,
      plant_daily_output: 407,
      daily_damage_qty: 10,
      max_daily_damage_qty: 13,
      machine_breakdown_count: 0,
      worker_shortage_count: 3,
      cumulative_completed_qty: 845,
    },
    recoveryValues: {
      ...INITIAL_RECOVERY_FORM,
      planned_worker_count: 50,
      max_additional_workers: 3,
    },
  },
  {
    label: 'Machine event',
    description: 'Breakdowns create a significant production gap.',
    values: {
      ...INITIAL_FORM,
      ...BULK_1_ORDER,
      production_date: '2024-08-01',
      working_day_no: 24,
      plant_daily_output: 265,
      daily_damage_qty: 14,
      max_daily_damage_qty: 13,
      machine_breakdown_count: 2,
      worker_shortage_count: 0,
      cumulative_completed_qty: 9_722,
    },
    recoveryValues: {
      ...INITIAL_RECOVERY_FORM,
      planned_machine_count: 40,
      available_backup_machines: 2,
      expected_machine_repair_hours: 4,
    },
  },
  {
    label: 'Quality pressure',
    description: 'Daily damage exceeds the accepted quality limit.',
    values: {
      ...INITIAL_FORM,
      ...BULK_1_ORDER,
      production_date: '2024-09-09',
      working_day_no: 51,
      plant_daily_output: 436,
      daily_damage_qty: 18,
      max_daily_damage_qty: 13,
      machine_breakdown_count: 0,
      worker_shortage_count: 0,
      cumulative_completed_qty: 20_825,
    },
    recoveryValues: INITIAL_RECOVERY_FORM,
  },
  {
    label: 'Critical delay',
    description: 'Large output and schedule gaps require escalation.',
    values: {
      ...INITIAL_FORM,
      ...BULK_1_ORDER,
      production_date: '2024-07-04',
      working_day_no: 4,
      plant_daily_output: 348,
      daily_damage_qty: 13,
      max_daily_damage_qty: 13,
      machine_breakdown_count: 0,
      worker_shortage_count: 0,
      cumulative_completed_qty: 1_605,
    },
    recoveryValues: {
      ...INITIAL_RECOVERY_FORM,
      max_overtime_hours_per_day: 3,
      backup_line_daily_capacity: 200,
    },
  },
];

const IDENTIFICATION_FIELDS: FieldDefinition[] = [
  { name: 'bulk_order_id', label: 'Bulk order ID' },
  { name: 'style_id', label: 'Style ID' },
  { name: 'buyer_name', label: 'Buyer name' },
  { name: 'allocated_bulk_plant', label: 'Allocated plant' },
  { name: 'plant_location', label: 'Plant location' },
];

const PRODUCTION_FIELDS: FieldDefinition[] = [
  { name: 'full_order_qty', label: 'Full order quantity', type: 'number', min: 1 },
  { name: 'daily_commitment', label: 'Daily commitment', type: 'number', min: 1 },
  { name: 'plant_daily_output', label: 'Actual daily output', type: 'number', min: 0 },
  { name: 'cumulative_completed_qty', label: 'Cumulative completed', type: 'number', min: 0 },
  { name: 'daily_damage_qty', label: 'Daily damage quantity', type: 'number', min: 0 },
  { name: 'max_daily_damage_qty', label: 'Maximum allowed damage', type: 'number', min: 0 },
  { name: 'machine_breakdown_count', label: 'Machine breakdowns', type: 'number', min: 0 },
  { name: 'worker_shortage_count', label: 'Worker shortage', type: 'number', min: 0 },
];

const TIMELINE_FIELDS: FieldDefinition[] = [
  {
    name: 'total_working_days',
    label: 'Total working days',
    type: 'number',
    min: 1,
    readOnly: true,
    helper:
      'Automatically calculated from the approved date through the buyer-required date (Monday-Friday, inclusive; public holidays are not excluded).',
  },
  { name: 'working_day_no', label: 'Current working day', type: 'number', min: 1 },
  { name: 'cutting_days', label: 'Cutting days', type: 'number', min: 0 },
  { name: 'sewing_days', label: 'Sewing days', type: 'number', min: 0 },
  { name: 'bulk_order_approved_date', label: 'Order approved date', type: 'date' },
  { name: 'production_date', label: 'Production date', type: 'date' },
  { name: 'buyer_required_date', label: 'Buyer required date', type: 'date' },
];

const RECOVERY_FIELDS: RecoveryFieldDefinition[] = [
  {
    name: 'planned_worker_count',
    label: 'Planned workers',
    min: 1,
    helper: 'Normal worker count allocated to this line.',
  },
  {
    name: 'max_additional_workers',
    label: 'Workers available to add',
    min: 0,
    helper: 'Maximum operators that can be reassigned.',
  },
  {
    name: 'planned_machine_count',
    label: 'Planned machines',
    min: 1,
    helper: 'Normal number of machines for this line.',
  },
  {
    name: 'available_backup_machines',
    label: 'Backup machines available',
    min: 0,
    helper: 'Ready machines that can be activated.',
  },
  {
    name: 'normal_shift_hours',
    label: 'Normal shift hours',
    min: 0.25,
    step: 0.25,
    helper: 'Hours in the standard production shift.',
  },
  {
    name: 'max_overtime_hours_per_day',
    label: 'Maximum OT hours/day',
    min: 0,
    step: 0.25,
    helper: 'Daily overtime limit approved by the plant.',
  },
  {
    name: 'backup_line_daily_capacity',
    label: 'Backup line capacity/day',
    min: 0,
    step: 1,
    helper: 'Pieces another line can accept per day.',
  },
  {
    name: 'expected_machine_repair_hours',
    label: 'Expected repair hours',
    min: 0,
    step: 0.25,
    helper: 'Estimated time to restore failed machines.',
  },
];

const NUMBER_FORMATTER = new Intl.NumberFormat('en-US');

function formatNumber(value: number) {
  return NUMBER_FORMATTER.format(value);
}

function formatCapacity(value: number | null | undefined) {
  if (value === null || value === undefined) return 'Not available';
  return NUMBER_FORMATTER.format(Number(value.toFixed(2)));
}

function clampPercentage(value: number) {
  return Math.min(100, Math.max(0, value));
}

function riskTone(level: string) {
  const normalized = level.toLowerCase();
  if (normalized === 'critical' || normalized === 'high') return styles.critical;
  if (normalized === 'moderate' || normalized === 'medium') return styles.warning;
  if (normalized === 'minor') return styles.minor;
  return styles.safe;
}

function recoveryStatusLabel(status: RecoveryPlan['status']) {
  const labels: Record<RecoveryPlan['status'], string> = {
    completed: 'Order completed',
    deadline_passed: 'Deadline passed',
    on_track: 'Current plan is feasible',
    recovery_required: 'Recovery required',
  };
  return labels[status];
}

function earlyWarningStatusLabel(warning: EarlyWarningResult) {
  if (warning.status === 'not_applicable_current_emergency') {
    return 'Current emergency active';
  }
  if (warning.status === 'unavailable') return 'Models unavailable';
  return warning.alert_generated ? 'Warning threshold crossed' : 'Below thresholds';
}

function historyStatusLabel(history: EarlyWarningResult['history']) {
  if (!history) return 'Not evaluated';
  const labels: Record<NonNullable<EarlyWarningResult['history']>['status'], string> = {
    complete: 'Complete 3-day feature history',
    partial: 'Partial saved history',
    current_only: 'Current day only',
    gapped: 'Saved history has gaps',
  };
  return labels[history.status];
}

function recoveryParameters(data: RecoveryFormData) {
  return Object.fromEntries(
    Object.entries(data).filter(([, value]) => value !== ''),
  );
}

function RecoveryOptionCard({
  option,
  recommended = false,
}: {
  option: RecoveryOption;
  recommended?: boolean;
}) {
  const resourceMetrics = [
    option.additional_workers
      ? { label: 'Add workers', value: String(option.additional_workers) }
      : null,
    option.required_overtime_hours_per_day
      ? {
          label: 'OT hours / day',
          value: formatCapacity(option.required_overtime_hours_per_day),
        }
      : null,
    option.repaired_machines
      ? { label: 'Repair machines', value: String(option.repaired_machines) }
      : null,
    option.repaired_machines && option.expected_machine_repair_hours !== undefined
      ? {
          label: 'Expected repair time',
          value: `${formatCapacity(option.expected_machine_repair_hours)} hr`,
        }
      : null,
    option.backup_machines
      ? { label: 'Backup machines', value: String(option.backup_machines) }
      : null,
    option.backup_line_daily_capacity_used
      ? {
          label: 'Backup line / day',
          value: formatCapacity(option.backup_line_daily_capacity_used),
        }
      : null,
    option.external_daily_capacity_required !== undefined &&
    option.external_daily_capacity_required !== null
      ? {
          label: 'External capacity / day',
          value: formatCapacity(option.external_daily_capacity_required),
        }
      : null,
  ].filter((metric): metric is { label: string; value: string } => metric !== null);

  return (
    <article
      className={`${styles.recoveryOption} ${
        recommended ? styles.recommendedOption : ''
      }`}
    >
      <div className={styles.optionHeading}>
        <div>
          {recommended && <span className={styles.recommendedLabel}>Recommended</span>}
          <h4>{option.title}</h4>
        </div>
        <span
          className={`${styles.feasibilityBadge} ${
            option.feasible_before_deadline
              ? styles.feasibleBadge
              : styles.infeasibleBadge
          }`}
        >
          {option.feasible_before_deadline ? 'Deadline feasible' : 'Not sufficient'}
        </span>
      </div>

      <p>{option.rationale}</p>

      {resourceMetrics.length > 0 && (
        <div className={styles.resourceMetrics}>
          {resourceMetrics.map((metric) => (
            <div key={metric.label}>
              <span>{metric.label}</span>
              <strong>{metric.value}</strong>
            </div>
          ))}
        </div>
      )}

      {(option.daily_capacity !== undefined || option.projected_completion_date) && (
        <dl className={styles.optionForecast}>
          {option.daily_capacity !== undefined && (
            <div>
              <dt>Recovered daily capacity</dt>
              <dd>{formatCapacity(option.daily_capacity)} pieces</dd>
            </div>
          )}
          {option.daily_capacity_gain !== undefined && (
            <div>
              <dt>Daily capacity gain</dt>
              <dd>+{formatCapacity(option.daily_capacity_gain)} pieces</dd>
            </div>
          )}
          {option.required_working_days !== undefined &&
            option.required_working_days !== null && (
              <div>
                <dt>Working days required</dt>
                <dd>{option.required_working_days}</dd>
              </div>
            )}
          {option.projected_completion_date && (
            <div>
              <dt>New completion date</dt>
              <dd>{option.projected_completion_date}</dd>
            </div>
          )}
          {option.deadline_margin_working_days !== undefined &&
            option.deadline_margin_working_days !== null && (
              <div>
                <dt>Deadline margin</dt>
                <dd>
                  {option.deadline_margin_working_days >= 0 ? '+' : ''}
                  {option.deadline_margin_working_days} working day(s)
                </dd>
              </div>
            )}
        </dl>
      )}
    </article>
  );
}

export default function MonitoringPage() {
  const [formData, setFormData] = useState<MonitoringFormData>(INITIAL_FORM);
  const [recoveryData, setRecoveryData] = useState<RecoveryFormData>(
    INITIAL_RECOVERY_FORM,
  );
  const [result, setResult] = useState<MonitoringResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [trackingActor, setTrackingActor] = useState('Production Manager');
  const [savingDailyRecord, setSavingDailyRecord] = useState(false);
  const [savedDailyRecordId, setSavedDailyRecordId] = useState('');
  const [dailyRecordError, setDailyRecordError] = useState('');
  const [savingIncident, setSavingIncident] = useState(false);
  const [savedIncidentId, setSavedIncidentId] = useState('');
  const [trackingError, setTrackingError] = useState('');
  const [formMode, setFormMode] = useState<'demo' | 'current'>('demo');
  const [analysisInvalidated, setAnalysisInvalidated] = useState(false);

  const invalidateAnalysis = () => {
    if (result) setAnalysisInvalidated(true);
    setResult(null);
    setError('');
    setSavedDailyRecordId('');
    setDailyRecordError('');
    setSavedIncidentId('');
    setTrackingError('');
  };

  const handleChange = (event: React.ChangeEvent<HTMLInputElement>) => {
    const { name, value, type } = event.currentTarget;
    const field = name as keyof MonitoringFormData;
    const nextValue = type === 'number' ? (value === '' ? '' : Number(value)) : value;

    invalidateAnalysis();
    setFormData((previous) => {
      const next = { ...previous, [field]: nextValue } as MonitoringFormData;
      if (
        field === 'bulk_order_approved_date' ||
        field === 'buyer_required_date'
      ) {
        next.total_working_days = countWorkingDaysInclusive(
          next.bulk_order_approved_date,
          next.buyer_required_date,
        );
      }
      return next;
    });
  };

  const handleRecoveryChange = (event: React.ChangeEvent<HTMLInputElement>) => {
    const { name, value } = event.currentTarget;
    const field = name as keyof RecoveryFormData;
    invalidateAnalysis();
    setRecoveryData((previous) => ({
      ...previous,
      [field]: value === '' ? '' : Number(value),
    }));
  };

  const selectScenario = (scenario: (typeof SCENARIOS)[number]) => {
    setFormData({ ...scenario.values });
    setRecoveryData({ ...scenario.recoveryValues });
    setFormMode('demo');
    setAnalysisInvalidated(false);
    setResult(null);
    setError('');
    setSavedDailyRecordId('');
    setDailyRecordError('');
    setSavedIncidentId('');
    setTrackingError('');
  };

  const startCurrentOrder = () => {
    setFormData(createCurrentOrderForm());
    setRecoveryData({ ...EMPTY_RECOVERY_FORM });
    setFormMode('current');
    setAnalysisInvalidated(false);
    setResult(null);
    setError('');
    setSavedDailyRecordId('');
    setDailyRecordError('');
    setSavedIncidentId('');
    setTrackingError('');
  };

  const handleSubmit = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setError('');
    setSavedDailyRecordId('');
    setDailyRecordError('');
    setSavedIncidentId('');
    setTrackingError('');

    const timelineError = validateTimeline(formData);
    if (timelineError) {
      setError(timelineError);
      return;
    }

    if (
      recoveryData.planned_worker_count !== '' &&
      formData.worker_shortage_count !== '' &&
      recoveryData.planned_worker_count < formData.worker_shortage_count
    ) {
      setError('Planned workers cannot be less than the reported worker shortage.');
      return;
    }
    if (
      recoveryData.planned_machine_count !== '' &&
      formData.machine_breakdown_count !== '' &&
      recoveryData.planned_machine_count < formData.machine_breakdown_count
    ) {
      setError('Planned machines cannot be less than the reported breakdown count.');
      return;
    }

    setLoading(true);

    try {
      const response = await fetch(`${API_BASE_URL}/predict`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          ...formData,
          recovery_parameters: recoveryParameters(recoveryData),
        }),
      });
      const payload: unknown = await response.json();

      if (!response.ok) {
        const apiError = payload as { error?: unknown };
        throw new Error(
          typeof apiError.error === 'string'
            ? apiError.error
            : 'The monitoring request could not be completed.',
        );
      }

      setResult(payload as MonitoringResponse);
      setAnalysisInvalidated(false);
    } catch (requestError: unknown) {
      setResult(null);
      setError(
        requestError instanceof Error
          ? requestError.message
          : 'Unable to connect to the Component 3 API.',
      );
    } finally {
      setLoading(false);
    }
  };

  const handleSaveDailyRecord = async () => {
    if (!result || !trackingActor.trim()) return;
    setSavingDailyRecord(true);
    setDailyRecordError('');

    try {
      const response = await fetch(`${API_BASE_URL}/monitoring-records`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          ...formData,
          recovery_parameters: recoveryParameters(recoveryData),
          recorded_by: trackingActor.trim(),
        }),
      });
      const payload: unknown = await response.json();
      if (!response.ok) {
        const apiError = payload as { error?: unknown };
        throw new Error(
          typeof apiError.error === 'string'
            ? apiError.error
            : 'The daily monitoring record could not be saved.',
        );
      }

      const saved = payload as {
        monitoring_record: {
          record_id: string;
          analysis: MonitoringResponse;
        };
      };
      setResult(saved.monitoring_record.analysis);
      setSavedDailyRecordId(saved.monitoring_record.record_id);
    } catch (requestError: unknown) {
      setDailyRecordError(
        requestError instanceof Error
          ? requestError.message
          : 'Unable to save this daily monitoring record.',
      );
    } finally {
      setSavingDailyRecord(false);
    }
  };

  const handleSaveIncident = async () => {
    if (!result || !trackingActor.trim()) return;
    setSavingIncident(true);
    setTrackingError('');

    try {
      const response = await fetch(`${API_BASE_URL}/incidents`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          ...formData,
          recovery_parameters: recoveryParameters(recoveryData),
          created_by: trackingActor.trim(),
        }),
      });
      const payload: unknown = await response.json();
      if (!response.ok) {
        const apiError = payload as { error?: unknown };
        throw new Error(
          typeof apiError.error === 'string'
            ? apiError.error
            : 'The incident could not be saved.',
        );
      }

      const saved = payload as {
        incident: { incident_id: string; analysis: MonitoringResponse };
      };
      setResult(saved.incident.analysis);
      setSavedIncidentId(saved.incident.incident_id);
    } catch (requestError: unknown) {
      setTrackingError(
        requestError instanceof Error
          ? requestError.message
          : 'Unable to save this recovery incident.',
      );
    } finally {
      setSavingIncident(false);
    }
  };

  const renderFields = (fields: FieldDefinition[]) =>
    fields.map((field) => (
      <div className={styles.formGroup} key={field.name}>
        <label htmlFor={field.name}>{field.label}</label>
        <input
          id={field.name}
          name={field.name}
          type={field.type ?? 'text'}
          value={formData[field.name]}
          min={field.min}
          step={field.step}
          onChange={handleChange}
          readOnly={field.readOnly}
          required={!field.readOnly}
        />
        {field.helper && <span className={styles.fieldHelper}>{field.helper}</span>}
      </div>
    ));

  const renderRecoveryFields = (fields: RecoveryFieldDefinition[]) =>
    fields.map((field) => (
      <div className={styles.formGroup} key={field.name}>
        <label htmlFor={field.name}>{field.label}</label>
        <input
          id={field.name}
          name={field.name}
          type="number"
          value={recoveryData[field.name]}
          min={field.min}
          step={field.step ?? 1}
          onChange={handleRecoveryChange}
          placeholder="Optional"
        />
        <span className={styles.fieldHelper}>{field.helper}</span>
      </div>
    ));

  const completionWidth = result
    ? clampPercentage(result.order_progress.completion_pct)
    : 0;
  const riskConfidence = result
    ? clampPercentage(result.risk_detection.risk_confidence * 100)
    : 0;
  const orderRiskProbability = result
    ? clampPercentage(result.risk_detection.order_risk_probability * 100)
    : 0;

  return (
    <div className={styles.container}>
      <section className={styles.hero}>
        <div>
          <span className={styles.eyebrow}>Research Component 03</span>
          <h1>Emergency Situation Detection &amp; Management</h1>
          <p>
            Monitor daily production, detect operational risk early, and receive a
            clear recovery plan before an order misses its buyer deadline.
          </p>
        </div>
        <div className={styles.serviceBadge}>
          <span className={styles.liveDot} aria-hidden="true" />
          {result ? `Model ${result.model_version.toUpperCase()}` : 'Component 3 API'}
        </div>
      </section>

      <section className={styles.scenarioSection} aria-labelledby="scenario-title">
        <div className={styles.sectionHeading}>
          <div>
            <span className={styles.sectionKicker}>Demo presets</span>
            <h2 id="scenario-title">Choose a production situation</h2>
          </div>
          <div className={styles.scenarioHeadingActions}>
            <p>
              Presets use historical example values. Start a current order to
              enter live factory data.
            </p>
            <div>
              <button type="button" onClick={startCurrentOrder}>
                + Enter current order
              </button>
              <Link href="/dashboard/monitoring-history#historical-import">
                Prepare demo history
              </Link>
            </div>
          </div>
        </div>
        <div className={styles.scenarioGrid}>
          {SCENARIOS.map((scenario) => (
            <button
              className={styles.scenarioButton}
              key={scenario.label}
              onClick={() => selectScenario(scenario)}
              type="button"
            >
              <strong>{scenario.label}</strong>
              <span>{scenario.description}</span>
            </button>
          ))}
        </div>
      </section>

      <div className={styles.workspace}>
        <section className={styles.formCard}>
          <div className={styles.cardHeading}>
            <div>
              <span className={styles.stepNumber}>01</span>
              <div>
                <h2>Daily production log</h2>
                <p>Enter today&apos;s order, output, resource and schedule information.</p>
              </div>
            </div>
            <span
              className={`${styles.formModeBadge} ${
                formMode === 'current'
                  ? styles.currentModeBadge
                  : styles.demoModeBadge
              }`}
            >
              {formMode === 'current' ? 'Current-order entry' : 'Demo preset'}
            </span>
          </div>

          <form onSubmit={handleSubmit}>
            <fieldset className={styles.fieldset}>
              <legend>Order identification</legend>
              <div className={styles.formGrid}>{renderFields(IDENTIFICATION_FIELDS)}</div>
            </fieldset>

            <fieldset className={styles.fieldset}>
              <legend>Production and disruption metrics</legend>
              <div className={styles.formGrid}>{renderFields(PRODUCTION_FIELDS)}</div>
            </fieldset>

            <fieldset className={styles.fieldset}>
              <legend>Timeline and process capacity</legend>
              <div className={styles.formGrid}>{renderFields(TIMELINE_FIELDS)}</div>
            </fieldset>

            <fieldset className={`${styles.fieldset} ${styles.recoveryFieldset}`}>
              <legend>Emergency recovery capacity</legend>
              <div className={styles.recoveryInputNote}>
                <span aria-hidden="true">↗</span>
                <p>
                  Enter actual plant limits. These values calculate executable
                  recovery options and are not used to retrain the ML models.
                </p>
              </div>
              <div className={styles.formGrid}>{renderRecoveryFields(RECOVERY_FIELDS)}</div>
            </fieldset>

            <button className={styles.submitButton} disabled={loading} type="submit">
              {loading ? (
                <>
                  <span className={styles.spinner} aria-hidden="true" />
                  Analysing production...
                </>
              ) : (
                <>
                  Analyse risk &amp; build recovery plan
                  <span aria-hidden="true">→</span>
                </>
              )}
            </button>
          </form>

          <div className={styles.apiNote}>
            API endpoint: <code>{API_BASE_URL}/predict</code>
          </div>
          {error && (
            <div className={styles.errorMessage} role="alert">
              <strong>Analysis failed</strong>
              <span>{error}</span>
              <small>Confirm that the Flask API is running with `python3 main.py`.</small>
            </div>
          )}
        </section>

        <section className={styles.resultCard} aria-live="polite">
          <div className={styles.cardHeading}>
            <div>
              <span className={styles.stepNumber}>02</span>
              <div>
                <h2>Risk command centre</h2>
                <p>Model prediction, schedule exposure, alerts and recovery decisions.</p>
              </div>
            </div>
          </div>

          {!result ? (
            <div className={styles.emptyState}>
              <div className={styles.radar} aria-hidden="true">
                <span />
              </div>
              <h3>
                {analysisInvalidated
                  ? 'Inputs changed'
                  : 'Ready to monitor an order'}
              </h3>
              <p>
                {analysisInvalidated
                  ? 'The previous result was cleared. Run the analysis again to use the updated values.'
                  : 'Select a preset or enter today\'s production log, then run the analysis.'}
              </p>
              <div className={styles.emptyLegend}>
                <span><i className={styles.legendSafe} /> Low</span>
                <span><i className={styles.legendMinor} /> Medium</span>
                <span><i className={styles.legendCritical} /> Critical</span>
              </div>
            </div>
          ) : (
            <div className={styles.results}>
              <div
                className={`${styles.riskBanner} ${riskTone(
                  result.risk_detection.severity ??
                    result.risk_detection.risk_status,
                )}`}
              >
                <div>
                  <span className={styles.bannerLabel}>
                    Current-day operational status
                  </span>
                  <h3>{result.risk_detection.risk_type}</h3>
                  <p>{result.risk_detection.recommendation}</p>
                </div>
                <div className={styles.bannerBadges}>
                  <span>{result.risk_detection.risk_status}</span>
                  <span>{result.risk_detection.severity ?? 'No Risk'} severity</span>
                </div>
              </div>

              <div
                className={`${styles.scheduleBanner} ${riskTone(
                  result.risk_detection.order_risk_level,
                )}`}
              >
                <div>
                  <span className={styles.bannerLabel}>
                    Order delivery outlook
                  </span>
                  <h3>
                    {result.risk_detection.order_risk_level} schedule risk
                  </h3>
                  <p>{result.order_progress.progress_summary}</p>
                </div>
                <div className={styles.bannerBadges}>
                  <span>
                    Schedule: {result.risk_detection.schedule_order_risk_level}
                  </span>
                  <span>
                    Combined: {result.risk_detection.order_risk_level}
                  </span>
                </div>
              </div>

              <section
                className={`${styles.earlyWarningPanel} ${
                  result.early_warning.status === 'available'
                    ? result.early_warning.alert_generated
                      ? styles.earlyWarningAlert
                      : styles.earlyWarningClear
                    : styles.earlyWarningNeutral
                }`}
                aria-labelledby="early-warning-title"
              >
                <div className={styles.earlyWarningHeader}>
                  <div>
                    <span className={styles.sectionKicker}>
                      Experimental early warning · next 3 production days
                    </span>
                    <h3 id="early-warning-title">Emerging subtype risks</h3>
                  </div>
                  <span className={styles.earlyWarningStatus}>
                    {earlyWarningStatusLabel(result.early_warning)}
                  </span>
                </div>

                {result.early_warning.status === 'available' ? (
                  <>
                    <div className={styles.earlyWarningHistory}>
                      <span>{historyStatusLabel(result.early_warning.history)}</span>
                      <span>
                        {result.early_warning.history?.saved_prior_records ?? 0}{' '}
                        saved prior day(s)
                      </span>
                    </div>
                    <div className={styles.earlyWarningGrid}>
                      {result.early_warning.warnings.map((warning) => {
                        const score = clampPercentage(warning.probability_pct);
                        return (
                          <article
                            className={
                              warning.warning_predicted
                                ? styles.warningCrossed
                                : styles.warningBelow
                            }
                            key={warning.target}
                          >
                            <div className={styles.warningScoreHeader}>
                              <div>
                                <span>{warning.display_name}</span>
                                <small>{warning.model_name.replaceAll('_', ' ')}</small>
                              </div>
                              <strong>{score.toFixed(1)}%</strong>
                            </div>
                            <div className={styles.warningScoreTrack}>
                              <span style={{ width: `${score}%` }} />
                            </div>
                            <div className={styles.warningDecision}>
                              <strong>
                                {warning.warning_predicted
                                  ? 'Warning indicated'
                                  : 'Below model threshold'}
                              </strong>
                              <span>
                                threshold{' '}
                                {(warning.decision_threshold * 100).toFixed(0)}%
                              </span>
                            </div>
                            <p>{warning.preparation}</p>
                          </article>
                        );
                      })}
                    </div>
                  </>
                ) : (
                  <div className={styles.earlyWarningMessage}>
                    <strong>Future subtype warning was not scored</strong>
                    <span>{result.early_warning.message}</span>
                  </div>
                )}

                <div className={styles.earlyWarningFootnote}>
                  <span>Research only · production approval pending</span>
                  <span>
                    Scores are uncalibrated; worker-shortage future warning is not
                    included.
                  </span>
                </div>
              </section>

              <div className={styles.confidenceGrid}>
                <div className={styles.confidenceCard}>
                  <div className={styles.metricHeader}>
                    <span>Risk-type confidence</span>
                    <strong>{riskConfidence.toFixed(1)}%</strong>
                  </div>
                  <div className={styles.meter}>
                    <span style={{ width: `${riskConfidence}%` }} />
                  </div>
                </div>
                <div className={styles.confidenceCard}>
                  <div className={styles.metricHeader}>
                    <span>ML high-risk probability</span>
                    <strong>{orderRiskProbability.toFixed(1)}%</strong>
                  </div>
                  <div className={`${styles.meter} ${styles.riskMeter}`}>
                    <span style={{ width: `${orderRiskProbability}%` }} />
                  </div>
                </div>
              </div>

              <div className={styles.assessmentGrid}>
                <div>
                  <span>ML assessment</span>
                  <strong>{result.risk_detection.ml_order_risk_level}</strong>
                </div>
                <div>
                  <span>Schedule assessment</span>
                  <strong>{result.risk_detection.schedule_order_risk_level}</strong>
                </div>
                <div>
                  <span>Final combined risk</span>
                  <strong>{result.risk_detection.order_risk_level}</strong>
                </div>
              </div>

              <div className={styles.progressCard}>
                <div className={styles.metricHeader}>
                  <div>
                    <span>Order completion</span>
                    <small>
                      Day {result.working_day_no} of {result.order_summary.total_working_days}
                    </small>
                  </div>
                  <strong>{result.order_progress.completion_pct.toFixed(1)}%</strong>
                </div>
                <div className={styles.progressTrack}>
                  <span style={{ width: `${completionWidth}%` }} />
                </div>
                <div className={styles.progressFooter}>
                  <span>{formatNumber(result.order_summary.cumulative_completed_qty)} completed</span>
                  <span>{formatNumber(result.order_summary.remaining_qty)} remaining</span>
                </div>
              </div>

              <div className={styles.statsGrid}>
                <article>
                  <span>Today&apos;s output</span>
                  <strong>{formatNumber(result.daily_production.plant_daily_output)}</strong>
                  <small>Commitment: {formatNumber(result.daily_production.daily_commitment)}</small>
                </article>
                <article className={result.daily_production.output_gap > 0 ? styles.statDanger : styles.statSuccess}>
                  <span>Output position</span>
                  <strong>
                    {result.daily_production.output_gap > 0
                      ? `${formatNumber(result.daily_production.output_gap)} short`
                      : result.daily_production.output_gap < 0
                        ? `${formatNumber(Math.abs(result.daily_production.output_gap))} ahead`
                        : 'On target'}
                  </strong>
                  <small>{result.daily_production.gap_pct.toFixed(1)}% gap</small>
                </article>
                <article className={result.daily_production.damage_exceeded ? styles.statDanger : ''}>
                  <span>Quality damage</span>
                  <strong>{formatNumber(result.daily_production.daily_damage_qty)}</strong>
                  <small>Limit: {formatNumber(result.daily_production.max_daily_damage_qty)}</small>
                </article>
                <article>
                  <span>Required daily rate</span>
                  <strong>{formatNumber(Math.round(result.production_summary.required_daily_rate))}</strong>
                  <small>pieces per working day</small>
                </article>
              </div>

              <section
                className={`${styles.recoveryPanel} ${
                  result.recovery_plan.manual_escalation_required
                    ? styles.recoveryCritical
                    : result.recovery_plan.status === 'on_track' ||
                        result.recovery_plan.status === 'completed'
                      ? styles.recoverySafe
                      : styles.recoveryWarning
                }`}
                aria-labelledby="recovery-plan-title"
              >
                <div className={styles.recoveryHeader}>
                  <div>
                    <span className={styles.sectionKicker}>
                      Recovery engine · {result.recovery_plan.engine_version}
                    </span>
                    <h3 id="recovery-plan-title">Emergency recovery plan</h3>
                  </div>
                  <span className={styles.recoveryStatus}>
                    {recoveryStatusLabel(result.recovery_plan.status)}
                  </span>
                </div>

                <div className={styles.recoverySummaryGrid}>
                  <div>
                    <span>Working days available</span>
                    <strong>{result.recovery_plan.available_working_days}</strong>
                  </div>
                  <div>
                    <span>Required daily rate</span>
                    <strong>
                      {formatCapacity(result.recovery_plan.required_daily_rate)}
                    </strong>
                  </div>
                  <div>
                    <span>Current daily capacity</span>
                    <strong>
                      {formatCapacity(result.recovery_plan.current_daily_capacity)}
                    </strong>
                  </div>
                  <div>
                    <span>Daily recovery gap</span>
                    <strong>
                      {formatCapacity(result.recovery_plan.daily_recovery_gap)}
                    </strong>
                  </div>
                </div>

                <div className={styles.triggerRow}>
                  <span>Planning triggers</span>
                  <div>
                    {(result.recovery_plan.triggered_by.length
                      ? result.recovery_plan.triggered_by
                      : ['No active incident']).map((trigger) => (
                      <strong key={trigger}>{trigger}</strong>
                    ))}
                  </div>
                </div>

                {result.recovery_plan.missing_parameters.length > 0 && (
                  <div className={styles.missingDataNotice} role="status">
                    <strong>More plant data will improve this plan</strong>
                    <span>
                      Add: {result.recovery_plan.missing_parameters.join(', ')}
                    </span>
                  </div>
                )}

                {result.recovery_plan.recommended_option ? (
                  <RecoveryOptionCard
                    option={result.recovery_plan.recommended_option}
                    recommended
                  />
                ) : (
                  <div className={styles.completedNotice}>
                    No recovery action is required because the order is complete.
                  </div>
                )}

                {result.recovery_plan.alternatives.length > 0 && (
                  <details className={styles.alternatives}>
                    <summary>
                      Compare {result.recovery_plan.alternatives.length} alternative
                      plan{result.recovery_plan.alternatives.length === 1 ? '' : 's'}
                    </summary>
                    <div className={styles.alternativeList}>
                      {result.recovery_plan.alternatives.map((option) => (
                        <RecoveryOptionCard key={option.option_id} option={option} />
                      ))}
                    </div>
                  </details>
                )}

                <details className={styles.assumptions}>
                  <summary>Calculation assumptions</summary>
                  <ul>
                    {result.recovery_plan.assumptions.map((assumption) => (
                      <li key={assumption}>{assumption}</li>
                    ))}
                  </ul>
                </details>

                <div className={`${styles.trackingCard} ${styles.dailyTrackingCard}`}>
                  <div>
                    <strong>Save today&apos;s monitoring record</strong>
                    <span>
                      Store both stable and emergency days. Three consecutive future
                      records automatically create the early-warning outcome label.
                    </span>
                  </div>
                  <div className={styles.trackingControls}>
                    <label htmlFor="daily-record-actor">
                      Recorded by
                      <input
                        id="daily-record-actor"
                        value={trackingActor}
                        onChange={(event) => setTrackingActor(event.target.value)}
                        placeholder="Production Manager"
                      />
                    </label>
                    <button
                      type="button"
                      onClick={handleSaveDailyRecord}
                      disabled={
                        savingDailyRecord ||
                        Boolean(savedDailyRecordId) ||
                        !trackingActor.trim()
                      }
                    >
                      {savingDailyRecord
                        ? 'Saving daily record...'
                        : savedDailyRecordId
                          ? 'Daily record saved'
                          : 'Save daily record'}
                    </button>
                  </div>
                  {dailyRecordError && (
                    <span className={styles.trackingError} role="alert">
                      {dailyRecordError}
                    </span>
                  )}
                  {savedDailyRecordId && (
                    <div className={styles.trackingSuccess} role="status">
                      <span>Daily record saved for early-warning data collection.</span>
                      <Link href="/dashboard/monitoring-history">
                        Open daily history →
                      </Link>
                    </div>
                  )}
                </div>

                {(result.risk_detection.risk_status === 'Risk' ||
                  result.recovery_plan.status === 'recovery_required' ||
                  result.recovery_plan.manual_escalation_required) && (
                  <div className={styles.trackingCard}>
                    <div>
                      <strong>Track this recovery case</strong>
                      <span>
                        Save the analysis before approving an action or recording
                        actual production results.
                      </span>
                    </div>
                    <div className={styles.trackingControls}>
                      <label htmlFor="tracking-actor">
                        Created by
                        <input
                          id="tracking-actor"
                          value={trackingActor}
                          onChange={(event) => setTrackingActor(event.target.value)}
                          placeholder="Production Manager"
                        />
                      </label>
                      <button
                        type="button"
                        onClick={handleSaveIncident}
                        disabled={savingIncident || !trackingActor.trim()}
                      >
                        {savingIncident
                          ? 'Saving incident...'
                          : 'Save & track incident'}
                      </button>
                    </div>
                    {trackingError && (
                      <span className={styles.trackingError} role="alert">
                        {trackingError}
                      </span>
                    )}
                    {savedIncidentId && (
                      <div className={styles.trackingSuccess} role="status">
                        <span>Incident saved successfully.</span>
                        <Link href="/dashboard/recovery-history">
                          Open recovery history →
                        </Link>
                      </div>
                    )}
                  </div>
                )}
              </section>

              <div className={styles.detailGrid}>
                <article className={styles.detailCard}>
                  <div className={styles.detailTitle}>
                    <span className={styles.iconBox} aria-hidden="true">◎</span>
                    <div>
                      <h3>Schedule forecast</h3>
                      <p>{result.scheduling.on_track ? 'Order is currently on track' : 'Deadline exposure detected'}</p>
                    </div>
                  </div>
                  <dl className={styles.detailList}>
                    <div><dt>Projected completion</dt><dd>{result.scheduling.projected_completion_date}</dd></div>
                    <div><dt>Buyer required date</dt><dd>{result.scheduling.buyer_required_date}</dd></div>
                    <div><dt>Working days remaining</dt><dd>{result.scheduling.working_days_remaining}</dd></div>
                    <div>
                      <dt>Deadline position</dt>
                      <dd className={result.scheduling.days_to_deadline < 0 ? styles.dangerText : styles.successText}>
                        {Math.abs(result.scheduling.days_to_deadline)} day(s) {result.scheduling.days_to_deadline < 0 ? 'late' : 'buffer'}
                      </dd>
                    </div>
                  </dl>
                </article>

                <article className={styles.detailCard}>
                  <div className={styles.detailTitle}>
                    <span className={styles.iconBox} aria-hidden="true">!</span>
                    <div>
                      <h3>Alert routing</h3>
                      <p>{result.alert_system.alert_generated ? 'Notifications are required' : 'No alert required'}</p>
                    </div>
                  </div>
                  <div className={styles.tagGroup}>
                    {(result.alert_system.alert_targets.length
                      ? result.alert_system.alert_targets
                      : ['No recipients']).map((target) => (
                      <span key={target}>{target}</span>
                    ))}
                  </div>
                  <div className={styles.channelRow}>
                    <span>Channels</span>
                    <strong>
                      {result.alert_system.notify_via.length
                        ? result.alert_system.notify_via.join(' · ')
                        : 'Dashboard monitoring only'}
                    </strong>
                  </div>
                </article>
              </div>

              <article className={styles.actionCard}>
                <div className={styles.actionTopline}>
                  <span>Initial incident guidance</span>
                  {result.action.escalation_needed && (
                    <strong>Risk escalation required</strong>
                  )}
                </div>
                <h3>{result.action.action_required}</h3>
                <p>{result.action.recommendation}</p>
                <div className={styles.nextStep}>
                  <span>Next control step</span>
                  <strong>{result.action.next_step}</strong>
                </div>
              </article>
            </div>
          )}
        </section>
      </div>
    </div>
  );
}
