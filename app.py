import dash
from dash import dcc, html, Input, Output, State, callback_context, dash_table
import dash_cytoscape as cyto
import plotly.graph_objects as go
from collections import Counter, defaultdict
import threading

import data as D
import components as C
import charts as CH

cyto.load_extra_layouts()

app = dash.Dash(__name__, suppress_callback_exceptions=True,
                meta_tags=[{"name":"viewport","content":"width=device-width,initial-scale=1"}])
app.title = "Jira Operations"
server = app.server

threading.Thread(target=D.get_issues, daemon=True).start()

NAV = [("Overview","/"),("Work Items","/items"),("By Label","/labels"),
       ("By Assignee","/assignee"),("Dependencies","/dependencies"),
       ("Timeline","/timeline"),("Alerts","/alerts"),("Settings","/settings")]

SIDEBAR = html.Nav([
    html.Div([
        html.Div("JIRA", style={"fontSize":"0.6rem","fontWeight":"900","letterSpacing":"0.2em","color":C.NAVY,"lineHeight":"1"}),
        html.Div("OPERATIONS", style={"fontSize":"0.55rem","fontWeight":"700","letterSpacing":"0.18em","color":C.MUTED}),
    ], style={"padding":"24px 20px 16px","borderBottom":f"1px solid {C.BORDER}"}),
    *[dcc.Link(label, href=href, style={
        "display":"block","padding":"10px 20px","color":C.MUTED,
        "textDecoration":"none","fontSize":"0.75rem","fontWeight":"600",
        "letterSpacing":"0.04em","borderLeft":"3px solid transparent",
        "transition":"all 0.15s",
    }) for label, href in NAV],
], style={
    "width":"190px","minHeight":"100vh","background":C.SURFACE,"flexShrink":"0",
    "borderRight":f"1px solid {C.BORDER}","position":"sticky","top":"0","overflowY":"auto",
})

def dd(id, placeholder, opts=None, multi=True):
    return dcc.Dropdown(
        id=id, placeholder=placeholder, multi=multi, clearable=True,
        options=opts or [],
        style={"minWidth":"140px","fontSize":"0.75rem","border":f"1px solid {C.BORDER}"},
    )

TOPBAR = html.Div([
    html.Div(id="page-title", style={
        "fontWeight":"800","fontSize":"0.85rem","color":C.NAVY,
        "letterSpacing":"0.04em","textTransform":"uppercase",
    }),
    html.Div([
        dd("g-project",  "Project"),
        dd("g-label",    "Label"),
        dd("g-assignee", "Assignee"),
        dd("g-type",     "Issue Type",
           [{"label":t,"value":t} for t in ["Task","Story","Bug","Sub-task","Epic"]]),
        dd("g-status",   "Status",
           [{"label":s,"value":s} for s in C.STATUS_CLR]),
        html.Button([html.Span("↻", style={"marginRight":"6px"}), "Refresh"],
                    id="btn-refresh", n_clicks=0, style={
            "background":C.NAVY,"color":"#fff","border":"none","borderRadius":"8px",
            "padding":"8px 16px","cursor":"pointer","fontSize":"0.75rem","fontWeight":"700",
        }),
        html.Div(id="sync-ts", style={"color":C.MUTED,"fontSize":"0.7rem","alignSelf":"center","whiteSpace":"nowrap"}),
    ], style={"display":"flex","gap":"8px","flexWrap":"wrap","alignItems":"center"}),
], style={
    "display":"flex","justifyContent":"space-between","alignItems":"center","flexWrap":"wrap",
    "gap":"12px","padding":"12px 24px","borderBottom":f"1px solid {C.BORDER}",
    "background":C.SURFACE,"position":"sticky","top":"0","zIndex":"100",
    "boxShadow":"0 1px 4px rgba(15,35,68,0.06)",
})

app.layout = html.Div([
    dcc.Location(id="url"),
    dcc.Store(id="store-issues"),
    dcc.Interval(id="auto-refresh", interval=600_000, n_intervals=0),
    dcc.Interval(id="init-refresh", interval=4000, n_intervals=0, max_intervals=8),
    html.Div([
        SIDEBAR,
        html.Div([
            TOPBAR,
            html.Div(id="page-content", style={"padding":"20px 24px","flex":"1","background":C.BG}),
        ], style={"flex":"1","display":"flex","flexDirection":"column","overflow":"hidden"}),
    ], style={"display":"flex","minHeight":"100vh","background":C.BG}),
], style={"fontFamily":"'DM Sans', 'Segoe UI', sans-serif"})


@app.callback(
    Output("store-issues","data"), Output("sync-ts","children"),
    Output("g-label","options"), Output("g-assignee","options"), Output("g-project","options"),
    Input("btn-refresh","n_clicks"), Input("auto-refresh","n_intervals"), Input("init-refresh","n_intervals"),
)
def load_data(n, _, init):
    force = callback_context.triggered_id == "btn-refresh"
    issues = D.get_issues(force=force)
    if not issues: return [], "Connecting...", [], [], []
    labels    = [{"label":l,"value":l} for l in D.get_labels(issues)]
    assignees = [{"label":a,"value":a} for a in D.get_assignees(issues)]
    projects  = [{"label":p,"value":p} for p in D.get_projects(issues)]
    return issues, f"Synced: {D.last_sync()} · {len(issues)} issues", labels, assignees, projects


def filter_issues(issues, labels, assignees, types, statuses, projects):
    r = issues
    if projects:  r = [i for i in r if i["project"] in projects]
    if labels:    r = [i for i in r if any(l in i["labels"] for l in labels)]
    if assignees: r = [i for i in r if i["assignee"] in assignees]
    if types:     r = [i for i in r if i["type"] in types]
    if statuses:  r = [i for i in r if i["status"] in statuses]
    return r


@app.callback(
    Output("page-content","children"), Output("page-title","children"),
    Input("url","pathname"), Input("store-issues","data"),
    Input("g-label","value"), Input("g-assignee","value"),
    Input("g-type","value"), Input("g-status","value"), Input("g-project","value"),
)
def route(path, issues, labels, assignees, types, statuses, projects):
    if not issues:
        return html.Div([
            html.Div("●", style={"fontSize":"2rem","color":C.ACCENT,"marginBottom":"12px","animation":"pulse 1.5s infinite"}),
            html.Div("Connecting to Jira...", style={"fontWeight":"700","color":C.NAVY,"fontSize":"1rem"}),
            html.Div("Loading issues in the background. Page refreshes automatically.", style={"color":C.MUTED,"fontSize":"0.8rem","marginTop":"6px"}),
        ], style={"padding":"60px","textAlign":"center"}), ""
    f = filter_issues(issues, labels or [], assignees or [], types or [], statuses or [], projects or [])
    pages = {
        "/":            (page_overview,  "Overview"),
        "/items":       (page_items,     "Work Items"),
        "/labels":      (page_labels,    "By Label"),
        "/assignee":    (page_assignee,  "By Assignee"),
        "/dependencies":(page_deps,      "Dependencies"),
        "/timeline":    (page_timeline,  "Timeline"),
        "/alerts":      (page_alerts,    "Alerts"),
        "/settings":    (page_settings,  "Settings"),
    }
    fn, title = pages.get(path, pages["/"])
    return fn(f, issues), title


def _g(fig, id, h=320): return dcc.Graph(figure=fig, id=id, style={"height":f"{h}px"}, config={"displayModeBar":False})


def page_overview(issues, _all):
    closed     = sum(1 for i in issues if i["status"]=="Closed")
    overdue    = sum(1 for i in issues if "Past Due" in i["due_flag"])
    bugs       = sum(1 for i in issues if i["type"]=="Bug")
    unassigned = sum(1 for i in issues if i["assignee"]=="Unassigned")
    stale      = sum(1 for i in issues if i["days_stale"]>7 and i["status"]!="Closed")
    in_dev     = sum(1 for i in issues if i["status"]=="Development In Progress")
    in_qa      = sum(1 for i in issues if "QA" in i["status"])
    pct        = round(closed/len(issues)*100,1) if issues else 0

    kpis = html.Div([
        C.kpi("Total",      len(issues), C.NAVY),
        C.kpi("Closed",     closed,      C.GREEN, f"{pct}%"),
        C.kpi("Past Due",   overdue,     C.RED),
        C.kpi("Bugs",       bugs,        C.ORANGE),
        C.kpi("In Dev",     in_dev,      C.AMBER),
        C.kpi("In QA",      in_qa,       "#7C3AED"),
        C.kpi("Unassigned", unassigned,  C.MUTED),
        C.kpi("Stale >7d",  stale,       C.MUTED),
    ], style={"display":"flex","gap":"12px","flexWrap":"wrap"})

    # Label summary
    by_label = defaultdict(lambda: {"total":0,"open":0,"past_due":0,"bugs":0,"closed":0})
    for i in issues:
        for l in (i["labels"] or ["(No Label)"]):
            by_label[l]["total"] += 1
            if i["status"] != "Closed": by_label[l]["open"] += 1
            if "Past Due" in i["due_flag"]: by_label[l]["past_due"] += 1
            if i["type"] == "Bug": by_label[l]["bugs"] += 1
            if i["status"] == "Closed": by_label[l]["closed"] += 1

    tbl = html.Table([
        html.Thead(html.Tr([html.Th(h) for h in ["Label","Total","Open","Closed","Past Due","Bugs"]],
                           style={"background":C.ACCENT2})),
        html.Tbody([html.Tr([
            html.Td(l, style={"fontWeight":"600","color":C.NAVY}),
            html.Td(d["total"]), html.Td(d["open"]),
            html.Td(d["closed"],style={"color":C.GREEN} if d["closed"] else {}),
            html.Td(d["past_due"],style={"color":C.RED,"fontWeight":"700"} if d["past_due"] else {}),
            html.Td(d["bugs"],style={"color":C.ORANGE,"fontWeight":"700"} if d["bugs"] else {}),
        ], style={"background":C.SURFACE if i%2==0 else C.BG}) for i,(l,d) in enumerate(sorted(by_label.items(), key=lambda x: -x[1]["total"]))]),
    ], style={"width":"100%","borderCollapse":"collapse","fontSize":"0.78rem"})

    activity = sorted(issues, key=lambda x: x["updated"], reverse=True)[:8]
    feed = html.Div([html.Div([
        html.A(i["key"], href=i["url"], target="_blank", style={"color":C.ACCENT,"fontSize":"0.73rem","fontWeight":"700","textDecoration":"none","marginRight":"8px","fontFamily":"DM Mono, monospace"}),
        C.status_badge(i["status"]),
        html.Span(i["assignee"], style={"color":C.MUTED,"fontSize":"0.7rem","marginLeft":"8px"}),
        html.Span(i["updated"], style={"color":C.MUTED,"fontSize":"0.68rem","float":"right"}),
    ], style={"padding":"8px 0","borderBottom":f"1px solid {C.BORDER}","display":"flex","alignItems":"center","gap":"4px","flexWrap":"wrap"})
    for i in activity])

    return html.Div([
        kpis,
        C.grid(
            C.card(C.section("Label Breakdown"), tbl, cols=2),
            C.card(C.section("Live Activity"), feed),
            C.card(_g(CH.status_bar(issues), "ov-status")),
            cols=3,
        ),
        C.grid(
            C.card(_g(CH.type_donut(issues), "ov-type")),
            C.card(_g(CH.priority_donut(issues), "ov-prio")),
            C.card(_g(CH.velocity_line(issues), "ov-vel")),
            cols=3,
        ),
    ])


def page_items(issues, _):
    cols = ["key","summary","type","status","assignee","priority","label_display","created","updated","due","due_flag","days_stale","comments_count"]
    hdrs = ["Key","Summary","Type","Status","Assignee","Priority","Label","Created","Updated","Due","Due Flag","Stale d","Comments"]
    return html.Div([
        C.section(f"{len(issues)} Issues"),
        dash_table.DataTable(
            id="items-table",
            data=[{h:i.get(c,"") for h,c in zip(hdrs,cols)} for i in issues],
            columns=[{"name":h,"id":h} for h in hdrs],
            page_size=50, filter_action="native", sort_action="native",
            style_table={"overflowX":"auto","borderRadius":"10px","border":f"1px solid {C.BORDER}"},
            style_cell={"background":C.SURFACE,"color":C.TEXT,"border":f"1px solid {C.BORDER}",
                        "fontSize":"0.75rem","padding":"9px 12px",
                        "fontFamily":"'DM Sans', sans-serif",
                        "textAlign":"left","maxWidth":"280px","overflow":"hidden","textOverflow":"ellipsis"},
            style_header={"background":C.ACCENT2,"fontWeight":"800","color":C.NAVY,
                          "border":f"1px solid {C.BORDER}","fontSize":"0.7rem",
                          "letterSpacing":"0.05em","textTransform":"uppercase"},
            style_data_conditional=[
                {"if":{"filter_query":"{Due Flag} contains 'Past Due'"},"color":C.RED,"fontWeight":"700"},
                {"if":{"filter_query":"{Type} = 'Bug'"},"color":C.ORANGE},
                {"if":{"row_index":"odd"},"backgroundColor":C.BG},
            ],
        ),
    ])


def page_labels(issues, _all):
    by_label = defaultdict(list)
    for i in issues:
        for l in (i["labels"] or ["(No Label)"]): by_label[l].append(i)
    panels = []
    for label, items in sorted(by_label.items(), key=lambda x: -len(x[1])):
        closed  = sum(1 for i in items if i["status"]=="Closed")
        overdue = sum(1 for i in items if "Past Due" in i["due_flag"])
        bugs    = sum(1 for i in items if i["type"]=="Bug")
        panels.append(C.card(
            html.Div([
                html.Span(label, style={"fontWeight":"800","fontSize":"0.88rem","color":C.NAVY}),
                html.Span(f"{len(items)} issues", style={"color":C.MUTED,"fontSize":"0.72rem","marginLeft":"8px"}),
            ]),
            html.Div([
                C.kpi("Open",    len(items)-closed, C.ACCENT),
                C.kpi("Closed",  closed,            C.GREEN),
                C.kpi("Past Due",overdue,           C.RED),
                C.kpi("Bugs",    bugs,              C.ORANGE),
            ], style={"display":"flex","gap":"8px","margin":"12px 0","flexWrap":"wrap"}),
            _g(CH.status_bar(items), f"lbl-{label[:20].replace(' ','-')}", h=180),
        ))
    return html.Div([
        C.section("By Initiative"),
        html.Div(panels, style={"display":"grid","gridTemplateColumns":"repeat(auto-fill,minmax(420px,1fr))","gap":"16px"}),
    ])


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
        lbl_parts = " · ".join(f"{l}: {len(v)}" for l,v in sorted(by_lbl.items(), key=lambda x: -len(x[1]))[:5])
        rows.append(html.Div([
            html.Div([
                html.Div(a, style={"fontWeight":"800","fontSize":"0.88rem","color":C.NAVY}),
                html.Div(lbl_parts, style={"color":C.MUTED,"fontSize":"0.7rem","marginTop":"2px"}),
            ]),
            html.Div([
                C.kpi("Open",     len(items)-closed, C.ACCENT),
                C.kpi("Closed",   closed,            C.GREEN),
                C.kpi("Past Due", overdue,           C.RED),
                C.kpi("Bugs",     bugs,              C.ORANGE),
                C.kpi("Avg Stale",f"{stale}d",      C.MUTED),
            ], style={"display":"flex","gap":"8px","flexWrap":"wrap","marginTop":"10px"}),
        ], style={
            "background":C.SURFACE,"borderRadius":"10px","padding":"16px",
            "border":f"1px solid {C.BORDER}","marginBottom":"10px",
            "boxShadow":"0 1px 6px rgba(15,35,68,0.06)",
        }))
    return html.Div([
        C.grid(
            C.card(_g(CH.bubble_chart(issues), "a-bubble", h=360)),
            C.card(_g(CH.heatmap(issues),      "a-heat",   h=360)),
            cols=2,
        ),
        C.card(_g(CH.assignee_stacked(issues, D.get_labels(issues)), "a-stack", h=320)),
        C.section("Per Assignee Detail"),
        html.Div(rows),
    ])


def page_deps(issues, _all):
    elements = C.cyto_elements(issues)
    return html.Div([
        C.section(f"Dependency Network", f"{len(issues)} issues · click a node to inspect"),
        html.Div([
            dcc.Dropdown(id="dep-layout", value="cose", clearable=False,
                         options=[{"label":l,"value":l} for l in ["cose","breadthfirst","circle","grid","concentric"]],
                         style={"width":"160px","fontSize":"0.75rem"}),
        ], style={"marginBottom":"12px"}),
        html.Div([
            cyto.Cytoscape(
                id="cyto-graph", elements=elements,
                layout={"name":"cose","animate":True,"animationDuration":500},
                style={"height":"580px","flex":"1","background":C.SURFACE,"borderRadius":"10px","border":f"1px solid {C.BORDER}"},
                stylesheet=C.CYTO_STYLE, responsive=True,
            ),
            html.Div(id="cyto-detail", style={
                "width":"280px","background":C.SURFACE,"borderRadius":"10px",
                "border":f"1px solid {C.BORDER}","overflowY":"auto","maxHeight":"580px",
            }),
        ], style={"display":"flex","gap":"16px"}),
    ])


def page_timeline(issues, _all):
    from datetime import date, timedelta
    today = date.today()
    dated = sorted([i for i in issues if i["due"]], key=lambda x: x["due"])
    if not dated: return html.Div("No issues with Due Date set.", style={"color":C.MUTED,"padding":"40px","textAlign":"center"})
    fig = go.Figure()
    for i in dated:
        start = i.get("created", str(today - timedelta(days=7)))
        fg = C.sc(i["status"]); bg = C.sc_bg(i["status"])
        fig.add_trace(go.Bar(
            x=[i["due"]], y=[f"{i['assignee'][:15]} / {i['key']}"],
            orientation="h", marker_color=bg, marker_line_color=fg, marker_line_width=2, width=0.6,
            hovertemplate=f"<b>{i['key']}</b><br>{i['summary'][:60]}<br>Status: {i['status']}<br>Due: {i['due']}<extra></extra>",
            showlegend=False, base=[start],
        ))
    fig.update_layout(
        paper_bgcolor=C.BG, plot_bgcolor=C.BG,
        font=dict(color=C.TEXT, size=10, family="DM Mono, monospace"),
        margin=dict(l=8,r=8,t=36,b=8),
        height=max(400, len(dated)*20), barmode="overlay",
        title=dict(text="Delivery Timeline", font=dict(size=12,color=C.NAVY2,weight=700)),
        xaxis=dict(gridcolor=C.BORDER), yaxis=dict(gridcolor=C.BORDER),
    )
    return html.Div([C.section(f"{len(dated)} Issues with Due Date"), dcc.Graph(figure=fig, config={"displayModeBar":False})])


def page_alerts(issues, _all):
    def _tbl(title, rows, color=C.RED):
        if not rows: return html.Div()
        return C.card(
            html.Div(f"{title}  ·  {len(rows)} issues", style={
                "fontSize":"0.65rem","fontWeight":"800","color":color,
                "letterSpacing":"0.12em","textTransform":"uppercase","marginBottom":"12px",
            }),
            html.Table([
                html.Thead(html.Tr([html.Th(h) for h in ["Key","Assignee","Status","Priority","Detail"]],
                                   style={"background":C.ACCENT2})),
                html.Tbody([html.Tr([
                    html.Td(html.A(r["key"], href=r["url"], target="_blank",
                                   style={"color":C.ACCENT,"textDecoration":"none","fontWeight":"700","fontFamily":"DM Mono, monospace","fontSize":"0.73rem"})),
                    html.Td(r["assignee"],style={"color":C.TEXT}),
                    html.Td(C.status_badge(r["status"])),
                    html.Td(r["priority"],style={"color":C.pc(r["priority"]),"fontWeight":"700"}),
                    html.Td(r.get("_detail",""),style={"color":C.MUTED,"fontSize":"0.72rem"}),
                ], style={"background":C.SURFACE if ri%2==0 else C.BG}) for ri,r in enumerate(rows)]),
            ], style={"width":"100%","borderCollapse":"collapse","fontSize":"0.76rem"}),
        )

    past_due   = [i for i in issues if "Past Due" in i["due_flag"] and i["status"]!="Closed"]
    no_act     = [i for i in issues if i["days_stale"]>7 and i["status"] not in ("Closed","Rejected")]
    unassigned = [i for i in issues if i["assignee"]=="Unassigned" and i["status"]!="Closed"]
    crit_bugs  = [i for i in issues if i["type"]=="Bug" and i["priority"] in ("Highest","High") and i["status"]!="Closed"]
    no_label   = [i for i in issues if not i["labels"] and i["status"]!="Closed"]

    for i in past_due: i["_detail"] = i["due_flag"]
    for i in no_act:   i["_detail"] = f"No update in {i['days_stale']}d"
    for i in crit_bugs: i["_detail"] = f"{i['priority']} Bug"

    return html.Div([
        html.Div([
            C.kpi("Past Due",      len(past_due),   C.RED),
            C.kpi("No Activity >7d",len(no_act),   C.ORANGE),
            C.kpi("Unassigned",    len(unassigned), C.MUTED),
            C.kpi("High Bugs",     len(crit_bugs),  "#D93025"),
            C.kpi("No Label",      len(no_label),   C.MUTED),
        ], style={"display":"flex","gap":"12px","flexWrap":"wrap","marginBottom":"20px"}),
        _tbl("Past Due Date", past_due, C.RED),
        _tbl("No Activity >7 Days", no_act, C.ORANGE),
        _tbl("Unassigned", unassigned, C.MUTED),
        _tbl("High / Highest Priority Bugs Open", crit_bugs, "#D93025"),
        _tbl("No Label Assigned", no_label, C.MUTED),
    ])


def page_settings(issues, _all):
    return html.Div([
        C.section("Configuration"),
        C.card(
            html.Div("Tracked Labels", style={"color":C.MUTED,"fontSize":"0.65rem","fontWeight":"700","letterSpacing":"0.1em","textTransform":"uppercase","marginBottom":"10px"}),
            html.Div([html.Span(l, style={
                "background":C.ACCENT2,"color":C.ACCENT,"borderRadius":"20px",
                "padding":"3px 12px","fontSize":"0.73rem","fontWeight":"600",
                "marginRight":"6px","marginBottom":"6px","display":"inline-block",
                "border":f"1px solid {C.ACCENT}33",
            }) for l in D.get_labels(issues)]),
        ),
        C.card(
            html.Div("Connection", style={"color":C.MUTED,"fontSize":"0.65rem","fontWeight":"700","letterSpacing":"0.1em","textTransform":"uppercase","marginBottom":"12px"}),
            *[html.Div([
                html.Span(k, style={"color":C.MUTED,"width":"160px","display":"inline-block","fontSize":"0.73rem","fontWeight":"600"}),
                html.Span(v, style={"color":C.TEXT,"fontSize":"0.78rem","fontWeight":"500","fontFamily":"DM Mono, monospace"}),
            ], style={"marginBottom":"8px"})
              for k,v in [("Jira URL",D.BASE_URL),("Projects",", ".join(D.PROJECTS)),
                          ("Cache TTL","10 min"),("Max Issues",D.MAX_ISSUES),
                          ("Days Back",D.DAYS_BACK),("Total Loaded",len(issues))]],
        ),
    ])


@app.callback(Output("cyto-detail","children"), Input("cyto-graph","tapNodeData"), State("store-issues","data"))
def cyto_click(node, issues):
    if not node or not issues:
        return html.Div("Click a node.", style={"color":C.MUTED,"padding":"20px","fontSize":"0.8rem"})
    hit = next((i for i in issues if i["key"]==node["id"]), None)
    return C.issue_drawer(hit)

@app.callback(Output("cyto-graph","layout"), Input("dep-layout","value"))
def cyto_layout(val): return {"name": val, "animate": True}


app.index_string = '''
<!DOCTYPE html>
<html>
<head>
{%metas%}<title>{%title%}</title>{%favicon%}{%css%}
<link href="https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600;700;800&family=DM+Mono:wght@400;500;700&display=swap" rel="stylesheet">
<style>
* { box-sizing: border-box; margin: 0; padding: 0; }
body { background: #F8FAFF; }
::-webkit-scrollbar { width: 5px; height: 5px; }
::-webkit-scrollbar-track { background: #F8FAFF; }
::-webkit-scrollbar-thumb { background: #DDE6F5; border-radius: 3px; }
::-webkit-scrollbar-thumb:hover { background: #1E6FDB44; }
table th { padding: 9px 12px; text-align: left; font-size: 0.68rem; letter-spacing: 0.08em; text-transform: uppercase; color: #6B7A99; font-weight: 700; }
table td { padding: 8px 12px; border-bottom: 1px solid #DDE6F5; }
table tr:hover td { background: #E8F0FB33 !important; }
a:hover { opacity: 0.8; }
nav a:hover { color: #1E6FDB !important; border-left-color: #1E6FDB !important; background: #E8F0FB44; }
.Select-control { background: #fff !important; border-color: #DDE6F5 !important; }
@keyframes pulse { 0%,100%{opacity:1} 50%{opacity:0.4} }
</style>
</head>
<body>{%app_entry%}<footer>{%config%}{%scripts%}{%renderer%}</footer></body>
</html>
'''

if __name__ == "__main__":
    app.run(debug=False, host="0.0.0.0", port=8050)
