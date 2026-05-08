# Delivery Intelligence Platform

A production-grade operational intelligence system for Jira-based delivery workflows. Built on real project data, it combines workflow analytics, predictive modelling, graph intelligence, and Monte Carlo simulation to reduce delivery uncertainty and support data-driven planning decisions.

**Live:** [jira-tracker-bpi2.onrender.com](https://jira-tracker-bpi2.onrender.com)

---

## Capabilities

### Executive Intelligence Briefing
- Composite delivery confidence score (0–100)
- Monte Carlo sprint completion simulation with configurable parameters
- At-risk deliverables register with rule-based risk scoring
- Ranked recommended actions in plain language

### Sprint Intelligence
- AI-assisted sprint structure generation (Epic → Story → Task/Bug hierarchy)
- Effort estimation from historical cycle time distributions
- Delivery probability simulation with adjustable uncertainty multiplier, bug buffer rate, and simulation count
- One-click Jira ticket creation via REST API
- Delivery Confidence Analyzer with velocity adjustment and capacity rebalancing recommendations

### Operational Intelligence
- Delivery Variance Signal — ETA adherence tracking per workstream
- Delivery Concentration Risk — composite risk scoring across workstreams and initiatives
- Dependency Propagation Analysis — BFS traversal of issue graph to quantify cascade delay impact
- Executive alert strip with ranked plain-language risk statements

### Predictive Analytics
- Deadline slip predictor (Random Forest / Gradient Boosting / Logistic Regression — selectable)
- Customizable training parameters: estimators, max depth, test split, contamination rate
- K-Means risk clustering of open issues (Critical / Elevated / Standard)
- Isolation Forest outlier pattern detection
- Feature importance visualisation with 10 engineered features including graph centrality

### Advanced Analytics
- Velocity forecasting: SARIMA/ARIMA with 80% confidence intervals
- Statistical tests: ADF stationarity, Shapiro-Wilk normality, Mann-Whitney U, Kruskal-Wallis
- Survival curve (issue age vs % still open)
- Weekly throughput, WIP by stage, bug injection rate, cycle time percentiles (P10–P95)
- Assignee performance radar across 5 operational dimensions

### Data Laboratory
- Full dataset inspection with descriptive statistics and correlation matrix
- Cycle time distribution by issue type, priority, and assignee
- Configurable train/test split with stratification options
- Download: raw issues CSV, full feature-engineered dataset, training set only

### Task Linkage Analysis
- Classifies all issues as Story-linked vs floating (unlinked)
- Separate filterable tables for each class
- Coverage donut, type/assignee breakdown, issues-per-story chart

### Core Pages
- **Command Centre** — KPI strip, health scores per initiative, at-risk issues, blockers, due-this-week
- **Capacity & Workstream Overview** — per-assignee load cards, bubble chart (load vs staleness), heatmap
- **Initiative Health** — scored health per label with breakdown
- **Dependency Graph** — Cytoscape network with node shapes by type, edge colors by link type, click-to-inspect drawer
- **Workflow Analysis** — stage gate analysis, velocity trends, funnel chart
- **Delivery Coordination** — ETA logging, planning variance tracking, Jira comment auto-post
- **Alerts** — beyond-target-date, no-progress, unowned, high-priority bugs

---

## Technology Stack

| Layer | Technology |
|---|---|
| Framework | Dash 2.17, Plotly 5.22 |
| Graph intelligence | NetworkX 3.x |
| Machine learning | scikit-learn 1.4+ |
| Forecasting | statsmodels (SARIMA/ARIMA) |
| Statistical tests | scipy |
| Graph visualisation | Dash Cytoscape |
| Data source | Jira Cloud REST API v3 |
| Deployment | Render (gunicorn) |
| Sprint planning AI | Anthropic Claude API |

---

## Setup

### Environment Variables

```
JIRA_EMAIL=your@email.com
JIRA_API_TOKEN=your_jira_token
JIRA_BASE_URL=https://yourorg.atlassian.net
JIRA_PROJECT=PROJECT_KEY
DAYS_BACK=365
MAX_ISSUES=2000
DATA_DIR=data
DATASET_PATH=data/jira_dataset.csv
MODEL_DIR=data/models
STORE_PATH=data/delivery_log.json
```

### Local

```bash
pip install -r requirements.txt
python app.py
```

Open `http://localhost:8050`

### Render Deployment

```yaml
startCommand: gunicorn app:server -b 0.0.0.0:$PORT --workers 1 --timeout 180
```

---

## Model Training

Navigate to **Predictive Analytics** → configure parameters → click **Train Model**.

Training uses all closed issues with due dates as labeled examples. Models persist to `MODEL_DIR`. Retrain anytime from the dashboard as new data accumulates.

**Default configuration:**
- Algorithm: Random Forest (class-balanced)
- Estimators: 200
- Test split: 20% stratified
- Clusters: 3 (K-Means)
- Outlier contamination: 10%

---

## Project Structure

```
app.py                      — Main Dash application, routing, layout
data.py                     — Jira API client, caching, parsing
components.py               — Shared UI primitives and colour system
charts.py                   — Reusable Plotly chart functions
ml_engine.py                — Feature engineering, model training, inference, forecasting
store.py                    — Delivery coordination log persistence

executive_briefing_page.py  — Executive Intelligence Briefing
sprint_page.py              — Sprint Intelligence (planner + analyzer)
intelligence_page.py        — Operational Intelligence
analytics_page.py           — Advanced Analytics
ml_page.py                  — Predictive Analytics
data_lab_page.py            — Data Laboratory
task_linkage_page.py        — Task Linkage Analysis
standup_page.py             — Delivery Coordination Log
```

---

## Architecture

```
Jira Cloud API
      │
   data.py ──── threading.Lock() cache (TTL 600s)
      │
   app.py ──── Dash routing + filter layer
      │
  ┌───┴────────────────────────────────────┐
  │              Page Layer                 │
  │  executive_briefing  sprint  analytics  │
  │  intelligence  ml_page  data_lab  ...   │
  └───┬────────────────────────────────────┘
      │
 ml_engine.py
  ├── Feature engineering (10 features + graph centrality)
  ├── RandomForest / GBM / Logistic slip predictor
  ├── K-Means risk clustering
  ├── Isolation Forest outlier detection
  ├── SARIMA/ARIMA velocity forecasting
  └── Statistical tests (ADF, Shapiro-Wilk, Mann-Whitney, Kruskal-Wallis)
```

---

## Data & Privacy

All data is sourced exclusively from your organisation's Jira instance. No data is transmitted to third parties. The platform is read-only except for the Delivery Coordination Log (which posts comments to Jira) and Sprint Intelligence (which creates tickets on explicit user action).

Analytical outputs are framed at the workstream and initiative level. The system is designed to surface systemic delivery patterns, not to evaluate individuals.
