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





