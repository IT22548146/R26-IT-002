'use client';

import { useState } from 'react';
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
}

interface FieldDefinition {
  name: keyof MonitoringFormData;
  label: string;
  type?: 'text' | 'number' | 'date';
  min?: number;
  helper?: string;
}

const API_BASE_URL = (
  process.env.NEXT_PUBLIC_COMPONENT3_API_URL ??
  'http://127.0.0.1:5001/api/component3'
).replace(/\/$/, '');

const INITIAL_FORM: MonitoringFormData = {
  bulk_order_id: 'BULK0015',
  style_id: 'KM327296',
  buyer_name: 'Tesco',
  allocated_bulk_plant: 'Dinusha Embroidery',
  plant_location: 'Weliweriya',
  full_order_qty: 26_499,
  bulk_order_approved_date: '2024-07-12',
  buyer_required_date: '2024-10-20',
  total_working_days: 35,
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
}> = [
  {
    label: 'Healthy line',
    description: 'Output is above commitment with stable resources.',
    values: INITIAL_FORM,
  },
  {
    label: 'Worker pressure',
    description: 'A staffing shortage is reducing daily output.',
    values: {
      ...INITIAL_FORM,
      ...BULK_1_ORDER,
      production_date: '2024-07-03',
      working_day_no: 3,
      plant_daily_output: 412,
      daily_damage_qty: 12,
      max_daily_damage_qty: 13,
      machine_breakdown_count: 0,
      worker_shortage_count: 2,
      cumulative_completed_qty: 1_257,
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
  { name: 'total_working_days', label: 'Total working days', type: 'number', min: 1 },
  { name: 'working_day_no', label: 'Current working day', type: 'number', min: 1 },
  { name: 'cutting_days', label: 'Cutting days', type: 'number', min: 0 },
  { name: 'sewing_days', label: 'Sewing days', type: 'number', min: 0 },
  { name: 'bulk_order_approved_date', label: 'Order approved date', type: 'date' },
  { name: 'production_date', label: 'Production date', type: 'date' },
  { name: 'buyer_required_date', label: 'Buyer required date', type: 'date' },
];

const NUMBER_FORMATTER = new Intl.NumberFormat('en-US');

function formatNumber(value: number) {
  return NUMBER_FORMATTER.format(value);
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

export default function MonitoringPage() {
  const [formData, setFormData] = useState<MonitoringFormData>(INITIAL_FORM);
  const [result, setResult] = useState<MonitoringResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const handleChange = (event: React.ChangeEvent<HTMLInputElement>) => {
    const { name, value, type } = event.currentTarget;
    const field = name as keyof MonitoringFormData;
    const nextValue = type === 'number' ? (value === '' ? '' : Number(value)) : value;

    setFormData((previous) => ({ ...previous, [field]: nextValue }));
  };

  const selectScenario = (values: MonitoringFormData) => {
    setFormData(values);
    setResult(null);
    setError('');
  };

  const handleSubmit = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setLoading(true);
    setError('');

    try {
      const response = await fetch(`${API_BASE_URL}/predict`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(formData),
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
          onChange={handleChange}
          required
        />
        {field.helper && <span className={styles.fieldHelper}>{field.helper}</span>}
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
          <p>Presets update operational values; you can edit every field before analysis.</p>
        </div>
        <div className={styles.scenarioGrid}>
          {SCENARIOS.map((scenario) => (
            <button
              className={styles.scenarioButton}
              key={scenario.label}
              onClick={() => selectScenario(scenario.values)}
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

            <button className={styles.submitButton} disabled={loading} type="submit">
              {loading ? (
                <>
                  <span className={styles.spinner} aria-hidden="true" />
                  Analysing production...
                </>
              ) : (
                <>
                  Analyse emergency risk
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
              <h3>Ready to monitor an order</h3>
              <p>Select a preset or enter today&apos;s production log, then run the analysis.</p>
              <div className={styles.emptyLegend}>
                <span><i className={styles.legendSafe} /> Low</span>
                <span><i className={styles.legendMinor} /> Medium</span>
                <span><i className={styles.legendCritical} /> Critical</span>
              </div>
            </div>
          ) : (
            <div className={styles.results}>
              <div className={`${styles.riskBanner} ${riskTone(result.risk_detection.order_risk_level)}`}>
                <div>
                  <span className={styles.bannerLabel}>Detected situation</span>
                  <h3>{result.risk_detection.risk_type}</h3>
                  <p>{result.order_progress.progress_summary}</p>
                </div>
                <div className={styles.bannerBadges}>
                  <span>{result.risk_detection.order_risk_level} order risk</span>
                  <span>{result.risk_detection.severity ?? 'No Risk'} severity</span>
                </div>
              </div>

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
                    <span>High-risk probability</span>
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
                  <span>Recovery action plan</span>
                  {result.action.escalation_needed && <strong>Escalation required</strong>}
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
