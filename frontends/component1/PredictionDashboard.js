import React from 'react';

const PredictionDashboard = ({ predictions, onSave }) => {
  const formatCurrency = (value) => {
    return new Intl.NumberFormat('en-US', {
      style: 'currency',
      currency: 'USD',
      minimumFractionDigits: 0,
      maximumFractionDigits: 0
    }).format(value);
  };

  const formatPercentage = (value) => {
    return `${value.toFixed(1)}%`;
  };

  return (
    <div className="prediction-dashboard">
      <div className={`status-banner ${predictions.status}`}>
        {predictions.isProfitable ? '✅ PROFITABLE CAMPAIGN' : '⚠️ HIGH RISK - NOT PROFITABLE'}
      </div>

      <div className="metrics-grid">
        <div className="metric-card">
          <div className="metric-label">Campaign</div>
          <div className="metric-value">{predictions.campaignName || 'Unnamed'}</div>
          <div className="metric-sub">{predictions.platform}</div>
        </div>

        <div className="metric-card">
          <div className="metric-label">Ad Spend</div>
          <div className="metric-value">{formatCurrency(predictions.budget)}</div>
          <div className="metric-sub">Proposed Budget</div>
        </div>

        <div className="metric-card">
          <div className="metric-label">Predicted Revenue</div>
          <div className="metric-value">{formatCurrency(predictions.predictedRevenue)}</div>
          <div className="metric-sub">Expected Sales</div>
        </div>

        <div className="metric-card">
          <div className="metric-label">Profit / Loss</div>
          <div className={`metric-value ${predictions.profit >= 0 ? 'positive' : 'negative'}`}>
            {formatCurrency(predictions.profit)}
          </div>
          <div className="metric-sub">After Ad Spend</div>
        </div>

        <div className="metric-card">
          <div className="metric-label">Return on Investment (ROI)</div>
          <div className={`metric-value ${predictions.roi >= 0 ? 'positive' : 'negative'}`}>
            {formatPercentage(predictions.roi)}
          </div>
          <div className="metric-sub">Industry Avg: 15-25%</div>
        </div>

        <div className="metric-card">
          <div className="metric-label">Optimal Budget</div>
          <div className="metric-value">{formatCurrency(predictions.optimalBudget)}</div>
          <div className="metric-sub">
            {predictions.optimalBudget !== predictions.budget ? 
              `Save ${formatCurrency(Math.abs(predictions.optimalBudget - predictions.budget))}` : 
              'Budget is optimal'}
          </div>
        </div>
      </div>

      {!predictions.isProfitable && (
        <div className="warning-box">
          <strong>⚠️ Warning:</strong> This campaign is predicted to be unprofitable.
          Consider adjusting your targeting, platform, or budget based on the optimization suggestions below.
        </div>
      )}

      {predictions.roi > 30 && (
        <div className="success-box">
          <strong>🎉 Excellent Opportunity!</strong> High ROI predicted. Consider scaling this campaign.
        </div>
      )}

      <div className="action-buttons">
        <button onClick={onSave} className="btn-secondary">💾 Save Campaign</button>
        <button className="btn-outline">📤 Export Report</button>
      </div>
    </div>
  );
};

export default PredictionDashboard;
