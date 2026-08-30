'use client';

import Link from 'next/link';
import { useCallback, useEffect, useMemo, useState } from 'react';
import styles from './recovery-history.module.css';

type WorkflowStatus = 'Pending' | 'Approved' | 'In Progress' | 'Completed';

interface IncidentSummary {
  incident_id: string;
  bulk_order_id: string;
  style_id: string;
  buyer_name: string;
  allocated_bulk_plant: string;
  production_date: string;
  risk_type: string;
  order_risk_level: string;
  severity: string | null;
  workflow_status: WorkflowStatus;
  recommended_option_id: string | null;
  selected_option_id: string | null;
  approved_by: string | null;
  approval_notes: string | null;
  created_at: string;
  updated_at: string;
}

interface RecoveryOption {
  option_id: string;
  title: string;
  rationale: string;
  feasible_before_deadline: boolean;
  daily_capacity?: number;
  required_overtime_hours_per_day?: number;
  additional_workers?: number;
  repaired_machines?: number;
  backup_machines?: number;
  backup_line_daily_capacity_used?: number;
  projected_completion_date?: string | null;
  deadline_margin_working_days?: number | null;
  external_daily_capacity_required?: number | null;
}

interface RecoveryPlan {
  status: string;
  remaining_quantity: number;
  available_working_days: number;
  required_daily_rate: number | null;
  current_daily_capacity: number;
  daily_recovery_gap: number | null;
  recommended_option: RecoveryOption | null;
  alternatives: RecoveryOption[];
}

interface Outcome {
  outcome_id: string;
  outcome_date: string;
  actual_daily_output: number;
  target_daily_output: number | null;
  output_variance: number | null;
  effectiveness_pct: number | null;
  recovery_gap_closed_pct: number | null;
  cumulative_completed_qty: number | null;
  notes: string | null;
  recorded_by: string;
}

interface TimelineEvent {
  event_id: string;
  event_type: string;
  actor: string;
  details: Record<string, unknown>;
  created_at: string;
}

interface IncidentDetail extends IncidentSummary {
  selected_option: RecoveryOption | null;
  analysis: {
    recovery_plan: RecoveryPlan;
    order_summary: {
      full_order_qty: number;
      remaining_qty: number;
      completion_pct: number;
    };
  };
  outcomes: Outcome[];
  timeline: TimelineEvent[];
}

interface IncidentListResponse {
  items: IncidentSummary[];
  total: number;
  limit: number;
  offset: number;
}

const API_BASE_URL = (
  process.env.NEXT_PUBLIC_COMPONENT3_API_URL ??
  'http://127.0.0.1:5001/api/component3'
).replace(/\/$/, '');

const NUMBER_FORMATTER = new Intl.NumberFormat('en-US', {
  maximumFractionDigits: 2,
});

function formatNumber(value: number | null | undefined) {
  return value === null || value === undefined
    ? 'Not available'
    : NUMBER_FORMATTER.format(value);
}

function formatTimestamp(value: string) {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString();
}

function statusClass(status: WorkflowStatus) {
  return styles[`status${status.replace(' ', '')}`];
}

function optionsForIncident(incident: IncidentDetail) {
  const plan = incident.analysis.recovery_plan;
  return [plan.recommended_option, ...plan.alternatives].filter(
    (option): option is RecoveryOption => option !== null,
  );
}

function optionAvailabilityLabel(option: RecoveryOption) {
  if (option.option_id === 'manual_escalation') {
    return '· requires external action';
  }
  return option.feasible_before_deadline ? '· feasible' : '· insufficient';
}

export default function RecoveryHistoryPage() {
  const [incidents, setIncidents] = useState<IncidentSummary[]>([]);
  const [total, setTotal] = useState(0);
  const [selectedIncident, setSelectedIncident] = useState<IncidentDetail | null>(
    null,
  );
  const [orderFilter, setOrderFilter] = useState('');
  const [statusFilter, setStatusFilter] = useState('');
  const [loadingList, setLoadingList] = useState(true);
  const [loadingDetail, setLoadingDetail] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');
  const [actor, setActor] = useState('Factory Manager');
  const [notes, setNotes] = useState('');
  const [selectedOptionId, setSelectedOptionId] = useState('');
  const [outcomeDate, setOutcomeDate] = useState(
    new Date().toISOString().slice(0, 10),
  );
  const [actualOutput, setActualOutput] = useState('');
  const [cumulativeCompleted, setCumulativeCompleted] = useState('');
  const [outcomeNotes, setOutcomeNotes] = useState('');

  const requestJson = useCallback(
    async (path: string, init?: RequestInit) => {
      const response = await fetch(`${API_BASE_URL}${path}`, {
        ...init,
        headers: {
          'Content-Type': 'application/json',
          ...init?.headers,
        },
      });
      const payload: unknown = await response.json();
      if (!response.ok) {
        const apiError = payload as { error?: unknown };
        throw new Error(
          typeof apiError.error === 'string'
            ? apiError.error
            : 'The recovery tracking request failed.',
        );
      }
      return payload;
    },
    [],
  );

  const loadIncident = useCallback(
    async (incidentId: string, quiet = false) => {
      if (!quiet) setLoadingDetail(true);
      setError('');
      try {
        const payload = (await requestJson(`/incidents/${incidentId}`)) as {
          incident: IncidentDetail;
        };
        setSelectedIncident(payload.incident);
        setSelectedOptionId(
          payload.incident.selected_option_id ??
            payload.incident.recommended_option_id ??
            '',
        );
      } catch (requestError: unknown) {
        setError(
          requestError instanceof Error
            ? requestError.message
            : 'Unable to load the incident.',
        );
      } finally {
        if (!quiet) setLoadingDetail(false);
      }
    },
    [requestJson],
  );

  const loadIncidents = useCallback(async () => {
    const parameters = new URLSearchParams({ limit: '100' });
    if (orderFilter.trim()) parameters.set('bulk_order_id', orderFilter.trim());
    if (statusFilter) parameters.set('status', statusFilter);

    try {
      const payload = (await requestJson(
        `/incidents?${parameters.toString()}`,
      )) as IncidentListResponse;
      setError('');
      setIncidents(payload.items);
      setTotal(payload.total);
    } catch (requestError: unknown) {
      setError(
        requestError instanceof Error
          ? requestError.message
          : 'Unable to load recovery incidents.',
      );
    } finally {
      setLoadingList(false);
    }
  }, [orderFilter, requestJson, statusFilter]);

  const automaticListQuery = useMemo(() => {
    const parameters = new URLSearchParams({ limit: '100' });
    if (orderFilter.trim()) parameters.set('bulk_order_id', orderFilter.trim());
    if (statusFilter) parameters.set('status', statusFilter);
    return parameters.toString();
  }, [orderFilter, statusFilter]);

  useEffect(() => {
    let cancelled = false;
    requestJson(`/incidents?${automaticListQuery}`)
      .then((payload) => {
        if (cancelled) return;
        const list = payload as IncidentListResponse;
        setIncidents(list.items);
        setTotal(list.total);
        setError('');
      })
      .catch((requestError: unknown) => {
        if (cancelled) return;
        setError(
          requestError instanceof Error
            ? requestError.message
            : 'Unable to load recovery incidents.',
        );
      })
      .finally(() => {
        if (!cancelled) setLoadingList(false);
      });
    return () => {
      cancelled = true;
    };
  }, [automaticListQuery, requestJson]);

  const visibleCounts = useMemo(
    () => ({
      pending: incidents.filter((incident) => incident.workflow_status === 'Pending')
        .length,
      active: incidents.filter((incident) =>
        ['Approved', 'In Progress'].includes(incident.workflow_status),
      ).length,
      completed: incidents.filter(
        (incident) => incident.workflow_status === 'Completed',
      ).length,
    }),
    [incidents],
  );

  const mutateIncident = async (
    path: string,
    method: 'POST' | 'PATCH',
    body: Record<string, unknown>,
    successMessage: string,
  ) => {
    if (!selectedIncident) return;
    setSaving(true);
    setError('');
    setSuccess('');
    try {
      const payload = (await requestJson(path, {
        method,
        body: JSON.stringify(body),
      })) as { incident?: IncidentDetail };
      if (payload.incident) {
        setSelectedIncident(payload.incident);
      } else {
        await loadIncident(selectedIncident.incident_id, true);
      }
      await loadIncidents();
      setSuccess(successMessage);
      setNotes('');
    } catch (requestError: unknown) {
      setError(
        requestError instanceof Error
          ? requestError.message
          : 'The workflow update failed.',
      );
    } finally {
      setSaving(false);
    }
  };

  const approveDecision = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!selectedIncident) return;
    await mutateIncident(
      `/incidents/${selectedIncident.incident_id}/decision`,
      'POST',
      {
        selected_option_id: selectedOptionId,
        approved_by: actor,
        notes,
      },
      'Recovery decision approved.',
    );
  };

  const advanceStatus = async (status: 'In Progress' | 'Completed') => {
    if (!selectedIncident) return;
    await mutateIncident(
      `/incidents/${selectedIncident.incident_id}/status`,
      'PATCH',
      { status, updated_by: actor, notes },
      status === 'Completed'
        ? 'Incident marked as completed.'
        : 'Recovery action is now in progress.',
    );
  };

  const recordOutcome = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!selectedIncident) return;
    setSaving(true);
    setError('');
    setSuccess('');
    try {
      await requestJson(
        `/incidents/${selectedIncident.incident_id}/outcomes`,
        {
          method: 'POST',
          body: JSON.stringify({
            outcome_date: outcomeDate,
            actual_daily_output: Number(actualOutput),
            cumulative_completed_qty: cumulativeCompleted
              ? Number(cumulativeCompleted)
              : null,
            recorded_by: actor,
            notes: outcomeNotes,
          }),
        },
      );
      await loadIncident(selectedIncident.incident_id, true);
      await loadIncidents();
      setActualOutput('');
      setCumulativeCompleted('');
      setOutcomeNotes('');
      setSuccess('Actual production outcome recorded.');
    } catch (requestError: unknown) {
      setError(
        requestError instanceof Error
          ? requestError.message
          : 'The production outcome could not be recorded.',
      );
    } finally {
      setSaving(false);
    }
  };

  const availableOptions = selectedIncident
    ? optionsForIncident(selectedIncident)
    : [];
  const displayedRecoveryOption = selectedIncident
    ? (selectedIncident.selected_option ??
      selectedIncident.analysis.recovery_plan.recommended_option)
    : null;

  return (
    <div className={styles.container}>
      <section className={styles.hero}>
        <div>
          <span>Recovery operations</span>
          <h1>Recovery History &amp; Feedback</h1>
          <p>
            Approve recovery decisions, follow execution, and compare actual
            production against the calculated target.
          </p>
        </div>
        <Link href="/component3/monitoring">← New monitoring analysis</Link>
      </section>

      <section className={styles.summaryGrid} aria-label="Visible incident summary">
        <article>
          <span>Total records</span>
          <strong>{total}</strong>
        </article>
        <article>
          <span>Pending approval</span>
          <strong>{visibleCounts.pending}</strong>
        </article>
        <article>
          <span>Active recovery</span>
          <strong>{visibleCounts.active}</strong>
        </article>
        <article>
          <span>Completed</span>
          <strong>{visibleCounts.completed}</strong>
        </article>
      </section>

      <section className={styles.filterCard}>
        <label>
          Bulk order ID
          <input
            value={orderFilter}
            onChange={(event) => setOrderFilter(event.target.value)}
            placeholder="Example: BULK0001"
          />
        </label>
        <label>
          Workflow status
          <select
            value={statusFilter}
            onChange={(event) => setStatusFilter(event.target.value)}
          >
            <option value="">All statuses</option>
            <option value="Pending">Pending</option>
            <option value="Approved">Approved</option>
            <option value="In Progress">In Progress</option>
            <option value="Completed">Completed</option>
          </select>
        </label>
        <button
          type="button"
          onClick={() => {
            setLoadingList(true);
            void loadIncidents();
          }}
        >
          Refresh records
        </button>
      </section>

      {error && <div className={styles.error} role="alert">{error}</div>}
      {success && <div className={styles.success} role="status">{success}</div>}

      <div className={styles.workspace}>
        <section className={styles.incidentList}>
          <div className={styles.sectionHeader}>
            <div>
              <span>Incident register</span>
              <h2>{loadingList ? 'Loading records...' : `${total} incident(s)`}</h2>
            </div>
          </div>

          {!loadingList && incidents.length === 0 ? (
            <div className={styles.emptyState}>
              <strong>No incidents found</strong>
              <span>Save a monitoring analysis or change the filters.</span>
            </div>
          ) : (
            <div className={styles.incidentCards}>
              {incidents.map((incident) => (
                <button
                  type="button"
                  key={incident.incident_id}
                  className={`${styles.incidentCard} ${
                    selectedIncident?.incident_id === incident.incident_id
                      ? styles.selectedCard
                      : ''
                  }`}
                  onClick={() => void loadIncident(incident.incident_id)}
                >
                  <div>
                    <strong>{incident.bulk_order_id}</strong>
                    <span className={`${styles.status} ${statusClass(incident.workflow_status)}`}>
                      {incident.workflow_status}
                    </span>
                  </div>
                  <h3>{incident.risk_type}</h3>
                  <p>{incident.allocated_bulk_plant}</p>
                  <dl>
                    <div><dt>Production date</dt><dd>{incident.production_date}</dd></div>
                    <div><dt>Order risk</dt><dd>{incident.order_risk_level}</dd></div>
                    <div><dt>Plan</dt><dd>{incident.selected_option_id ?? incident.recommended_option_id ?? 'None'}</dd></div>
                  </dl>
                </button>
              ))}
            </div>
          )}
        </section>

        <section className={styles.detailPanel} aria-live="polite">
          {loadingDetail ? (
            <div className={styles.detailEmpty}>Loading incident details...</div>
          ) : !selectedIncident ? (
            <div className={styles.detailEmpty}>
              <span className={styles.detailIcon} aria-hidden="true">↗</span>
              <h2>Select a recovery incident</h2>
              <p>Choose a record to approve its plan or record actual results.</p>
            </div>
          ) : (
            <div className={styles.detailContent}>
              <header className={styles.detailHeader}>
                <div>
                  <span>{selectedIncident.incident_id}</span>
                  <h2>{selectedIncident.bulk_order_id} · {selectedIncident.risk_type}</h2>
                  <p>{selectedIncident.buyer_name} · {selectedIncident.style_id}</p>
                </div>
                <span className={`${styles.status} ${statusClass(selectedIncident.workflow_status)}`}>
                  {selectedIncident.workflow_status}
                </span>
              </header>

              <div className={styles.planMetrics}>
                <div><span>Remaining pieces</span><strong>{formatNumber(selectedIncident.analysis.recovery_plan.remaining_quantity)}</strong></div>
                <div><span>Days available</span><strong>{selectedIncident.analysis.recovery_plan.available_working_days}</strong></div>
                <div><span>Required / day</span><strong>{formatNumber(selectedIncident.analysis.recovery_plan.required_daily_rate)}</strong></div>
                <div><span>Recovery gap / day</span><strong>{formatNumber(selectedIncident.analysis.recovery_plan.daily_recovery_gap)}</strong></div>
              </div>

              <section className={styles.selectedPlan}>
                <span>{selectedIncident.selected_option ? 'Approved recovery action' : 'System recommendation'}</span>
                <h3>
                  {displayedRecoveryOption?.title ?? 'No recovery action'}
                </h3>
                <p>
                  {displayedRecoveryOption?.rationale ?? 'This order was already complete when saved.'}
                </p>
                {displayedRecoveryOption?.option_id === 'manual_escalation' && (
                  <div className={styles.externalRequirement}>
                    <span>External capacity required</span>
                    <strong>
                      {displayedRecoveryOption.external_daily_capacity_required ===
                      null ||
                      displayedRecoveryOption.external_daily_capacity_required ===
                        undefined
                        ? 'Confirm with another line or plant'
                        : `${formatNumber(
                            displayedRecoveryOption.external_daily_capacity_required,
                          )} pieces / day`}
                    </strong>
                  </div>
                )}
              </section>

              <section className={styles.workflowCard}>
                <div className={styles.workflowHeading}>
                  <div><span>Management control</span><h3>Recovery workflow</h3></div>
                  <label>
                    Responsible person
                    <input value={actor} onChange={(event) => setActor(event.target.value)} required />
                  </label>
                </div>

                {selectedIncident.workflow_status === 'Pending' && (
                  <form onSubmit={approveDecision} className={styles.workflowForm}>
                    <label>
                      Select recovery option
                      <select value={selectedOptionId} onChange={(event) => setSelectedOptionId(event.target.value)} required>
                        {availableOptions.map((option) => (
                          <option key={option.option_id} value={option.option_id}>
                            {option.title} {optionAvailabilityLabel(option)}
                          </option>
                        ))}
                      </select>
                    </label>
                    <label>
                      Approval notes
                      <textarea value={notes} onChange={(event) => setNotes(event.target.value)} rows={3} placeholder="Reason for selecting this plan" />
                    </label>
                    <button disabled={saving || !actor.trim() || !selectedOptionId} type="submit">
                      {saving ? 'Saving...' : 'Approve selected action'}
                    </button>
                  </form>
                )}

                {selectedIncident.workflow_status === 'Approved' && (
                  <div className={styles.workflowAction}>
                    <p>The decision is approved. Start it when resources are assigned.</p>
                    <button disabled={saving || !actor.trim()} type="button" onClick={() => void advanceStatus('In Progress')}>
                      Start recovery action
                    </button>
                  </div>
                )}

                {selectedIncident.workflow_status === 'In Progress' && (
                  <>
                    <form onSubmit={recordOutcome} className={styles.outcomeForm}>
                      <label>Outcome date<input type="date" value={outcomeDate} onChange={(event) => setOutcomeDate(event.target.value)} required /></label>
                      <label>Actual output<input type="number" min="0" value={actualOutput} onChange={(event) => setActualOutput(event.target.value)} required /></label>
                      <label>Cumulative completed<input type="number" min="0" value={cumulativeCompleted} onChange={(event) => setCumulativeCompleted(event.target.value)} placeholder="Optional" /></label>
                      <label className={styles.fullField}>Outcome notes<textarea value={outcomeNotes} onChange={(event) => setOutcomeNotes(event.target.value)} rows={2} placeholder="Workers, OT or machine action applied" /></label>
                      <button disabled={saving || !actor.trim()} type="submit">Record actual outcome</button>
                    </form>
                    <div className={styles.completeAction}>
                      <span>At least one outcome is required before completion.</span>
                      <button disabled={saving || selectedIncident.outcomes.length === 0 || !actor.trim()} type="button" onClick={() => void advanceStatus('Completed')}>
                        Complete incident
                      </button>
                    </div>
                  </>
                )}

                {selectedIncident.workflow_status === 'Completed' && (
                  <div className={styles.completedBanner}>Recovery workflow completed and retained for research feedback.</div>
                )}
              </section>

              <section className={styles.outcomesSection}>
                <div className={styles.sectionHeader}><div><span>Measured performance</span><h3>Actual outcomes</h3></div></div>
                {selectedIncident.outcomes.length === 0 ? (
                  <p className={styles.noData}>No actual production outcome has been recorded.</p>
                ) : (
                  <div className={styles.outcomeCards}>
                    {selectedIncident.outcomes.map((outcome) => (
                      <article key={outcome.outcome_id}>
                        <header><strong>{outcome.outcome_date}</strong><span>{formatNumber(outcome.effectiveness_pct)}% effective</span></header>
                        <dl>
                          <div><dt>Actual output</dt><dd>{formatNumber(outcome.actual_daily_output)}</dd></div>
                          <div><dt>Target output</dt><dd>{formatNumber(outcome.target_daily_output)}</dd></div>
                          <div><dt>Variance</dt><dd>{outcome.output_variance !== null && outcome.output_variance > 0 ? '+' : ''}{formatNumber(outcome.output_variance)}</dd></div>
                          <div><dt>Recovery gap closed</dt><dd>{formatNumber(outcome.recovery_gap_closed_pct)}%</dd></div>
                        </dl>
                        <p>{outcome.notes ?? `Recorded by ${outcome.recorded_by}`}</p>
                      </article>
                    ))}
                  </div>
                )}
              </section>

              <section className={styles.timelineSection}>
                <div className={styles.sectionHeader}><div><span>Audit trail</span><h3>Incident timeline</h3></div></div>
                <ol>
                  {selectedIncident.timeline.map((event) => (
                    <li key={event.event_id}>
                      <i aria-hidden="true" />
                      <div><strong>{event.event_type}</strong><span>{event.actor} · {formatTimestamp(event.created_at)}</span></div>
                    </li>
                  ))}
                </ol>
              </section>
            </div>
          )}
        </section>
      </div>
    </div>
  );
}
