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
           "created","updated","duedate","comment","issuelinks","parent","fixVersions",
           "story_points","customfield_10016","customfield_10020",  # story points, sprint
           "customfield_10050",  # QA Tester
           "timespent","timeoriginalestimate","aggregatetimespent"]
URL     = f"https://api.atlassian.com/ex/jira/{CLOUD_ID}/rest/api/3/search/jql"

_cache = {"data": [], "ts": 0}
TTL    = 600

# ── Changelog cache (RTY) — 24h TTL, fetched in background ───────────────────
_changelog_cache = {"data": {}, "ts": 0}
TTL_CHANGELOG    = 86_400  # 24 hours

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


# Sprint field IDs vary per Jira instance — try all known ones
# Confirmed from live NNG Jira: sprint is customfield_10020, returns list of dicts with "name"
_SPRINT_FIELDS = ["customfield_10020", "customfield_10021", "customfield_10014", "sprint"]

def _extract_sprint(f):
    """
    Extract sprint name from Jira sprint custom field.
    Tries multiple known field IDs — correct one auto-detected at runtime.
    """
    import re
    for field_id in _SPRINT_FIELDS:
        sprints = f.get(field_id)
        if not sprints:
            continue
        if isinstance(sprints, list) and sprints:
            s = sprints[-1]
            if isinstance(s, dict): return s.get("name", "")
            if isinstance(s, str):
                m = re.search(r"name=([^,\]]+)", s)
                return m.group(1).strip() if m else s[:40]
        if isinstance(sprints, str):
            return sprints[:40]
    return ""

def _workflow_type(issue_type):
    """Map issue type to workflow type per Solytics JIRA Workflow doc."""
    return {
        "Story":       "story_task",
        "Task":        "story_task",
        "Bug":         "bug",
        "Sub-task":    "subtask",
        "QA-Sub-task": "qa_subtask",
        "Epic":        "epic",
    }.get(issue_type, "story_task")

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
        elif dd < today:           due_flag = f"Beyond Target Date ({(today-dd).days}d)"
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
        "days_since_progress": days_stale,
        "comments_count": len(comments),
        "latest_comment": latest_comment,
        "links":          links,
        "fix_version":    ", ".join(v.get("name","") for v in (f.get("fixVersions") or [])),
        "parent":         (f.get("parent") or {}).get("key", ""),
        "url":            f"{BASE_URL}/browse/{raw['key']}",
        # ── Workflow-specific fields (per Solytics JIRA Workflow doc) ──────────
        "story_points":    (f.get("customfield_10016") or f.get("story_points")),
        "sprint":          _extract_sprint(f),
        "qa_tester":       (f.get("customfield_10050") or {}).get("displayName", ""),
        "time_spent_sec":  f.get("timespent") or 0,
        "time_est_sec":    f.get("timeoriginalestimate") or 0,
        "time_logged":     bool(f.get("timespent")),   # True if any time has been logged
        "has_story_points":bool(f.get("customfield_10016") not in (None, 0) or f.get("story_points") not in (None, 0)),
        "rca":             "",   # populated from comments if RCA keyword found
        "workflow_type":   _workflow_type(f.get("issuetype",{}).get("name","")),
        "transition_valid":True,  # placeholder — enforced at Jira level
    }

def get_issues(force=False):
    now = time.time()
    if force or now - _cache["ts"] > TTL or not _cache["data"]:
        try:
            import gc
            raw = _fetch_all()
            _cache["data"] = [_parse(i) for i in raw]
            del raw; gc.collect()
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

def get_changelog(force=False):
    """
    Fetch Jira status transition history for all open issues.
    Used for real RTY calculation in six_sigma_engine.
    Cached for 24 hours — heavy call (1 request per issue).
    Returns: {issue_key: [{"from": str, "to": str, "date": str}]}
    """
    now = time.time()
    if not force and now - _changelog_cache["ts"] < TTL_CHANGELOG and _changelog_cache["data"]:
        log.info("Changelog: serving from cache")
        return _changelog_cache["data"]

    issues = get_issues()
    if not issues:
        return {}

    # Only fetch open issues — closed issues don't add new bounces
    MAX_CHANGELOG = int(os.getenv("MAX_CHANGELOG", "30"))
    targets = [i for i in issues if i["status"] not in ("Closed", "Rejected")][:MAX_CHANGELOG]
    log.info(f"Fetching changelog for {len(targets)} open issues...")

    changelog_data = {}
    api_base = f"https://api.atlassian.com/ex/jira/{CLOUD_ID}/rest/api/3"

    for issue in targets:
        try:
            r = requests.get(
                f"{api_base}/issue/{issue['key']}",
                params={"expand": "changelog", "fields": "status"},
                headers=HEADERS,
                timeout=10,
            )
            if r.status_code != 200:
                continue
            transitions = []
            for hist in r.json().get("changelog", {}).get("histories", []):
                for item in hist.get("items", []):
                    if item.get("field") == "status":
                        transitions.append({
                            "from": item.get("fromString", ""),
                            "to":   item.get("toString",   ""),
                            "date": hist.get("created",    "")[:10],
                        })
            if transitions:
                changelog_data[issue["key"]] = transitions
        except Exception as e:
            log.warning(f"Changelog fetch failed for {issue['key']}: {e}")
            continue

    _changelog_cache["data"] = changelog_data
    _changelog_cache["ts"]   = now
    log.info(f"Changelog cached: {len(changelog_data)} issues with transitions")
    return changelog_data


def get_changelog_last_sync():
    if _changelog_cache["ts"]:
        return datetime.fromtimestamp(_changelog_cache["ts"], tz=IST).strftime("%d %b %Y %H:%M IST")
    return "Never"


def post_jira_comment(issue_key, text):
    """Post a structured standup comment to Jira."""
    import base64, requests as req
    basic = base64.b64encode(f"{EMAIL}:{TOKEN}".encode()).decode()
    headers = {"Authorization": f"Basic {basic}", "Accept":"application/json","Content-Type":"application/json"}
    body = {"body":{"type":"doc","version":1,"content":[{"type":"paragraph","content":[{"type":"text","text":text}]}]}}
    r = req.post(f"{BASE_URL}/rest/api/3/issue/{issue_key}/comment", headers=headers, json=body, timeout=15)
    return r.status_code == 201
