"""Persistent standup log store using JSON file on Render disk."""
import json, os, time, uuid
from datetime import datetime

STORE_PATH = os.getenv("STORE_PATH", "/tmp/standup_log.json")

def _load():
    try:
        with open(STORE_PATH) as f: return json.load(f)
    except: return []

def _save(data):
    with open(STORE_PATH, "w") as f: json.dump(data, f, indent=2)

def add_log(issue_key, assignee, update_text, eta, logged_by="PM"):
    data = _load()
    entry = {
        "id": str(uuid.uuid4())[:8],
        "issue_key": issue_key,
        "assignee": assignee,
        "update": update_text,
        "eta": eta,                    # YYYY-MM-DD or ""
        "logged_by": logged_by,
        "logged_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "date": datetime.now().strftime("%Y-%m-%d"),
        "status": "open",              # open | resolved | broken
    }
    data.append(entry)
    _save(data)
    return entry

def get_logs(issue_key=None, assignee=None, days=30):
    from datetime import date, timedelta
    cutoff = (date.today() - timedelta(days=days)).isoformat()
    data = _load()
    result = [e for e in data if e.get("date","") >= cutoff]
    if issue_key: result = [e for e in result if e["issue_key"] == issue_key]
    if assignee:  result = [e for e in result if e["assignee"] == assignee]
    return sorted(result, key=lambda x: x["logged_at"], reverse=True)

def mark_resolved(log_id):
    data = _load()
    for e in data:
        if e["id"] == log_id: e["status"] = "resolved"
    _save(data)

def get_promise_broken(issues):
    """Returns logs where ETA passed but issue still open."""
    from datetime import date
    today = date.today().isoformat()
    logs = _load()
    key_map = {i["key"]: i for i in issues}
    broken = []
    for e in logs:
        if e["status"] == "resolved": continue
        if not e.get("eta"): continue
        if e["eta"] < today:
            issue = key_map.get(e["issue_key"])
            if issue and issue["status"] not in ("Closed","Rejected"):
                days_over = (date.today() - date.fromisoformat(e["eta"])).days
                broken.append({**e, "days_over": days_over, "issue": issue})
    return sorted(broken, key=lambda x: -x["days_over"])
