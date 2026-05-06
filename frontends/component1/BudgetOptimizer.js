import React, { useState } from 'react';

const BudgetOptimizer = ({ predictions, onOptimize }) => {
  const [selectedBudget, setSelectedBudget] = useState(predictions.budget);
  
  const budgetOptions = [
    { label: 'Minimum', value: Math.max(100, predictions.budget * 0.5), roi: '8-12%' },
    { label: 'Recommended', value: predictions.optimalBudget, roi: '20-30%' },
    { label: 'Aggressive', value: Math.min(50000, predictions.budget * 2), roi: '15-20%' }
  ];

  const handleOptimize = () => {
    const optimizedCampaign = {
      ...predictions,
      budget: selectedBudget
    };
    onOptimize(optimizedCampaign);
  };

  return (
    <div className="budget-optimizer">
      <div className="optimizer-info">
        <p>Based on your campaign data, we've calculated the optimal budget allocation:</p>
      </div>

      <div className="budget-options">
        {budgetOptions.map((option, index) => (
          <div 
            key={index}
            className={`budget-option ${selectedBudget === option.value ? 'selected' : ''}`}
            onClick={() => setSelectedBudget(option.value)}
          >
            <div className="budget-option-label">{option.label}</div>
            <div className="budget-option-value">
              ${option.value.toLocaleString()}
            </div>
            <div className="budget-option-roi">Expected ROI: {option.roi}</div>
          </div>
        ))}
      </div>

      <div className="custom-budget">
        <label>Custom Budget Amount:</label>
        <input
          type="range"
          min="100"
          max="50000"
          step="100"
          value={selectedBudget}
          onChange={(e) => setSelectedBudget(Number(e.target.value))}
        />
        <div className="budget-value-display">
          ${selectedBudget.toLocaleString()}
        </div>
      </div>

      <div className="optimization-tips">
        <h4>💰 Optimization Tips:</h4>
        <ul>
          <li>✓ {predictions.platform} performs best with ${predictions.optimalBudget.toLocaleString()} budget</li>
          <li>✓ Target audience {predictions.targetAudience} shows high conversion potential</li>
          <li>✓ Consider A/B testing creative formats for better engagement</li>
        </ul>
      </div>

      <button onClick={handleOptimize} className="btn-primary">
        🔄 Apply Optimized Budget
      </button>
    </div>
  );
};

export default BudgetOptimizer;
