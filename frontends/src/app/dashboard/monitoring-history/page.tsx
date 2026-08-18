'use client';

import Link from 'next/link';
import { useCallback, useEffect, useMemo, useState } from 'react';
import styles from './monitoring-history.module.css';

type RiskStatus = 'No Risk' | 'Risk';
type LabelStatus =
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
  stable_records: number;
  emergency_records: number;
  label_status_counts: Record<LabelStatus, number>;
  three_day_target: {
    ready_rows: number;
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

const API_BASE_URL = (
  process.env.NEXT_PUBLIC_COMPONENT3_API_URL ??
  'http://127.0.0.1:5001/api/component3'
).replace(/\/$/, '');

const NUMBER_FORMATTER = new Intl.NumberFormat('en-US');

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
  const [total, setTotal] = useState(0);
  const [orderFilter, setOrderFilter] = useState('');
  const [riskFilter, setRiskFilter] = useState('');
  const [labelFilter, setLabelFilter] = useState('');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [refreshVersion, setRefreshVersion] = useState(0);

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
    return parameters.toString();
  }, [labelFilter, orderFilter, riskFilter]);

  useEffect(() => {
    let cancelled = false;
    Promise.all([
      requestJson(`/monitoring-records?${query}`),
      requestJson('/monitoring-readiness'),
    ])
      .then(([listPayload, readinessPayload]) => {
        if (cancelled) return;
        const list = listPayload as MonitoringListResponse;
        setRecords(list.items);
        setTotal(list.total);
        setReadiness(readinessPayload as ReadinessResponse);
        setError('');
      })
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

  return (
    <div className={styles.container}>
      <section className={styles.hero}>
        <div>
          <span>Component 3 data collection</span>
          <h1>Daily Monitoring History</h1>
          <p>
            Review stable and emergency observations, automatic future labels,
            and live readiness for the three-day early-warning target.
          </p>
        </div>
        <Link href="/dashboard/monitoring">+ Record another day</Link>
      </section>

      <section className={styles.metrics} aria-label="Monitoring readiness summary">
        <article>
          <span>Total records</span>
          <strong>{NUMBER_FORMATTER.format(readiness?.total_records ?? 0)}</strong>
          <small>All saved Component 3 days</small>
        </article>
        <article>
          <span>Stable records</span>
          <strong>{NUMBER_FORMATTER.format(readiness?.stable_records ?? 0)}</strong>
          <small>Potential early-warning source days</small>
        </article>
        <article>
          <span>Emergency records</span>
          <strong>{NUMBER_FORMATTER.format(readiness?.emergency_records ?? 0)}</strong>
          <small>Used as future outcomes</small>
        </article>
        <article>
          <span>Ready labels</span>
          <strong>{NUMBER_FORMATTER.format(target?.ready_rows ?? 0)}</strong>
          <small>Complete next-three-day windows</small>
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
            Training requires both outcomes across independent orders. Waiting,
            incomplete and current-emergency rows are not treated as negative labels.
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
            Label status
            <select
              value={labelFilter}
              onChange={(event) => setLabelFilter(event.target.value)}
            >
              <option value="">All</option>
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
                  <th>Current status</th>
                  <th>Output</th>
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
                      <span className={`${styles.labelBadge} ${labelClass(record.label_status)}`}>
                        {record.label_status}
                      </span>
                    </td>
                    <td className={styles.futureOutcome}>{futureOutcome(record)}</td>
                    <td>
                      <strong>{record.recorded_by}</strong>
                      <span>{new Date(record.created_at).toLocaleString()}</span>
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
