import os, requests, time, logging, base64
from datetime import date, datetime
from zoneinfo import ZoneInfo
IST = ZoneInfo("Asia/Kolkata")
from dotenv import load_dotenv

load_dotenv()
logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)

CLOUD_ID   = os.getenv("JIRA_CLOUD_ID", "5fb74332-b7cc-4502-8a2b-37aaa9228d95")
BASE_URL   = os.getenv("JIRA_BASE_URL", "https://solytics.atlassian.net")
EMAIL      = os.getenv("JIRA_EMAIL", "")
TOKEN      = os.getenv("JIRA_API_TOKEN", "")
PROJECTS   = [p.strip() for p in os.getenv("JIRA_PROJECT", "NNG").split(",")]
MAX_ISSUES = int(os.getenv("MAX_ISSUES", "500"))
DAYS_BACK  = int(os.getenv("DAYS_BACK", "60"))

BASIC   = base64.b64encode(f"{EMAIL}:{TOKEN}".encode()).decode()
HEADERS = {"Authorization": f"Basic {BASIC}", "Accept": "application/json", "Content-Type": "application/json"}
FIELDS  = ["summary","issuetype","status","assignee","priority","labels",
           "created","updated","duedate","comment","issuelinks","parent","fixVersions"]
URL     = f"https://api.atlassian.com/ex/jira/{CLOUD_ID}/rest/api/3/search/jql"

_cache = {"data": [], "ts": 0}
TTL    = 600

def _fetch_all():
    projects_jql = ",".join(PROJECTS)
    jql = f"project in ({projects_jql}) AND updated >= -{DAYS_BACK}d ORDER BY updated DESC"
    log.info(f"Fetching: {jql} (max {MAX_ISSUES})")
    issues, next_token = [], None
    while len(issues) < MAX_ISSUES:
        body = {"jql": jql, "fields": FIELDS, "maxResults": 50}
        if next_token:
            body["nextPageToken"] = next_token
        r = requests.post(URL, headers=HEADERS, json=body, timeout=60)
        if r.status_code != 200:
            log.error(f"Error {r.status_code}: {r.text[:200]}")
            r.raise_for_status()
        res = r.json()
        batch = res.get("issues", [])
        issues += batch
        next_token = res.get("nextPageToken")
        log.info(f"Fetched {len(issues)}, isLast={res.get('isLast')}")
        if res.get("isLast", True) or not batch: break
    return issues[:MAX_ISSUES]

def _parse(raw):
    f = raw["fields"]
    assignee = (f.get("assignee") or {}).get("displayName", "Unassigned")
    due      = f.get("duedate") or ""
    updated  = (f.get("updated") or "")[:10]
    created  = (f.get("created") or "")[:10]
    today    = datetime.now(tz=IST).date()
    try: days_stale = (today - date.fromisoformat(updated)).days
    except: days_stale = 0
    if due:
        dd = date.fromisoformat(due)
        st = f.get("status", {}).get("name", "")
        if st == "Closed":         due_flag = "Closed"
        elif dd < today:           due_flag = f"Past Due Date ({(today-dd).days}d)"
        elif (dd-today).days <= 7: due_flag = "Due This Week"
        else:                      due_flag = "On Track"
    else:
        due_flag = "No Due Date"
    comments = f.get("comment", {}).get("comments", [])
    latest_comment = ""
    if comments:
        body = comments[-1].get("body", {})
        if isinstance(body, dict):
            for block in body.get("content", []):
                for inline in block.get("content", []):
                    if inline.get("type") == "text":
                        latest_comment += inline.get("text", "")
        elif isinstance(body, str):
            latest_comment = body
        latest_comment = latest_comment[:200].replace("\n", " ")
    links = []
    for lnk in f.get("issuelinks", []):
        lt = lnk.get("type", {}).get("name", "")
        if "inwardIssue"  in lnk: links.append({"type": lt, "direction": "inward",  "key": lnk["inwardIssue"]["key"]})
        if "outwardIssue" in lnk: links.append({"type": lt, "direction": "outward", "key": lnk["outwardIssue"]["key"]})
    labels = f.get("labels", []) or []
    return {
        "key":            raw["key"],
        "project":        raw["key"].split("-")[0],
        "summary":        f.get("summary", ""),
        "type":           f.get("issuetype", {}).get("name", ""),
        "status":         f.get("status", {}).get("name", ""),
        "assignee":       assignee,
        "reporter":       "",
        "priority":       (f.get("priority") or {}).get("name", ""),
        "labels":         labels,
        "label_display":  ", ".join(labels) if labels else "(No Label)",
        "created":        created,
        "updated":        updated,
        "due":            due,
        "due_flag":       due_flag,
        "days_stale":     days_stale,
        "comments_count": len(comments),
        "latest_comment": latest_comment,
        "links":          links,
        "sprint":         "",
        "fix_version":    ", ".join(v.get("name","") for v in (f.get("fixVersions") or [])),
        "parent":         (f.get("parent") or {}).get("key", ""),
        "url":            f"{BASE_URL}/browse/{raw['key']}",
        "story_points":   None,
    }

def get_issues(force=False):
    now = time.time()
    if force or now - _cache["ts"] > TTL or not _cache["data"]:
        try:
            _cache["data"] = [_parse(i) for i in _fetch_all()]
            _cache["ts"] = now
            log.info(f"Cache updated: {len(_cache['data'])} issues")
        except Exception as e:
            log.error(f"Failed: {e}")
    return _cache["data"]

def get_labels(issues):
    s = set()
    for i in issues:
        for l in i["labels"]: s.add(l)
    return sorted(s)

def get_assignees(issues): return sorted(set(i["assignee"] for i in issues))
def get_projects(issues):  return sorted(set(i["project"]  for i in issues))
def last_sync():
    if _cache["ts"]: return datetime.fromtimestamp(_cache["ts"], tz=IST).strftime("%d %b %Y %H:%M IST")
    return "Never"

def post_jira_comment(issue_key, text):
    """Post a structured standup comment to Jira."""
    import base64, requests as req
    basic = base64.b64encode(f"{EMAIL}:{TOKEN}".encode()).decode()
    headers = {"Authorization": f"Basic {basic}", "Accept":"application/json","Content-Type":"application/json"}
    body = {"body":{"type":"doc","version":1,"content":[{"type":"paragraph","content":[{"type":"text","text":text}]}]}}
    r = req.post(f"{API_BASE}/rest/api/3/issue/{issue_key}/comment", headers=headers, json=body, timeout=15)
    return r.status_code == 201
