"""
people_page.py — Person-wise Ticket Drill-Down
Full ticket list per assignee with Jira links, status, priority, staleness.
"""
from dash import html, dcc, dash_table, Input, Output
import plotly.graph_objects as go
from collections import Counter, defaultdict
from datetime import date
import components as C
import data as D

def layout(issues):
    assignees = sorted(set(i["assignee"] for i in issues if i["assignee"] != "Unassigned"))
    all_assignees = ["All"] + assignees

    return html.Div([
        C.section("People Intelligence — Ticket Drill-Down",
                  "Per-person workload, ticket list, and delivery health"),

        # ── Filter bar ──────────────────────────────────────────────────────
        html.Div([
            html.Div([
                html.Label("Assignee", style={"fontSize":"0.62rem","fontWeight":"800",
                           "color":C.MUTED,"letterSpacing":"0.1em","textTransform":"uppercase"}),
                dcc.Dropdown(
                    id="pp-assignee",
                    options=[{"label":a,"value":a} for a in all_assignees],
                    value="All",
                    clearable=False,
                    style={"fontSize":"0.78rem","marginTop":"4px"},
                ),
            ], style={"flex":"1","minWidth":"200px"}),
            html.Div([
                html.Label("Status", style={"fontSize":"0.62rem","fontWeight":"800",
                           "color":C.MUTED,"letterSpacing":"0.1em","textTransform":"uppercase"}),
                dcc.Dropdown(
                    id="pp-status",
                    options=[{"label":"All","value":"All"}] +
                            [{"label":s,"value":s} for s in sorted(set(i["status"] for i in issues))],
                    value="All",
                    clearable=False,
                    style={"fontSize":"0.78rem","marginTop":"4px"},
                ),
            ], style={"flex":"1","minWidth":"160px"}),
            html.Div([
                html.Label("Type", style={"fontSize":"0.62rem","fontWeight":"800",
                           "color":C.MUTED,"letterSpacing":"0.1em","textTransform":"uppercase"}),
                dcc.Dropdown(
                    id="pp-type",
                    options=[{"label":"All","value":"All"}] +
                            [{"label":t,"value":t} for t in sorted(set(i["type"] for i in issues))],
                    value="All",
                    clearable=False,
                    style={"fontSize":"0.78rem","marginTop":"4px"},
                ),
            ], style={"flex":"1","minWidth":"140px"}),
        ], style={"display":"flex","gap":"12px","flexWrap":"wrap","marginBottom":"16px",
                  "padding":"14px","background":C.SURFACE,"borderRadius":"10px",
                  "border":f"1px solid {C.BORDER}"}),

        # ── KPI strip (reactive) ─────────────────────────────────────────────
        html.Div(id="pp-kpi-strip"),

        html.Div(style={"marginTop":"16px"}),

        # ── Workload bar chart ───────────────────────────────────────────────
        html.Div(id="pp-workload-chart"),

        html.Div(style={"marginTop":"16px"}),

        # ── Ticket table ─────────────────────────────────────────────────────
        html.Div(id="pp-ticket-table"),

        # Hidden store for issues
        dcc.Store(id="pp-issues-store", data=[{
            "key":      i["key"],
            "summary":  i["summary"][:70],
            "type":     i["type"],
            "status":   i["status"],
            "assignee": i["assignee"],
            "priority": i["priority"],
            "due":      i["due"] or "—",
            "due_flag": i["due_flag"],
            "labels":   ", ".join(i.get("labels") or []),
            "days_stale": i.get("days_since_progress", i.get("days_stale", 0)),
            "sprint":   i.get("sprint",""),
            "url":      i["url"],
        } for i in issues]),
    ])


def register_callbacks(app, get_issues_fn):

    @app.callback(
        Output("pp-kpi-strip","children"),
        Output("pp-workload-chart","children"),
        Output("pp-ticket-table","children"),
        Input("pp-assignee","value"),
        Input("pp-status","value"),
        Input("pp-type","value"),
        Input("pp-issues-store","data"),
    )
    def update(assignee, status, itype, rows):
        if not rows: return html.Div(), html.Div(), html.Div()

        # Filter
        filtered = rows
        if assignee and assignee != "All":
            filtered = [r for r in filtered if r["assignee"] == assignee]
        if status and status != "All":
            filtered = [r for r in filtered if r["status"] == status]
        if itype and itype != "All":
            filtered = [r for r in filtered if r["type"] == itype]

        total    = len(filtered)
        open_n   = sum(1 for r in filtered if r["status"] != "Closed")
        overdue  = sum(1 for r in filtered if "Beyond Target Date" in r["due_flag"])
        stale    = sum(1 for r in filtered if r["days_stale"] > 7)
        closed   = total - open_n

        # KPI strip
        kpi_strip = html.Div([
            C.kpi("Total",   total,  C.NAVY),
            C.kpi("Open",    open_n, C.ACCENT),
            C.kpi("Closed",  closed, C.GREEN),
            C.kpi("Overdue", overdue,C.RED),
            C.kpi("Stale >7d",stale, C.ORANGE),
        ], style={"display":"flex","gap":"10px","flexWrap":"wrap","marginBottom":"4px"})

        # Workload bar (only when showing All assignees)
        chart_div = html.Div()
        if assignee == "All":
            by_person = Counter(r["assignee"] for r in filtered if r["status"] != "Closed")
            top = by_person.most_common(20)
            if top:
                fig = go.Figure(go.Bar(
                    x=[a for a,_ in top], y=[c for _,c in top],
                    marker_color=C.ACCENT, opacity=0.85,
                    text=[str(c) for _,c in top], textposition="outside",
                ))
                fig.update_layout(
                    paper_bgcolor=C.SURFACE, plot_bgcolor=C.SURFACE,
                    font=dict(color=C.TEXT, size=11, family="JetBrains Mono,monospace"),
                    margin=dict(l=8,r=8,t=36,b=8),
                    title=dict(text="Open Issues per Person",
                               font=dict(size=11,color=C.NAVY2,weight="bold")),
                    xaxis=dict(tickangle=-30,gridcolor=C.BORDER),
                    yaxis=dict(gridcolor=C.BORDER),
                    height=280,
                )
                chart_div = C.card(
                    dcc.Graph(figure=fig, config={"displayModeBar":False},
                              style={"height":"280px"})
                )

        # Ticket table with clickable Jira links
        if not filtered:
            table = html.Div("No tickets match the selected filters.",
                             style={"color":C.MUTED,"fontSize":"0.78rem","padding":"20px 0"})
        else:
            sorted_rows = sorted(filtered,
                key=lambda r: (r["status"]=="Closed", -r["days_stale"]))

            table_rows = []
            for r in sorted_rows:
                due_color = C.RED if "Beyond Target Date" in r["due_flag"] else \
                            (C.AMBER if r["due_flag"]=="Due This Week" else C.TEXT)
                stale_color = C.RED if r["days_stale"]>14 else \
                              (C.ORANGE if r["days_stale"]>7 else C.GREEN)
                table_rows.append(html.Tr([
                    html.Td(html.A(r["key"], href=r["url"], target="_blank",
                        style={"color":C.ACCENT,"fontWeight":"700","fontFamily":"JetBrains Mono,monospace",
                               "fontSize":"0.72rem","textDecoration":"none"})),
                    html.Td(r["summary"], style={"fontSize":"0.71rem","color":C.TEXT,
                                                  "maxWidth":"280px","overflow":"hidden",
                                                  "textOverflow":"ellipsis","whiteSpace":"nowrap"}),
                    html.Td(C.status_badge(r["status"])),
                    html.Td(r["type"],   style={"fontSize":"0.7rem","color":C.tc(r["type"]),"fontWeight":"700"}),
                    html.Td(r["priority"],style={"fontSize":"0.7rem","color":C.pc(r["priority"]),"fontWeight":"700"}),
                    html.Td(r["assignee"],style={"fontSize":"0.7rem","color":C.MUTED}),
                    html.Td(r["sprint"] or "—", style={"fontSize":"0.68rem","color":C.MUTED,
                                                        "fontFamily":"JetBrains Mono,monospace"}),
                    html.Td(r["due"],    style={"fontSize":"0.7rem","color":due_color,"fontWeight":"600",
                                                "fontFamily":"JetBrains Mono,monospace"}),
                    html.Td(f"{r['days_stale']}d", style={"color":stale_color,"fontWeight":"700",
                                                           "fontFamily":"JetBrains Mono,monospace","fontSize":"0.72rem"}),
                    html.Td(r["labels"][:30] if r["labels"] else "—",
                            style={"fontSize":"0.65rem","color":C.MUTED}),
                ], style={
                    "borderBottom":f"1px solid {C.BORDER}",
                    "background":"#FEF2F222" if "Beyond Target Date" in r["due_flag"] else C.SURFACE,
                }))

            table = html.Div([
                html.Div(f"{len(sorted_rows)} tickets", style={
                    "fontSize":"0.62rem","fontWeight":"800","color":C.MUTED,
                    "letterSpacing":"0.1em","marginBottom":"8px"
                }),
                html.Div(style={"overflowX":"auto"}, children=[
                    html.Table([
                        html.Thead(html.Tr([
                            html.Th(h) for h in
                            ["Key","Summary","Status","Type","Priority",
                             "Assignee","Sprint","Due","Stale","Labels"]
                        ], style={"background":C.ACCENT2,"position":"sticky","top":"0"})),
                        html.Tbody(table_rows),
                    ], style={"width":"100%","borderCollapse":"collapse","fontSize":"0.73rem"}),
                ]),
            ], style={"maxHeight":"60vh","overflowY":"auto"})

        return kpi_strip, chart_div, C.card(table, pad="12px")
