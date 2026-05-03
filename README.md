# Jira Operations Dashboard

Live Dash app pulling directly from Jira REST API. Zero manual exports.

## Deploy to Render (5 minutes)

1. Push this folder to a GitHub repo
2. Go to render.com → New Web Service → connect repo
3. Set environment variables in Render dashboard:
   - `JIRA_EMAIL` — your Atlassian email
   - `JIRA_API_TOKEN` — generate at https://id.atlassian.com/manage-api-tokens
   - `JIRA_BASE_URL` — https://solytics.atlassian.net
   - `JIRA_PROJECT` — NNG (or comma-separated: NNG,ABC)
4. Deploy. Done.

## Run Locally

```bash
cp .env.example .env   # fill in your credentials
pip install -r requirements.txt
python app.py
# open http://localhost:8050
```

## Pages

| Page | URL |
|---|---|
| Overview | / |
| Work Items | /items |
| By Label | /labels |
| By Assignee | /assignee |
| Dependencies | /dependencies |
| Timeline | /timeline |
| Alerts | /alerts |
| Settings | /settings |

## Adding a new project/label

No code change needed. The app auto-discovers all labels and projects on every refresh.
To track a new Jira project, add it to the `JIRA_PROJECT` env var (comma-separated).

## Files

```
app.py          Main Dash app — layout, routing, all callbacks
data.py         Jira API fetcher with 10-min cache
components.py   KPI cards, drawer, Cytoscape builder, colour system
charts.py       All Plotly chart functions
render.yaml     One-click Render deployment
requirements.txt
.env.example
```
