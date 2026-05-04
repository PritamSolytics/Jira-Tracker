import dash
from dash import dcc, html, Input, Output, State, callback_context, dash_table
import dash_cytoscape as cyto
import plotly.graph_objects as go
from collections import Counter, defaultdict
from datetime import date, timedelta
import threading, math


def accordion(title, children, id_key, default_open=True):
    """Expandable section with click-to-toggle."""
    return html.Div([
        html.Div([
            html.Span(title, style={"fontWeight":"800","fontSize":"0.78rem","color":C.NAVY,"letterSpacing":"0.04em","textTransform":"uppercase"}),
            html.Span("▲" if default_open else "▼", id=f"acc-icon-{id_key}",
                      style={"color":C.MUTED,"fontSize":"0.7rem","marginLeft":"8px","transition":"transform 0.2s"}),
        ], id=f"acc-hdr-{id_key}", style={
            "display":"flex","alignItems":"center","justifyContent":"space-between",
            "padding":"10px 14px","background":C.ACCENT2,"borderRadius":"8px",
            "cursor":"pointer","border":f"1px solid {C.BORDER}","marginTop":"16px",
            "userSelect":"none",
        }),
        html.Div(children, id=f"acc-body-{id_key}", style={
            "display":"block" if default_open else "none",
            "marginTop":"8px","transition":"all 0.2s",
        }),
    ])


import data as D
import components as C
import charts as CH
import store as ST
import standup_page as SL

cyto.load_extra_layouts()
app = dash.Dash(__name__, suppress_callback_exceptions=True,
                meta_tags=[{"name":"viewport","content":"width=device-width,initial-scale=1"}])
app.title = "Jira Operations"
server = app.server
threading.Thread(target=D.get_issues, daemon=True).start()

# ── Health score calculator ────────────────────────────────────
def calc_health(issues):
    if not issues: return 100
    open_i = [i for i in issues if i["status"] != "Closed"]
    if not open_i: return 100
    overdue_pct  = sum(1 for i in open_i if "Past Due" in i["due_flag"]) / len(open_i)
    stale_pct    = sum(1 for i in open_i if i["days_stale"] > 7) / len(open_i)
    bug_pct      = sum(1 for i in issues if i["type"] == "Bug") / len(issues)
    unassign_pct = sum(1 for i in open_i if i["assignee"] == "Unassigned") / len(open_i)
    score = 100 - (overdue_pct*40 + stale_pct*25 + bug_pct*20 + unassign_pct*15)
    return max(0, min(100, round(score)))

# ── At-risk score ──────────────────────────────────────────────
def at_risk_score(i):
    score = 0
    if "Past Due" in i["due_flag"]: score += 40
    if i["days_stale"] > 7: score += 20
    if i["type"] == "Bug": score += 15
    if i["priority"] in ("Highest","High"): score += 15
    if i["assignee"] == "Unassigned": score += 10
    return score

# ── Nav ────────────────────────────────────────────────────────
NAV_GROUPS = {
    "COMMAND":   [("Command Centre","/")],
    "PEOPLE":    [("People Intelligence","/people")],
    "INITIATIVE":[("Initiative Health","/initiatives")],
    "WORK":      [("Work Items","/items"),("Timeline","/timeline")],
    "STRUCTURE": [("Dependency Graph","/dependencies"),("Workflow Gates","/workflow")],
    "STANDUP":  [("Standup Log","/standup")],
    "OPERATIONS":[("Alerts","/alerts"),("Settings","/settings")],
}

def sidebar():
    items = [html.Div([
        html.Div("JIRA",style={"fontSize":"1.1rem","fontWeight":"900","color":"#FFFFFF","letterSpacing":"0.1em"}),
        html.Div("OPERATIONS CENTRE",style={"fontSize":"0.52rem","fontWeight":"700","color":"#4A6898","letterSpacing":"0.12em","marginTop":"2px"}),
        html.Div("Solytics Partners",style={"fontSize":"0.6rem","color":"#3A5080","marginTop":"6px"}),
    ],style={"padding":"22px 18px 16px","borderBottom":"1px solid #1E3560"}),
    html.Div(id="nav-sync",style={"padding":"6px 18px","fontSize":"0.6rem","color":"#3A5080","borderBottom":"1px solid #152845"})]
    for group, links in NAV_GROUPS.items():
        items.append(html.Div(group,style={"fontSize":"0.5rem","fontWeight":"800","letterSpacing":"0.18em","color":"#2A4570","padding":"14px 18px 4px","textTransform":"uppercase"}))
        for label,href in links:
            items.append(dcc.Link(label,href=href,style={"display":"block","padding":"8px 18px","color":"#8AA0CC","textDecoration":"none","fontSize":"0.75rem","fontWeight":"600","letterSpacing":"0.02em","borderLeft":"3px solid transparent","transition":"all 0.12s"}))
    return html.Nav(items,style={"width":"200px","minHeight":"100vh","background":C.NAVY,"flexShrink":"0","position":"sticky","top":"0","overflowY":"auto"})

def dd(id,ph,opts=None):
    return dcc.Dropdown(id=id,placeholder=ph,multi=True,clearable=True,options=opts or [],
                        style={"minWidth":"130px","fontSize":"0.74rem","border":f"1px solid {C.BORDER}","borderRadius":"6px"})

TOPBAR = html.Div([
    html.Div(id="page-title",style={"fontWeight":"800","fontSize":"0.82rem","color":C.NAVY,"letterSpacing":"0.06em","textTransform":"uppercase"}),
    html.Div([
        dd("g-project","Project"), dd("g-label","Label"), dd("g-assignee","Assignee"),
        dd("g-type","Type",[{"label":t,"value":t} for t in ["Task","Story","Bug","Sub-task","Epic"]]),
        dd("g-status","Status",[{"label":s,"value":s} for s in C.STATUS_CLR]),
        html.Button("↻  Refresh",id="btn-refresh",n_clicks=0,style={"background":C.NAVY,"color":"#fff","border":"none","borderRadius":"6px","padding":"8px 14px","cursor":"pointer","fontSize":"0.73rem","fontWeight":"700"}),
    ],style={"display":"flex","gap":"8px","flexWrap":"wrap","alignItems":"center"}),
],style={"display":"flex","justifyContent":"space-between","alignItems":"center","flexWrap":"wrap","gap":"12px","padding":"11px 22px","borderBottom":f"1px solid {C.BORDER}","background":C.SURFACE,"position":"sticky","top":"0","zIndex":"100","boxShadow":"0 2px 6px rgba(11,29,58,0.07)"})

app.layout = html.Div([
    dcc.Location(id="url"),
    dcc.Store(id="store-issues"),
    dcc.Interval(id="auto-refresh",interval=600_000,n_intervals=0),
    dcc.Interval(id="init-refresh",interval=4000,n_intervals=0,max_intervals=8),
    html.Div([sidebar(),html.Div([TOPBAR,html.Div(id="page-content",style={"padding":"18px 22px","flex":"1","background":C.BG})],
             style={"flex":"1","display":"flex","flexDirection":"column"})],
             style={"display":"flex","minHeight":"100vh"}),
],style={"fontFamily":"'DM Sans','Segoe UI',sans-serif"})

@app.callback(
    Output("store-issues","data"),Output("nav-sync","children"),
    Output("g-label","options"),Output("g-assignee","options"),Output("g-project","options"),
    Input("btn-refresh","n_clicks"),Input("auto-refresh","n_intervals"),Input("init-refresh","n_intervals"),
)
def load_data(n,_,init):
    force = callback_context.triggered_id=="btn-refresh"
    issues = D.get_issues(force=force)
    if not issues: return [],"Connecting...",[],[],[]
    return (issues, f"↻ {D.last_sync()} · {len(issues)} issues",
            [{"label":l,"value":l} for l in D.get_labels(issues)],
            [{"label":a,"value":a} for a in D.get_assignees(issues)],
            [{"label":p,"value":p} for p in D.get_projects(issues)])

def filt(issues,labels,assignees,types,statuses,projects):
    r=issues
    if projects:  r=[i for i in r if i["project"] in projects]
    if labels:    r=[i for i in r if any(l in i["labels"] for l in labels)]
    if assignees: r=[i for i in r if i["assignee"] in assignees]
    if types:     r=[i for i in r if i["type"] in types]
    if statuses:  r=[i for i in r if i["status"] in statuses]
    return r

@app.callback(
    Output("page-content","children"),Output("page-title","children"),
    Input("url","pathname"),Input("store-issues","data"),
    Input("g-label","value"),Input("g-assignee","value"),
    Input("g-type","value"),Input("g-status","value"),Input("g-project","value"),
)
def route(path,issues,labels,assignees,types,statuses,projects):
    if not issues:
        return html.Div([html.Div("◎",style={"fontSize":"3rem","color":C.ACCENT,"marginBottom":"12px"}),
                         html.Div("Connecting to Jira...",style={"fontWeight":"800","color":C.NAVY,"fontSize":"1rem"}),
                         html.Div("Auto-refreshes every 10 minutes.",style={"color":C.MUTED,"fontSize":"0.78rem","marginTop":"6px"})],
                        style={"padding":"80px","textAlign":"center"}),""
    f=filt(issues,labels or [],assignees or [],types or [],statuses or [],projects or [])
    pages={
        "/":            (page_command,      "Command Centre"),
        "/people":      (page_people,       "People Intelligence"),
        "/initiatives": (page_initiatives,  "Initiative Health"),
        "/items":       (page_items,        "Work Items"),
        "/dependencies":(page_deps,         "Dependency Graph"),
        "/workflow":    (page_workflow,      "Workflow Gates"),
        "/timeline":    (page_timeline,     "Timeline"),
        "/alerts":      (page_alerts,       "Alerts"),
        "/settings":    (page_settings,     "Settings"),
    }
    fn,title=pages.get(path,pages["/"])
    return fn(f,issues),title

def _g(fig,id,h=300): return dcc.Graph(figure=fig,id=id,style={"height":f"{h}px"},config={"displayModeBar":False})

# ══════════════════════════════════════════════════════════════
# PAGE 1: COMMAND CENTRE
# ══════════════════════════════════════════════════════════════
def page_command(issues, all_issues):
    today = date.today()
    next_fri = today + timedelta(days=(4-today.weekday())%7 or 7)

    # Health scores per label
    by_label = defaultdict(list)
    for i in issues:
        for l in (i["labels"] or ["(No Label)"]): by_label[l].append(i)
    top_labels = sorted(by_label, key=lambda l: -len(by_label[l]))[:4]

    health_row = html.Div([
        C.health_score("Overall", calc_health(issues), len(issues)),
        *[C.health_score(l, calc_health(by_label[l]), len(by_label[l])) for l in top_labels[:3]],
    ],style={"display":"flex","gap":"12px","flexWrap":"wrap"})

    # At-risk top 10
    open_issues = [i for i in issues if i["status"] not in ("Closed","Rejected")]
    at_risk = sorted(open_issues, key=at_risk_score, reverse=True)[:10]
    risk_rows = html.Div([
        html.Div([
            html.Div([
                html.Span(f"{at_risk_score(i)}",style={"background":C.RED if at_risk_score(i)>=60 else (C.ORANGE if at_risk_score(i)>=30 else C.AMBER),"color":"#fff","borderRadius":"4px","padding":"1px 6px","fontSize":"0.65rem","fontWeight":"800","marginRight":"8px","fontFamily":"JetBrains Mono,monospace"}),
                html.A(i["key"],href=i["url"],target="_blank",style={"color":C.ACCENT,"fontWeight":"700","fontSize":"0.73rem","textDecoration":"none","marginRight":"8px","fontFamily":"JetBrains Mono,monospace"}),
                html.Span(i["summary"][:55]+"…" if len(i["summary"])>55 else i["summary"],style={"color":C.TEXT,"fontSize":"0.74rem"}),
            ],style={"flex":"1"}),
            html.Div([
                C.status_badge(i["status"]),
                html.Span(i["assignee"],style={"color":C.MUTED,"fontSize":"0.68rem","marginLeft":"8px"}),
            ]),
        ],style={"display":"flex","alignItems":"center","justifyContent":"space-between","padding":"8px 0","borderBottom":f"1px solid {C.BORDER}","gap":"8px","flexWrap":"wrap"})
        for i in at_risk
    ])

    # Blocker chains
    blocking_map = defaultdict(list)
    for i in issues:
        for lnk in i["links"]:
            if "block" in lnk["type"].lower() and lnk["direction"]=="outward":
                blocking_map[i["key"]].append(lnk["key"])
    key_map = {i["key"]:i for i in issues}
    blockers = [(k,v) for k,v in blocking_map.items() if len(v)>=1]
    blockers.sort(key=lambda x: -len(x[1]))

    blocker_rows = html.Div([
        html.Div([
            html.Div([
                html.Span(f"🔴 blocks {len(blocked)}",style={"background":"#FEF2F2","color":C.RED,"borderRadius":"4px","padding":"2px 8px","fontSize":"0.65rem","fontWeight":"800","marginRight":"8px"}),
                html.A(key,href=f"{D.BASE_URL}/browse/{key}",target="_blank",style={"color":C.NAVY,"fontWeight":"700","fontSize":"0.73rem","textDecoration":"none","marginRight":"6px","fontFamily":"JetBrains Mono,monospace"}),
                html.Span(key_map[key]["assignee"] if key in key_map else "—",style={"color":C.MUTED,"fontSize":"0.68rem"}),
            ]),
            html.Div("→ " + ", ".join(blocked[:4]),style={"color":C.MUTED,"fontSize":"0.68rem","fontFamily":"JetBrains Mono,monospace","marginTop":"2px"}),
        ],style={"padding":"8px 0","borderBottom":f"1px solid {C.BORDER}"})
        for key,blocked in blockers[:8] if key in key_map
    ]) if blockers else html.Div("No blocking relationships found.",style={"color":C.MUTED,"fontSize":"0.78rem","padding":"12px 0"})

    # Due this week by assignee
    due_week = [i for i in issues if i["due"] and date.fromisoformat(i["due"]) <= next_fri and i["status"] not in ("Closed","Rejected")]
    by_assignee_due = defaultdict(list)
    for i in due_week: by_assignee_due[i["assignee"]].append(i)
    due_panel = html.Div([
        html.Div([
            html.Div(a,style={"fontWeight":"700","fontSize":"0.74rem","color":C.NAVY,"marginBottom":"4px"}),
            *[html.Div([
                html.A(i["key"],href=i["url"],target="_blank",style={"color":C.ACCENT,"fontSize":"0.68rem","fontWeight":"700","textDecoration":"none","marginRight":"6px","fontFamily":"JetBrains Mono,monospace"}),
                C.status_badge(i["status"]),
                html.Span(i["due"],style={"color":C.RED if i["due_flag"].startswith("Past") else C.AMBER,"fontSize":"0.66rem","marginLeft":"6px"}),
            ],style={"marginBottom":"4px"}) for i in sorted(items,key=lambda x:x["due"])[:3]],
        ],style={"padding":"8px 0","borderBottom":f"1px solid {C.BORDER}"})
        for a,items in sorted(by_assignee_due.items(),key=lambda x:-len(x[1]))[:8]
    ]) if due_week else html.Div("Nothing due this week.",style={"color":C.MUTED,"fontSize":"0.78rem"})

    # KPI strip
    closed=sum(1 for i in issues if i["status"]=="Closed")
    overdue=sum(1 for i in issues if "Past Due" in i["due_flag"])
    kpi_strip=html.Div([
        C.kpi("Total",len(issues),C.NAVY),C.kpi("Closed",closed,C.GREEN,f"{round(closed/max(1,len(issues))*100,1)}%"),
        C.kpi("Past Due",overdue,C.RED),C.kpi("Bugs",sum(1 for i in issues if i["type"]=="Bug"),C.ORANGE),
        C.kpi("In Dev",sum(1 for i in issues if i["status"]=="Development In Progress"),C.AMBER),
        C.kpi("In QA",sum(1 for i in issues if "QA" in i["status"]),C.PURPLE),
        C.kpi("Blockers",len(blockers),C.RED),C.kpi("Stale >7d",sum(1 for i in open_issues if i["days_stale"]>7),C.MUTED),
    ],style={"display":"flex","gap":"10px","flexWrap":"wrap","marginBottom":"16px"})

    return html.Div([
        kpi_strip, health_row,
        html.Div([
            html.Div([
                accordion("⚠ At Risk — Top 10 Issues", C.card(risk_rows,pad="12px"), "atrisk", True),
                accordion("🔴 Blocker Chains — Resolve These First", C.card(blocker_rows,pad="12px"), "blockers", True),
            ],style={"flex":"1","minWidth":"0"}),
            html.Div([
                accordion(f"📅 Due This Week — by {next_fri.strftime('%d %b')}", C.card(due_panel,pad="12px"), "dueweek", True),
            ],style={"width":"320px","flexShrink":"0"}),
        ],style={"display":"flex","gap":"16px","marginTop":"8px","alignItems":"flex-start"}),
    ])


# ══════════════════════════════════════════════════════════════
# PAGE 2: PEOPLE INTELLIGENCE
# ══════════════════════════════════════════════════════════════
def page_people(issues, all_issues):
    by_a = defaultdict(list)
    for i in issues: by_a[i["assignee"]].append(i)

    # Bottleneck score = issues this person's work is blocking
    blocking_map = defaultdict(int)
    key_map = {i["key"]:i for i in issues}
    for i in issues:
        for lnk in i["links"]:
            if "block" in lnk["type"].lower() and lnk["direction"]=="outward":
                blocking_map[i["assignee"]] += 1

    cards = []
    for a, items in sorted(by_a.items(),key=lambda x:-len(x[1])):
        open_i=[i for i in items if i["status"]!="Closed"]
        closed=len(items)-len(open_i)
        overdue=sum(1 for i in open_i if "Past Due" in i["due_flag"])
        bugs=sum(1 for i in items if i["type"]=="Bug")
        stale=sum(1 for i in open_i if i["days_stale"]>7)
        avg_stale=round(sum(i["days_stale"] for i in open_i)/max(1,len(open_i)),1)
        bottleneck=blocking_map.get(a,0)
        tl=C.traffic_light(overdue,len(open_i))

        # Label breakdown
        lbl_c=Counter(l for i in items for l in (i["labels"] or ["(No Label)"]))
        lbl_str=" · ".join(f"{l}:{c}" for l,c in lbl_c.most_common(4))

        capacity = len(open_i)<3
        card_border = C.GREEN if capacity else (C.RED if overdue>2 else C.BORDER)

        # Status breakdown mini
        status_c=Counter(i["status"] for i in open_i)
        status_pills=html.Div([html.Span(f"{s[:8]}·{c}",style={"background":C.sc_bg(s),"color":C.sc(s),"borderRadius":"3px","padding":"1px 6px","fontSize":"0.6rem","fontWeight":"700","marginRight":"4px","marginBottom":"3px","display":"inline-block"}) for s,c in status_c.most_common(5)],style={"marginTop":"6px","flexWrap":"wrap","display":"flex"})

        cards.append(html.Div([
            html.Div([
                html.Div([
                    html.Span(tl,style={"fontSize":"1.2rem","marginRight":"8px"}),
                    html.Span(a,style={"fontWeight":"800","fontSize":"0.88rem","color":C.NAVY}),
                    html.Span(" AVAILABLE",style={"background":"#F0FDF4","color":C.GREEN,"borderRadius":"3px","padding":"1px 6px","fontSize":"0.6rem","fontWeight":"800","marginLeft":"8px"}) if capacity else None,
                    html.Span(f"⚠ {bottleneck} blocking",style={"background":"#FEF2F2","color":C.RED,"borderRadius":"3px","padding":"1px 6px","fontSize":"0.6rem","fontWeight":"800","marginLeft":"8px"}) if bottleneck else None,
                ],style={"display":"flex","alignItems":"center"}),
                html.Div(lbl_str,style={"color":C.MUTED,"fontSize":"0.68rem","marginTop":"3px"}),
            ]),
            html.Div([
                C.kpi("Open",len(open_i),C.ACCENT),C.kpi("Closed",closed,C.GREEN),
                C.kpi("Past Due",overdue,C.RED),C.kpi("Bugs",bugs,C.ORANGE),
                C.kpi("Stale>7d",stale,C.MUTED),C.kpi("Avg Stale",f"{avg_stale}d",C.MUTED),
            ],style={"display":"flex","gap":"8px","flexWrap":"wrap","marginTop":"10px"}),
            status_pills,
        ],style={"background":C.SURFACE,"borderRadius":"10px","padding":"14px","border":f"1px solid {card_border}","marginBottom":"8px","boxShadow":"0 1px 6px rgba(11,29,58,0.05)","borderLeft":f"4px solid {card_border}"}))

    return html.Div([
        accordion("📊 Charts — Load vs Staleness & Status Heatmap",
            C.grid(_g(CH.bubble_chart(issues),"p-b",380), _g(CH.heatmap(issues),"p-h",380), cols=2),
            "p-charts", True),
        accordion("📦 Assignee Load by Label",
            C.card(_g(CH.assignee_stacked(issues,D.get_labels(issues)),"p-s",320)),
            "p-stack", False),
        accordion("👤 Individual Load — 🟢 Available (<3 open) · 🟡 Moderate · 🔴 Overloaded",
            html.Div(cards), "p-cards", True),
    ])


# ══════════════════════════════════════════════════════════════
# PAGE 3: INITIATIVE HEALTH
# ══════════════════════════════════════════════════════════════
def page_initiatives(issues, all_issues):
    by_label=defaultdict(list)
    for i in issues:
        for l in (i["labels"] or ["(No Label)"]): by_label[l].append(i)

    panels=[]
    for label,items in sorted(by_label.items(),key=lambda x:-len(x[1])):
        score=calc_health(items)
        color=C.GREEN if score>=70 else (C.AMBER if score>=40 else C.RED)
        open_i=[i for i in items if i["status"]!="Closed"]
        overdue=sum(1 for i in open_i if "Past Due" in i["due_flag"])
        bugs=sum(1 for i in items if i["type"]=="Bug")
        stale=sum(1 for i in open_i if i["days_stale"]>7)
        closed=len(items)-len(open_i)
        unassigned=sum(1 for i in open_i if i["assignee"]=="Unassigned")
        top_assignees=Counter(i["assignee"] for i in open_i).most_common(3)
        assignee_str=", ".join(f"{a}({c})" for a,c in top_assignees)

        # Score breakdown bar
        breakdown=html.Div([
            html.Div(style={"width":f"{score}%","height":"6px","background":color,"borderRadius":"3px","transition":"width 0.3s"}),
        ],style={"background":C.BORDER,"borderRadius":"3px","overflow":"hidden","marginBottom":"10px"})

        panels.append(html.Div([
            html.Div([
                html.Div([
                    html.Span(f"{score}",style={"fontSize":"2rem","fontWeight":"900","color":color,"fontFamily":"JetBrains Mono,monospace","lineHeight":"1"}),
                    html.Span("/100",style={"fontSize":"0.7rem","color":C.MUTED,"marginLeft":"2px"}),
                ],style={"display":"flex","alignItems":"flex-end","gap":"2px"}),
                html.Div(label,style={"fontWeight":"800","fontSize":"0.85rem","color":C.NAVY,"marginTop":"4px","fontFamily":"JetBrains Mono,monospace"}),
                html.Div(f"{len(items)} issues",style={"fontSize":"0.68rem","color":C.MUTED}),
            ]),
            breakdown,
            html.Div([
                C.kpi("Open",len(open_i),C.ACCENT),C.kpi("Closed",closed,C.GREEN),
                C.kpi("Overdue",overdue,C.RED),C.kpi("Bugs",bugs,C.ORANGE),
                C.kpi("Stale",stale,C.MUTED),C.kpi("Unassigned",unassigned,C.MUTED),
            ],style={"display":"flex","gap":"6px","flexWrap":"wrap","marginBottom":"8px"}),
            html.Div([
                html.Span("Top assignees: ",style={"color":C.MUTED,"fontSize":"0.67rem","fontWeight":"600"}),
                html.Span(assignee_str or "—",style={"color":C.TEXT,"fontSize":"0.67rem"}),
            ]),
            _g(CH.status_bar(items),f"init-{label[:12].replace(' ','-')}",h=160),
        ],style={"background":C.SURFACE,"borderRadius":"12px","padding":"16px","border":f"1px solid {color}33",
                 "borderTop":f"3px solid {color}","boxShadow":f"0 2px 10px {color}15"}))

    return html.Div([
        C.section("Initiative Health","Health score = 100 − (overdue%×40 + stale%×25 + bug%×20 + unassigned%×15)"),
        accordion("🏷 All Initiatives",
            html.Div(panels,style={"display":"grid","gridTemplateColumns":"repeat(auto-fill,minmax(380px,1fr))","gap":"14px"}),
            "initiatives", True),
    ])


# ══════════════════════════════════════════════════════════════
# REMAINING PAGES
# ══════════════════════════════════════════════════════════════
def page_items(issues,_):
    cols=["key","summary","type","status","assignee","priority","label_display","project","created","updated","due","due_flag","days_stale","comments_count"]
    hdrs=["Key","Summary","Type","Status","Assignee","Priority","Label","Project","Created","Updated","Due","Due Flag","Stale","Comments"]
    return html.Div([C.section(f"{len(issues)} Issues"),
        dash_table.DataTable(id="items-tbl",
            data=[{h:i.get(c,"") for h,c in zip(hdrs,cols)} for i in issues],
            columns=[{"name":h,"id":h} for h in hdrs],
            page_size=50,filter_action="native",sort_action="native",
            style_table={"overflowX":"auto","borderRadius":"10px","border":f"1px solid {C.BORDER}"},
            style_cell={"background":C.SURFACE,"color":C.TEXT,"border":f"1px solid {C.BORDER}","fontSize":"0.74rem","padding":"8px 12px","fontFamily":"'DM Sans',sans-serif","textAlign":"left","maxWidth":"260px","overflow":"hidden","textOverflow":"ellipsis"},
            style_header={"background":C.ACCENT2,"fontWeight":"800","color":C.NAVY,"border":f"1px solid {C.BORDER}","fontSize":"0.67rem","letterSpacing":"0.07em","textTransform":"uppercase"},
            style_data_conditional=[
                {"if":{"filter_query":"{Due Flag} contains 'Past Due'"},"color":C.RED,"fontWeight":"700"},
                {"if":{"filter_query":"{Type} = 'Bug'"},"color":C.ORANGE},
                {"if":{"row_index":"odd"},"backgroundColor":C.BG},
            ])])

def page_deps(issues,_):
    elements=C.cyto_elements(issues)
    link_types=sorted(set(l["type"] for i in issues for l in i["links"]))
    legend=html.Div([html.Div([
        html.Span("─",style={"color":C.edge_color(lt),"fontWeight":"900","marginRight":"4px","fontSize":"1rem"}),
        html.Span(lt,style={"fontSize":"0.64rem","color":C.MUTED}),
    ],style={"marginRight":"14px","display":"inline-flex","alignItems":"center"}) for lt in link_types],
    style={"padding":"8px 0","borderTop":f"1px solid {C.BORDER}","marginTop":"8px"})
    return html.Div([
        C.section("Dependency Graph",f"{len(issues)} issues · Blocks=🔴 thick · Relates=🔵 · shapes: Story=hexagon, Bug=diamond"),
        html.Div([
            dcc.Dropdown(id="dep-layout",value="cose",clearable=False,
                         options=[{"label":l,"value":l} for l in ["cose","breadthfirst","circle","concentric","grid"]],
                         style={"width":"160px","fontSize":"0.73rem"}),
        ],style={"marginBottom":"12px"}),
        html.Div([
            html.Div([cyto.Cytoscape(id="cyto-graph",elements=elements,layout={"name":"cose","animate":True,"animationDuration":500,"nodeRepulsion":5000},
                         style={"height":"560px","background":C.SURFACE,"borderRadius":"10px","border":f"1px solid {C.BORDER}"},
                         stylesheet=C.CYTO_STYLE,responsive=True),legend],style={"flex":"1"}),
            html.Div(id="cyto-detail",children=[C.issue_drawer(None)],style={"width":"280px","background":C.SURFACE,"borderRadius":"10px","border":f"1px solid {C.BORDER}","overflowY":"auto","maxHeight":"600px"}),
        ],style={"display":"flex","gap":"14px"}),
    ])

def page_workflow(issues,_):
    ORDER=["Groomed","To Do","Development In Progress","Code Review","Integration Testing","Fixing in Progress","Ready For QA Testing","QA Testing","Closed"]
    c=Counter(i["status"] for i in issues)
    avg_stale=defaultdict(list)
    for i in issues: avg_stale[i["status"]].append(i["days_stale"])
    gate_cards=[html.Div([
        html.Div(str(c.get(s,0)),style={"fontSize":"1.8rem","fontWeight":"800","color":C.sc(s),"fontFamily":"JetBrains Mono,monospace"}),
        html.Div(s,style={"fontSize":"0.65rem","fontWeight":"700","color":C.sc(s),"marginTop":"3px"}),
        html.Div(f"avg {round(sum(avg_stale[s])/max(1,len(avg_stale[s])),1)}d stale",style={"fontSize":"0.6rem","color":C.MUTED,"marginTop":"2px"}),
    ],style={"background":C.sc_bg(s),"border":f"1px solid {C.sc(s)}33","borderRadius":"8px","padding":"14px","textAlign":"center","minWidth":"100px","borderTop":f"3px solid {C.sc(s)}"})
    for s in ORDER]
    return html.Div([
        C.section("Workflow Gate Analysis","Issue volume and avg staleness at each pipeline stage"),
        html.Div(gate_cards,style={"display":"flex","gap":"10px","flexWrap":"wrap","marginBottom":"16px"}),
        C.card(_g(CH.workflow_funnel(issues),"wf-main",h=320)),
        C.grid(C.card(_g(CH.velocity_line(issues),"wf-vel",h=260)),C.card(_g(CH.status_bar(issues),"wf-s",h=260)),cols=2),
    ])

def page_timeline(issues,_):
    dated=sorted([i for i in issues if i["due"]],key=lambda x:x["due"])
    if not dated: return html.Div("No issues with Due Date.",style={"color":C.MUTED,"padding":"40px","textAlign":"center"})
    fig=go.Figure()
    for i in dated:
        start=i.get("created",str(date.today()-timedelta(days=7)))
        fig.add_trace(go.Bar(x=[i["due"]],y=[f"{i['assignee'][:12]}/{i['key']}"],orientation="h",
            marker_color=C.sc_bg(i["status"]),marker_line_color=C.sc(i["status"]),marker_line_width=2,width=0.6,
            hovertemplate=f"<b>{i['key']}</b><br>{i['summary'][:60]}<br>{i['status']}<br>Due:{i['due']}<extra></extra>",
            showlegend=False,base=[start]))
    fig.update_layout(paper_bgcolor=C.SURFACE,plot_bgcolor=C.SURFACE,font=dict(color=C.TEXT,size=10,family="JetBrains Mono,monospace"),
                      margin=dict(l=8,r=8,t=36,b=8),height=max(400,len(dated)*20),barmode="overlay",
                      title=dict(text="Delivery Timeline",font=dict(size=11,color=C.NAVY2,weight="bold")),
                      xaxis=dict(gridcolor=C.BORDER),yaxis=dict(gridcolor=C.BORDER))
    return html.Div([C.section(f"Timeline — {len(dated)} issues"),dcc.Graph(figure=fig,config={"displayModeBar":False})])

def page_alerts(issues,_):
    def _tbl(title,rows,color=C.RED):
        if not rows: return html.Div()
        return C.card(
            html.Div(f"{title}  ·  {len(rows)}",style={"fontSize":"0.62rem","fontWeight":"800","color":color,"letterSpacing":"0.12em","textTransform":"uppercase","marginBottom":"10px"}),
            html.Table([html.Thead(html.Tr([html.Th(h) for h in ["Key","Assignee","Status","Priority","Detail"]],style={"background":C.ACCENT2})),
                html.Tbody([html.Tr([
                    html.Td(html.A(r["key"],href=r["url"],target="_blank",style={"color":C.ACCENT,"textDecoration":"none","fontWeight":"700","fontFamily":"JetBrains Mono,monospace","fontSize":"0.72rem"})),
                    html.Td(r["assignee"]),html.Td(C.status_badge(r["status"])),
                    html.Td(r["priority"],style={"color":C.pc(r["priority"]),"fontWeight":"700","fontSize":"0.72rem"}),
                    html.Td(r.get("_detail",""),style={"color":C.MUTED,"fontSize":"0.71rem"}),
                ],style={"background":C.SURFACE if ri%2==0 else C.BG}) for ri,r in enumerate(rows)])],
                style={"width":"100%","borderCollapse":"collapse","fontSize":"0.75rem"}),
            style={"marginBottom":"12px"})
    past_due=[i for i in issues if "Past Due" in i["due_flag"] and i["status"]!="Closed"]
    no_act=[i for i in issues if i["days_stale"]>7 and i["status"] not in ("Closed","Rejected")]
    unassigned=[i for i in issues if i["assignee"]=="Unassigned" and i["status"]!="Closed"]
    crit_bugs=[i for i in issues if i["type"]=="Bug" and i["priority"] in ("Highest","High") and i["status"]!="Closed"]
    for i in past_due: i["_detail"]=i["due_flag"]
    for i in no_act: i["_detail"]=f"No update {i['days_stale']}d"
    for i in crit_bugs: i["_detail"]=f"{i['priority']} Bug"
    return html.Div([
        html.Div([C.kpi("Past Due",len(past_due),C.RED),C.kpi("No Activity >7d",len(no_act),C.ORANGE),
                  C.kpi("Unassigned",len(unassigned),C.MUTED),C.kpi("High Bugs",len(crit_bugs),"#DC2626")],
                 style={"display":"flex","gap":"10px","flexWrap":"wrap","marginBottom":"20px"}),
        _tbl("Past Due Date",past_due,C.RED),_tbl("No Activity >7 Days",no_act,C.ORANGE),
        _tbl("Unassigned",unassigned,C.MUTED),_tbl("High/Highest Bugs",crit_bugs,"#DC2626"),
    ])

def page_settings(issues,_):
    return html.Div([C.section("Configuration"),
        C.card(html.Div("Tracked Labels",style={"color":C.MUTED,"fontSize":"0.62rem","fontWeight":"700","letterSpacing":"0.1em","textTransform":"uppercase","marginBottom":"10px"}),
               html.Div([html.Span(l,style={"background":C.ACCENT2,"color":C.ACCENT,"borderRadius":"4px","padding":"3px 10px","fontSize":"0.72rem","fontWeight":"700","marginRight":"6px","marginBottom":"6px","display":"inline-block","fontFamily":"JetBrains Mono,monospace"}) for l in D.get_labels(issues)])),
        C.card(*[html.Div([html.Span(k,style={"color":C.MUTED,"width":"160px","display":"inline-block","fontSize":"0.72rem","fontWeight":"700"}),
                           html.Span(v,style={"color":C.TEXT,"fontSize":"0.76rem","fontFamily":"JetBrains Mono,monospace"})],style={"marginBottom":"8px"})
                 for k,v in [("Jira URL",D.BASE_URL),("Projects",", ".join(D.PROJECTS)),("Auto-refresh","Every 10 minutes"),("Max Issues",str(D.MAX_ISSUES)),("Days Back",str(D.DAYS_BACK)),("Loaded",str(len(issues)))]])])

def page_standup(issues, _):
    return SL.layout(issues)

@app.callback(Output("cyto-detail","children"),Input("cyto-graph","tapNodeData"),State("store-issues","data"))
def cyto_click(node,issues):
    if not node or not issues: return C.issue_drawer(None)
    return C.issue_drawer(next((i for i in issues if i["key"]==node["id"]),None))

@app.callback(Output("cyto-graph","layout"),Input("dep-layout","value"))
def cyto_layout(val): return {"name":val,"animate":True,"nodeRepulsion":5000}

app.index_string='''<!DOCTYPE html>
<html>
<head>
{%metas%}<title>{%title%}</title>{%favicon%}{%css%}
<link href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;500;600;700;800&family=DM+Sans:wght@400;500;600;700;800&display=swap" rel="stylesheet">
<style>
*{box-sizing:border-box;margin:0;padding:0}body{background:#F0F4FF}
::-webkit-scrollbar{width:5px;height:5px}::-webkit-scrollbar-track{background:#F0F4FF}::-webkit-scrollbar-thumb{background:#D4DFFF;border-radius:3px}
table th{padding:9px 12px;text-align:left;font-size:0.67rem;letter-spacing:0.08em;text-transform:uppercase;color:#5A6E99;font-weight:800}
table td{padding:8px 12px;border-bottom:1px solid #D4DFFF}
table tr:hover td{background:#EEF4FF55!important}
a:hover{opacity:0.8}nav a:hover{color:#7EA8E8!important;border-left-color:#2563EB!important;background:#1E356022}
</style>
</head>
<body>{%app_entry%}<footer>{%config%}{%scripts%}{%renderer%}</footer></body>
</html>'''


# Clientside callbacks for accordion toggle — no server round-trip needed
for _id in ["atrisk","blockers","dueweek","p-charts","p-stack","p-cards","initiatives"]:
    app.clientside_callback(
        """
        function(n_clicks, current_style) {
            if (!n_clicks) return [current_style, '▲'];
            const is_open = current_style.display !== 'none';
            return [
                {...current_style, display: is_open ? 'none' : 'block'},
                is_open ? '▼' : '▲'
            ];
        }
        """,
        [Output(f"acc-body-{_id}", "style"), Output(f"acc-icon-{_id}", "children")],
        Input(f"acc-hdr-{_id}", "n_clicks"),
        State(f"acc-body-{_id}", "style"),
        prevent_initial_call=True,
    )

SL.register_callbacks(app, D.get_issues)

if __name__=="__main__":
    app.run(debug=False,host="0.0.0.0",port=8050)
