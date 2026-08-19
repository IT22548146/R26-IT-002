# Garment Production Management System — AI Backend

A robust Flask-based API providing real-time predictive analytics and decision support for garment production. This system leverages Machine Learning models (XGBoost, Random Forest, etc.) to optimize planning, resource allocation, and emergency detection.

## 🚀 Core Components

The backend is organized into four specialized components, each accessible via its own API prefix:

### 1. Sample Planning System (`/api/component1`)
- **Overrun Prediction**: Predicts potential delays in sample production.
- **Plant Selection**: Recommends the optimal manufacturing plant based on quality, capacity, and historical performance.
- **Delay Assessment**: Provides probability scores for meeting delivery deadlines.

### 2. Bulk Order Planning & Capacity Allocation (`/api/component2`)
- **Capacity Forecasting**: Optimizes production lines for large-scale orders.
- **Resource Balancing**: Ensures efficient distribution of workloads across available resources.

### 3. Emergency Situation Detection (`/api/component3`)
- **Bottleneck Identification**: Real-time detection of production stalls.
- **Risk Mitigation**: Proactive alerts for potential supply chain or production failures.
- **Recovery Planning**: Calculates deadline-aware overtime, worker, machine,
  backup-line, and escalation options. See
  [`COMPONENT3_RECOVERY_ENGINE.md`](COMPONENT3_RECOVERY_ENGINE.md).
- **Recovery Tracking**: Stores approval, execution, actual output,
  effectiveness and the incident audit timeline. See
  [`COMPONENT3_TRACKING_API.md`](COMPONENT3_TRACKING_API.md).
- **Historical Validation**: Replays recovery plans against the next recorded
  production day and reports calibration evidence without assuming an action
  was applied. See
  [`COMPONENT3_HISTORICAL_VALIDATION.md`](COMPONENT3_HISTORICAL_VALIDATION.md).
- **Early-Warning Readiness**: Builds leakage-safe future labels from currently
  stable production days and checks whether grouped model training is valid.
  See [`COMPONENT3_EARLY_WARNING_STEP5A.md`](COMPONENT3_EARLY_WARNING_STEP5A.md).
- **Daily Monitoring Collection**: Stores daily detections, captures
  supervisor-verified actual outcomes with an audit history, derives exact
  three-day future labels, and reports live training readiness. See
  [`COMPONENT3_DAILY_MONITORING.md`](COMPONENT3_DAILY_MONITORING.md).

### 4. Production Analysis & Resource Optimization (`/api/component4`)
- **Efficiency Analytics**: Detailed insights into production performance.
- **Optimization Suggestions**: AI-driven recommendations to improve throughput and reduce waste.

## 🛠️ Prerequisites

- **Python**: 3.10 or 3.12 (Recommended)
- **Environment**: Windows/Linux/macOS

## 📦 Setup & Installation

1. **Create a Virtual Environment**:
   ```powershell
   python -m venv .venv
   
   
   py -3.11 -m venv .venv --clear    -> if you have multiple vertions use this
   ```

2. **Activate the Virtual Environment**:
   - **Windows (PowerShell)**:
     ```powershell
     .\.venv\Scripts\Activate.ps1
     ```
   *Note: If you get a "Script execution is disabled" error, run `Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope Process` in your terminal first.*

3. **Install Dependencies**:
   ```bash
   .venv\Scripts\python.exe -m pip install -r requirements.txt
   ```

## 🏃 Running the Application

Start the Flask server:
```bash
python app.py
```

- **Server URL**: `http://localhost:5000`
- **Health Check**: `GET http://localhost:5000/health`

## 🔌 API Usage Example

### Sample Planning Prediction
**Endpoint**: `POST /api/component1/predict`

**Request Body**:
```json
{
    "buyer_name": "Tesco",
    "style_id": "KM123456",
    "sample_qty": 3,
    "buffer_days": 5,
    "process_type": "Embroidery",
    "priority_level": "High",
    "cap_util_pct": 75.0,
    "daily_cap_styles": 9,
    "quality_rating": 4.8
}
```

**Response**:
```json
{
    "status": "success",
    "model1_overrun": {
        "predicted_overrun_days": 0.45,
        "interpretation": "On time"
    },
    "model2_plant_selection": {
        "recommended_plant": "Dinusha Embroidery"
    }
}
```

## 📂 Project Structure

- `app.py`: Main entry point and blueprint registration.
- `blueprints/`: Route definitions for the 4 core components.
- `models/`: Trained `.pkl` machine learning models and encoders.
- `data/`: Supplementary data files and datasets.
- `requirements.txt`: Project dependencies.

## ⚠️ Important Notes

- **Model Files**: Ensure all `.pkl` files are present in the `models/` directory before running predictions.
- **Data Validation**: The API enforces strict validation on input fields (e.g., `sample_qty` must be between 1 and 10 for Component 1).

