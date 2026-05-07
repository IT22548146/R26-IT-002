import React from 'react';

const CampaignHistory = ({ history, onRerun }) => {
  const formatCurrency = (value) => {
    return new Intl.NumberFormat('en-US', {
      style: 'currency',
      currency: 'USD',
      minimumFractionDigits: 0,
      maximumFractionDigits: 0
    }).format(value);
  };

  const formatDate = (dateString) => {
    return new Date(dateString).toLocaleDateString();
  };

  if (history.length === 0) {
    return (
      <div className="empty-state">
        <p>No campaigns saved yet. Predict and save campaigns to see history.</p>
      </div>
    );
  }

  return (
    <div className="campaign-history">
      <table className="history-table">
        <thead>
          <tr>
            <th>Campaign Name</th>
            <th>Platform</th>
            <th>Budget</th>
            <th>Revenue</th>
            <th>Profit</th>
            <th>ROI</th>
            <th>Status</th>
            <th>Actions</th>
          </tr>
        </thead>
        <tbody>
          {history.map((campaign, index) => (
            <tr key={index} className={campaign.isProfitable ? 'profitable-row' : 'warning-row'}>
              <td>{campaign.campaignName || 'Unnamed'}</td>
              <td>{campaign.platform}</td>
              <td>{formatCurrency(campaign.budget)}</td>
              <td>{formatCurrency(campaign.predictedRevenue)}</td>
              <td className={campaign.profit >= 0 ? 'positive' : 'negative'}>
                {formatCurrency(campaign.profit)}
              </td>
              <td className={campaign.roi >= 0 ? 'positive' : 'negative'}>
                {campaign.roi.toFixed(1)}%
              </td>
              <td>
                <span className={`status-badge ${campaign.status}`}>
                  {campaign.isProfitable ? 'Profitable' : 'At Risk'}
                </span>
              </td>
              <td>
                <button 
                  onClick={() => onRerun(campaign)} 
                  className="btn-small"
                >
                  Rerun
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      
      <div className="history-summary">
        <div className="summary-stat">
          <strong>Total Campaigns:</strong> {history.length}
        </div>
        <div className="summary-stat">
          <strong>Profitable:</strong> {history.filter(h => h.isProfitable).length}
        </div>
        <div className="summary-stat">
          <strong>Average ROI:</strong> 
          {(history.reduce((sum, h) => sum + h.roi, 0) / history.length).toFixed(1)}%
        </div>
      </div>
    </div>
  );
};

export default CampaignHistory;
