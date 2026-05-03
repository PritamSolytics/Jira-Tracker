import dash
from dash import dcc, html, Input, Output, State, callback_context, dash_table
import dash_cytoscape as cyto
import plotly.graph_objects as go
from collections import Counter, defaultdict

import data as D
import components as C
import charts as CH

cyto.load_extra_layouts()

app = dash.Dash(__name__, suppress_callback_exceptions=True,
                meta_tags=[{"name":"viewport","content":"width=device-width,initial-scale=1"}])
app.title = "Jira Dashboard"
server = app.server

# ── Shared style tokens ────────────────────────────────────────
BG, SURFACE, BORDER = "#0f172a", "#111827", "#1e293b"
TEXT, MUTED = "#e2e8f0", "#64748b"
FONT = "IBM Plex Mono, monospace"

SIDEBAR = html.Nav([
    html.Div("JIRA OPERATIONS", style={
        "color":MUTED,"fontSize":"0.6rem","letterSpacing":"0.15em",
        "padding":"24px 20px 12px","borderBottom":f"1px solid {BORDER}",
    }),
    *[dcc.Link(label, href=href, style={
        "display":"block","padding":"11px 20px","color":TEXT,
        "textDecoration":"none","fontSize":"0.78rem","letterSpacing":"0.04em",
        "borderLeft":"3px solid transparent",
    }) for label, href in [
        ("Overview",           "/"),
        ("Work Items",         "/items"),
        ("By Label",           "/labels"),
        ("By Assignee",        "/assignee"),
        ("Dependencies",       "/dependencies"),
        ("Timeline",           "/timeline"),
        ("Alerts",             "/alerts"),
        ("Settings",           "/settings"),
    ]],
], style={
    "width":"200px","minHeight":"100vh","background":SURFACE,
    "borderRight":f"1px solid {BORDER}","flexShrink":"0","position":"sticky","top":"0",
})

TOPBAR = html.Div([
    html.Div(id="page-title", style={"fontWeight":"700","fontSize":"0.95rem","color":TEXT}),
    html.Div([
        dcc.Dropdown(id="g-project",  placeholder="Project",   multi=True, clearable=True, style={"minWidth":"120px","fontSize":"0.78rem"}),
        dcc.Dropdown(id="g-label",    placeholder="Label",     multi=True, clearable=True, style={"minWidth":"150px","fontSize":"0.78rem"}),
        dcc.Dropdown(id="g-assignee", placeholder="Assignee",  multi=True, clearable=True, style={"minWidth":"150px","fontSize":"0.78rem"}),
        dcc.Dropdown(id="g-type",     placeholder="Issue Type", multi=True, clearable=True,
                     options=[{"label":t,"value":t} for t in ["Task","Story","Bug","Sub-task","Epic"]],
                     style={"minWidth":"140px","fontSize":"0.78rem"}),
        dcc.Dropdown(id="g-status",   placeholder="Status",    multi=True, clearable=True,
                     options=[{"label":s,"value":s} for s in C.STATUS_CLR],
                     style={"minWidth":"150px","fontSize":"0.78rem"}),
        html.Button("↻ Refresh", id="btn-refresh", n_clicks=0, style={
            "background":"#1e40af","color":"#fff","border":"none",
            "borderRadius":"5px","padding":"6px 14px","cursor":"pointer","fontSize":"0.75rem",
        }),
        html.Div(id="sync-ts", style={"color":MUTED,"fontSize":"0.7rem","alignSelf":"center","whiteSpace":"nowrap"}),
    ], style={"display":"flex","gap":"8px","flexWrap":"wrap","alignItems":"center"}),
], style={
    "display":"flex","justifyContent":"space-between","alignItems":"center","flexWrap":"wrap",
    "gap":"12px","padding":"14px 24px","borderBottom":f"1px solid {BORDER}",
    "background":SURFACE,"position":"sticky","top":"0","zIndex":"100",
})

DRAWER = html.Div([
    html.Button("✕", id="drawer-close", style={
        "position":"absolute","top":"12px","right":"12px","background":"none",
        "border":"none","color":MUTED,"fontSize":"1rem","cursor":"pointer",
    }),
    html.Div(id="drawer-content"),
], id="drawer", style={
    "position":"fixed","right":"0","top":"0","height":"100vh","width":"360px",
    "background":SURFACE,"borderLeft":f"1px solid {BORDER}","zIndex":"200",
    "overflowY":"auto","display":"none","boxShadow":"-8px 0 32px rgba(0,0,0,0.4)",
})

app.layout = html.Div([
    dcc.Location(id="url"),
    dcc.Store(id="store-issues"),
    dcc.Store(id="store-selected-issue"),
    dcc.Interval(id="auto-refresh", interval=600_000, n_intervals=0),
    html.Div([SIDEBAR, html.Div([TOPBAR, html.Div(id="page-content", style={"padding":"20px 24px","flex":"1"})],
             style={"flex":"1","display":"flex","flexDirection":"column","overflow":"hidden"})],
             style={"display":"flex","fontFamily":FONT,"background":BG,"color":TEXT,"minHeight":"100vh"}),
    DRAWER,
], style={"fontFamily":FONT})


# ── Data load ──────────────────────────────────────────────────
@app.callback(
    Output("store-issues","data"), Output("sync-ts","children"),
    Output("g-label","options"),  Output("g-assignee","options"), Output("g-project","options"),
    Input("btn-refresh","n_clicks"), Input("auto-refresh","n_intervals"),
    prevent_initial_call=False,
)
def load_data(n, _):
    force = callback_context.triggered_id == "btn-refresh"
    issues = D.get_issues(force=force)
    labels    = [{"label":l,"value":l} for l in D.get_labels(issues)]
    assignees = [{"label":a,"value":a} for a in D.get_assignees(issues)]
    projects  = [{"label":p,"value":p} for p in D.get_projects(issues)]
    return issues, f"Last sync: {D.last_sync()}", labels, assignees, projects


def filter_issues(issues, labels, assignees, types, statuses, projects=None):
    r = issues
    if projects:  r = [i for i in r if i["project"] in projects]
    if labels:    r = [i for i in r if any(l in i["labels"] for l in labels)]
    if assignees: r = [i for i in r if i["assignee"] in assignees]
    if types:     r = [i for i in r if i["type"] in types]
    if statuses:  r = [i for i in r if i["status"] in statuses]
    return r


# ── Router ─────────────────────────────────────────────────────
@app.callback(
    Output("page-content","children"), Output("page-title","children"),
    Input("url","pathname"),
    Input("store-issues","data"),
    Input("g-label","value"), Input("g-assignee","value"),
    Input("g-type","value"),  Input("g-status","value"), Input("g-project","value"),
)
def route(path, issues, labels, assignees, types, statuses, projects):
    if not issues: return html.Div("Loading…"), ""
    f = filter_issues(issues, labels or [], assignees or [], types or [], statuses or [], projects or [])
    pages = {
        "/":            (page_overview,     "Overview"),
        "/items":       (page_items,        "Work Items"),
        "/labels":      (page_labels,       "By Label"),
        "/assignee":    (page_assignee,     "By Assignee"),
        "/dependencies":(page_deps,         "Dependencies"),
        "/timeline":    (page_timeline,     "Timeline"),
        "/alerts":      (page_alerts,       "Alerts"),
        "/settings":    (page_settings,     "Settings"),
    }
    fn, title = pages.get(path, pages["/"])
    return fn(f, issues), title


# ════════════════════════════════════════════════════════════════
# PAGE BUILDERS
# ════════════════════════════════════════════════════════════════
def _graph(fig, id, h=340): return dcc.Graph(figure=fig, id=id, style={"height":f"{h}px"}, config={"displayModeBar":False})
def _card(*children, cols=1): return html.Div(children, style={"background":SURFACE,"borderRadius":"8px","border":f"1px solid {BORDER}","padding":"16px","gridColumn":f"span {cols}"})
def _grid(*cards, cols=2): return html.Div(cards, style={"display":"grid","gridTemplateColumns":f"repeat({cols},1fr)","gap":"16px","marginTop":"16px"})


def page_overview(issues, _all):
    closed = sum(1 for i in issues if i["status"]=="Closed")
    overdue = sum(1 for i in issues if "Past Due" in i["due_flag"])
    bugs = sum(1 for i in issues if i["type"]=="Bug")
    unassigned = sum(1 for i in issues if i["assignee"]=="Unassigned")
    stale = sum(1 for i in issues if i["days_stale"]>7 and i["status"]!="Closed")
    in_dev = sum(1 for i in issues if i["status"]=="Development In Progress")
    in_qa  = sum(1 for i in issues if "QA" in i["status"])
    pct = round(closed/len(issues)*100,1) if issues else 0

    kpis = html.Div([
        C.kpi("Total Issues",  len(issues), "#3b82f6"),
        C.kpi("Closed",        closed,      "#16a34a", f"{pct}%"),
        C.kpi("Past Due Date", overdue,     "#ef4444"),
        C.kpi("Bugs Open",     bugs,        "#f97316"),
        C.kpi("In Dev",        in_dev,      "#f59e0b"),
        C.kpi("In QA",         in_qa,       "#6366f1"),
        C.kpi("Unassigned",    unassigned,  "#94a3b8"),
        C.kpi("Stale >7d",     stale,       "#64748b"),
    ], style={"display":"flex","gap":"12px","flexWrap":"wrap"})

    # Label summary table
    by_label = defaultdict(lambda: {"total":0,"open":0,"past_due":0,"bugs":0,"closed":0})
    for i in issues:
        for l in (i["labels"] or ["(No Label)"]):
            by_label[l]["total"] += 1
            if i["status"] != "Closed": by_label[l]["open"] += 1
            if "Past Due" in i["due_flag"]: by_label[l]["past_due"] += 1
            if i["type"] == "Bug": by_label[l]["bugs"] += 1
            if i["status"] == "Closed": by_label[l]["closed"] += 1

    tbl = html.Table([
        html.Thead(html.Tr([html.Th(h) for h in ["Label","Total","Open","Closed","Past Due Date","Bugs"]],
                   style={"background":"#1e293b"})),
        html.Tbody([html.Tr([
            html.Td(l), html.Td(d["total"]), html.Td(d["open"]),
            html.Td(d["closed"]), html.Td(d["past_due"],style={"color":"#ef4444"} if d["past_due"] else {}),
            html.Td(d["bugs"],style={"color":"#f97316"} if d["bugs"] else {}),
        ]) for l,d in sorted(by_label.items(), key=lambda x: -x[1]["total"])]),
    ], style={"width":"100%","borderCollapse":"collapse","fontSize":"0.78rem"})

    activity = sorted([i for i in issues], key=lambda x: x["updated"], reverse=True)[:10]
    feed = html.Div([
        html.Div([
            html.A(i["key"], href=i["url"], target="_blank",
                   style={"color":"#60a5fa","fontSize":"0.75rem","textDecoration":"none","marginRight":"8px"}),
            html.Span(i["status"], style={"color":C.sc(i["status"]),"fontSize":"0.72rem","marginRight":"8px"}),
            html.Span(i["assignee"], style={"color":MUTED,"fontSize":"0.7rem","marginRight":"8px"}),
            html.Span(i["updated"], style={"color":"#334155","fontSize":"0.68rem"}),
        ], style={"padding":"7px 0","borderBottom":f"1px solid {BORDER}"})
        for i in activity
    ])

    return html.Div([
        kpis,
        _grid(
            _card(C.section("Label Summary"), tbl, cols=2),
            _card(C.section("Live Activity Feed"), feed),
            _card(_graph(CH.status_bar(issues), "ov-status")),
            cols=3
        ),
        _grid(
            _card(_graph(CH.type_donut(issues), "ov-type")),
            _card(_graph(CH.priority_donut(issues), "ov-prio")),
            _card(_graph(CH.velocity_line(issues), "ov-vel")),
            cols=3
        ),
    ])


def page_items(issues, _):
    cols = ["key","summary","type","status","assignee","priority","label_display","created","updated","due","due_flag","days_stale","comments_count"]
    hdrs = ["Key","Summary","Type","Status","Assignee","Priority","Label","Created","Updated","Due Date","Due Flag","Days Stale","Comments"]
    return html.Div([
        C.section(f"{len(issues)} Issues"),
        dash_table.DataTable(
            id="items-table",
            data=[{h:i.get(c,"") for h,c in zip(hdrs,cols)} for i in issues],
            columns=[{"name":h,"id":h,"presentation":"markdown" if h=="Key" else "input"} for h in hdrs],
            page_size=50, filter_action="native", sort_action="native",
            style_table={"overflowX":"auto"},
            style_cell={"background":SURFACE,"color":TEXT,"border":f"1px solid {BORDER}",
                        "fontSize":"0.76rem","padding":"8px 12px","fontFamily":FONT,
                        "textAlign":"left","maxWidth":"260px","overflow":"hidden","textOverflow":"ellipsis"},
            style_header={"background":"#1e293b","fontWeight":"700","color":TEXT,"border":f"1px solid {BORDER}"},
            style_data_conditional=[
                {"if":{"filter_query":"{Due Flag} contains 'Past Due'"},"color":"#ef4444"},
                {"if":{"filter_query":"{Type} = 'Bug'"},"color":"#f97316"},
                {"if":{"filter_query":"{Days Stale} > 7 && {Status} != 'Closed'"},"backgroundColor":"#1c1917"},
                {"if":{"row_index":"odd"},"backgroundColor":"#0f172a"},
            ],
            style_as_list_view=True,
        ),
    ])


def page_labels(issues, _all):
    by_label = defaultdict(list)
    for i in issues:
        for l in (i["labels"] or ["(No Label)"]): by_label[l].append(i)

    panels = []
    for label, items in sorted(by_label.items(), key=lambda x: -len(x[1])):
        closed = sum(1 for i in items if i["status"]=="Closed")
        overdue = sum(1 for i in items if "Past Due" in i["due_flag"])
        bugs = sum(1 for i in items if i["type"]=="Bug")
        panels.append(_card(
            html.Div([
                html.Span(label, style={"fontWeight":"700","fontSize":"0.9rem","color":TEXT}),
                html.Span(f"{len(items)} issues", style={"color":MUTED,"fontSize":"0.72rem","marginLeft":"8px"}),
            ]),
            html.Div([
                C.kpi("Open",     len(items)-closed, "#3b82f6"),
                C.kpi("Closed",   closed,            "#16a34a"),
                C.kpi("Past Due", overdue,           "#ef4444"),
                C.kpi("Bugs",     bugs,              "#f97316"),
            ], style={"display":"flex","gap":"8px","margin":"12px 0"}),
            _graph(CH.status_bar(items), f"lbl-{label.replace(' ','-')}", h=200),
        ))

    return html.Div([C.section("Initiatives"), html.Div(panels, style={"display":"grid","gridTemplateColumns":"repeat(auto-fill,minmax(400px,1fr))","gap":"16px"})])


def page_assignee(issues, _all):
    by_a = defaultdict(list)
    for i in issues: by_a[i["assignee"]].append(i)

    rows = []
    for a, items in sorted(by_a.items(), key=lambda x: -len(x[1])):
        by_lbl = defaultdict(list)
        for i in items:
            for l in (i["labels"] or ["(No Label)"]): by_lbl[l].append(i)
        closed  = sum(1 for i in items if i["status"]=="Closed")
        overdue = sum(1 for i in items if "Past Due" in i["due_flag"])
        bugs    = sum(1 for i in items if i["type"]=="Bug")
        stale   = round(sum(i["days_stale"] for i in items if i["status"]!="Closed") / max(1,len([i for i in items if i["status"]!="Closed"])),1)
        lbl_breakdown = " | ".join(f"{l}: {len(v)}" for l,v in sorted(by_lbl.items(), key=lambda x: -len(x[1])))
        rows.append(html.Div([
            html.Div([
                html.Span(a, style={"fontWeight":"700","fontSize":"0.85rem"}),
                html.Span(f"{len(items)} total", style={"color":MUTED,"fontSize":"0.72rem","marginLeft":"8px"}),
            ]),
            html.Div(lbl_breakdown, style={"color":MUTED,"fontSize":"0.7rem","margin":"4px 0 8px"}),
            html.Div([
                C.kpi("Open",    len(items)-closed, "#3b82f6"),
                C.kpi("Closed",  closed,            "#16a34a"),
                C.kpi("Past Due",overdue,           "#ef4444"),
                C.kpi("Bugs",    bugs,              "#f97316"),
                C.kpi("Avg Stale",f"{stale}d",     "#64748b"),
            ], style={"display":"flex","gap":"8px","flexWrap":"wrap"}),
        ], style={"background":SURFACE,"border":f"1px solid {BORDER}","borderRadius":"8px",
                  "padding":"16px","marginBottom":"10px"}))

    return html.Div([
        _grid(
            _card(_graph(CH.bubble_chart(issues), "a-bubble", h=380)),
            _card(_graph(CH.heatmap(issues),      "a-heat",   h=380)),
            cols=2
        ),
        _card(_graph(CH.assignee_stacked(issues, D.get_labels(issues)), "a-stack", h=340)),
        C.section("Per Assignee Detail"),
        html.Div(rows),
    ])


def page_deps(issues, _all):
    elements = C.cyto_elements(issues)
    return html.Div([
        C.section(f"Dependency Network — {len(issues)} Issues"),
        html.Div([
            dcc.Dropdown(id="dep-layout", value="cose", clearable=False,
                         options=[{"label":l,"value":l} for l in ["cose","breadthfirst","circle","grid","concentric"]],
                         style={"width":"180px","fontSize":"0.78rem"}),
        ], style={"marginBottom":"10px"}),
        html.Div([
            cyto.Cytoscape(
                id="cyto-graph",
                elements=elements,
                layout={"name":"cose","animate":True,"animationDuration":500},
                style={"height":"600px","flex":"1","background":"#0d1117","borderRadius":"8px"},
                stylesheet=C.CYTO_STYLE,
                responsive=True,
            ),
            html.Div(id="cyto-detail", style={
                "width":"300px","background":SURFACE,"borderRadius":"8px",
                "border":f"1px solid {BORDER}","overflowY":"auto","maxHeight":"600px",
            }),
        ], style={"display":"flex","gap":"16px"}),
    ])


def page_timeline(issues, _all):
    from datetime import date, timedelta
    today = date.today()
    dated = sorted([i for i in issues if i["due"]], key=lambda x: x["due"])
    if not dated:
        return html.Div("No issues with Due Date set.", style={"color":MUTED})

    fig = go.Figure()
    for i in dated:
        start = i.get("created", str(today - timedelta(days=7)))
        color = C.sc(i["status"])
        fig.add_trace(go.Bar(
            x=[(i["due"] if i["due"] else str(today))],
            y=[f"{i['assignee']} / {i['key']}"],
            orientation="h", marker_color=color, width=0.5,
            hovertemplate=f"<b>{i['key']}</b><br>{i['summary'][:60]}<br>Status: {i['status']}<br>Due: {i['due']}<extra></extra>",
            showlegend=False, base=[start],
        ))
    fig.update_layout(**{**CH.LAYOUT, "height":max(400, len(dated)*22),
                         "barmode":"overlay","title":"Timeline by Due Date"})
    return html.Div([C.section(f"{len(dated)} Issues with Due Date"), dcc.Graph(figure=fig, config={"displayModeBar":False})])


def page_alerts(issues, _all):
    from datetime import date, timedelta
    today = date.today()

    def _tbl(title, rows, color="#ef4444"):
        if not rows: return html.Div()
        return html.Div([
            html.Div(f"{title} ({len(rows)})", style={
                "fontSize":"0.72rem","fontWeight":"700","color":color,
                "letterSpacing":"0.1em","textTransform":"uppercase","marginBottom":"8px","marginTop":"20px",
            }),
            html.Table([
                html.Thead(html.Tr([html.Th(h) for h in ["Key","Assignee","Status","Priority","Detail"]],
                           style={"background":"#1e293b"})),
                html.Tbody([html.Tr([
                    html.Td(html.A(r["key"], href=r["url"], target="_blank",
                                   style={"color":"#60a5fa","textDecoration":"none"})),
                    html.Td(r["assignee"]), html.Td(r["status"],style={"color":C.sc(r["status"])}),
                    html.Td(r["priority"],style={"color":C.pc(r["priority"])}), html.Td(r.get("_detail","")),
                ]) for r in rows]),
            ], style={"width":"100%","borderCollapse":"collapse","fontSize":"0.76rem"}),
        ])

    past_due   = [i for i in issues if "Past Due" in i["due_flag"] and i["status"]!="Closed"]
    no_act     = [i for i in issues if i["days_stale"]>7 and i["status"] not in ("Closed","Rejected")]
    unassigned = [i for i in issues if i["assignee"]=="Unassigned" and i["status"]!="Closed"]
    crit_bugs  = [i for i in issues if i["type"]=="Bug" and i["priority"] in ("Highest","High") and i["status"]!="Closed"]
    no_label   = [i for i in issues if not i["labels"] and i["status"]!="Closed"]
    no_due     = [i for i in issues if not i["due"] and i["status"] not in ("Closed","Rejected","Groomed","To Do")]

    for i in past_due:  i["_detail"] = i["due_flag"]
    for i in no_act:    i["_detail"] = f"No update in {i['days_stale']}d"
    for i in crit_bugs: i["_detail"] = f"{i['priority']} Bug"

    return html.Div([
        html.Div([
            C.kpi("Past Due Date", len(past_due),   "#ef4444"),
            C.kpi("No Activity >7d",len(no_act),   "#f97316"),
            C.kpi("Unassigned",    len(unassigned), "#94a3b8"),
            C.kpi("High/Highest Bugs",len(crit_bugs),"#dc2626"),
            C.kpi("No Label",      len(no_label),  "#64748b"),
            C.kpi("No Due Date (active)",len(no_due),"#475569"),
        ], style={"display":"flex","gap":"12px","flexWrap":"wrap"}),
        _tbl("Past Due Date", past_due),
        _tbl("No Activity >7 Days", no_act, "#f97316"),
        _tbl("Unassigned Issues", unassigned, "#94a3b8"),
        _tbl("High/Highest Priority Bugs Open", crit_bugs, "#dc2626"),
        _tbl("No Label Assigned", no_label, "#64748b"),
        _tbl("Active Issues with No Due Date", no_due, "#475569"),
    ])


def page_settings(issues, _all):
    labels = D.get_labels(issues)
    return html.Div([
        C.section("Configuration"),
        html.Div([
            html.Div("Tracked Labels", style={"color":MUTED,"fontSize":"0.72rem","marginBottom":"8px"}),
            html.Div([html.Span(l, style={
                "background":"#1e293b","border":f"1px solid {BORDER}","borderRadius":"4px",
                "padding":"4px 10px","fontSize":"0.75rem","color":TEXT,"marginRight":"6px","marginBottom":"6px","display":"inline-block",
            }) for l in labels]),
        ], style={"background":SURFACE,"borderRadius":"8px","border":f"1px solid {BORDER}","padding":"20px","marginBottom":"16px"}),
        html.Div([
            html.Div("Connection", style={"color":MUTED,"fontSize":"0.72rem","marginBottom":"12px"}),
            *[html.Div([html.Span(k, style={"color":MUTED,"width":"180px","display":"inline-block","fontSize":"0.75rem"}),
                         html.Span(v, style={"color":TEXT,"fontSize":"0.75rem"})],
                        style={"marginBottom":"8px"})
              for k,v in [("Jira URL", D.BASE_URL),("Project", D.PROJECT),("Cache TTL","10 min"),("Total Issues",len(issues))]],
        ], style={"background":SURFACE,"borderRadius":"8px","border":f"1px solid {BORDER}","padding":"20px"}),
    ])


# ── Cytoscape click → detail ────────────────────────────────────
@app.callback(
    Output("cyto-detail","children"),
    Input("cyto-graph","tapNodeData"),
    State("store-issues","data"),
)
def cyto_click(node, issues):
    if not node or not issues: return html.Div("Click a node to see details.", style={"color":MUTED,"padding":"20px","fontSize":"0.78rem"})
    hit = next((i for i in issues if i["key"]==node["id"]), None)
    return C.issue_drawer(hit)


# ── Cytoscape layout update ─────────────────────────────────────
@app.callback(Output("cyto-graph","layout"), Input("dep-layout","value"))
def cyto_layout(val): return {"name": val, "animate": True}


# ── Global CSS ──────────────────────────────────────────────────
app.index_string = '''
<!DOCTYPE html>
<html>
<head>
{%metas%}<title>{%title%}</title>{%favicon%}{%css%}
<link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500;700&display=swap" rel="stylesheet">
<style>
* { box-sizing: border-box; margin: 0; padding: 0; }
body { background: #0f172a; }
::-webkit-scrollbar { width: 4px; height: 4px; }
::-webkit-scrollbar-track { background: #0f172a; }
::-webkit-scrollbar-thumb { background: #1e293b; border-radius: 2px; }
table th, table td { border: 1px solid #1e293b; padding: 7px 12px; text-align: left; }
table th { font-weight: 600; font-size: 0.7rem; letter-spacing: 0.08em; text-transform: uppercase; color: #64748b; }
table tr:hover td { background: #1e293b22; }
.Select-control, .Select-menu-outer { background: #111827 !important; border-color: #1e293b !important; color: #e2e8f0 !important; }
a:hover { opacity: 0.85; }
nav a:hover { color: #60a5fa !important; border-left-color: #3b82f6 !important; background: #1e293b22; }
</style>
</head>
<body>{%app_entry%}<footer>{%config%}{%scripts%}{%renderer%}</footer></body>
</html>
'''

if __name__ == "__main__":
    app.run(debug=False, host="0.0.0.0", port=8050)
