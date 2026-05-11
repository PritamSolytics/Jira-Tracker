"""
resource_allocation_page.py — Resource Allocation & Sprint Intelligence
=======================================================================
Features:
  1. Sprint-wise deliverables summary
  2. Dev vs QA split with FE/BE breakdown
  3. Overall Daily Status Movement chart (stacked by destination status)
  4. Assignee-wise Daily Status Movement chart
  5. Status Movement Feed — real transitions with IST timestamp + assignee
  6. Assignee daily heatmap
  7. Time log assignee-wise (hours)
  8. Unique resources count + list
  9. Blockers list (label = "Blocker")
"""
from dash import html, dcc, Input, Output
import plotly.graph_objects as go
from collections import defaultdict, Counter
from datetime import date, timedelta
import components as C
import data as D

# ── Status groups ─────────────────────────────────────────────────────────────
DEV_STATUSES = {
    "To Do", "Groomed", "Development In Progress", "Fixing in Progress",
    "Code Review", "Integration Testing", "Info-Needed", "On-Hold", "Reopened",
    "Ready For QA Testing",
}
QA_STATUSES = {"QA Testing", "UAT", "Ready For Deployment UAT", "Rejected", "Closed"}

# Color per destination status for movement charts
STATUS_MOVE_COLORS = {
    "Groomed":                 "#475569",
    "To Do":                   "#5A6E99",
    "Development In Progress": "#D97706",
    "Fixing in Progress":      "#DC2626",
    "Code Review":             "#7C3AED",
    "Integration Testing":     "#0D9488",
    "Ready For QA Testing":    "#2563EB",
    "QA Testing":              "#2563EB",
    "UAT":                     "#7C3AED",
    "Ready For Deployment UAT":"#7C3AED",
    "Closed":                  "#16A34A",
    "Rejected":                "#DC2626",
    "Reopened":                "#EA580C",
    "On-Hold":                 "#475569",
    "Info-Needed":             "#D97706",
}

L = dict(paper_bgcolor=C.SURFACE, plot_bgcolor=C.SURFACE,
         font=dict(color=C.TEXT, size=11, family="JetBrains Mono, monospace"),
         margin=dict(l=8, r=8, t=40, b=8))

def _g(fig, gid, h=280):
    return dcc.Graph(figure=fig, id=gid, style={"height": f"{h}px"}, config={"displayModeBar": False})

def _t(text):
    return dict(text=text, font=dict(size=11, color=C.NAVY2, weight="bold"))

def _sec(t, s=None): return C.section(t, s)

def _fe_be(issue):
    labels = issue.get("labels") or []
    if any(l.startswith("FE") for l in labels): return "FE"
    if any(l.startswith("BE") for l in labels): return "BE"
    return "Other"

def _hrs(sec): return round((sec or 0) / 3600, 1)


def _build_movement_feed(issues, changelog, days=14):
    """
    Build flat list of all status transitions in last N days from changelog.
    Each entry: {key, assignee, type, priority, summary, from, to, date, timestamp, url}
    Sorted by timestamp descending (most recent first).
    """
    today  = date.today()
    cutoff = (today - timedelta(days=days)).isoformat()
    key_map = {i["key"]: i for i in issues}
    feed = []

    for issue_key, transitions in changelog.items():
        issue = key_map.get(issue_key, {})
        for t in transitions:
            if t.get("date", "") >= cutoff:
                feed.append({
                    "key":       issue_key,
                    "assignee":  issue.get("assignee", "Unassigned"),
                    "type":      issue.get("type", ""),
                    "priority":  issue.get("priority", ""),
                    "summary":   issue.get("summary", "")[:60],
                    "from":      t.get("from", ""),
                    "to":        t.get("to", ""),
                    "date":      t.get("date", ""),
                    "timestamp": t.get("timestamp", t.get("date", "")),
                    "url":       issue.get("url", f"{D.BASE_URL}/browse/{issue_key}"),
                })

    return sorted(feed, key=lambda x: x["timestamp"], reverse=True)


# ── Layout ────────────────────────────────────────────────────────────────────
def layout(issues):
    sprints = sorted(set(i.get("sprint","") for i in issues if i.get("sprint")), reverse=True)
    sprint_opts = [{"label":"All Sprints","value":"ALL"}] + \
                  [{"label":s,"value":s} for s in sprints]

    return html.Div([
        _sec("Resource Allocation",
             "Sprint deliverables · Status movement · Dev/QA split · Time logs · Blockers"),

        # ── Sprint filter ──────────────────────────────────────────────────
        html.Div([
            html.Label("Sprint", style={"fontSize":"0.62rem","fontWeight":"800",
                       "color":C.MUTED,"letterSpacing":"0.1em","textTransform":"uppercase"}),
            dcc.Dropdown(id="ra-sprint", options=sprint_opts, value="ALL",
                         clearable=False,
                         style={"fontSize":"0.78rem","marginTop":"4px","minWidth":"220px"}),
        ], style={"padding":"14px","background":C.SURFACE,"borderRadius":"10px",
                  "border":f"1px solid {C.BORDER}","marginBottom":"16px","display":"inline-block"}),

        # ── KPI strip ─────────────────────────────────────────────────────
        html.Div(id="ra-kpis"),
        html.Div(style={"marginTop":"16px"}),

        # ── Row 1: Sprint deliverables + FE/BE split ───────────────────────
        C.grid(
            C.card(html.Div(id="ra-sprint-table"), cols=1),
            C.card(html.Div(id="ra-febe-chart"),   cols=1),
            cols=2
        ),
        html.Div(style={"marginTop":"16px"}),

        # ── Row 2: Overall daily status movement ───────────────────────────
        C.card(html.Div(id="ra-movement-overall"), cols=1),
        html.Div(style={"marginTop":"16px"}),

        # ── Row 3: Assignee-wise daily status movement ─────────────────────
        C.card(html.Div(id="ra-movement-assignee"), cols=1),
        html.Div(style={"marginTop":"16px"}),

        # ── Row 4: Status movement feed ────────────────────────────────────
        C.card(html.Div(id="ra-movement-feed"), cols=1),
        html.Div(style={"marginTop":"16px"}),

        # ── Row 5: Assignee daily heatmap ─────────────────────────────────
        C.card(html.Div(id="ra-heatmap"), cols=1),
        html.Div(style={"marginTop":"16px"}),

        # ── Row 6: Time log + Resources ───────────────────────────────────
        C.grid(
            C.card(html.Div(id="ra-timelog"),   cols=1),
            C.card(html.Div(id="ra-resources"), cols=1),
            cols=2
        ),
        html.Div(style={"marginTop":"16px"}),

        # ── Row 7: Blockers ────────────────────────────────────────────────
        C.card(html.Div(id="ra-blockers"), cols=1),

        # Store
        dcc.Store(id="ra-store", data=[{
            "key":      i["key"],
            "summary":  i["summary"][:70],
            "type":     i["type"],
            "status":   i["status"],
            "assignee": i["assignee"],
            "priority": i["priority"],
            "sprint":   i.get("sprint",""),
            "labels":   i.get("labels") or [],
            "updated":  i.get("updated",""),
            "due":      i.get("due","") or "",
            "due_flag": i.get("due_flag",""),
            "timespent":i.get("time_spent_sec", 0) or 0,
            "url":      i["url"],
        } for i in issues]),
    ])


# ── Callbacks ─────────────────────────────────────────────────────────────────
def register_callbacks(app, get_issues_fn):

    @app.callback(
        Output("ra-kpis",              "children"),
        Output("ra-sprint-table",      "children"),
        Output("ra-febe-chart",        "children"),
        Output("ra-movement-overall",  "children"),
        Output("ra-movement-assignee", "children"),
        Output("ra-movement-feed",     "children"),
        Output("ra-heatmap",           "children"),
        Output("ra-timelog",           "children"),
        Output("ra-resources",         "children"),
        Output("ra-blockers",          "children"),
        Input("ra-sprint", "value"),
        Input("ra-store",  "data"),
    )
    def update(sprint, rows):
        if not rows:
            empty = html.Div("No data.", style={"color":C.MUTED,"fontSize":"0.75rem"})
            return (empty,)*10

        f = rows if sprint == "ALL" else [r for r in rows if r["sprint"] == sprint]
        if not f:
            empty = html.Div("No issues in selected sprint.",
                             style={"color":C.MUTED,"fontSize":"0.75rem","padding":"12px 0"})
            return (empty,)*10

        total     = len(f)
        open_n    = sum(1 for r in f if r["status"] != "Closed")
        closed_n  = total - open_n
        blockers  = [r for r in f if "Blocker" in r["labels"]]
        dev_n     = sum(1 for r in f if r["status"] in DEV_STATUSES)
        qa_n      = sum(1 for r in f if r["status"] in QA_STATUSES)
        total_hrs = round(sum(r["timespent"] for r in f) / 3600, 1)

        # ── KPIs ──────────────────────────────────────────────────────────
        kpis = html.Div([
            C.kpi("Total Tickets", total,         C.NAVY),
            C.kpi("Open",          open_n,         C.ACCENT),
            C.kpi("Closed",        closed_n,       C.GREEN),
            C.kpi("In Dev",        dev_n,          C.AMBER),
            C.kpi("In QA",         qa_n,           C.PURPLE),
            C.kpi("Blockers",      len(blockers),  C.RED),
            C.kpi("Hours Logged",  total_hrs,      C.TEAL),
        ], style={"display":"flex","gap":"10px","flexWrap":"wrap"})

        # ── Sprint deliverables table ──────────────────────────────────────
        by_sprint = defaultdict(list)
        for r in rows:
            by_sprint[r["sprint"] or "No Sprint"].append(r)

        sprint_rows = []
        for sp in sorted(by_sprint, reverse=True)[:10]:
            items = by_sprint[sp]
            cl    = sum(1 for r in items if r["status"] == "Closed")
            tot   = len(items)
            pct   = round(cl / max(1, tot) * 100)
            color = C.GREEN if pct >= 80 else (C.AMBER if pct >= 40 else C.RED)
            sprint_rows.append(html.Tr([
                html.Td(sp, style={"fontWeight":"700","fontSize":"0.73rem","color":C.NAVY,
                                   "fontFamily":"JetBrains Mono,monospace"}),
                html.Td(str(tot), style={"fontFamily":"JetBrains Mono,monospace","fontSize":"0.72rem"}),
                html.Td(str(cl),  style={"color":C.GREEN,"fontFamily":"JetBrains Mono,monospace",
                                          "fontSize":"0.72rem","fontWeight":"700"}),
                html.Td(f"{pct}%",style={"color":color,"fontWeight":"800",
                                          "fontFamily":"JetBrains Mono,monospace","fontSize":"0.75rem"}),
                html.Td(str(tot-cl), style={"color":C.ORANGE,"fontFamily":"JetBrains Mono,monospace",
                                             "fontSize":"0.72rem"}),
            ], style={"borderBottom":f"1px solid {C.BORDER}"}))

        sprint_table = html.Div([
            html.Div("SPRINT DELIVERABLES", style={"fontSize":"0.58rem","fontWeight":"800",
                     "letterSpacing":"0.16em","color":C.NAVY2,"marginBottom":"10px"}),
            html.Table([
                html.Thead(html.Tr([html.Th(h) for h in ["Sprint","Total","Closed","Done%","Open"]],
                           style={"background":C.ACCENT2})),
                html.Tbody(sprint_rows),
            ], style={"width":"100%","borderCollapse":"collapse","fontSize":"0.73rem"}),
        ])

        # ── FE/BE × Dev/QA ────────────────────────────────────────────────
        categories = {"FE Dev":0,"FE QA":0,"BE Dev":0,"BE QA":0,"Other Dev":0,"Other QA":0}
        for r in f:
            fb    = _fe_be(r)
            phase = "Dev" if r["status"] in DEV_STATUSES else "QA"
            key   = f"{fb} {phase}"
            if key in categories:
                categories[key] += 1

        febe_fig = go.Figure([
            go.Bar(name="Dev", x=["FE","BE","Other"],
                   y=[categories["FE Dev"],categories["BE Dev"],categories["Other Dev"]],
                   marker_color=C.ACCENT, opacity=0.85),
            go.Bar(name="QA",  x=["FE","BE","Other"],
                   y=[categories["FE QA"], categories["BE QA"], categories["Other QA"]],
                   marker_color=C.PURPLE, opacity=0.85),
        ])
        febe_fig.update_layout(**L, barmode="stack",
                               title=_t("Dev vs QA — FE / BE Split"),
                               xaxis=dict(gridcolor=C.BORDER),
                               yaxis=dict(gridcolor=C.BORDER))

        # ── Pull changelog ─────────────────────────────────────────────────
        issues_full = get_issues_fn()
        changelog   = D.get_changelog()
        sprint_keys = set(r["key"] for r in f)
        today       = date.today()
        days14      = [(today - timedelta(days=i)).isoformat() for i in range(13, -1, -1)]

        all_feed = _build_movement_feed(issues_full, changelog, days=14)
        feed     = [e for e in all_feed if sprint == "ALL" or e["key"] in sprint_keys]

        # ── Chart 3: Overall daily status movement ─────────────────────────
        daily_to = defaultdict(lambda: defaultdict(int))
        for e in feed:
            if e["date"] in days14:
                daily_to[e["date"]][e["to"]] += 1

        dest_statuses = sorted(
            set(e["to"] for e in feed if e["date"] in days14),
            key=lambda s: list(STATUS_MOVE_COLORS.keys()).index(s)
            if s in STATUS_MOVE_COLORS else 99
        )

        overall_traces = []
        for s in dest_statuses:
            color = STATUS_MOVE_COLORS.get(s, C.MUTED)
            vals  = [daily_to[d].get(s, 0) for d in days14]
            if any(v > 0 for v in vals):
                overall_traces.append(go.Bar(
                    name=s, x=days14, y=vals,
                    marker_color=color, opacity=0.88,
                    hovertemplate=f"<b>→ {s}</b><br>%{{x}}<br>%{{y}} tickets<extra></extra>",
                ))

        if overall_traces:
            overall_fig = go.Figure(overall_traces)
            overall_fig.update_layout(**L, barmode="stack",
                title=_t("Overall Daily Status Movement — Last 14 Days"),
                xaxis=dict(tickangle=-30, gridcolor=C.BORDER),
                yaxis=dict(title="Transitions", gridcolor=C.BORDER))
            movement_overall = html.Div([
                html.Div("OVERALL DAILY STATUS MOVEMENT", style={"fontSize":"0.58rem",
                         "fontWeight":"800","letterSpacing":"0.16em","color":C.NAVY2,
                         "marginBottom":"4px"}),
                html.Div("Each bar = tickets that transitioned INTO that status on that day.",
                         style={"fontSize":"0.67rem","color":C.MUTED,"marginBottom":"10px",
                                "fontStyle":"italic"}),
                _g(overall_fig, "ra-overall-fig", 300),
            ])
        else:
            movement_overall = html.Div([
                html.Div("OVERALL DAILY STATUS MOVEMENT", style={"fontSize":"0.58rem",
                         "fontWeight":"800","letterSpacing":"0.16em","color":C.NAVY2,
                         "marginBottom":"8px"}),
                html.Div("No transitions found. Changelog loads in background — refresh in ~60s.",
                         style={"color":C.AMBER,"fontSize":"0.74rem","padding":"12px 0"}),
            ])

        # ── Chart 4: Assignee-wise daily movement ──────────────────────────
        assignee_daily = defaultdict(lambda: defaultdict(int))
        for e in feed:
            if e["date"] in days14 and e["assignee"] != "Unassigned":
                assignee_daily[e["assignee"]][e["date"]] += 1

        top_movers = sorted(assignee_daily, key=lambda a: -sum(assignee_daily[a].values()))[:10]
        a_colors   = [C.ACCENT, C.RED, C.GREEN, C.PURPLE, C.AMBER,
                      C.TEAL, C.ORANGE, C.NAVY, C.MUTED, "#475569"]

        assignee_traces = []
        for idx, a in enumerate(top_movers):
            vals = [assignee_daily[a].get(d, 0) for d in days14]
            assignee_traces.append(go.Bar(
                name=a.split()[0] if " " in a else a,
                x=days14, y=vals,
                marker_color=a_colors[idx % len(a_colors)], opacity=0.85,
                hovertemplate=f"<b>{a}</b><br>%{{x}}<br>%{{y}} transitions<extra></extra>",
            ))

        if assignee_traces:
            assignee_fig = go.Figure(assignee_traces)
            assignee_fig.update_layout(**L, barmode="stack",
                title=_t("Assignee-wise Daily Status Movement — Last 14 Days"),
                xaxis=dict(tickangle=-30, gridcolor=C.BORDER),
                yaxis=dict(title="Transitions", gridcolor=C.BORDER))
            movement_assignee = html.Div([
                html.Div("ASSIGNEE-WISE DAILY STATUS MOVEMENT", style={"fontSize":"0.58rem",
                         "fontWeight":"800","letterSpacing":"0.16em","color":C.NAVY2,
                         "marginBottom":"4px"}),
                html.Div("How many status transitions each person drove per day.",
                         style={"fontSize":"0.67rem","color":C.MUTED,"marginBottom":"10px",
                                "fontStyle":"italic"}),
                _g(assignee_fig, "ra-assignee-fig", 300),
            ])
        else:
            movement_assignee = html.Div("No assignee movement data.",
                                          style={"color":C.MUTED,"fontSize":"0.74rem"})

        # ── Status Movement Feed ───────────────────────────────────────────
        if feed:
            by_date   = defaultdict(list)
            for e in feed[:300]:
                by_date[e["date"]].append(e)

            feed_rows = []
            for d in sorted(by_date.keys(), reverse=True):
                day_count = len(by_date[d])
                feed_rows.append(html.Div([
                    html.Span(d, style={"fontWeight":"800","fontSize":"0.7rem","color":C.NAVY2,
                                        "fontFamily":"JetBrains Mono,monospace"}),
                    html.Span(f"  {day_count} transition{'s' if day_count!=1 else ''}",
                              style={"fontSize":"0.63rem","color":C.MUTED}),
                ], style={"margin":"14px 0 6px","borderBottom":f"2px solid {C.BORDER}",
                           "paddingBottom":"4px"}))

                for e in by_date[d]:
                    from_c = STATUS_MOVE_COLORS.get(e["from"], C.MUTED)
                    to_c   = STATUS_MOVE_COLORS.get(e["to"],   C.GREEN)

                    feed_rows.append(html.Div([
                        # Top row: timestamp + issue key + assignee
                        html.Div([
                            html.Span(e["timestamp"], style={
                                "fontSize":"0.62rem","color":C.MUTED,
                                "fontFamily":"JetBrains Mono,monospace",
                                "marginRight":"12px","flexShrink":"0",
                            }),
                            html.A(e["key"], href=e["url"], target="_blank", style={
                                "color":C.ACCENT,"fontWeight":"800",
                                "fontFamily":"JetBrains Mono,monospace",
                                "fontSize":"0.74rem","textDecoration":"none",
                                "marginRight":"10px","flexShrink":"0",
                            }),
                            html.Span(e["assignee"], style={
                                "color":C.NAVY,"fontWeight":"700","fontSize":"0.72rem",
                                "marginRight":"12px",
                            }),
                            # FROM → TO
                            html.Span(e["from"] or "—", style={
                                "background":from_c+"22","color":from_c,
                                "borderRadius":"4px","padding":"2px 8px",
                                "fontSize":"0.65rem","fontWeight":"700",
                                "border":f"1px solid {from_c}44",
                                "whiteSpace":"nowrap",
                            }),
                            html.Span(" → ", style={"color":C.MUTED,"fontWeight":"900",
                                                     "fontSize":"0.8rem","margin":"0 4px"}),
                            html.Span(e["to"] or "—", style={
                                "background":to_c+"22","color":to_c,
                                "borderRadius":"4px","padding":"2px 8px",
                                "fontSize":"0.65rem","fontWeight":"700",
                                "border":f"1px solid {to_c}44",
                                "whiteSpace":"nowrap","marginRight":"10px",
                            }),
                            # Type + Priority
                            html.Span(e["type"], style={
                                "color":C.tc(e["type"]) if e["type"] else C.MUTED,
                                "fontSize":"0.62rem","fontWeight":"700","marginRight":"6px",
                            }),
                            html.Span(e["priority"], style={
                                "color":C.pc(e["priority"]) if e["priority"] else C.MUTED,
                                "fontSize":"0.62rem","fontWeight":"700",
                            }) if e["priority"] else None,
                        ], style={"display":"flex","alignItems":"center",
                                  "flexWrap":"wrap","gap":"2px"}),
                        # Summary line
                        html.Div(e["summary"], style={
                            "color":C.MUTED,"fontSize":"0.67rem","marginTop":"3px",
                            "paddingLeft":"6px","borderLeft":f"2px solid {to_c}44",
                        }),
                    ], style={
                        "padding":"9px 12px","background":C.SURFACE,
                        "borderRadius":"6px","border":f"1px solid {C.BORDER}",
                        "borderLeft":f"3px solid {to_c}","marginBottom":"5px",
                    }))

            movement_feed = html.Div([
                html.Div([
                    html.Div("STATUS MOVEMENT FEED", style={"fontSize":"0.58rem","fontWeight":"800",
                             "letterSpacing":"0.16em","color":C.NAVY2}),
                    html.Div(
                        f"{len(feed)} transitions · Last 14 days · "
                        f"Changelog synced: {D.get_changelog_last_sync()}",
                        style={"fontSize":"0.66rem","color":C.MUTED,"marginTop":"2px",
                               "fontStyle":"italic"},
                    ),
                ], style={"marginBottom":"12px"}),
                html.Div(feed_rows, style={"maxHeight":"600px","overflowY":"auto","paddingRight":"4px"}),
            ])
        else:
            movement_feed = html.Div([
                html.Div("STATUS MOVEMENT FEED", style={"fontSize":"0.58rem","fontWeight":"800",
                         "letterSpacing":"0.16em","color":C.NAVY2,"marginBottom":"8px"}),
                html.Div([
                    html.Div("⏳ Changelog loading in background (first load only).",
                             style={"color":C.AMBER,"fontWeight":"700","fontSize":"0.74rem"}),
                    html.Div("Shows real status transitions with IST timestamps. Refresh in ~60 seconds.",
                             style={"color":C.MUTED,"fontSize":"0.7rem","marginTop":"4px"}),
                ], style={"padding":"12px","background":"#FFFBEB","borderRadius":"6px",
                          "border":f"1px solid {C.AMBER}33"}),
            ])

        # ── Assignee × Day heatmap ─────────────────────────────────────────
        assignees_hm = sorted(set(r["assignee"] for r in f if r["assignee"] != "Unassigned"))[:20]
        days7 = [(today - timedelta(days=i)).isoformat() for i in range(6, -1, -1)]
        z = [[sum(1 for r in f if r["assignee"] == a and r.get("updated","")[:10] == d)
              for d in days7] for a in assignees_hm]
        heatmap_fig = go.Figure(go.Heatmap(
            z=z, x=days7, y=assignees_hm,
            colorscale=[[0,C.SURFACE],[0.5,"rgba(37,99,235,0.4)"],[1,C.ACCENT]],
            hovertemplate="<b>%{y}</b><br>%{x}<br>Updates: %{z}<extra></extra>",
        ))
        heatmap_fig.update_layout(**L,
            title=_t("Assignee × Day — Ticket Updates (Last 7 Days)"),
            xaxis=dict(tickangle=-20),
            height=max(240, len(assignees_hm)*22))

        # ── Time log ──────────────────────────────────────────────────────
        time_by_assignee = defaultdict(float)
        for r in f:
            time_by_assignee[r["assignee"]] += r["timespent"]
        top_time = sorted(time_by_assignee.items(), key=lambda x: -x[1])
        max_hrs  = _hrs(top_time[0][1]) if top_time else 1

        time_rows = [html.Tr([
            html.Td(a, style={"fontWeight":"600","fontSize":"0.72rem","color":C.NAVY}),
            html.Td(f"{_hrs(s)}h", style={"fontFamily":"JetBrains Mono,monospace",
                    "fontWeight":"700","fontSize":"0.75rem",
                    "color":C.TEAL if s > 0 else C.MUTED}),
            html.Td(html.Div(style={
                "width":f"{min(100, _hrs(s)/max(1,max_hrs)*100):.0f}%",
                "height":"6px","background":C.TEAL,"borderRadius":"3px",
            })),
        ], style={"borderBottom":f"1px solid {C.BORDER}"})
        for a, s in top_time if a != "Unassigned"]

        timelog = html.Div([
            html.Div("TIME LOG — HOURS PER ASSIGNEE", style={"fontSize":"0.58rem","fontWeight":"800",
                     "letterSpacing":"0.16em","color":C.NAVY2,"marginBottom":"10px"}),
            html.Div(f"Total: {total_hrs}h logged",
                     style={"fontSize":"0.68rem","color":C.MUTED,"marginBottom":"8px"}),
            html.Table([
                html.Thead(html.Tr([html.Th(h) for h in ["Assignee","Hours","Distribution"]],
                           style={"background":C.ACCENT2})),
                html.Tbody(time_rows or [html.Tr([html.Td(
                    "No time logged",
                    style={"color":C.MUTED,"fontSize":"0.72rem","padding":"8px"},
                )])]),
            ], style={"width":"100%","borderCollapse":"collapse","fontSize":"0.73rem"}),
        ])

        # ── Unique resources ──────────────────────────────────────────────
        all_assignees    = sorted(set(r["assignee"] for r in rows if r["assignee"] != "Unassigned"))
        sprint_assignees = sorted(set(r["assignee"] for r in f    if r["assignee"] != "Unassigned"))
        resources = html.Div([
            html.Div("RESOURCES", style={"fontSize":"0.58rem","fontWeight":"800",
                     "letterSpacing":"0.16em","color":C.NAVY2,"marginBottom":"12px"}),
            html.Div([
                html.Div(f"{len(all_assignees)}", style={"fontSize":"2.4rem","fontWeight":"900",
                         "color":C.NAVY,"fontFamily":"JetBrains Mono,monospace"}),
                html.Div("Total Unique Resources", style={"fontSize":"0.62rem","color":C.MUTED,
                         "fontWeight":"700","textTransform":"uppercase","letterSpacing":"0.1em"}),
            ], style={"marginBottom":"14px"}),
            html.Div([
                html.Div(f"{len(sprint_assignees)}", style={"fontSize":"1.8rem","fontWeight":"900",
                         "color":C.ACCENT,"fontFamily":"JetBrains Mono,monospace"}),
                html.Div("Active in Selected Sprint", style={"fontSize":"0.62rem","color":C.MUTED,
                         "fontWeight":"700","textTransform":"uppercase","letterSpacing":"0.1em"}),
            ], style={"marginBottom":"14px"}),
            html.Div([html.Span(a, style={
                "display":"inline-block","background":C.ACCENT2,"color":C.ACCENT,
                "borderRadius":"4px","padding":"3px 8px","fontSize":"0.68rem",
                "fontWeight":"700","marginRight":"4px","marginBottom":"4px",
            }) for a in sprint_assignees]),
        ])

        # ── Blockers ──────────────────────────────────────────────────────
        active_blockers = [r for r in rows
                           if "Blocker" in r["labels"] and r["status"] not in ("Closed","Rejected")]
        blocker_rows = []
        for r in sorted(active_blockers,
                        key=lambda x: x["priority"] in ("Highest","High"), reverse=True):
            pcolor = C.RED if r["priority"] in ("Highest","High") else C.AMBER
            fe_be  = "FE" if any(l.startswith("FE") for l in r["labels"]) else \
                     "BE" if any(l.startswith("BE") for l in r["labels"]) else "—"
            blocker_rows.append(html.Tr([
                html.Td(html.A(r["key"], href=r["url"], target="_blank",
                    style={"color":C.ACCENT,"fontWeight":"700",
                           "fontFamily":"JetBrains Mono,monospace",
                           "fontSize":"0.72rem","textDecoration":"none"})),
                html.Td(r["summary"][:60],
                        style={"fontSize":"0.71rem","color":C.TEXT,"maxWidth":"300px"}),
                html.Td(r["assignee"],      style={"fontSize":"0.7rem","color":C.MUTED}),
                html.Td(r["sprint"] or "—", style={"fontSize":"0.68rem","color":C.MUTED,
                                                     "fontFamily":"JetBrains Mono,monospace"}),
                html.Td(C.status_badge(r["status"])),
                html.Td(html.Span(r["priority"],
                    style={"color":pcolor,"fontWeight":"700","fontSize":"0.7rem"})),
                html.Td(fe_be, style={"fontSize":"0.7rem","fontWeight":"700",
                         "color":C.ACCENT if fe_be == "FE" else C.ORANGE}),
            ], style={"borderBottom":f"1px solid {C.BORDER}","background":"#FEF2F222"}))

        blockers_section = html.Div([
            html.Div([
                html.Div("ACTIVE BLOCKERS", style={"fontSize":"0.58rem","fontWeight":"800",
                         "letterSpacing":"0.16em","color":C.RED,"marginBottom":"4px"}),
                html.Div(f"{len(active_blockers)} open issues labeled 'Blocker' across all sprints",
                         style={"fontSize":"0.68rem","color":C.MUTED,"marginBottom":"10px"}),
            ]),
            html.Div(style={"overflowX":"auto"}, children=[
                html.Table([
                    html.Thead(html.Tr([html.Th(h) for h in
                        ["Key","Summary","Assignee","Sprint","Status","Priority","FE/BE"]],
                        style={"background":"#FEF2F2"})),
                    html.Tbody(blocker_rows or [
                        html.Tr([html.Td("✓ No active blockers",
                                 style={"color":C.GREEN,"fontWeight":"700",
                                        "padding":"10px","fontSize":"0.75rem"})])
                    ]),
                ], style={"width":"100%","borderCollapse":"collapse","fontSize":"0.73rem"}),
            ]),
        ])

        return (kpis, sprint_table,
                _g(febe_fig, "ra-febe-fig", 280),
                movement_overall,
                movement_assignee,
                movement_feed,
                _g(heatmap_fig, "ra-heat-fig", max(260, len(assignees_hm)*22)),
                timelog, resources, blockers_section)
