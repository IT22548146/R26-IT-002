'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import styles from './predict.module.css';

interface PredictionResponse {
  buyer_name: string;
  confidence: string;
  input_summary: {
    buffer_days: number;
    buyer_required_date: string;
    completion_days: number;
    is_q4: boolean;
    priority_level: string;
    receive_date: string;
    sample_qty: number;
  };
  model1_overrun: {
    interpretation: string;
    predicted_overrun_days: number;
  };
  model2_plant_selection: {
    ranking: Array<{
      plant: string;
      rank: number;
      score: number;
    }>;
    recommended_plant: string;
  };
  model3_delay: {
    delay_prediction: string;
    delay_probability: number;
    shipment_status: string;
  };
  planning_output: {
    action_required: string;
    allocated: boolean;
    allocation_remark: string;
    auto_priority: string;
    buyer_approval_status: string;
    feasible: boolean;
    final_shipment_date: string;
    priority_level: string;
    risk_level: string;
    risk_summary: string;
  };
  scheduling: {
    buyer_ship_day: string;
    days_completion_to_ship: number;
    estimated_completion_date: string;
    nearest_shipment_date: string;
  };
  status: string;
  style_id: string;
}

export default function PredictPage() {
  const [formData, setFormData] = useState({
    buyer_name: 'M&S',
    style_id: 'TG1808',
    sample_qty: 10,
    cap_util_pct: 100,
    is_emergency_shipment: 1,
    receive_date: '2025-08-01',
    buyer_required_date: '2025-08-08',
  });

  const [result, setResult] = useState<PredictionResponse | null>(null);
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
      const response = await fetch('http://localhost:5000/api/component1/predict', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(formData),
      });

      if (!response.ok) {
        throw new Error('Failed to fetch prediction.');
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
            <svg fill="none" viewBox="0 0 24 24" stroke="currentColor" width="24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2" /></svg>
            Model Input Details
          </h2>
          <form onSubmit={handleSubmit} className={styles.formGrid}>
            <div className={styles.formGroup}>
              <label>Buyer Name</label>
              <input name="buyer_name" value={formData.buyer_name} onChange={handleChange} required placeholder="Enter buyer name" />
            </div>
            <div className={styles.formGroup}>
              <label>Style ID</label>
              <input name="style_id" value={formData.style_id} onChange={handleChange} required placeholder="Enter style ID" />
            </div>
            <div className={styles.formGroup}>
              <label>Sample Quantity</label>
              <input type="number" name="sample_qty" value={formData.sample_qty ?? ''} onChange={handleChange} required />
            </div>
            <div className={styles.formGroup}>
              <label>Cap Util %</label>
              <input type="number" name="cap_util_pct" value={formData.cap_util_pct ?? ''} onChange={handleChange} required />
            </div>
            <div className={styles.formGroup}>
              <label>Emergency Shipment</label>
              <select name="is_emergency_shipment" value={formData.is_emergency_shipment} onChange={handleChange}>
                <option value={0}>No</option>
                <option value={1}>Yes</option>
              </select>
            </div>
            <div className={styles.formGroup}>
              <label>Receive Date</label>
              <input type="date" name="receive_date" value={formData.receive_date} onChange={handleChange} required />
            </div>
            <div className={styles.formGroup}>
              <label>Buyer Required Date</label>
              <input type="date" name="buyer_required_date" value={formData.buyer_required_date} onChange={handleChange} required />
            </div>
            
            <button type="submit" className={styles.submitBtn} disabled={loading}>
              {loading ? (
                'Processing...'
              ) : (
                <>
                  <svg fill="none" viewBox="0 0 24 24" stroke="currentColor" width="20"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 10V3L4 14h7v7l9-11h-7z" /></svg>
                  Generate Prediction
                </>
              )}
            </button>
          </form>
          {error && <p style={{ color: 'var(--error)', marginTop: '1rem', fontSize: '0.875rem' }}>{error}</p>}
        </div>

        {/* Results Section */}
        <div className={styles.card}>
          <h2>
            <svg fill="none" viewBox="0 0 24 24" stroke="currentColor" width="24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" /></svg>
            Prediction Analysis
          </h2>

          {result ? (
            <div className={styles.results}>
              <div className={styles.resultHeader}>
                <div>
                  <h3 style={{ fontSize: '1.125rem', fontWeight: 600 }}>{result.style_id}</h3>
                  <p style={{ fontSize: '0.875rem', color: 'var(--secondary)' }}>Buyer: {result.buyer_name}</p>
                </div>
                <div style={{ display: 'flex', gap: '0.5rem' }}>
                  <span className={`${styles.badge} ${result.planning_output.risk_level === 'Low' ? styles.badgeSuccess : styles.badgeWarning}`}>
                    Risk: {result.planning_output.risk_level}
                  </span>
                  <span className={`${styles.badge} ${result.model3_delay.shipment_status === 'On Time' ? styles.badgeSuccess : styles.badgeWarning}`}>
                    {result.model3_delay.shipment_status}
                  </span>
                </div>
              </div>

              <div className={styles.summaryGrid}>
                <div className={styles.summaryItem}>
                  <span className={styles.summaryLabel}>Confidence</span>
                  <span className={styles.summaryValue}>{result.confidence}</span>
                </div>
                <div className={styles.summaryItem}>
                  <span className={styles.summaryLabel}>Overrun</span>
                  <span className={styles.summaryValue}>{result.model1_overrun.interpretation}</span>
                </div>
                <div className={styles.summaryItem}>
                  <span className={styles.summaryLabel}>Probability</span>
                  <span className={styles.summaryValue}>{(result.model3_delay.delay_probability * 100).toFixed(1)}%</span>
                </div>
                <div className={styles.summaryItem}>
                  <span className={styles.summaryLabel}>Priority</span>
                  <span className={styles.summaryValue}>{result.planning_output.priority_level}</span>
                </div>
              </div>

              <div className={styles.schedulingInfo}>
                <h4 style={{ fontSize: '0.875rem', fontWeight: 600, marginBottom: '0.8rem', color: 'var(--primary)' }}>Scheduling & Logistics</h4>
                <div className={styles.scheduleGrid}>
                  <div className={styles.scheduleItem}>
                    <span>Est. Completion</span>
                    <strong>{result.scheduling.estimated_completion_date}</strong>
                  </div>
                  <div className={styles.scheduleItem}>
                    <span>Nearest Ship Date</span>
                    <strong>{result.scheduling.nearest_shipment_date}</strong>
                  </div>
                  <div className={styles.scheduleItem}>
                    <span>Buyer Ship Day</span>
                    <strong>{result.scheduling.buyer_ship_day}</strong>
                  </div>
                  <div className={styles.scheduleItem}>
                    <span>Final Ship Date</span>
                    <strong>{result.planning_output.final_shipment_date}</strong>
                  </div>
                </div>
              </div>

              <div className={styles.plantSelection}>
                <h4 style={{ fontSize: '0.875rem', fontWeight: 600, marginBottom: '0.5rem' }}>Plant Recommendations</h4>
                <table className={styles.rankingTable}>
                  <thead>
                    <tr>
                      <th>Rank</th>
                      <th>Plant Name</th>
                      <th>Score</th>
                    </tr>
                  </thead>
                  <tbody>
                    {result.model2_plant_selection.ranking.map((item) => (
                      <tr key={item.plant} className={item.plant === result.model2_plant_selection.recommended_plant ? styles.recommended : ''}>
                        <td><div className={styles.rankBadge}>{item.rank}</div></td>
                        <td>
                          {item.plant}
                          {item.plant === result.model2_plant_selection.recommended_plant && 
                            <span style={{ marginLeft: '0.5rem', fontSize: '0.7rem', color: 'var(--primary)', fontWeight: 700 }}>(Best)</span>
                          }
                        </td>
                        <td>{item.score.toFixed(3)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              
              <div style={{ marginTop: '1rem', padding: '1rem', background: 'rgba(99, 102, 241, 0.05)', borderRadius: 'var(--radius-md)', fontSize: '0.875rem' }}>
                <div style={{ marginBottom: '0.5rem' }}>
                  <strong>Action Required:</strong> <span style={{ color: 'var(--primary)', fontWeight: 600 }}>{result.planning_output.action_required}</span>
                </div>
                <div>
                  <strong>Remark:</strong> {result.planning_output.allocation_remark}
                </div>
                <div style={{ marginTop: '0.5rem', fontSize: '0.8rem', color: 'var(--secondary)' }}>
                  {result.planning_output.risk_summary}
                </div>
              </div>
            </div>
          ) : (
            <div className={styles.noResults}>
              <svg fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 11H5m14 0a2 2 0 012 2v6a2 2 0 01-2 2H5a2 2 0 01-2-2v-6a2 2 0 012-2m14 0V9a2 2 0 00-2-2M5 11V9a2 2 0 012-2m0 0V5a2 2 0 012-2h6a2 2 0 012 2v2M7 7h10" /></svg>
              <p>Enter details and click generate to see the prediction analysis.</p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
