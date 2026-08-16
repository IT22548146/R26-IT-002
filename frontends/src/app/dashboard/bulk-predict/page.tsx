'use client';

import { useState } from 'react';
import styles from './bulk-predict.module.css';

interface BulkPredictionResponse {
  allocation: {
    allocated_bulk_plant: string;
    allocated_plant_location: string;
    allocation_remark: string;
    allocation_type: string;
    plant_ranking: Array<{
      can_handle_solo: boolean;
      is_sample_plant: boolean;
      location: string;
      monthly_capacity: number;
      plant: string;
      preferred: boolean;
      quality_rating: number;
      rank: number;
      score: number;
      working_days: number;
    }>;
  };
  capacity_check: {
    load_ratio: number;
    manager_confirmation: string;
    monthly_piece_capacity: number;
    monthly_styles_capacity: number;
    plant_working_days: number;
    sample_plant: string;
    sample_plant_capacity_status: string;
    utilisation_pct: number;
  };
  confidence: string;
  deadline_assessment: {
    buyer_approval_required: boolean;
    buyer_email_required: string;
    buyer_required_date: string;
    days_to_deadline: number;
    deadline_match_status: string;
    system_action: string;
  };
  design_analysis: {
    color_count: number;
    color_impact: string;
    complexity_score: number;
    derived_complexity: string;
    design_length: number;
    design_width: number;
    matrix_complexity: string;
    stitch_count: number;
    stitch_impact: string;
  };
  order_summary: {
    bulk_order_quantity: number;
    daily_commitment: number;
    damage_pct: number;
    effective_quantity: number;
    sample_plant: string;
    style_priority: string;
  };
  planning_output: {
    final_decision: string;
    recommended_action: string;
    risk_level: string;
    risk_summary: string;
  };
  production_days: {
    base_embroidery_days: number;
    bulk_shipment_date: string;
    capacity_factor: number;
    capacity_load_ratio: number;
    color_factor: number;
    cutting_days: number;
    daily_commitment_warning: string | null;
    design_area_factor: number;
    design_emb_days: number;
    embroidery_days: number;
    lead_days: number;
    predicted_completion_date: string;
    recommended_daily_commitment: number;
    sewing_days: number;
    stitch_factor: number;
    total_production_days: number;
  };
  status: string;
  style_id: string;
}

export default function BulkPredictPage() {
  const [formData, setFormData] = useState({
    style_id: 'BYGR5001',
    buyer_name: 'George',
    bulk_order_quantity: 10360,
    daily_commitment: 364,
    style_priority: 'Normal',
    design_width: 25,
    design_length: 38,
    color_count: 8,
    stitch_count: 1000,
    sample_plant: 'MRC Group',
    bulk_order_approved_date: '2025-03-01',
    buyer_required_date: '2025-06-15',
    damage_pct: 0,
  });

  const [monthlyCapacity, setMonthlyCapacity] = useState({
    "Dinusha Embroidery": 11,
    "Regal Image International": 160,
    "MRC Group": 132,
    "The Bobbin Group": 178,
    "Sunrose Lanka (Pvt) Ltd": 146,
    "Amsral Lanka Enterprises": 113
  });

  const [result, setResult] = useState<BulkPredictionResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const handleChange = (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) => {
    const { name, value, type } = e.target;
    setFormData((prev) => ({
      ...prev,
      [name]: type === 'number' ? (value === '' ? '' : parseFloat(value)) : value,
    }));
  };

  const handleCapacityChange = (plant: string, value: string) => {
    setMonthlyCapacity((prev) => ({
      ...prev,
      [plant]: value === '' ? '' : parseFloat(value),
    }));
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError('');
    setResult(null);

    const payload = {
      ...formData,
      monthly_capacity: monthlyCapacity
    };

    try {
      const response = await fetch('http://localhost:5000/api/component2/predict', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(payload),
      });

      if (!response.ok) {
        throw new Error('Failed to fetch bulk prediction.');
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
            <svg fill="none" viewBox="0 0 24 24" stroke="currentColor" width="24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 21V5a2 2 0 00-2-2H7a2 2 0 00-2 2v16m14 0h2m-2 0h-5m-9 0H3m2 0h5M9 7h1m-1 4h1m4-4h1m-1 4h1m-5 10v-5a1 1 0 011-1h2a1 1 0 011 1v5m-4 0h4" /></svg>
            Bulk Order Input
          </h2>
          <form onSubmit={handleSubmit} className={styles.formGrid}>
            <div className={styles.sectionTitle}>Basic Info</div>
            <div className={styles.formGroup}>
              <label>Style ID</label>
              <input name="style_id" value={formData.style_id} onChange={handleChange} required placeholder="Enter style ID" />
            </div>
            <div className={styles.formGroup}>
              <label>Buyer Name</label>
              <input name="buyer_name" value={formData.buyer_name} onChange={handleChange} required placeholder="Enter buyer name" />
            </div>
            
            <div className={styles.sectionTitle}>Order Metrics</div>
            <div className={styles.formGroup}>
              <label>Order Qty</label>
              <input type="number" name="bulk_order_quantity" value={formData.bulk_order_quantity ?? ''} onChange={handleChange} required />
            </div>
            <div className={styles.formGroup}>
              <label>Daily Commitment</label>
              <input type="number" name="daily_commitment" value={formData.daily_commitment ?? ''} onChange={handleChange} required />
            </div>
            <div className={styles.formGroup}>
              <label>Style Priority</label>
              <select name="style_priority" value={formData.style_priority} onChange={handleChange}>
                <option value="High">High</option>
                <option value="Normal">Normal</option>
                <option value="Low">Low</option>
              </select>
            </div>
            <div className={styles.formGroup}>
              <label>Design Width</label>
              <input type="number" step="0.1" name="design_width" value={formData.design_width ?? ''} onChange={handleChange} required />
            </div>
            <div className={styles.formGroup}>
              <label>Design Length</label>
              <input type="number" step="0.1" name="design_length" value={formData.design_length ?? ''} onChange={handleChange} required />
            </div>
            <div className={styles.formGroup}>
              <label>Color Count</label>
              <input type="number" name="color_count" value={formData.color_count ?? ''} onChange={handleChange} required />
            </div>
            <div className={styles.formGroup}>
              <label>Stitch Count</label>
              <input type="number" name="stitch_count" value={formData.stitch_count ?? ''} onChange={handleChange} required />
            </div>
            <div className={styles.formGroup}>
              <label>Damage %</label>
              <input type="number" step="0.01" name="damage_pct" value={formData.damage_pct ?? ''} onChange={handleChange} required />
            </div>

            <div className={styles.sectionTitle}>Plant & Timeline</div>
            <div className={styles.formGroup}>
              <label>Sample Plant</label>
              <input name="sample_plant" value={formData.sample_plant} onChange={handleChange} required />
            </div>
            <div className={styles.formGroup}>
              <label>Approved Date</label>
              <input type="date" name="bulk_order_approved_date" value={formData.bulk_order_approved_date} onChange={handleChange} required />
            </div>
            <div className={styles.formGroup}>
              <label>Buyer Required Date</label>
              <input type="date" name="buyer_required_date" value={formData.buyer_required_date} onChange={handleChange} required />
            </div>

            <div className={styles.sectionTitle}>Monthly Capacities (Plants)</div>
            {Object.entries(monthlyCapacity).map(([plant, cap]) => (
              <div key={plant} className={styles.formGroup}>
                <label>{plant}</label>
                <input type="number" value={cap ?? ''} onChange={(e) => handleCapacityChange(plant, e.target.value)} required />
              </div>
            ))}
            
            <button type="submit" className={styles.submitBtn} disabled={loading}>
              {loading ? 'Analyzing Bulk Order...' : 'Run Bulk Analysis'}
            </button>
          </form>
          {error && <p style={{ color: 'var(--error)', marginTop: '1rem' }}>{error}</p>}
        </div>

        {/* Results Section */}
        <div className={styles.card}>
          <h2>
            <svg fill="none" viewBox="0 0 24 24" stroke="currentColor" width="24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 7h8m0 0v8m0-8l-8 8-4-4-6 6" /></svg>
            Production Timeline & Allocation
          </h2>

          {result ? (
            <div className={styles.results}>
              {/* Planning & Decision Card */}
              <div className={`${styles.statusCard} ${result.planning_output.risk_level === 'Low' ? styles.statusLowRisk : styles.statusHighRisk}`}>
                <div className={styles.statusHeader}>
                  <div className={styles.statusTitle}>Final Decision: {result.planning_output.final_decision}</div>
                  <span className={styles.riskBadge}>Risk: {result.planning_output.risk_level}</span>
                </div>
                <div className={styles.statusAction}>{result.planning_output.recommended_action}</div>
                <p className={styles.statusRemark}>{result.planning_output.risk_summary}</p>
              </div>

              {/* Allocation Section */}
              <div className={styles.allocationSection}>
                <div className={styles.sectionHeader}>
                  <h3 className={styles.sectionHeading}>Allocation Recommendation</h3>
                  <span className={styles.allocationType}>{result.allocation.allocation_type}</span>
                </div>
                <div className={styles.allocationRemark}>{result.allocation.allocation_remark}</div>
                <div className={styles.allocatedPlantInfo}>
                  <strong>Allocated Plant:</strong> {result.allocation.allocated_bulk_plant} ({result.allocation.allocated_plant_location})
                </div>

                <div className={styles.tableContainer}>
                  <table className={styles.rankingTable}>
                    <thead>
                      <tr>
                        <th>Rank</th>
                        <th>Plant</th>
                        <th>Location</th>
                        <th>Monthly Cap</th>
                        <th>Score</th>
                        <th>Preferred</th>
                      </tr>
                    </thead>
                    <tbody>
                      {result.allocation.plant_ranking.map((item) => (
                        <tr key={item.plant} className={item.plant === result.allocation.allocated_bulk_plant ? styles.recommended : ''}>
                          <td><div className={styles.rankBadge}>{item.rank}</div></td>
                          <td>{item.plant} {item.is_sample_plant && <span className={styles.sampleLabel}>(Sample)</span>}</td>
                          <td>{item.location}</td>
                          <td>{item.monthly_capacity}</td>
                          <td>{item.score.toFixed(2)}</td>
                          <td>{item.preferred ? '✅' : '-'}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>

              {/* Production Timeline Grid */}
              <div className={styles.timelineSection}>
                <h3 className={styles.sectionHeading}>Production Timeline Breakdown</h3>
                <div className={styles.leadTimeGrid}>
                  <div className={styles.leadTimeItem}>
                    <span className={styles.leadTimeLabel}>Cutting</span>
                    <span className={styles.leadTimeValue}>{result.production_days.cutting_days} d</span>
                  </div>
                  <div className={styles.leadTimeItem}>
                    <span className={styles.leadTimeLabel}>Embroidery</span>
                    <span className={styles.leadTimeValue}>{result.production_days.embroidery_days} d</span>
                  </div>
                  <div className={styles.leadTimeItem}>
                    <span className={styles.leadTimeLabel}>Sewing</span>
                    <span className={styles.leadTimeValue}>{result.production_days.sewing_days} d</span>
                  </div>
                  <div className={`${styles.leadTimeItem} ${styles.totalLeadTime}`}>
                    <span className={styles.leadTimeLabel}>Total Lead Time</span>
                    <span className={styles.leadTimeValue}>{result.production_days.lead_days} Days</span>
                  </div>
                </div>

                <div className={styles.dateSummaryGrid}>
                  <div className={styles.dateItem}>
                    <span className={styles.dateLabel}>Predicted Completion</span>
                    <strong className={styles.dateValue}>{result.production_days.predicted_completion_date}</strong>
                  </div>
                  <div className={styles.dateItem}>
                    <span className={styles.dateLabel}>Bulk Shipment Date</span>
                    <strong className={styles.dateValue}>{result.production_days.bulk_shipment_date}</strong>
                  </div>
                </div>
                {result.production_days.daily_commitment_warning && (
                  <div className={styles.warningBox}>
                    <svg fill="none" viewBox="0 0 24 24" stroke="currentColor" width="16"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" /></svg>
                    {result.production_days.daily_commitment_warning}
                  </div>
                )}
              </div>

              {/* Capacity & Deadline Checks */}
              <div className={styles.checksGrid}>
                <div className={styles.checkCard}>
                  <h4 className={styles.checkTitle}>Capacity Assessment</h4>
                  <div className={styles.checkRow}>
                    <span>Utilisation:</span>
                    <strong>{result.capacity_check.utilisation_pct.toFixed(1)}%</strong>
                  </div>
                  <div className={styles.checkRow}>
                    <span>Load Ratio:</span>
                    <strong>{result.capacity_check.load_ratio.toFixed(4)}</strong>
                  </div>
                  <div className={styles.checkRow}>
                    <span>Manager Conf:</span>
                    <strong className={result.capacity_check.manager_confirmation === 'No Capacity' ? styles.textError : styles.textSuccess}>
                      {result.capacity_check.manager_confirmation}
                    </strong>
                  </div>
                </div>
                <div className={styles.checkCard}>
                  <h4 className={styles.checkTitle}>Deadline Verification</h4>
                  <div className={styles.checkRow}>
                    <span>Status:</span>
                    <strong className={result.deadline_assessment.deadline_match_status === 'Match' ? styles.textSuccess : styles.textError}>
                      {result.deadline_assessment.deadline_match_status}
                    </strong>
                  </div>
                  <div className={styles.checkRow}>
                    <span>Days to Deadline:</span>
                    <strong>{result.deadline_assessment.days_to_deadline} Days</strong>
                  </div>
                  <div className={styles.checkRow}>
                    <span>System Action:</span>
                    <span className={styles.actionSmall}>{result.deadline_assessment.system_action}</span>
                  </div>
                </div>
              </div>
            </div>
          ) : (
            <div className={styles.noResults}>
              <svg fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 17v-2m3 2v-4m3 4v-6m2 10H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" /></svg>
              <p>Run the analysis to see the bulk order production timeline.</p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
