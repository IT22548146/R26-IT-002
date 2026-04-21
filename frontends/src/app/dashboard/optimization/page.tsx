'use client';

import { useState } from 'react';
import styles from './optimization.module.css';

interface OptimizationResponse {
  buyer_name: string;
  confidence: string;
  optimization: {
    days_to_clear_workload: number;
    machine_allocation_advice: string;
    priority_handling: string;
    risk_flag_count: number;
    risk_flags: string[];
    risk_level: string;
    workforce_plan: string;
    workload_balance: string;
  };
  performance_analysis: {
    best_plant_recommendation: string;
    performance_score: number;
    recommendation: string;
    star_description: string;
    star_label: string;
    star_rating: string;
  };
  planning_output: {
    final_assessment: string;
    future_strategy: string;
    immediate_actions: string[];
    key_issues: string[];
  };
  plant_location: string;
  plant_name: string;
  plant_recommendation: {
    eligible_count: number;
    eligible_plants: string[];
    ineligible_plants: string[];
    plant_ranking: Array<{
      can_handle: boolean;
      location: string;
      p75_output: number;
      plant: string;
      quality_score: number;
      rank: number;
    }>;
    plant_score: number;
    recommendation_note: string;
    recommended_plant: string;
    required_daily_rate: number;
    split_needed: boolean;
    urgent_bonus_applied: boolean;
  };
  production_summary: {
    actual_completion_days: number;
    breakdown_worker_days: number;
    delay_days: number;
    delay_ratio: number;
    delay_status: string;
    efficiency_score: number;
    machine_idle_rate: number;
    machine_utilization: number;
    order_quantity: number;
    overrun_days: number;
    planned_completion_days: number;
    risk_per_workload: number;
  };
  record_id: string;
  status: string;
  style_id: string;
}

export default function OptimizationPage() {
  const [formData, setFormData] = useState({
    plant_name: "MRC Group",
    buyer_name: "Hirdaramani",
    style_id: "AH3821",
    order_quantity: 12000,
    planned_completion_days: 28,
    actual_completion_days: 33,
    machine_count: 16,
    active_machine_count: 11,
    employee_count: 48,
    daily_output_avg: 450,
    total_workload: 18000,
    urgent_style_flag: "Yes",
    urgent_handled_count: 2,
    risk_count_from_component3: 6,
    machine_breakdown_days: 4,
    worker_shortage_days: 2,
    damage_rate: 3.2
  });

  const [result, setResult] = useState<OptimizationResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const handleChange = (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) => {
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
      const response = await fetch('http://localhost:5000/api/component4/predict', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(formData),
      });

      if (!response.ok) {
        throw new Error('Failed to fetch optimization data.');
      }

      const data = await response.json();
      setResult(data);
    } catch (err: any) {
      setError(err.message || 'An error occurred');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className={styles.container}>
      <div className={styles.grid}>
        {/* Form Section */}
        <div className={styles.card}>
          <h2>
            <svg fill="none" viewBox="0 0 24 24" stroke="currentColor" width="24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M11 3.055A9.001 9.001 0 1020.945 13H11V3.055z" /><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M20.488 9H15V3.512A9.025 9.025 0 0120.488 9z" /></svg>
            Performance Metrics
          </h2>
          <form onSubmit={handleSubmit} className={styles.formGrid}>
            <div className={styles.sectionTitle}>Identification</div>
            <div className={styles.formGroup}>
              <label>Plant Name</label>
              <input name="plant_name" value={formData.plant_name} onChange={handleChange} required placeholder="Enter plant name" />
            </div>
            <div className={styles.formGroup}>
              <label>Buyer Name</label>
              <input name="buyer_name" value={formData.buyer_name} onChange={handleChange} required placeholder="Enter buyer name" />
            </div>
            <div className={styles.formGroup}>
              <label>Style ID</label>
              <input name="style_id" value={formData.style_id} onChange={handleChange} required placeholder="Enter style ID" />
            </div>
            
            <div className={styles.sectionTitle}>Timeline & Scale</div>
            <div className={styles.formGroup}>
              <label>Order Quantity</label>
              <input type="number" name="order_quantity" value={formData.order_quantity ?? ''} onChange={handleChange} required />
            </div>
            <div className={styles.formGroup}>
              <label>Total Workload</label>
              <input type="number" name="total_workload" value={formData.total_workload ?? ''} onChange={handleChange} required />
            </div>
            <div className={styles.formGroup}>
              <label>Planned Days</label>
              <input type="number" name="planned_completion_days" value={formData.planned_completion_days ?? ''} onChange={handleChange} required />
            </div>
            <div className={styles.formGroup}>
              <label>Actual Days</label>
              <input type="number" name="actual_completion_days" value={formData.actual_completion_days ?? ''} onChange={handleChange} required />
            </div>

            <div className={styles.sectionTitle}>Resources & Output</div>
            <div className={styles.formGroup}>
              <label>Total Machines</label>
              <input type="number" name="machine_count" value={formData.machine_count ?? ''} onChange={handleChange} required />
            </div>
            <div className={styles.formGroup}>
              <label>Active Machines</label>
              <input type="number" name="active_machine_count" value={formData.active_machine_count ?? ''} onChange={handleChange} required />
            </div>
            <div className={styles.formGroup}>
              <label>Daily Output Avg</label>
              <input type="number" step="0.1" name="daily_output_avg" value={formData.daily_output_avg ?? ''} onChange={handleChange} required />
            </div>
            <div className={styles.formGroup}>
              <label>Employee Count</label>
              <input type="number" name="employee_count" value={formData.employee_count ?? ''} onChange={handleChange} required />
            </div>
            <div className={styles.formGroup}>
              <label>Damage Rate %</label>
              <input type="number" step="0.01" name="damage_rate" value={formData.damage_rate ?? ''} onChange={handleChange} required />
            </div>

            <div className={styles.sectionTitle}>Issues & Risks</div>
            <div className={styles.formGroup}>
              <label>Breakdown Days</label>
              <input type="number" name="machine_breakdown_days" value={formData.machine_breakdown_days ?? ''} onChange={handleChange} required />
            </div>
            <div className={styles.formGroup}>
              <label>Shortage Days</label>
              <input type="number" name="worker_shortage_days" value={formData.worker_shortage_days ?? ''} onChange={handleChange} required />
            </div>
            <div className={styles.formGroup}>
              <label>Risk Count (C3)</label>
              <input type="number" name="risk_count_from_component3" value={formData.risk_count_from_component3 ?? ''} onChange={handleChange} required />
            </div>
            <div className={styles.formGroup}>
              <label>Urgent Style?</label>
              <select name="urgent_style_flag" value={formData.urgent_style_flag} onChange={handleChange}>
                <option value="No">No</option>
                <option value="Yes">Yes</option>
              </select>
            </div>
            <div className={styles.formGroup}>
              <label>Urgent Handled</label>
              <input type="number" name="urgent_handled_count" value={formData.urgent_handled_count ?? ''} onChange={handleChange} required />
            </div>
            
            <button type="submit" className={styles.submitBtn} disabled={loading}>
              {loading ? 'Optimizing...' : 'Analyze & Optimize Performance'}
            </button>
          </form>
          {error && <p style={{ color: 'var(--error)', marginTop: '1rem' }}>{error}</p>}
        </div>

        {/* Results Section */}
        <div className={styles.card}>
          <h2>
            <svg fill="none" viewBox="0 0 24 24" stroke="currentColor" width="24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 3v4M3 5h4M6 17v4m-2-2h4m5-16l2.286 6.857L21 12l-5.714 2.143L13 21l-2.286-6.857L5 12l5.714-2.143L13 3z" /></svg>
            Optimization Results
          </h2>

          {result ? (
            <div className={styles.results}>
              {/* Performance Analysis Header */}
              <div className={styles.performanceHeader}>
                <div className={styles.stars}>{result.performance_analysis.star_rating}</div>
                <div className={styles.scoreContainer}>
                  <div className={styles.scoreValue}>{result.performance_analysis.performance_score.toFixed(2)}</div>
                  <div className={styles.scoreLabel}>Performance Score</div>
                </div>
                <div className={styles.performanceInfo}>
                  <h3>{result.performance_analysis.star_label}</h3>
                  <p>{result.performance_analysis.star_description}</p>
                </div>
                <span className={`${styles.statusBadge} ${result.production_summary.delay_status === 'Delayed' ? styles.delayed : styles.ontime}`}>
                  {result.production_summary.delay_status} ({result.production_summary.delay_days}d delay)
                </span>
              </div>

              {/* Summary Stats Grid */}
              <div className={styles.statsGrid}>
                <div className={styles.statItem}>
                  <span className={styles.statLabel}>Machine Utilization</span>
                  <span className={styles.statValue}>{(result.production_summary.machine_utilization * 100).toFixed(1)}%</span>
                  <div className={styles.miniBar}><div style={{ width: `${result.production_summary.machine_utilization * 100}%` }}></div></div>
                </div>
                <div className={styles.statItem}>
                  <span className={styles.statLabel}>Machine Idle Rate</span>
                  <span className={styles.statValue} style={{ color: result.production_summary.machine_idle_rate > 0.2 ? 'var(--error)' : 'inherit' }}>
                    {(result.production_summary.machine_idle_rate * 100).toFixed(1)}%
                  </span>
                </div>
                <div className={styles.statItem}>
                  <span className={styles.statLabel}>Efficiency Score</span>
                  <span className={styles.statValue}>{result.production_summary.efficiency_score.toFixed(2)}</span>
                </div>
                <div className={styles.statItem}>
                  <span className={styles.statLabel}>Risk Level</span>
                  <span className={`${styles.riskBadge} ${result.optimization.risk_level === 'Medium' ? styles.riskMedium : result.optimization.risk_level === 'High' ? styles.riskHigh : styles.riskLow}`}>
                    {result.optimization.risk_level}
                  </span>
                </div>
              </div>

              {/* Detailed Optimization Cards */}
              <div className={styles.optimizationDetails}>
                <div className={styles.optCard}>
                  <div className={styles.optTitle}>Workload Balance</div>
                  <p className={styles.optText}>{result.optimization.workload_balance}</p>
                </div>
                <div className={styles.optCard}>
                  <div className={styles.optTitle}>Machine Allocation</div>
                  <p className={styles.optText}>{result.optimization.machine_allocation_advice}</p>
                </div>
                <div className={styles.optCard}>
                  <div className={styles.optTitle}>Workforce Plan</div>
                  <p className={styles.optText}>{result.optimization.workforce_plan}</p>
                </div>
              </div>

              {/* Plant Recommendations Ranking */}
              <div className={styles.recommendationSection}>
                <div className={styles.sectionHeader}>
                  <h4>Alternative Plant Recommendations</h4>
                  <span className={styles.eligibleCount}>{result.plant_recommendation.eligible_count} Eligible Plants</span>
                </div>
                <p className={styles.recommendationNote}>{result.plant_recommendation.recommendation_note}</p>
                
                <div className={styles.tableContainer}>
                  <table className={styles.rankingTable}>
                    <thead>
                      <tr>
                        <th>Rank</th>
                        <th>Plant</th>
                        <th>Location</th>
                        <th>Quality</th>
                        <th>P75 Output</th>
                      </tr>
                    </thead>
                    <tbody>
                      {result.plant_recommendation.plant_ranking.map((item) => (
                        <tr key={item.rank} className={item.plant === result.plant_recommendation.recommended_plant ? styles.recommended : ''}>
                          <td><span className={styles.rankCircle}>{item.rank}</span></td>
                          <td>
                            {item.plant}
                            {item.plant === result.plant_recommendation.recommended_plant && <span className={styles.bestLabel}>BEST</span>}
                          </td>
                          <td>{item.location}</td>
                          <td>{item.quality_score.toFixed(2)}</td>
                          <td>{item.p75_output.toFixed(0)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>

              {/* Action Strategy */}
              <div className={styles.strategySection}>
                <div className={styles.strategyCard}>
                  <div className={styles.strategyHeader}>Immediate Actions</div>
                  <ul className={styles.actionList}>
                    {result.planning_output.immediate_actions.map((action, i) => (
                      <li key={i}>{action}</li>
                    ))}
                  </ul>
                </div>
                <div className={styles.strategyCard}>
                  <div className={styles.strategyHeader}>Future Strategy</div>
                  <p className={styles.strategyText}>{result.planning_output.future_strategy}</p>
                </div>
              </div>
            </div>
          ) : (
            <div className={styles.noResults}>
              <svg fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 10V3L4 14h7v7l9-11h-7z" /></svg>
              <p>Analyze performance metrics to receive optimization scores and suggested actions.</p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
