from dash import html, dcc
import dash_cytoscape as cyto

# ── Colour system ──────────────────────────────────────────────
STATUS_CLR = {
    "Closed":                   "#16a34a",
    "QA Testing":               "#2563eb",
    "Ready For QA Testing":     "#3b82f6",
    "Code Review":              "#6366f1",
    "Development In Progress":  "#f59e0b",
    "Fixing in Progress":       "#ef4444",
    "Groomed":                  "#64748b",
    "To Do":                    "#94a3b8",
    "Rejected":                 "#dc2626",
    "Integration Testing":      "#8b5cf6",
}
TYPE_CLR  = {"Task":"#3b82f6","Story":"#8b5cf6","Bug":"#ef4444","Sub-task":"#f59e0b","Epic":"#10b981"}
PRIO_CLR  = {"Highest":"#dc2626","High":"#f97316","Medium":"#eab308","Low":"#22c55e"}
DEFAULT   = "#94a3b8"

def sc(s): return STATUS_CLR.get(s, DEFAULT)
def tc(t): return TYPE_CLR.get(t,  DEFAULT)
def pc(p): return PRIO_CLR.get(p,  DEFAULT)

# ── KPI card ──────────────────────────────────────────────────
def kpi(label, value, color="#1e40af", sub=None):
    return html.Div([
        html.Div(str(value), style={"fontSize":"2.2rem","fontWeight":"700","color":color,"lineHeight":"1"}),
        html.Div(label, style={"fontSize":"0.7rem","color":"#94a3b8","marginTop":"4px","letterSpacing":"0.08em","textTransform":"uppercase"}),
        html.Div(sub, style={"fontSize":"0.68rem","color":color,"marginTop":"2px"}) if sub else None,
    ], style={
        "background":"#111827","border":f"1px solid {color}22",
        "borderRadius":"8px","padding":"16px 20px","minWidth":"120px",
        "borderTop":f"3px solid {color}",
    })

# ── Section header ─────────────────────────────────────────────
def section(title):
    return html.Div(title, style={
        "fontSize":"0.65rem","fontWeight":"700","letterSpacing":"0.12em",
        "textTransform":"uppercase","color":"#475569","marginBottom":"12px","marginTop":"24px",
    })

# ── Filter bar ─────────────────────────────────────────────────
def filter_bar(labels, assignees):
    dd = lambda i,p,opts: dcc.Dropdown(
        id=i, placeholder=p, multi=True, clearable=True,
        options=[{"label":o,"value":o} for o in opts],
        style={"minWidth":"180px","fontSize":"0.8rem"},
        className="dash-dropdown-dark"
    )
    return html.Div([
        dd("f-label",    "Label",         labels),
        dd("f-assignee", "Assignee",      assignees),
        dd("f-type",     "Issue Type",    ["Task","Story","Bug","Sub-task","Epic"]),
        dd("f-status",   "Status",        list(STATUS_CLR.keys())),
        dd("f-priority", "Priority",      ["Highest","High","Medium","Low"]),
        html.Button("Refresh", id="btn-refresh", n_clicks=0, style={
            "background":"#1e40af","color":"#fff","border":"none",
            "borderRadius":"6px","padding":"8px 16px","cursor":"pointer","fontSize":"0.8rem",
        }),
        html.Div(id="sync-time", style={"color":"#475569","fontSize":"0.72rem","alignSelf":"center"}),
    ], style={"display":"flex","gap":"10px","flexWrap":"wrap","alignItems":"center","padding":"12px 0"})

# ── Cytoscape stylesheet ────────────────────────────────────────
CYTO_STYLE = [
    {"selector":"node","style":{
        "label":"data(label)","font-size":"9px","color":"#e2e8f0",
        "background-color":"data(color)","border-color":"data(color)",
        "border-width":"2px","width":"data(size)","height":"data(size)",
        "text-valign":"bottom","text-halign":"center","text-margin-y":"4px",
    }},
    {"selector":"edge","style":{
        "line-color":"#334155","target-arrow-color":"#334155",
        "target-arrow-shape":"triangle","curve-style":"bezier",
        "label":"data(label)","font-size":"8px","color":"#64748b","width":"1.5",
    }},
    {"selector":":selected","style":{"border-width":"3px","border-color":"#f8fafc"}},
]

# ── Build cytoscape elements from issues ───────────────────────
def cyto_elements(issues):
    nodes, edges, seen = [], [], set()
    key_map = {i["key"]: i for i in issues}
    for i in issues:
        sz = 28 + len(i["links"]) * 4
        nodes.append({"data":{
            "id":i["key"],"label":i["key"],
            "color":sc(i["status"]),"size":min(sz,60),
            "type":i["type"],"status":i["status"],
            "assignee":i["assignee"],"summary":i["summary"][:60],
        }})
        for lnk in i["links"]:
            eid = f"{i['key']}-{lnk['key']}-{lnk['type']}"
            rev = f"{lnk['key']}-{i['key']}-{lnk['type']}"
            if eid not in seen and rev not in seen and lnk["key"] in key_map:
                edges.append({"data":{
                    "source":i["key"] if lnk["direction"]=="outward" else lnk["key"],
                    "target":lnk["key"] if lnk["direction"]=="outward" else i["key"],
                    "label":lnk["type"],
                }})
                seen.add(eid)
    return nodes + edges

# ── Issue detail drawer ────────────────────────────────────────
def issue_drawer(issue):
    if not issue: return html.Div()
    rows = [
        ("Issue Type",  issue["type"]),
        ("Status",      issue["status"]),
        ("Assignee",    issue["assignee"]),
        ("Reporter",    issue["reporter"]),
        ("Priority",    issue["priority"]),
        ("Label",       issue["label_display"]),
        ("Created",     issue["created"]),
        ("Updated",     issue["updated"]),
        ("Due Date",    issue["due"] or "—"),
        ("Due Flag",    issue["due_flag"]),
        ("Days Stale",  issue["days_stale"]),
        ("Comments",    issue["comments_count"]),
        ("Sprint",      issue["sprint"] or "—"),
        ("Fix Version", issue["fix_version"] or "—"),
        ("Parent",      issue["parent"] or "—"),
    ]
    return html.Div([
        html.A(issue["key"], href=issue["url"], target="_blank", style={
            "fontSize":"1rem","fontWeight":"700","color":"#60a5fa","textDecoration":"none",
        }),
        html.Div(issue["summary"], style={"color":"#e2e8f0","fontSize":"0.82rem","margin":"8px 0 16px","lineHeight":"1.4"}),
        *[html.Div([
            html.Span(k, style={"color":"#64748b","fontSize":"0.7rem","width":"100px","display":"inline-block"}),
            html.Span(str(v), style={"color":"#e2e8f0","fontSize":"0.78rem"}),
        ], style={"marginBottom":"6px"}) for k,v in rows],
        html.Div("Latest Comment", style={"color":"#64748b","fontSize":"0.7rem","marginTop":"16px","marginBottom":"4px"}),
        html.Div(issue["latest_comment"] or "—", style={"color":"#94a3b8","fontSize":"0.75rem","lineHeight":"1.5"}),
    ], style={"padding":"20px"})
