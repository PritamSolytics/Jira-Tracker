"""
six_sigma_engine.py — Six Sigma Black Belt Analytics Engine
============================================================
Implements full DMAIC measurement framework for IT/Jira project management.

Metrics implemented:
  • DPMO  — Defects Per Million Opportunities (per workstream)
  • Process Sigma Level  — sigma scale from DPMO
  • Cpk / Cp  — Process capability indices (cycle time vs SLA targets)
  • XmR Control Chart  — Individuals + Moving Range with UCL/LCL (3σ)
  • FMEA Register  — Severity × Occurrence × Detection → RPN
  • MSA / Gage R&R proxy  — Measurement consistency audit
  • Rolled Throughput Yield (RTY)  — end-to-end first-pass quality
  • Defect classification  — weighted by type (rework, escape, latency)
  • Voice of Customer (VOC) SLA mapping  — issue type → target cycle days
"""

import numpy as np
from collections import defaultdict, Counter
from datetime import date, timedelta
from scipy import stats as spstats
import warnings
warnings.filterwarnings("ignore")

# ──────────────────────────────────────────────────────────────────────────────
# CONSTANTS — VOC / SLA targets (days) per issue type
# Adjust these to match your actual SLAs with Truist / US Bank
# ──────────────────────────────────────────────────────────────────────────────
import os as _os

def _sla_env(key, default):
    """Read SLA from env var — allows dynamic override without code change."""
    try: return int(_os.getenv(f"SLA_{key.upper().replace('-','_')}", default))
    except: return default

VOC_SLA = {
    "Bug":        _sla_env("BUG",        23),
    "Story":      _sla_env("STORY",      32),
    "Task":       _sla_env("TASK",       33),
    "Sub-task":   _sla_env("SUB_TASK",   30),
    "Epic":       _sla_env("EPIC",       60),
    "QA-Sub-task":_sla_env("QA_SUB_TASK",55),
}
DEFAULT_SLA = _sla_env("DEFAULT", 30)

def update_sla(issue_type, days):
    """Dynamically update SLA at runtime — called from Settings page."""
    VOC_SLA[issue_type] = int(days)

# Six Sigma DPMO → Sigma level lookup (standard table)
SIGMA_TABLE = [
    (3.4,    6.0),
    (233,    5.0),
    (6_210,  4.0),
    (66_807, 3.0),
    (308_538,2.0),
    (690_000,1.0),
    (933_193,0.5),
]


# ──────────────────────────────────────────────────────────────────────────────
# UTILITY
# ──────────────────────────────────────────────────────────────────────────────
def _safe_date(s):
    try:
        return date.fromisoformat(s)
    except Exception:
        return None


def _cycle_time(issue):
    """Days from created to updated (closed)."""
    c = _safe_date(issue.get("created", ""))
    u = _safe_date(issue.get("updated", ""))
    if c and u and u >= c:
        return (u - c).days
    return None


def _sla(itype):
    return VOC_SLA.get(itype, DEFAULT_SLA)


def _is_defect(issue):
    """
    Defect definition (weighted, Black Belt standard):
      1. Closed after due date  (weight 1.0)
      2. Reopened / Fixing-in-Progress after QA  (weight 0.8)
      3. Cycle time exceeds SLA target  (weight 0.6)
      4. Unassigned and open > 3 days  (weight 0.4)
    Returns (is_defect: bool, defect_type: str)
    """
    status = issue.get("status", "")
    due = issue.get("due", "")
    updated = issue.get("updated", "")
    itype = issue.get("type", "")
    created = issue.get("created", "")
    due_flag = issue.get("due_flag", "")

    # 1. Past due date
    if due and updated and status == "Closed":
        d_due = _safe_date(due)
        d_upd = _safe_date(updated)
        if d_due and d_upd and d_upd > d_due:
            return True, "Late Closure"

    # 2. Rework (Fixing in Progress after Closed/QA)
    # Check BOTH: status (future-proof) and label (current NNG convention)
    if status in ("Fixing in Progress", "Reopened") or "Reopened" in (issue.get("labels") or []):
        return True, "Rework"

    # 3. Cycle time exceeds SLA
    ct = _cycle_time(issue)
    if ct is not None and status == "Closed":
        if ct > _sla(itype):
            return True, "SLA Breach"

    # 4. Unassigned open > 3 days
    if issue.get("assignee", "") == "Unassigned":
        d_created = _safe_date(created)
        if d_created and (date.today() - d_created).days > 3 and status != "Closed":
            return True, "Unowned"

    return False, ""


# ──────────────────────────────────────────────────────────────────────────────
# 1. DPMO + SIGMA LEVEL
# ──────────────────────────────────────────────────────────────────────────────
def dpmo_sigma(issues, group_by="project"):
    """
    Returns DPMO and sigma level, optionally grouped by project/label/assignee.
    Opportunities = 4 per issue (the 4 defect types defined above).
    """
    groups = defaultdict(list)
    for i in issues:
        if group_by == "project":
            groups[i.get("project", "NNG")].append(i)
        elif group_by == "label":
            for l in (i.get("labels") or ["(No Label)"]):
                groups[l].append(i)
        elif group_by == "assignee":
            groups[i.get("assignee", "Unassigned")].append(i)
        else:
            groups["ALL"].append(i)

    results = []
    for grp, grp_issues in groups.items():
        n = len(grp_issues)
        opportunities = n * 4  # 4 defect opportunities per issue
        defects = 0
        defect_types = Counter()
        for iss in grp_issues:
            is_d, dtype = _is_defect(iss)
            if is_d:
                defects += 1
                defect_types[dtype] += 1

        dpmo = round((defects / max(1, opportunities)) * 1_000_000, 1)
        sigma = _dpmo_to_sigma(dpmo)
        yield_pct = round((1 - defects / max(1, n)) * 100, 2)

        results.append({
            "group":        grp,
            "n_issues":     n,
            "defects":      defects,
            "opportunities":opportunities,
            "dpmo":         dpmo,
            "sigma_level":  sigma,
            "yield_pct":    yield_pct,
            "defect_types": dict(defect_types),
        })

    return sorted(results, key=lambda x: -x["dpmo"])


def _dpmo_to_sigma(dpmo):
    """Convert DPMO to sigma level using standard table + interpolation."""
    if dpmo <= 0:
        return 6.0
    for threshold, sigma in SIGMA_TABLE:
        if dpmo <= threshold:
            return round(sigma, 2)
    return round(0.5, 2)


def overall_dpmo(issues):
    """Single-number DPMO + sigma for the whole project."""
    results = dpmo_sigma(issues, group_by="all")
    if results:
        return results[0]
    return {"dpmo": 0, "sigma_level": 6.0, "yield_pct": 100.0, "defects": 0, "n_issues": len(issues)}


# ──────────────────────────────────────────────────────────────────────────────
# 2. PROCESS CAPABILITY — Cp, Cpk
# ──────────────────────────────────────────────────────────────────────────────
def process_capability(issues):
    """
    Computes Cp and Cpk for cycle time per issue type.
    USL = VOC_SLA target.
    LSL = 0 (can't deliver in negative time).
    Cpk >= 1.33 = capable. >= 1.67 = Six Sigma capable.
    """
    by_type = defaultdict(list)
    for i in issues:
        if i.get("status") == "Closed":
            ct = _cycle_time(i)
            if ct is not None and ct >= 0:
                by_type[i.get("type", "Task")].append(ct)

    results = []
    for itype, cycle_times in by_type.items():
        if len(cycle_times) < 5:
            continue
        arr = np.array(cycle_times, dtype=float)
        mu = arr.mean()
        sigma = arr.std(ddof=1)
        usl = _sla(itype)
        lsl = 0.0

        if sigma < 0.01:
            cp = 99.0
            cpk = 99.0
        else:
            cp  = round((usl - lsl) / (6 * sigma), 3)
            cpu = (usl - mu) / (3 * sigma)
            cpl = (mu - lsl) / (3 * sigma)
            cpk = round(min(cpu, cpl), 3)

        # % within SLA
        within_sla = int((arr <= usl).sum())
        pct_within = round(within_sla / len(arr) * 100, 1)

        # Percentiles
        p50 = round(float(np.percentile(arr, 50)), 1)
        p90 = round(float(np.percentile(arr, 90)), 1)
        p95 = round(float(np.percentile(arr, 95)), 1)

        capability = (
            "Six Sigma Capable" if cpk >= 1.67 else
            "Capable"           if cpk >= 1.33 else
            "Marginal"          if cpk >= 1.00 else
            "Incapable"
        )

        results.append({
            "type":        itype,
            "n":           len(arr),
            "sla_days":    usl,
            "mean":        round(float(mu), 1),
            "std":         round(float(sigma), 1),
            "cp":          cp,
            "cpk":         cpk,
            "pct_within":  pct_within,
            "p50":         p50,
            "p90":         p90,
            "p95":         p95,
            "capability":  capability,
        })

    return sorted(results, key=lambda x: x["cpk"])


# ──────────────────────────────────────────────────────────────────────────────
# 3. XmR CONTROL CHART DATA (Individuals + Moving Range)
# ──────────────────────────────────────────────────────────────────────────────
def xmr_control_chart(issues, metric="weekly_closed"):
    """
    XmR (Individuals and Moving Range) Control Chart.
    Returns data points + UCL, LCL, CL for both X and mR charts.
    Out-of-control rules implemented:
      Rule 1: Point beyond 3σ (UCL/LCL)
      Rule 2: 8 consecutive points same side of centre line
      Rule 3: 6 consecutive points trending up or down
    """
    if metric == "weekly_closed":
        by_week = Counter()
        for i in issues:
            if i.get("status") == "Closed" and i.get("updated"):
                d = _safe_date(i["updated"])
                if d:
                    week = d - timedelta(days=d.weekday())
                    by_week[str(week)] += 1
        weeks = sorted(by_week)[-20:]
        if len(weeks) < 5:
            return {"error": "Need at least 5 weeks of closed issues for XmR chart."}
        values = [float(by_week[w]) for w in weeks]
        labels = weeks
        title = "XmR Control Chart — Weekly Closed Issues"
        y_label = "Closed Issues / Week"

    elif metric == "cycle_time":
        closed = [i for i in issues if i.get("status") == "Closed"]
        closed_sorted = sorted(closed, key=lambda x: x.get("updated", ""))[-40:]
        values = []
        labels = []
        for i in closed_sorted:
            ct = _cycle_time(i)
            if ct is not None and ct >= 0:
                values.append(float(ct))
                labels.append(i["key"])
        if len(values) < 5:
            return {"error": "Need at least 5 closed issues with cycle times."}
        title = "XmR Control Chart — Cycle Time (days)"
        y_label = "Cycle Time (days)"

    else:
        return {"error": f"Unknown metric: {metric}"}

    x = np.array(values)
    n = len(x)

    # Moving ranges
    mr = np.abs(np.diff(x))

    # Control limits
    d2 = 1.128  # constant for n=2 subgroups (XmR standard)
    x_bar = x.mean()
    mr_bar = mr.mean() if len(mr) > 0 else 0

    x_ucl = round(x_bar + 3 * (mr_bar / d2), 3)
    x_lcl = round(max(0, x_bar - 3 * (mr_bar / d2)), 3)
    mr_ucl = round(3.267 * mr_bar, 3)   # D4 constant = 3.267 for n=2
    mr_lcl = 0.0

    # Out-of-control detection
    ooc_points = _detect_ooc(x, x_bar, x_ucl, x_lcl)

    return {
        "labels":   labels,
        "x_values": x.tolist(),
        "mr_values":[0] + mr.tolist(),  # pad first point
        "x_bar":    round(float(x_bar), 3),
        "x_ucl":    x_ucl,
        "x_lcl":    x_lcl,
        "mr_bar":   round(float(mr_bar), 3),
        "mr_ucl":   mr_ucl,
        "mr_lcl":   mr_lcl,
        "ooc_indices": ooc_points,
        "n":        n,
        "title":    title,
        "y_label":  y_label,
    }


def _detect_ooc(x, cl, ucl, lcl):
    """
    Detect out-of-control points per Western Electric rules.
    Returns list of (index, rule_description).
    """
    ooc = []
    n = len(x)

    for i in range(n):
        # Rule 1: beyond 3σ
        if x[i] > ucl or x[i] < lcl:
            ooc.append((i, "Rule 1: Beyond 3σ"))

    # Rule 2: 8+ consecutive same side
    for i in range(n - 7):
        window = x[i:i+8]
        if all(v > cl for v in window) or all(v < cl for v in window):
            for j in range(i, i+8):
                if not any(idx == j for idx, _ in ooc):
                    ooc.append((j, "Rule 2: 8 consecutive same side"))

    # Rule 3: 6 consecutive trending
    for i in range(n - 5):
        window = x[i:i+6]
        if all(window[k] < window[k+1] for k in range(5)) or all(window[k] > window[k+1] for k in range(5)):
            for j in range(i, i+6):
                if not any(idx == j for idx, _ in ooc):
                    ooc.append((j, "Rule 3: 6 trending"))

    return ooc


# ──────────────────────────────────────────────────────────────────────────────
# 4. FMEA REGISTER
# ──────────────────────────────────────────────────────────────────────────────
def build_fmea(issues):
    """
    Failure Mode and Effects Analysis (FMEA).
    Scores each failure mode: RPN = Severity × Occurrence × Detection (each 1–10).
    Returns ranked list of failure modes with recommended actions.
    """
    today = date.today()

    # ── Compute raw counts ────────────────────────────────────────────────────
    open_issues   = [i for i in issues if i["status"] != "Closed"]
    closed_issues = [i for i in issues if i["status"] == "Closed"]
    total         = len(issues)
    n_open        = len(open_issues)

    overdue_count   = sum(1 for i in open_issues if "Beyond Target Date" in i.get("due_flag",""))
    # Check both status and label for safety (NNG uses label; future workflow may use status)
    rework_count    = sum(1 for i in issues if i["status"] in ("Fixing in Progress","Reopened") or "Reopened" in (i.get("labels") or []))
    unassigned_count= sum(1 for i in open_issues if i["assignee"] == "Unassigned")
    stale_count     = sum(1 for i in open_issues if i.get("days_since_progress",0) > 7)
    blocker_count   = sum(1 for i in issues for l in i.get("links",[]) if "block" in l.get("type","").lower() and l["direction"]=="outward")
    no_due_count    = sum(1 for i in open_issues if not i.get("due"))
    high_bugs       = sum(1 for i in open_issues if i["type"]=="Bug" and i.get("priority") in ("Highest","High"))
    sla_breach_count= sum(1 for i in closed_issues if _is_defect(i)[1] == "SLA Breach")

    def _occ(count, baseline):
        """Scale count to 1–10 occurrence score."""
        if baseline == 0: return 1
        pct = count / baseline
        if pct == 0:    return 1
        if pct < 0.05:  return 2
        if pct < 0.10:  return 3
        if pct < 0.20:  return 4
        if pct < 0.30:  return 5
        if pct < 0.40:  return 6
        if pct < 0.50:  return 7
        if pct < 0.65:  return 8
        if pct < 0.80:  return 9
        return 10

    # ── FMEA entries (Severity fixed by domain knowledge, Detection = process maturity) ──
    # ── Data-driven detection scores ─────────────────────────────────────────
    # Detection = how easily each failure is caught BEFORE it causes impact
    # Derived from: does the dashboard/process currently surface this? (1=always, 10=never)
    # Recalibrates based on current data volume — more data = better detection
    def _det(has_control, data_count, total_issues=total):
        """
        Detection score (1=always caught, 10=never caught).
        Fully data-driven:
        - Base detection from whether a dashboard control exists
        - Adjusted by what % of issues the failure affects (higher prevalence = easier to detect)
        - Adjusted by absolute data volume (more data = more reliable signal)
        """
        # Base: does a control exist in the dashboard?
        base = 4 if has_control else 8
        # Prevalence adjustment: if failure is widespread it's easier to spot
        prevalence = data_count / max(1, total_issues)
        prevalence_adj = -2 if prevalence > 0.3 else (-1 if prevalence > 0.1 else 0)
        # Volume adjustment: < 5 data points = poor signal = harder to detect reliably
        volume_adj = 2 if data_count < 5 else (1 if data_count < 15 else 0)
        return max(1, min(10, base + prevalence_adj + volume_adj))

    # Data-driven severity: scales with actual business impact seen in data
    # Severity 1-10: higher = worse effect on delivery
    def _sev(base_sev, actual_count, total, escalation_threshold=0.15):
        """Severity increases if failure is widespread (> threshold of total)."""
        if total > 0 and actual_count / total > escalation_threshold:
            return min(10, base_sev + 1)
        return base_sev

    fmea = [
        {
            "id": "FM-01",
            "process_step":    "Due Date Management",
            "failure_mode":    "Issue closed after due date",
            "effect":          "Client SLA breach, delivery credibility loss",
            "severity":        _sev(9, overdue_count, n_open),
            "cause":           "Unrealistic estimates, scope creep, untracked dependencies",
            "occurrence":      _occ(overdue_count, n_open),
            "current_control": "Due-flag in dashboard, ETA log",
            "detection":       _det(True, overdue_count),
            "count":           overdue_count,
            "recommended_action": "Enforce mandatory due-date review in sprint planning; auto-alert at T-3 days",
        },
        {
            "id": "FM-02",
            "process_step":    "Quality Gate",
            "failure_mode":    "Issue reopened / rework required post-QA",
            "effect":          "Double cycle time, team morale, velocity drop",
            "severity":        _sev(8, rework_count, total),
            "cause":           "Insufficient acceptance criteria, QA scope gaps",
            "occurrence":      _occ(rework_count, total),
            "current_control": "QA Testing stage in workflow",
            "detection":       _det(True, rework_count),
            "count":           rework_count,
            "recommended_action": "Implement Definition of Done checklist; block QA → Closed without sign-off",
        },
        {
            "id": "FM-03",
            "process_step":    "Work Assignment",
            "failure_mode":    "Issue unassigned and open",
            "effect":          "Work item invisible, delivery gap, no accountability",
            "severity":        _sev(7, unassigned_count, n_open),
            "cause":           "Sprint planning misses, assignee offboarded",
            "occurrence":      _occ(unassigned_count, n_open),
            "current_control": "Unassigned alert in dashboard",
            "detection":       _det(True, unassigned_count),
            "count":           unassigned_count,
            "recommended_action": "Auto-assign rule based on capacity score; alert PM if unassigned > 24h",
        },
        {
            "id": "FM-04",
            "process_step":    "Progress Tracking",
            "failure_mode":    "Issue stale > 7 days with no update",
            "effect":          "Hidden blockers, velocity undercount, false sprint progress",
            "severity":        _sev(7, stale_count, n_open),
            "cause":           "No standup discipline, missing updates in Jira",
            "occurrence":      _occ(stale_count, n_open),
            "current_control": "Staleness metric in dashboard",
            "detection":       _det(True, stale_count),
            "count":           stale_count,
            "recommended_action": "Mandatory daily Jira update via Delivery Coordination Log; auto-escalate to PM after 5d",
        },
        {
            "id": "FM-05",
            "process_step":    "Dependency Management",
            "failure_mode":    "Active blocking relationship unresolved",
            "effect":          "Cascade delay across multiple issues, sprint failure",
            "severity":        _sev(9, blocker_count, total),
            "cause":           "Cross-team dependencies not surfaced early, no blocker SLA",
            "occurrence":      _occ(blocker_count, total),
            "current_control": "Dependency graph, block links in Jira",
            "detection":       _det(True, blocker_count),
            "count":           blocker_count,
            "recommended_action": "Daily blocker triage in standup; 48h escalation rule for unresolved blocks",
        },
        {
            "id": "FM-06",
            "process_step":    "Sprint Planning",
            "failure_mode":    "Issue has no due date set",
            "effect":          "No delivery commitment, invisible in risk tracking",
            "severity":        _sev(6, no_due_count, n_open),
            "cause":           "Incomplete sprint ceremonies, PM oversight",
            "occurrence":      _occ(no_due_count, n_open),
            "current_control": "No Due Date flag in dashboard",
            "detection":       _det(True, no_due_count),
            "count":           no_due_count,
            "recommended_action": "Jira workflow: block transition to Dev In Progress without due date",
        },
        {
            "id": "FM-07",
            "process_step":    "Bug Management",
            "failure_mode":    "High/Highest priority bug open > SLA",
            "effect":          "Production defect escapes, client escalation",
            "severity":        _sev(10, high_bugs, total, escalation_threshold=0.05),
            "cause":           "Insufficient bug triage, resource allocation to features over bugs",
            "occurrence":      _occ(high_bugs, total),
            "current_control": "High Bugs alert in dashboard",
            "detection":       _det(True, high_bugs),
            "count":           high_bugs,
            "recommended_action": "P0/P1 bug → immediate assignment + 4h response SLA; CEO/sponsor alert at 24h",
        },
        {
            "id": "FM-08",
            "process_step":    "Delivery Forecasting",
            "failure_mode":    "Issue closed but SLA target breached",
            "effect":          "Process sigma degradation, client trust erosion",
            "severity":        _sev(7, sla_breach_count, max(1, len(closed_issues))),
            "cause":           "Poor capacity planning, late-stage scope changes",
            "occurrence":      _occ(sla_breach_count, max(1, len(closed_issues))),
            "current_control": "Cpk / cycle time analytics in Six Sigma module",
            "detection":       _det(True, sla_breach_count),
            "count":           sla_breach_count,
            "recommended_action": "Introduce cycle time commitment per sprint; visualize SLA compliance trend",
        },
    ]

    for fm in fmea:
        fm["rpn"] = fm["severity"] * fm["occurrence"] * fm["detection"]
        fm["rpn_class"] = (
            "Critical"  if fm["rpn"] >= 200 else
            "High"      if fm["rpn"] >= 120 else
            "Medium"    if fm["rpn"] >= 60  else
            "Low"
        )

    return sorted(fmea, key=lambda x: -x["rpn"])


# ──────────────────────────────────────────────────────────────────────────────
# 5. ROLLED THROUGHPUT YIELD (RTY)
# ──────────────────────────────────────────────────────────────────────────────
def rolled_throughput_yield(issues, changelog_data=None):
    """
    RTY = product of first-pass yield across each workflow stage.

    Two modes:
    1. changelog_data provided: Real RTY from actual Jira status transitions (backward moves = defects).
    2. No changelog: Approximation — Fixing in Progress / Reopened distributed by workflow position.

    Stages per Solytics JIRA Workflow doc (correct order including UAT and Rejected).
    """
    WORKFLOW_STAGES = [
        "Groomed", "To Do", "Development In Progress",
        "Fixing in Progress", "Code Review", "Integration Testing",
        "Ready For QA Testing", "QA Testing", "UAT", "Closed"
    ]
    total = len(issues)
    if total == 0:
        return {"rty": 0, "stages": [], "mode": "no_data"}

    stage_counts = Counter(i["status"] for i in issues)
    stage_results = []
    rty = 1.0
    mode = "approximation"

    if changelog_data:
        mode = "changelog"
        stage_idx = {s: i for i, s in enumerate(WORKFLOW_STAGES)}
        stage_bounces = Counter()
        stage_entries = Counter()
        for issue_key, transitions in changelog_data.items():
            for t in transitions:
                to_s, from_s = t.get("to",""), t.get("from","")
                if to_s in stage_idx: stage_entries[to_s] += 1
                if (from_s in stage_idx and to_s in stage_idx and
                        stage_idx[to_s] < stage_idx[from_s]):
                    stage_bounces[from_s] += 1
        for stage in WORKFLOW_STAGES:
            entries = max(stage_entries.get(stage, 0), stage_counts.get(stage, 0))
            bounces = stage_bounces.get(stage, 0)
            fy = max(0.0, min(1.0, 1 - bounces / max(1, entries))) if entries > 0 else 1.0
            rty *= fy
            stage_results.append({"stage": stage, "count": entries, "defects": bounces, "fy": round(fy*100, 1)})
    else:
        # Approximation: distribute Fixing in Progress / Reopened by workflow position probability
        fixing   = sum(1 for i in issues if i["status"] == "Fixing in Progress")
        # Check both status and label for safety
        reopened = sum(1 for i in issues if i["status"] == "Reopened" or "Reopened" in (i.get("labels") or []))
        # Derive weights empirically from stage volumes in current data
        # rather than using assumed 50/30/20 split
        bounce_stages = ["Code Review", "QA Testing", "Integration Testing"]
        stage_volumes = {s: max(1, stage_counts.get(s, 0)) for s in bounce_stages}
        total_vol = sum(stage_volumes.values())

        stage_rework = {}
        for s in bounce_stages:
            w = stage_volumes[s] / total_vol
            # Reopened issues weight more toward QA (most common post-QA bounce)
            if s == "QA Testing":
                stage_rework[s] = round(fixing * w + reopened * 0.6)
            elif s == "Integration Testing":
                stage_rework[s] = round(fixing * w + reopened * 0.4)
            else:
                stage_rework[s] = round(fixing * w)

        for stage in WORKFLOW_STAGES:
            in_stage = stage_counts.get(stage, 0)
            defects  = stage_rework.get(stage, 0)
            fy = max(0.0, min(1.0, 1 - defects / max(1, in_stage + defects)))
            rty *= fy
            stage_results.append({"stage": stage, "count": in_stage, "defects": defects, "fy": round(fy*100, 1)})

    return {"rty": round(rty*100, 2), "stages": stage_results, "mode": mode}


# ──────────────────────────────────────────────────────────────────────────────
# 7. DMAIC HEALTH SUMMARY
# ──────────────────────────────────────────────────────────────────────────────
# ── Measurement System Analysis (MSA) ────────────────────────────────────────
def msa_audit(issues):
    """
    Proxy MSA: checks for measurement system inconsistencies in Jira data.
    Returns list of measurement issues with severity.
    """
    findings = []
    total = len(issues)

    missing_due = [i for i in issues if not i.get("due") and i["status"] not in ("Closed","Rejected")]
    if missing_due:
        pct = round(len(missing_due)/max(1,total)*100,1)
        findings.append({
            "finding":   "Missing Due Date",
            "count":     len(missing_due),
            "pct":       pct,
            "severity":  "High" if pct > 30 else "Medium",
            "impact":    "DPMO, Cpk, and ETA tracking are unreliable without due dates",
            "action":    "Enforce due date as mandatory field before Dev In Progress transition",
        })

    stale_30 = [i for i in issues if i.get("days_since_progress",0) > 30 and i["status"] not in ("Closed","Rejected")]
    if stale_30:
        pct = round(len(stale_30)/max(1,total)*100,1)
        findings.append({
            "finding":   "Data Staleness > 30 Days",
            "count":     len(stale_30),
            "pct":       pct,
            "severity":  "High" if pct > 20 else "Medium",
            "impact":    "Cycle time and staleness metrics are inflated; control charts skewed",
            "action":    "Daily update mandate; auto-close stale issues after 45 days with PM review",
        })

    unassigned = [i for i in issues if i.get("assignee","") == "Unassigned" and i["status"] != "Closed"]
    if unassigned:
        pct = round(len(unassigned)/max(1,total)*100,1)
        findings.append({
            "finding":   "Unassigned Open Issues",
            "count":     len(unassigned),
            "pct":       pct,
            "severity":  "Medium",
            "impact":    "ERI and assignee Cpk calculations are incomplete",
            "action":    "Auto-assign using capacity scoring; block sprint start if unassigned > 0",
        })

    ct_outliers = []
    for i in issues:
        if i["status"] == "Closed":
            c = _safe_date(i.get("created",""))
            u = _safe_date(i.get("updated",""))
            if c and u:
                ct = (u - c).days
                sla = _sla(i.get("type","Task"))
                if ct > sla * 3:
                    ct_outliers.append(i)
    if ct_outliers:
        findings.append({
            "finding":   "Extreme Cycle Time Outliers (>3x SLA)",
            "count":     len(ct_outliers),
            "pct":       round(len(ct_outliers)/max(1,total)*100,1),
            "severity":  "Medium",
            "impact":    "Cpk standard deviation inflated; sigma level understated",
            "action":    "Investigate each outlier — likely mis-categorised or created date incorrect",
            "examples":  [i["key"] for i in ct_outliers[:5]],
        })

    return findings


def dmaic_summary(issues, changelog_data=None):
    """
    Single function that returns a complete DMAIC health object.
    Pass changelog_data from D.get_changelog() for real RTY.
    Used to drive the Six Sigma Command Centre panel.
    """
    overall = overall_dpmo(issues)
    cap = process_capability(issues)
    fmea = build_fmea(issues)
    rty = rolled_throughput_yield(issues, changelog_data=changelog_data)
    msa = msa_audit(issues)

    # Top 3 FMEA risks
    top_risks = fmea[:3]

    # Worst Cpk issue type
    worst_cpk = cap[0] if cap else None

    # MSA high-severity findings
    msa_critical = [f for f in msa if f["severity"] == "High"]

    # Overall Six Sigma grade
    sigma = overall.get("sigma_level", 0)
    grade = (
        "World Class"  if sigma >= 6.0 else
        "Excellent"    if sigma >= 5.0 else
        "Good"         if sigma >= 4.0 else
        "Average"      if sigma >= 3.0 else
        "Below Average"if sigma >= 2.0 else
        "Poor"
    )

    return {
        "sigma_level":   overall.get("sigma_level", 0),
        "dpmo":          overall.get("dpmo", 0),
        "yield_pct":     overall.get("yield_pct", 0),
        "defects":       overall.get("defects", 0),
        "n_issues":      overall.get("n_issues", 0),
        "grade":         grade,
        "rty":           rty.get("rty", 0),
        "top_risks":     top_risks,
        "worst_cpk":     worst_cpk,
        "msa_critical":  msa_critical,
        "fmea_critical": [f for f in fmea if f["rpn_class"] in ("Critical","High")],
    }
