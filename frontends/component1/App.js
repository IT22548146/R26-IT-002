import React, { useState } from 'react';
import './App.css';
import CampaignForm from './components/CampaignForm';
import PredictionDashboard from './components/PredictionDashboard';
import BudgetOptimizer from './components/BudgetOptimizer';
import CampaignHistory from './components/CampaignHistory';
import ROIChart from './components/ROIChart';

function App() {
  const [predictions, setPredictions] = useState(null);
  const [currentCampaign, setCurrentCampaign] = useState(null);
  const [campaignHistory, setCampaignHistory] = useState([]);

  const handlePredict = (campaignData) => {
    // AI Prediction Logic
    const predictedRevenue = calculatePredictedRevenue(campaignData);
    const profit = predictedRevenue - campaignData.budget;
    const roi = (profit / campaignData.budget) * 100;
    const isProfitable = profit > 0;
    
    // Optimal budget suggestion
    const optimalBudget = findOptimalBudget(campaignData);
    
    const predictionResult = {
      ...campaignData,
      predictedRevenue,
      profit,
      roi,
      isProfitable,
      optimalBudget,
      timestamp: new Date().toISOString(),
      status: isProfitable ? 'success' : 'warning'
    };
    
    setPredictions(predictionResult);
    setCurrentCampaign(predictionResult);
    
    // Add to history
    setCampaignHistory([predictionResult, ...campaignHistory].slice(0, 10));
  };

  const calculatePredictedRevenue = (data) => {
    // Advanced prediction algorithm based on multiple factors
    const baseConversionRate = {
      'Facebook': 0.025,
      'Instagram': 0.032,
      'TikTok': 0.028,
      'Google': 0.045,
      'YouTube': 0.022
    };
    
    const platformMultiplier = {
      'Facebook': 1.0,
      'Instagram': 1.2,
      'TikTok': 1.1,
      'Google': 1.5,
      'YouTube': 0.9
    };
    
    const audienceMultiplier = {
      '18-24': 0.8,
      '25-34': 1.3,
      '35-44': 1.2,
      '45-54': 1.0,
      '55+': 0.7
    };
    
    const productMultiplier = {
      'Fashion': 1.2,
      'Electronics': 1.4,
      'Food': 0.9,
      'Health': 1.1,
      'Education': 1.3,
      'Other': 1.0
    };
    
    // Expected clicks
    const expectedClicks = data.budget * 0.05; // Assuming $0.05 per click average
    
    // Conversion rate based on platform, audience, and product
    let conversionRate = baseConversionRate[data.platform] || 0.03;
    conversionRate *= platformMultiplier[data.platform];
    conversionRate *= audienceMultiplier[data.targetAudience];
    conversionRate *= productMultiplier[data.productType];
    
    // Expected sales
    const expectedSales = expectedClicks * conversionRate;
    
    // Average order value
    const avgOrderValue = data.productType === 'Electronics' ? 150 :
                         data.productType === 'Fashion' ? 75 :
                         data.productType === 'Education' ? 200 :
                         data.productType === 'Health' ? 60 : 50;
    
    // Predicted revenue
    const predictedRevenue = expectedSales * avgOrderValue;
    
    // Add seasonality adjustment (assuming Q4 for better performance)
    const currentMonth = new Date().getMonth();
    const seasonalityMultiplier = currentMonth >= 9 && currentMonth <= 11 ? 1.4 : 1.0;
    
    return predictedRevenue * seasonalityMultiplier;
  };
  
  const findOptimalBudget = (data) => {
    // Test different budget levels to find max ROI
    let bestBudget = data.budget;
    let bestROI = -Infinity;
    
    const budgets = [500, 1000, 2000, 3000, 5000, 7500, 10000, 15000];
    
    for (const testBudget of budgets) {
      const testData = { ...data, budget: testBudget };
      const revenue = calculatePredictedRevenue(testData);
      const profit = revenue - testBudget;
      const roi = profit / testBudget;
      
      if (roi > bestROI && profit > 0) {
        bestROI = roi;
        bestBudget = testBudget;
      }
    }
    
    return bestBudget;
  };

  const handleSaveCampaign = () => {
    if (currentCampaign) {
      alert('✅ Campaign saved to history! Check the "Campaign History" section.');
    }
  };

  const handleRerunCampaign = (campaign) => {
    handlePredict(campaign);
  };

  return (
    <div className="app">
      <header className="app-header">
        <div className="header-content">
          <h1>📊 AdProfit AI</h1>
          <p>Intelligent ROI Prediction System for Digital Advertising</p>
        </div>
      </header>

      <main className="main-content">
        <div className="grid-2cols">
          <div className="card">
            <h2>🎯 New Campaign Configuration</h2>
            <CampaignForm onPredict={handlePredict} />
          </div>
          
          <div className="card">
            <h2>📈 AI Prediction Results</h2>
            {predictions ? (
              <PredictionDashboard 
                predictions={predictions} 
                onSave={handleSaveCampaign}
              />
            ) : (
              <div className="empty-state">
                <p>Configure a campaign and click "Predict Profitability" to see results</p>
              </div>
            )}
          </div>
        </div>

        <div className="grid-2cols">
          <div className="card">
            <h2>💰 Budget Optimizer</h2>
            {predictions ? (
              <BudgetOptimizer 
                predictions={predictions} 
                onOptimize={handlePredict}
              />
            ) : (
              <div className="empty-state">
                <p>Run a prediction first to see budget optimization suggestions</p>
              </div>
            )}
          </div>
          
          <div className="card">
            <h2>📉 ROI Visualization</h2>
            {predictions ? (
              <ROIChart predictions={predictions} />
            ) : (
              <div className="empty-state">
                <p>Run a prediction to visualize ROI metrics</p>
              </div>
            )}
          </div>
        </div>

        <div className="card full-width">
          <h2>📜 Campaign History (Last 10)</h2>
          <CampaignHistory 
            history={campaignHistory} 
            onRerun={handleRerunCampaign}
          />
        </div>
      </main>
    </div>
  );
}

export default App;
