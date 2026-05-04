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
       ("By Assignee","/assignee"),("Dependency Graph","/dependencies"),
       ("Relationship Matrix","/matrix"),("Workflow Gates","/workflow"),
       ("Timeline","/timeline"),("Alerts","/alerts"),("Settings","/settings")]

NAV_GROUPS = {
    "ANALYSIS":  ["Overview","Work Items"],
    "BREAKDOWN": ["By Label","By Assignee"],
    "STRUCTURE": ["Dependency Graph","Relationship Matrix","Workflow Gates"],
    "OPERATIONS":["Timeline","Alerts"],
    "SYSTEM":    ["Settings"],
}

def sidebar_nav():
    link_map = {label: href for label, href in NAV}
    items = []
    for group, labels in NAV_GROUPS.items():
        items.append(html.Div(group, style={
            "fontSize":"0.52rem","fontWeight":"800","letterSpacing":"0.18em",
            "color":"#3A5080","padding":"16px 18px 4px","textTransform":"uppercase",
        }))
        for label in labels:
            items.append(dcc.Link(label, href=link_map[label], style={
                "display":"block","padding":"8px 18px","color":"#8AA0CC",
                "textDecoration":"none","fontSize":"0.75rem","fontWeight":"600",
                "letterSpacing":"0.03em","borderLeft":"3px solid transparent","transition":"all 0.12s",
            }))
    return items

SIDEBAR = html.Nav([
    html.Div([
        html.Div("JIRA", style={"fontSize":"1rem","fontWeight":"900","color":"#FFFFFF","letterSpacing":"0.1em","lineHeight":"1"}),
        html.Div("OPERATIONS CENTRE", style={"fontSize":"0.55rem","fontWeight":"700","color":"#4A6898","letterSpacing":"0.12em","marginTop":"2px"}),
        html.Div("Solytics Partners", style={"fontSize":"0.6rem","color":"#3A5080","marginTop":"6px","fontWeight":"500"}),
    ], style={"padding":"22px 18px 16px","borderBottom":"1px solid #1E3560"}),
    html.Div(id="nav-sync", style={"padding":"8px 18px","fontSize":"0.62rem","color":"#3A5080","borderBottom":"1px solid #152845"}),
    *sidebar_nav(),
], style={
    "width":"200px","minHeight":"100vh","background":C.NAVY,
    "flexShrink":"0","position":"sticky","top":"0","overflowY":"auto",
})

def dd(id, placeholder, opts=None):
    return dcc.Dropdown(id=id, placeholder=placeholder, multi=True, clearable=True, options=opts or [],
        style={"minWidth":"130px","fontSize":"0.74rem","border":f"1px solid {C.BORDER}","borderRadius":"6px"})

TOPBAR = html.Div([
    html.Div(id="page-title", style={"fontWeight":"800","fontSize":"0.82rem","color":C.NAVY,"letterSpacing":"0.06em","textTransform":"uppercase"}),
    html.Div([
        dd("g-project","Project"),
        dd("g-label","Label"),
        dd("g-assignee","Assignee"),
        dd("g-type","Issue Type",[{"label":t,"value":t} for t in ["Task","Story","Bug","Sub-task","Epic"]]),
        dd("g-status","Status",[{"label":s,"value":s} for s in C.STATUS_CLR]),
        html.Button("↻  Refresh", id="btn-refresh", n_clicks=0, style={
            "background":C.NAVY,"color":"#fff","border":"none","borderRadius":"6px",
            "padding":"8px 14px","cursor":"pointer","fontSize":"0.73rem","fontWeight":"700","letterSpacing":"0.04em",
        }),
    ], style={"display":"flex","gap":"8px","flexWrap":"wrap","alignItems":"center"}),
], style={
    "display":"flex","justifyContent":"space-between","alignItems":"center","flexWrap":"wrap",
    "gap":"12px","padding":"11px 22px","borderBottom":f"1px solid {C.BORDER}",
    "background":C.SURFACE,"position":"sticky","top":"0","zIndex":"100",
    "boxShadow":"0 2px 6px rgba(11,29,58,0.07)",
})

app.layout = html.Div([
    dcc.Location(id="url"),
    dcc.Store(id="store-issues"),
    dcc.Store(id="store-depth", data=2),
    dcc.Interval(id="auto-refresh", interval=600_000, n_intervals=0),
    dcc.Interval(id="init-refresh", interval=4000, n_intervals=0, max_intervals=8),
    html.Div([
        SIDEBAR,
        html.Div([TOPBAR, html.Div(id="page-content", style={"padding":"18px 22px","flex":"1","background":C.BG})],
                 style={"flex":"1","display":"flex","flexDirection":"column","overflow":"hidden"}),
    ], style={"display":"flex","minHeight":"100vh","background":C.BG}),
], style={"fontFamily":"'DM Sans','Segoe UI',sans-serif"})


@app.callback(
    Output("store-issues","data"), Output("nav-sync","children"),
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
    return issues, f"↻ {D.last_sync()}  ·  {len(issues)} issues", labels, assignees, projects


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
            html.Div("◎", style={"fontSize":"3rem","color":C.ACCENT,"marginBottom":"12px"}),
            html.Div("Connecting to Jira...", style={"fontWeight":"800","color":C.NAVY,"fontSize":"1rem"}),
            html.Div("Auto-refreshes every 10 minutes. Loading in background.", style={"color":C.MUTED,"fontSize":"0.78rem","marginTop":"6px"}),
        ], style={"padding":"80px","textAlign":"center"}), ""
    f = filter_issues(issues, labels or [], assignees or [], types or [], statuses or [], projects or [])
    pages = {
        "/":           (page_overview,   "Overview"),
        "/items":      (page_items,      "Work Items"),
        "/labels":     (page_labels,     "By Label"),
        "/assignee":   (page_assignee,   "By Assignee"),
        "/dependencies":(page_deps,      "Dependency Graph"),
        "/matrix":     (page_matrix,     "Relationship Matrix"),
        "/workflow":   (page_workflow,   "Workflow Gates"),
        "/timeline":   (page_timeline,   "Timeline"),
        "/alerts":     (page_alerts,     "Alerts"),
        "/settings":   (page_settings,   "Settings"),
    }
    fn, title = pages.get(path, pages["/"])
    return fn(f, issues), title


def _g(fig, id, h=320):
    return dcc.Graph(figure=fig, id=id, style={"height":f"{h}px"}, config={"displayModeBar":False})


# ════════════════════ PAGES ════════════════════════════════════

def page_overview(issues, _all):
    closed = sum(1 for i in issues if i["status"]=="Closed")
    overdue = sum(1 for i in issues if "Past Due" in i["due_flag"])
    bugs = sum(1 for i in issues if i["type"]=="Bug")
    unassigned = sum(1 for i in issues if i["assignee"]=="Unassigned")
    stale = sum(1 for i in issues if i["days_stale"]>7 and i["status"]!="Closed")
    in_dev = sum(1 for i in issues if i["status"]=="Development In Progress")
    in_qa = sum(1 for i in issues if "QA" in i["status"])
    pct = round(closed/len(issues)*100,1) if issues else 0

    kpis = html.Div([
        C.kpi("Total",      len(issues), C.NAVY),
        C.kpi("Closed",     closed,      C.GREEN, f"{pct}%"),
        C.kpi("Past Due",   overdue,     C.RED),
        C.kpi("Bugs Open",  bugs,        C.ORANGE),
        C.kpi("In Dev",     in_dev,      C.AMBER),
        C.kpi("In QA",      in_qa,       C.PURPLE),
        C.kpi("Unassigned", unassigned,  C.MUTED),
        C.kpi("Stale >7d",  stale,       C.MUTED),
    ], style={"display":"flex","gap":"10px","flexWrap":"wrap"})

    by_label = defaultdict(lambda: {"total":0,"open":0,"past_due":0,"bugs":0,"closed":0})
    for i in issues:
        for l in (i["labels"] or ["(No Label)"]):
            by_label[l]["total"] += 1
            if i["status"]!="Closed": by_label[l]["open"] += 1
            if "Past Due" in i["due_flag"]: by_label[l]["past_due"] += 1
            if i["type"]=="Bug": by_label[l]["bugs"] += 1
            if i["status"]=="Closed": by_label[l]["closed"] += 1

    tbl = html.Table([
        html.Thead(html.Tr([html.Th(h) for h in ["Label","Total","Open","Closed","Past Due","Bugs"]],
                           style={"background":C.ACCENT2})),
        html.Tbody([html.Tr([
            html.Td(l, style={"fontWeight":"700","color":C.NAVY,"fontFamily":"JetBrains Mono, monospace","fontSize":"0.72rem"}),
            html.Td(d["total"]), html.Td(d["open"]),
            html.Td(d["closed"], style={"color":C.GREEN,"fontWeight":"700"} if d["closed"] else {}),
            html.Td(d["past_due"], style={"color":C.RED,"fontWeight":"800"} if d["past_due"] else {}),
            html.Td(d["bugs"], style={"color":C.ORANGE,"fontWeight":"700"} if d["bugs"] else {}),
        ], style={"background":C.SURFACE if ri%2==0 else C.BG})
          for ri,(l,d) in enumerate(sorted(by_label.items(), key=lambda x: -x[1]["total"]))]),
    ], style={"width":"100%","borderCollapse":"collapse","fontSize":"0.77rem"})

    activity = sorted(issues, key=lambda x: x["updated"], reverse=True)[:8]
    feed = html.Div([html.Div([
        html.A(i["key"], href=i["url"], target="_blank",
               style={"color":C.ACCENT,"fontSize":"0.72rem","fontWeight":"700","textDecoration":"none","marginRight":"8px","fontFamily":"JetBrains Mono, monospace"}),
        C.status_badge(i["status"]),
        html.Span(i["assignee"], style={"color":C.MUTED,"fontSize":"0.69rem","marginLeft":"8px"}),
        html.Span(i["updated"], style={"color":C.MUTED,"fontSize":"0.67rem","marginLeft":"auto"}),
    ], style={"padding":"7px 0","borderBottom":f"1px solid {C.BORDER}","display":"flex","alignItems":"center","gap":"4px"})
    for i in activity])

    return html.Div([
        kpis,
        C.grid(C.card(C.section("Initiative Summary"), tbl, cols=2),
               C.card(C.section("Live Activity"), feed),
               C.card(_g(CH.status_bar(issues),"ov-s")), cols=3),
        C.grid(C.card(_g(CH.type_donut(issues),"ov-t")),
               C.card(_g(CH.priority_donut(issues),"ov-p")),
               C.card(_g(CH.velocity_line(issues),"ov-v")), cols=3),
    ])


def page_items(issues, _):
    cols = ["key","summary","type","status","assignee","priority","label_display","project","created","updated","due","due_flag","days_stale","comments_count"]
    hdrs = ["Key","Summary","Type","Status","Assignee","Priority","Label","Project","Created","Updated","Due","Due Flag","Stale","Comments"]
    return html.Div([
        C.section(f"{len(issues)} Issues"),
        dash_table.DataTable(
            id="items-tbl",
            data=[{h:i.get(c,"") for h,c in zip(hdrs,cols)} for i in issues],
            columns=[{"name":h,"id":h} for h in hdrs],
            page_size=50, filter_action="native", sort_action="native",
            style_table={"overflowX":"auto","borderRadius":"10px","border":f"1px solid {C.BORDER}"},
            style_cell={"background":C.SURFACE,"color":C.TEXT,"border":f"1px solid {C.BORDER}",
                        "fontSize":"0.74rem","padding":"8px 12px","fontFamily":"'DM Sans',sans-serif",
                        "textAlign":"left","maxWidth":"260px","overflow":"hidden","textOverflow":"ellipsis"},
            style_header={"background":C.ACCENT2,"fontWeight":"800","color":C.NAVY,
                          "border":f"1px solid {C.BORDER}","fontSize":"0.67rem","letterSpacing":"0.07em","textTransform":"uppercase"},
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
        closed=sum(1 for i in items if i["status"]=="Closed")
        overdue=sum(1 for i in items if "Past Due" in i["due_flag"])
        bugs=sum(1 for i in items if i["type"]=="Bug")
        panels.append(C.card(
            html.Div([html.Span(label,style={"fontWeight":"800","fontSize":"0.88rem","color":C.NAVY,"fontFamily":"JetBrains Mono,monospace"}),
                      html.Span(f" · {len(items)} issues",style={"color":C.MUTED,"fontSize":"0.72rem"})]),
            html.Div([C.kpi("Open",len(items)-closed,C.ACCENT),C.kpi("Closed",closed,C.GREEN),
                      C.kpi("Past Due",overdue,C.RED),C.kpi("Bugs",bugs,C.ORANGE)],
                     style={"display":"flex","gap":"8px","margin":"10px 0","flexWrap":"wrap"}),
            _g(CH.status_bar(items),f"l-{label[:15].replace(' ','-')}",h=170),
        ))
    return html.Div([C.section("By Initiative"),
                     html.Div(panels,style={"display":"grid","gridTemplateColumns":"repeat(auto-fill,minmax(400px,1fr))","gap":"14px"})])


def page_assignee(issues, _all):
    by_a = defaultdict(list)
    for i in issues: by_a[i["assignee"]].append(i)
    rows = []
    for a, items in sorted(by_a.items(), key=lambda x: -len(x[1])):
        by_lbl = defaultdict(list)
        for i in items:
            for l in (i["labels"] or ["(No Label)"]): by_lbl[l].append(i)
        closed=sum(1 for i in items if i["status"]=="Closed")
        overdue=sum(1 for i in items if "Past Due" in i["due_flag"])
        bugs=sum(1 for i in items if i["type"]=="Bug")
        open_items = [i for i in items if i["status"]!="Closed"]
        stale = round(sum(i["days_stale"] for i in open_items)/max(1,len(open_items)),1)
        lbl_str = " · ".join(f"{l}: {len(v)}" for l,v in sorted(by_lbl.items(), key=lambda x:-len(x[1]))[:5])
        rows.append(html.Div([
            html.Div(a, style={"fontWeight":"800","fontSize":"0.88rem","color":C.NAVY}),
            html.Div(lbl_str, style={"color":C.MUTED,"fontSize":"0.7rem","marginTop":"2px"}),
            html.Div([C.kpi("Open",len(items)-closed,C.ACCENT),C.kpi("Closed",closed,C.GREEN),
                      C.kpi("Past Due",overdue,C.RED),C.kpi("Bugs",bugs,C.ORANGE),
                      C.kpi("Avg Stale",f"{stale}d",C.MUTED)],
                     style={"display":"flex","gap":"8px","flexWrap":"wrap","marginTop":"10px"}),
        ], style={"background":C.SURFACE,"borderRadius":"10px","padding":"14px",
                  "border":f"1px solid {C.BORDER}","marginBottom":"8px","boxShadow":"0 1px 6px rgba(11,29,58,0.05)"}))
    return html.Div([
        C.grid(C.card(_g(CH.bubble_chart(issues),"a-b",h=360)),C.card(_g(CH.heatmap(issues),"a-h",h=360)),cols=2),
        C.card(_g(CH.assignee_stacked(issues,D.get_labels(issues)),"a-s",h=320)),
        C.section("Per Assignee Detail"), html.Div(rows),
    ])


def page_deps(issues, _all):
    # MRM-style: depth control + layout selector + inspect panel
    elements = C.cyto_elements(issues)
    link_types = sorted(set(l["type"] for i in issues for l in i["links"]))
    edge_legend = html.Div([
        html.Div([
            html.Span("──", style={"color":C.EDGE_COLORS.get(lt, "#94A3B8"),"fontWeight":"800","marginRight":"4px","fontFamily":"monospace"}),
            html.Span(lt, style={"fontSize":"0.65rem","color":C.MUTED}),
        ], style={"marginRight":"14px","display":"inline-flex","alignItems":"center"})
        for lt in link_types
    ], style={"marginBottom":"12px","padding":"8px 0","borderTop":f"1px solid {C.BORDER}","marginTop":"8px"})

    controls = html.Div([
        html.Div([
            html.Span("LAYOUT", style={"fontSize":"0.6rem","color":C.MUTED,"fontWeight":"700","marginRight":"8px","letterSpacing":"0.1em"}),
            dcc.Dropdown(id="dep-layout", value="cose", clearable=False,
                         options=[{"label":l,"value":l} for l in ["cose","breadthfirst","circle","concentric","grid"]],
                         style={"width":"140px","fontSize":"0.73rem"}),
        ], style={"display":"flex","alignItems":"center","gap":"8px"}),
    ], style={"marginBottom":"12px","display":"flex","gap":"16px","alignItems":"center"})

    return html.Div([
        C.section("Dependency Graph", f"{len(issues)} issues · {len(elements)//2} relationships · click node to inspect"),
        controls,
        html.Div([
            html.Div([
                cyto.Cytoscape(
                    id="cyto-graph", elements=elements,
                    layout={"name":"cose","animate":True,"animationDuration":500,"nodeRepulsion":4500},
                    style={"height":"580px","background":C.SURFACE,"borderRadius":"10px","border":f"1px solid {C.BORDER}"},
                    stylesheet=C.CYTO_STYLE, responsive=True,
                ),
                edge_legend,
            ], style={"flex":"1"}),
            html.Div(id="cyto-detail", children=[C.issue_drawer(None)], style={
                "width":"290px","background":C.SURFACE,"borderRadius":"10px",
                "border":f"1px solid {C.BORDER}","overflowY":"auto","maxHeight":"620px",
                "boxShadow":"0 2px 10px rgba(11,29,58,0.08)",
            }),
        ], style={"display":"flex","gap":"14px"}),
    ])


def page_matrix(issues, _all):
    return html.Div([
        C.section("Relationship Matrix", "Assignee × Label — click cell to drill down"),
        C.card(_g(CH.relationship_matrix(issues),"rm-main",h=420)),
        C.grid(
            C.card(_g(CH.heatmap(issues),"rm-heat",h=360)),
            C.card(_g(CH.assignee_stacked(issues,D.get_labels(issues)),"rm-stack",h=360)),
            cols=2
        ),
    ])


def page_workflow(issues, _all):
    ORDER = ["Groomed","To Do","Development In Progress","Code Review","Integration Testing","Fixing in Progress","Ready For QA Testing","QA Testing","Closed"]
    c = Counter(i["status"] for i in issues)
    avg_stale = defaultdict(list)
    for i in issues: avg_stale[i["status"]].append(i["days_stale"])

    gate_cards = []
    for s in ORDER:
        cnt = c.get(s,0)
        fg,bg = C.STATUS_CLR.get(s,(C.MUTED,C.BG))
        avg = round(sum(avg_stale[s])/len(avg_stale[s]),1) if avg_stale[s] else 0
        gate_cards.append(html.Div([
            html.Div(str(cnt), style={"fontSize":"1.8rem","fontWeight":"800","color":fg,"fontFamily":"JetBrains Mono,monospace"}),
            html.Div(s, style={"fontSize":"0.68rem","fontWeight":"700","color":fg,"marginTop":"4px"}),
            html.Div(f"avg {avg}d stale", style={"fontSize":"0.62rem","color":C.MUTED,"marginTop":"3px"}),
        ], style={"background":bg,"border":f"1px solid {fg}33","borderRadius":"8px",
                  "padding":"14px","textAlign":"center","minWidth":"100px",
                  "borderTop":f"3px solid {fg}"}))

    return html.Div([
        C.section("Workflow Gate Analysis", "Issue volume and staleness at each pipeline stage"),
        html.Div(gate_cards, style={"display":"flex","gap":"10px","flexWrap":"wrap","marginBottom":"20px"}),
        C.card(_g(CH.workflow_funnel(issues),"wf-main",h=340)),
        C.grid(
            C.card(_g(CH.velocity_line(issues),"wf-vel",h=280)),
            C.card(_g(CH.status_bar(issues),"wf-s",h=280)),
            cols=2
        ),
    ])


def page_timeline(issues, _all):
    from datetime import date, timedelta
    today = date.today()
    dated = sorted([i for i in issues if i["due"]], key=lambda x: x["due"])
    if not dated: return html.Div("No issues with Due Date set.", style={"color":C.MUTED,"padding":"40px","textAlign":"center"})
    fig = go.Figure()
    for i in dated:
        start = i.get("created", str(today-timedelta(days=7)))
        fig.add_trace(go.Bar(
            x=[i["due"]], y=[f"{i['assignee'][:12]} / {i['key']}"],
            orientation="h", marker_color=C.sc_bg(i["status"]), marker_line_color=C.sc(i["status"]), marker_line_width=2, width=0.6,
            hovertemplate=f"<b>{i['key']}</b><br>{i['summary'][:60]}<br>{i['status']}<br>Due: {i['due']}<extra></extra>",
            showlegend=False, base=[start],
        ))
    fig.update_layout(paper_bgcolor=C.SURFACE,plot_bgcolor=C.SURFACE,font=dict(color=C.TEXT,size=10,family="JetBrains Mono,monospace"),
                      margin=dict(l=8,r=8,t=36,b=8),height=max(400,len(dated)*20),barmode="overlay",
                      title=dict(text="Delivery Timeline",font=dict(size=11,color=C.NAVY2,weight="bold")),
                      xaxis=dict(gridcolor=C.BORDER),yaxis=dict(gridcolor=C.BORDER))
    return html.Div([C.section(f"Timeline — {len(dated)} issues with Due Date"), dcc.Graph(figure=fig,config={"displayModeBar":False})])


def page_alerts(issues, _all):
    def _tbl(title, rows, color=C.RED):
        if not rows: return html.Div()
        return C.card(
            html.Div(f"{title}  ·  {len(rows)}", style={"fontSize":"0.62rem","fontWeight":"800","color":color,"letterSpacing":"0.12em","textTransform":"uppercase","marginBottom":"10px"}),
            html.Table([
                html.Thead(html.Tr([html.Th(h) for h in ["Key","Assignee","Status","Priority","Detail"]], style={"background":C.ACCENT2})),
                html.Tbody([html.Tr([
                    html.Td(html.A(r["key"],href=r["url"],target="_blank",style={"color":C.ACCENT,"textDecoration":"none","fontWeight":"700","fontFamily":"JetBrains Mono,monospace","fontSize":"0.72rem"})),
                    html.Td(r["assignee"],style={"color":C.TEXT}),
                    html.Td(C.status_badge(r["status"])),
                    html.Td(r["priority"],style={"color":C.pc(r["priority"]),"fontWeight":"700","fontSize":"0.72rem"}),
                    html.Td(r.get("_detail",""),style={"color":C.MUTED,"fontSize":"0.71rem"}),
                ], style={"background":C.SURFACE if ri%2==0 else C.BG}) for ri,r in enumerate(rows)]),
            ], style={"width":"100%","borderCollapse":"collapse","fontSize":"0.75rem"}),
            style={"marginBottom":"12px"},
        )

    past_due=[i for i in issues if "Past Due" in i["due_flag"] and i["status"]!="Closed"]
    no_act=[i for i in issues if i["days_stale"]>7 and i["status"] not in ("Closed","Rejected")]
    unassigned=[i for i in issues if i["assignee"]=="Unassigned" and i["status"]!="Closed"]
    crit_bugs=[i for i in issues if i["type"]=="Bug" and i["priority"] in ("Highest","High") and i["status"]!="Closed"]
    no_label=[i for i in issues if not i["labels"] and i["status"]!="Closed"]
    for i in past_due: i["_detail"]=i["due_flag"]
    for i in no_act: i["_detail"]=f"No update {i['days_stale']}d"
    for i in crit_bugs: i["_detail"]=f"{i['priority']} Bug"

    return html.Div([
        html.Div([C.kpi("Past Due",len(past_due),C.RED),C.kpi("No Activity >7d",len(no_act),C.ORANGE),
                  C.kpi("Unassigned",len(unassigned),C.MUTED),C.kpi("High Bugs",len(crit_bugs),"#DC2626"),
                  C.kpi("No Label",len(no_label),C.MUTED)],
                 style={"display":"flex","gap":"10px","flexWrap":"wrap","marginBottom":"20px"}),
        _tbl("Past Due Date", past_due, C.RED),
        _tbl("No Activity >7 Days", no_act, C.ORANGE),
        _tbl("Unassigned", unassigned, C.MUTED),
        _tbl("High / Highest Bugs Open", crit_bugs, "#DC2626"),
        _tbl("No Label", no_label, C.MUTED),
    ])


def page_settings(issues, _all):
    return html.Div([
        C.section("Configuration"),
        C.card(html.Div("Tracked Labels",style={"color":C.MUTED,"fontSize":"0.62rem","fontWeight":"700","letterSpacing":"0.1em","textTransform":"uppercase","marginBottom":"10px"}),
               html.Div([html.Span(l,style={"background":C.ACCENT2,"color":C.ACCENT,"borderRadius":"4px","padding":"3px 10px","fontSize":"0.72rem","fontWeight":"700","marginRight":"6px","marginBottom":"6px","display":"inline-block","border":f"1px solid {C.ACCENT}33","fontFamily":"JetBrains Mono,monospace"}) for l in D.get_labels(issues)])),
        C.card(*[html.Div([
            html.Span(k,style={"color":C.MUTED,"width":"160px","display":"inline-block","fontSize":"0.72rem","fontWeight":"700"}),
            html.Span(v,style={"color":C.TEXT,"fontSize":"0.76rem","fontFamily":"JetBrains Mono,monospace"}),
        ], style={"marginBottom":"8px"}) for k,v in [
            ("Jira URL",D.BASE_URL),("Projects",", ".join(D.PROJECTS)),
            ("Auto-refresh","Every 10 minutes"),("Max Issues",str(D.MAX_ISSUES)),
            ("Days Back",str(D.DAYS_BACK)),("Loaded",str(len(issues))),
        ]]),
    ])


@app.callback(Output("cyto-detail","children"), Input("cyto-graph","tapNodeData"), State("store-issues","data"))
def cyto_click(node, issues):
    if not node or not issues: return C.issue_drawer(None)
    hit = next((i for i in issues if i["key"]==node["id"]), None)
    return C.issue_drawer(hit)

@app.callback(Output("cyto-graph","layout"), Input("dep-layout","value"))
def cyto_layout(val): return {"name":val,"animate":True,"nodeRepulsion":4500}


app.index_string = '''<!DOCTYPE html>
<html>
<head>
{%metas%}<title>{%title%}</title>{%favicon%}{%css%}
<link href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;500;600;700;800&family=DM+Sans:wght@400;500;600;700;800&display=swap" rel="stylesheet">
<style>
*{box-sizing:border-box;margin:0;padding:0}
body{background:#F0F4FF}
::-webkit-scrollbar{width:5px;height:5px}
::-webkit-scrollbar-track{background:#F0F4FF}
::-webkit-scrollbar-thumb{background:#D4DFFF;border-radius:3px}
::-webkit-scrollbar-thumb:hover{background:#2563EB55}
table th{padding:9px 12px;text-align:left;font-size:0.67rem;letter-spacing:0.08em;text-transform:uppercase;color:#5A6E99;font-weight:800}
table td{padding:8px 12px;border-bottom:1px solid #D4DFFF}
table tr:hover td{background:#EEF4FF55!important}
a:hover{opacity:0.8}
nav a:hover{color:#7EA8E8!important;border-left-color:#2563EB!important;background:#1E356022}
</style>
</head>
<body>{%app_entry%}<footer>{%config%}{%scripts%}{%renderer%}</footer></body>
</html>'''

if __name__ == "__main__":
    app.run(debug=False, host="0.0.0.0", port=8050)
