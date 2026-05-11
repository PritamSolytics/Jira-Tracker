"""
store.py — Persistent delivery log store using MongoDB.
Falls back to local JSON if MONGODB_URI not set (dev mode).
"""
import json, os, time, uuid
from datetime import datetime, date, timedelta

MONGODB_URI  = os.getenv("MONGODB_URI", "")
DB_NAME      = os.getenv("MONGODB_DB", "jira_dashboard")
COLLECTION   = "delivery_logs"
STORE_PATH   = os.getenv("STORE_PATH", os.path.join(os.getenv("DATA_DIR","data"), "delivery_log.json"))

# ── MongoDB client (lazy init) ────────────────────────────────────────────────
_mongo_client = None
_mongo_col    = None

def _get_col():
    global _mongo_client, _mongo_col
    if _mongo_col is not None:
        return _mongo_col
    if not MONGODB_URI:
        return None
    try:
        from pymongo import MongoClient
        _mongo_client = MongoClient(MONGODB_URI, serverSelectionTimeoutMS=3000)
        _mongo_col    = _mongo_client[DB_NAME][COLLECTION]
        _mongo_col.create_index("date")
        _mongo_col.create_index("issue_key")
        return _mongo_col
    except Exception as e:
        print(f"MongoDB unavailable: {e} — falling back to local JSON")
        return None

# ── Local JSON fallback ───────────────────────────────────────────────────────
def _load():
    try:
        os.makedirs(os.path.dirname(STORE_PATH), exist_ok=True)
        with open(STORE_PATH) as f: return json.load(f)
    except: return []

def _save(data):
    os.makedirs(os.path.dirname(STORE_PATH), exist_ok=True)
    with open(STORE_PATH, "w") as f: json.dump(data, f, indent=2)

# ── Public API ────────────────────────────────────────────────────────────────
def add_log(issue_key, assignee, update_text, eta, logged_by="PM"):
    entry = {
        "id":         str(uuid.uuid4())[:8],
        "issue_key":  issue_key,
        "assignee":   assignee,
        "update":     update_text,
        "eta":        eta,
        "logged_by":  logged_by,
        "logged_at":  datetime.now().strftime("%Y-%m-%d %H:%M"),
        "date":       datetime.now().strftime("%Y-%m-%d"),
        "status":     "active",
    }
    col = _get_col()
    if col is not None:
        col.insert_one({**entry, "_id": entry["id"]})
    else:
        data = _load(); data.append(entry); _save(data)
    return entry

def get_logs(issue_key=None, assignee=None, days=30):
    cutoff = (date.today() - timedelta(days=days)).isoformat()
    col = _get_col()
    if col is not None:
        query = {"date": {"$gte": cutoff}}
        if issue_key: query["issue_key"] = issue_key
        if assignee:  query["assignee"]  = assignee
        return sorted(list(col.find(query, {"_id":0})), key=lambda x: x["logged_at"], reverse=True)
    data = _load()
    result = [e for e in data if e.get("date","") >= cutoff]
    if issue_key: result = [e for e in result if e["issue_key"] == issue_key]
    if assignee:  result = [e for e in result if e["assignee"] == assignee]
    return sorted(result, key=lambda x: x["logged_at"], reverse=True)

def mark_resolved(log_id):
    col = _get_col()
    if col is not None:
        col.update_one({"id": log_id}, {"$set": {"status": "resolved"}})
    else:
        data = _load()
        for e in data:
            if e["id"] == log_id: e["status"] = "resolved"
        _save(data)

def get_forecast_event_delayed(issues):
    today = date.today().isoformat()
    logs  = get_logs(days=365)
    key_map = {i["key"]: i for i in issues}
    delayed = []
    for e in logs:
        if e["status"] == "resolved": continue
        if not e.get("eta"):          continue
        if e["eta"] < today:
            issue = key_map.get(e["issue_key"])
            if issue and issue["status"] not in ("Closed","Rejected"):
                days_over = (date.today() - date.fromisoformat(e["eta"])).days
                delayed.append({**e, "days_over": days_over, "issue": issue})
    return sorted(delayed, key=lambda x: -x["days_over"])
