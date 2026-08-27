'use client';

import { useState } from 'react';
import styles from './monitoring.module.css';

interface MonitoringResponse {
  alert_system: {
    alert_generated: boolean;
    alert_targets: string[];
    display_on: string[];
    notify_via: string[];
  };
  allocated_bulk_plant: string;
  bulk_order_id: string;
  buyer_name: string;
  daily_production: {
    daily_commitment: number;
    daily_damage_qty: number;
    damage_exceeded: boolean;
    damage_pct_of_commitment: number;
    gap_pct: number;
    machine_breakdown_count: number;
    max_daily_damage_qty: number;
    output_gap: number;
    plant_daily_output: number;
    worker_shortage_count: number;
  };
  order_progress: {
    completion_pct: number;
    days_elapsed_pct: number;
    order_risk_level: string;
    progress_gap_pct: number;
    progress_summary: string;
  };
  order_summary: {
    completion_pct: number;
    cumulative_completed_qty: number;
    cutting_days: number;
    daily_commitment: number;
    full_order_qty: number;
    remaining_qty: number;
    sewing_days: number;
    total_working_days: number;
  };
  planning_output: {
    action_required: string;
    escalation_needed: boolean;
    next_step: string;
    store_for_ml_training: boolean;
  };
  plant_location: string;
  production_date: string;
  risk_detection: {
    gap_severity_label: string;
    recommendation: string;
    risk_status: string;
    risk_type: string;
    severity: string | null;
  };
  scheduling: {
    bulk_order_approved_date: string;
    bulk_start_date: string;
    buyer_required_date: string;
    days_to_deadline: number;
    on_track: boolean;
    projected_completion_date: string;
    working_days_remaining: number;
  };
  status: string;
  style_id: string;
  working_day_no: number;
}

export default function MonitoringPage() {
  const [formData, setFormData] = useState({
    bulk_order_id: "BULK0001",
    style_id: "AH2495",
    buyer_name: "Hirdaramani",
    allocated_bulk_plant: "Sunrose Lanka (Pvt) Ltd",
    plant_location: "Katubedda",
    full_order_qty: 46430,
    bulk_order_approved_date: "2024-06-29",
    buyer_required_date: "2024-11-27",
    total_working_days: 108,
    cutting_days: 25,
    sewing_days: 30,
    daily_commitment: 430,
    production_date: "2024-07-02",
    working_day_no: 10,
    plant_daily_output: 470,
    daily_damage_qty: 10,
    max_daily_damage_qty: 13,
    machine_breakdown_count: 0,
    worker_shortage_count: 0,
    cumulative_completed_qty: 845
  });

  const [result, setResult] = useState<MonitoringResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const { name, value, type } = e.target;
    setFormData((prev) => ({
      ...prev,
      [name]: type === 'number' ? (value === '' ? '' : parseFloat(value)) : value,
    }));
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError('');
    setResult(null);

    try {
      const response = await fetch('http://localhost:5000/api/component3/predict', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(formData),
      });

      if (!response.ok) {
        throw new Error('Failed to fetch monitoring data.');
      }

      const data = await response.json();
      setResult(data);
    } catch (err: any) {
      setError(err.message || 'An error occurred');
    } finally {
      setLoading(false);
    }
  };

  const getAlertClass = (color: string) => {
    switch (color.toLowerCase()) {
      case 'green': return styles.green;
      case 'yellow': return styles.yellow;
      case 'red': return styles.red;
      default: return '';
    }
  };

  return (
    <div className={styles.container}>
      <div className={styles.grid}>
        {/* Form Section */}
        <div className={styles.card}>
          <h2>
            <svg fill="none" viewBox="0 0 24 24" stroke="currentColor" width="24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M11 5.882V19.24a1.76 1.76 0 01-3.417.592l-2.147-6.15M18 13a3 3 0 100-6M5.436 13.683A4.001 4.001 0 017 6h1.832c4.1 0 7.625-1.234 9.168-3v14c-1.543-1.766-5.067-3-9.168-3H7a3.988 3.988 0 01-1.564-.317z" /></svg>
            Daily Production Log
          </h2>
          <form onSubmit={handleSubmit} className={styles.formGrid}>
            <div className={styles.sectionTitle}>Order Identification</div>
            <div className={styles.formGroup}>
              <label>Bulk Order ID</label>
              <input name="bulk_order_id" value={formData.bulk_order_id} onChange={handleChange} required placeholder="e.g. BULK0001" />
            </div>
            <div className={styles.formGroup}>
              <label>Style ID</label>
              <input name="style_id" value={formData.style_id} onChange={handleChange} required placeholder="Enter style ID" />
            </div>
            <div className={styles.formGroup}>
              <label>Buyer Name</label>
              <input name="buyer_name" value={formData.buyer_name} onChange={handleChange} required placeholder="Enter buyer name" />
            </div>
            <div className={styles.formGroup}>
              <label>Allocated Plant</label>
              <input name="allocated_bulk_plant" value={formData.allocated_bulk_plant} onChange={handleChange} required placeholder="Enter plant name" />
            </div>
            <div className={styles.formGroup}>
              <label>Plant Location</label>
              <input name="plant_location" value={formData.plant_location} onChange={handleChange} required placeholder="e.g. Katubedda" />
            </div>
            
            <div className={styles.sectionTitle}>Production Metrics</div>
            <div className={styles.formGroup}>
              <label>Full Order Qty</label>
              <input type="number" name="full_order_qty" value={formData.full_order_qty ?? ''} onChange={handleChange} required />
            </div>
            <div className={styles.formGroup}>
              <label>Daily Commitment</label>
              <input type="number" name="daily_commitment" value={formData.daily_commitment ?? ''} onChange={handleChange} required />
            </div>
            <div className={styles.formGroup}>
              <label>Actual Output</label>
              <input type="number" name="plant_daily_output" value={formData.plant_daily_output ?? ''} onChange={handleChange} required />
            </div>
            <div className={styles.formGroup}>
              <label>Cumulative Completed</label>
              <input type="number" name="cumulative_completed_qty" value={formData.cumulative_completed_qty ?? ''} onChange={handleChange} required />
            </div>
            <div className={styles.formGroup}>
              <label>Damage Qty</label>
              <input type="number" name="daily_damage_qty" value={formData.daily_damage_qty ?? ''} onChange={handleChange} required />
            </div>
            <div className={styles.formGroup}>
              <label>Max Allowed Damage</label>
              <input type="number" name="max_daily_damage_qty" value={formData.max_daily_damage_qty ?? ''} onChange={handleChange} required />
            </div>
            <div className={styles.formGroup}>
              <label>Machine Breakdowns</label>
              <input type="number" name="machine_breakdown_count" value={formData.machine_breakdown_count ?? ''} onChange={handleChange} required />
            </div>
            <div className={styles.formGroup}>
              <label>Worker Shortage</label>
              <input type="number" name="worker_shortage_count" value={formData.worker_shortage_count ?? ''} onChange={handleChange} required />
            </div>

            <div className={styles.sectionTitle}>Timeline & Capacity</div>
            <div className={styles.formGroup}>
              <label>Total Working Days</label>
              <input type="number" name="total_working_days" value={formData.total_working_days ?? ''} onChange={handleChange} required />
            </div>
            <div className={styles.formGroup}>
              <label>Working Day No</label>
              <input type="number" name="working_day_no" value={formData.working_day_no ?? ''} onChange={handleChange} required />
            </div>
            <div className={styles.formGroup}>
              <label>Cutting Days</label>
              <input type="number" name="cutting_days" value={formData.cutting_days ?? ''} onChange={handleChange} required />
            </div>
            <div className={styles.formGroup}>
              <label>Sewing Days</label>
              <input type="number" name="sewing_days" value={formData.sewing_days ?? ''} onChange={handleChange} required />
            </div>
            <div className={styles.formGroup}>
              <label>Approved Date</label>
              <input type="date" name="bulk_order_approved_date" value={formData.bulk_order_approved_date} onChange={handleChange} required />
            </div>
            <div className={styles.formGroup}>
              <label>Required Date</label>
              <input type="date" name="buyer_required_date" value={formData.buyer_required_date} onChange={handleChange} required />
            </div>
            <div className={styles.formGroup}>
              <label>Production Date</label>
              <input type="date" name="production_date" value={formData.production_date} onChange={handleChange} required />
            </div>
            
            <button type="submit" className={styles.submitBtn} disabled={loading}>
              {loading ? 'Analyzing Production...' : 'Log & Analyze Production'}
            </button>
          </form>
          {error && <p style={{ color: 'var(--error)', marginTop: '1rem' }}>{error}</p>}
        </div>

        {/* Results Section */}
        <div className={styles.card}>
          <h2>
            <svg fill="none" viewBox="0 0 24 24" stroke="currentColor" width="24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z" /></svg>
            Risk & Status Monitoring
          </h2>

          {result ? (
            <div className={styles.results}>
              {/* Risk Status Header */}
              <div className={`${styles.statusCard} ${result.order_progress.order_risk_level === 'Low' ? styles.statusLowRisk : styles.statusHighRisk}`}>
                <div className={styles.statusHeader}>
                  <div className={styles.statusTitle}>{result.risk_detection.risk_status}</div>
                  <span className={styles.riskBadge}>Risk: {result.order_progress.order_risk_level}</span>
                </div>
                <p className={styles.statusRemark}>{result.order_progress.progress_summary}</p>
              </div>

              {/* Progress Overview */}
              <div className={styles.progressSection}>
                <div className={styles.progressHeader}>
                  <span className={styles.progressLabel}>Production Completion</span>
                  <span className={styles.progressValue}>{result.order_progress.completion_pct.toFixed(1)}%</span>
                </div>
                <div className={styles.progressBar}>
                  <div className={styles.progressFill} style={{ width: `${result.order_progress.completion_pct}%` }}></div>
                </div>
                <div className={styles.progressSubtext}>
                  Day {result.working_day_no} of {result.order_summary.total_working_days} | 
                  Progress Gap: <strong style={{ color: result.order_progress.progress_gap_pct < 0 ? 'var(--error)' : 'var(--success)' }}>
                    {result.order_progress.progress_gap_pct.toFixed(2)}%
                  </strong>
                </div>
              </div>

              {/* Daily Stats Grid */}
              <div className={styles.statsGrid}>
                <div className={styles.statItem}>
                  <span className={styles.statLabel}>Output Gap</span>
                  <span className={styles.statValue} style={{ color: result.daily_production.output_gap < 0 ? 'var(--error)' : 'var(--success)' }}>
                    {result.daily_production.output_gap} units
                  </span>
                </div>
                <div className={styles.statItem}>
                  <span className={styles.statLabel}>Damage Pct</span>
                  <span className={styles.statValue} style={{ color: result.daily_production.damage_exceeded ? 'var(--error)' : 'var(--foreground)' }}>
                    {result.daily_production.damage_pct_of_commitment.toFixed(1)}%
                  </span>
                </div>
                <div className={styles.statItem}>
                  <span className={styles.statLabel}>Gap Percentage</span>
                  <span className={styles.statValue}>{result.daily_production.gap_pct.toFixed(1)}%</span>
                </div>
                <div className={styles.statItem}>
                  <span className={styles.statLabel}>Working Days Left</span>
                  <span className={styles.statValue}>{result.scheduling.working_days_remaining}</span>
                </div>
              </div>

              {/* Scheduling & Timeline */}
              <div className={styles.timelineCard}>
                <h4 className={styles.cardTitle}>Scheduling & Deadlines</h4>
                <div className={styles.timelineRow}>
                  <span>Projected Completion:</span>
                  <strong>{result.scheduling.projected_completion_date}</strong>
                </div>
                <div className={styles.timelineRow}>
                  <span>Buyer Required Date:</span>
                  <strong>{result.scheduling.buyer_required_date}</strong>
                </div>
                <div className={styles.timelineRow}>
                  <span>Days to Deadline:</span>
                  <strong style={{ color: result.scheduling.days_to_deadline < 0 ? 'var(--error)' : 'inherit' }}>
                    {result.scheduling.days_to_deadline} Days
                  </strong>
                </div>
                <div className={`${styles.deadlineStatus} ${result.scheduling.on_track ? styles.onTrack : styles.offTrack}`}>
                  {result.scheduling.on_track ? 'ON TRACK' : 'OFF TRACK / BEHIND SCHEDULE'}
                </div>
              </div>

              {/* Action Plan */}
              <div className={styles.actionCard}>
                <div className={styles.actionHeader}>
                  <svg fill="none" viewBox="0 0 24 24" stroke="currentColor" width="20"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 10V3L4 14h7v7l9-11h-7z" /></svg>
                  <span>AI Action Plan</span>
                </div>
                <div className={styles.actionContent}>
                  <strong>Recommendation:</strong> {result.risk_detection.recommendation}
                </div>
                <div className={styles.actionContent}>
                  <strong>Next Step:</strong> {result.planning_output.next_step}
                </div>
                {result.planning_output.escalation_needed && (
                  <div className={styles.escalationWarning}>
                    Escalation required to production manager.
                  </div>
                )}
              </div>
            </div>
          ) : (
            <div className={styles.noResults}>
              <svg fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" /></svg>
              <p>Submit daily production logs to monitor risk levels and gaps.</p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
