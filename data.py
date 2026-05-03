import os, requests, time, logging, base64
from datetime import date, datetime
from dotenv import load_dotenv

load_dotenv()
logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)

CLOUD_ID = os.getenv("JIRA_CLOUD_ID", "5fb74332-b7cc-4502-8a2b-37aaa9228d95")
BASE_URL  = os.getenv("JIRA_BASE_URL", "https://solytics.atlassian.net")
EMAIL     = os.getenv("JIRA_EMAIL", "")
TOKEN     = os.getenv("JIRA_API_TOKEN", "")
PROJECTS  = [p.strip() for p in os.getenv("JIRA_PROJECT", "NNG").split(",")]
FIELDS    = ["summary","issuetype","status","assignee","reporter","priority","labels",
             "created","updated","duedate","comment","issuelinks","parent",
             "customfield_10015","customfield_10016","fixVersions","sprint"]

# Try both auth methods
BASIC_TOKEN = base64.b64encode(f"{EMAIL}:{TOKEN}".encode()).decode()

_cache = {"data": [], "ts": 0}
TTL = 600

ENDPOINTS = [
    # (url_template, headers, use_post)
    (f"{BASE_URL}/rest/api/3/search/jql",                               {"Authorization": f"Basic {BASIC_TOKEN}", "Accept": "application/json", "Content-Type": "application/json"}, True),
    (f"https://api.atlassian.com/ex/jira/{CLOUD_ID}/rest/api/3/search/jql", {"Authorization": f"Basic {BASIC_TOKEN}", "Accept": "application/json", "Content-Type": "application/json"}, True),
    (f"https://api.atlassian.com/ex/jira/{CLOUD_ID}/rest/api/3/search/jql", {"Authorization": f"Bearer {TOKEN}",        "Accept": "application/json", "Content-Type": "application/json"}, True),
]

def _search(jql, start=0):
    payload = {"jql": jql, "fields": FIELDS, "maxResults": 100, "startAt": start}
    last_err = None
    for url, headers, use_post in ENDPOINTS:
        try:
            if use_post:
                r = requests.post(url, headers=headers, json=payload, timeout=30)
            else:
                r = requests.get(url, headers=headers, params={"jql":jql,"fields":",".join(FIELDS),"maxResults":100,"startAt":start}, timeout=30)
            log.info(f"Tried {url[:60]} → {r.status_code}")
            if r.status_code == 200:
                return r.json()
            last_err = f"{r.status_code}: {r.text[:200]}"
        except Exception as e:
            last_err = str(e)
    raise Exception(f"All endpoints failed. Last error: {last_err}")

def _fetch_all():
    projects_jql = ",".join(PROJECTS)
    jql = f"project in ({projects_jql}) AND updated >= -90d ORDER BY updated DESC"
    log.info(f"Fetching: {jql}")
    issues, start = [], 0
    while True:
        res = _search(jql, start)
        issues += res["issues"]
        start += 100
        log.info(f"Fetched {len(issues)}/{res['total']}")
        if start >= res["total"]: break
    return issues

def _parse(raw):
    f = raw["fields"]
    assignee  = (f.get("assignee") or {}).get("displayName", "Unassigned")
    reporter  = (f.get("reporter") or {}).get("displayName", "")
    due       = f.get("duedate") or ""
    updated   = (f.get("updated") or "")[:10]
    created   = (f.get("created") or "")[:10]
    today     = date.today()

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
        latest_comment = latest_comment[:300].replace("\n", " ")

    links = []
    for lnk in f.get("issuelinks", []):
        lt = lnk.get("type", {}).get("name", "")
        if "inwardIssue"  in lnk: links.append({"type": lt, "direction": "inward",  "key": lnk["inwardIssue"]["key"]})
        if "outwardIssue" in lnk: links.append({"type": lt, "direction": "outward", "key": lnk["outwardIssue"]["key"]})

    labels     = f.get("labels", []) or []
    sprint_raw = f.get("sprint") or {}
    sprint     = sprint_raw.get("name", "") if isinstance(sprint_raw, dict) else ""

    return {
        "key":            raw["key"],
        "project":        raw["key"].split("-")[0],
        "summary":        f.get("summary", ""),
        "type":           f.get("issuetype", {}).get("name", ""),
        "status":         f.get("status", {}).get("name", ""),
        "assignee":       assignee,
        "reporter":       reporter,
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
        "sprint":         sprint,
        "fix_version":    ", ".join(v.get("name","") for v in (f.get("fixVersions") or [])),
        "parent":         (f.get("parent") or {}).get("key", ""),
        "url":            f"{BASE_URL}/browse/{raw['key']}",
        "story_points":   f.get("customfield_10016") or f.get("customfield_10015") or None,
    }

def get_issues(force=False):
    now = time.time()
    if force or now - _cache["ts"] > TTL or not _cache["data"]:
        try:
            _cache["data"] = [_parse(i) for i in _fetch_all()]
            _cache["ts"] = now
            log.info(f"Cache updated: {len(_cache['data'])} issues")
        except Exception as e:
            log.error(f"Failed to fetch: {e}")
    return _cache["data"]

def get_labels(issues):
    s = set()
    for i in issues:
        for l in i["labels"]: s.add(l)
    return sorted(s)

def get_assignees(issues): return sorted(set(i["assignee"] for i in issues))
def get_projects(issues):  return sorted(set(i["project"]  for i in issues))

def last_sync():
    if _cache["ts"]: return datetime.fromtimestamp(_cache["ts"]).strftime("%d %b %Y %H:%M")
    return "Never"
