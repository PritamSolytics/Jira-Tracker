"""Standup Logger page — injected into app.py"""
from dash import html, dcc, Input, Output, State, callback_context
import components as C
import store as ST
import data as D
from datetime import date, timedelta

def layout(issues):
    key_map = {i["key"]:i for i in issues}
    issue_opts = [{"label":f"{i['key']} — {i['summary'][:50]} ({i['assignee']})", "value":i["key"]} for i in sorted(issues, key=lambda x:x["assignee"])]
    assignee_opts = [{"label":a,"value":a} for a in D.get_assignees(issues)]
    today = date.today().isoformat()

    # Log form
    log_form = C.card(
        html.Div("LOG STANDUP UPDATE", style={"fontSize":"0.58rem","fontWeight":"800","letterSpacing":"0.16em","color":C.NAVY2,"marginBottom":"14px"}),
        html.Div([
            html.Div([
                html.Label("Issue", style={"fontSize":"0.65rem","fontWeight":"700","color":C.MUTED,"letterSpacing":"0.08em","textTransform":"uppercase"}),
                dcc.Dropdown(id="sl-issue", options=issue_opts, placeholder="Select issue...",
                             style={"fontSize":"0.75rem","marginTop":"4px"}),
            ], style={"flex":"2"}),
            html.Div([
                html.Label("ETA (promised by)", style={"fontSize":"0.65rem","fontWeight":"700","color":C.MUTED,"letterSpacing":"0.08em","textTransform":"uppercase"}),
                dcc.Input(id="sl-eta", type="date", value="", style={"width":"100%","marginTop":"4px","padding":"8px","border":f"1px solid {C.BORDER}","borderRadius":"6px","fontSize":"0.75rem"}),
            ], style={"flex":"1"}),
        ], style={"display":"flex","gap":"12px","marginBottom":"12px"}),
        html.Div([
            html.Label("Update / What they said", style={"fontSize":"0.65rem","fontWeight":"700","color":C.MUTED,"letterSpacing":"0.08em","textTransform":"uppercase"}),
            dcc.Textarea(id="sl-text", placeholder="e.g. Said it will be done by Friday, waiting for API spec from Rohan...",
                         style={"width":"100%","marginTop":"4px","padding":"10px","border":f"1px solid {C.BORDER}","borderRadius":"6px","fontSize":"0.75rem","fontFamily":"DM Sans,sans-serif","minHeight":"80px","resize":"vertical"}),
        ], style={"marginBottom":"12px"}),
        html.Div([
            html.Button("✓  Log Update + Post to Jira", id="sl-submit", n_clicks=0, style={
                "background":C.NAVY,"color":"#fff","border":"none","borderRadius":"6px",
                "padding":"10px 20px","cursor":"pointer","fontSize":"0.75rem","fontWeight":"700","marginRight":"10px",
            }),
            html.Span(id="sl-feedback", style={"fontSize":"0.75rem","color":C.GREEN,"fontWeight":"600"}),
        ]),
        pad="20px",
    )

    # Promise broken section
    broken = ST.get_promise_broken(issues)
    broken_panel = html.Div([
        html.Div(f"⚠ {len(broken)} Promise{'s' if len(broken)!=1 else ''} Overdue",
                 style={"fontSize":"0.62rem","fontWeight":"800","color":C.RED,"letterSpacing":"0.12em","textTransform":"uppercase","marginBottom":"10px"}),
        html.Table([
            html.Thead(html.Tr([html.Th(h) for h in ["Issue","Assignee","Promised By","Days Over","What They Said","Status"]],
                               style={"background":"#FEF2F2"})),
            html.Tbody([html.Tr([
                html.Td(html.A(b["issue_key"],href=f"{D.BASE_URL}/browse/{b['issue_key']}",target="_blank",
                               style={"color":C.ACCENT,"fontWeight":"700","fontFamily":"JetBrains Mono,monospace","fontSize":"0.72rem","textDecoration":"none"})),
                html.Td(b["assignee"],style={"color":C.TEXT}),
                html.Td(b["eta"],style={"color":C.RED,"fontWeight":"700"}),
                html.Td(f"{b['days_over']}d",style={"color":C.RED,"fontWeight":"800","fontFamily":"JetBrains Mono,monospace"}),
                html.Td(b["update"][:60]+"…" if len(b["update"])>60 else b["update"],style={"color":C.MUTED,"fontSize":"0.71rem"}),
                html.Td(C.status_badge(b["issue"]["status"])),
            ], style={"background":"#FFF5F5"}) for b in broken[:20]])
        ], style={"width":"100%","borderCollapse":"collapse","fontSize":"0.76rem"}),
    ]) if broken else html.Div("No planning variance. 🟢", style={"color":C.GREEN,"fontSize":"0.78rem","padding":"12px 0"})

    # Recent logs
    recent = ST.get_logs(days=30)

    # Group by date
    by_date = {}
    for e in recent:
        by_date.setdefault(e["date"],[]).append(e)

    log_rows = []
    for d_str in sorted(by_date.keys(), reverse=True)[:7]:
        log_rows.append(html.Div(d_str, style={"fontWeight":"800","fontSize":"0.7rem","color":C.NAVY2,"margin":"12px 0 6px","letterSpacing":"0.06em"}))
        for e in by_date[d_str]:
            issue = key_map.get(e["issue_key"],{})
            log_rows.append(html.Div([
                html.Div([
                    html.A(e["issue_key"],href=f"{D.BASE_URL}/browse/{e['issue_key']}",target="_blank",
                           style={"color":C.ACCENT,"fontWeight":"700","fontSize":"0.72rem","textDecoration":"none","marginRight":"8px","fontFamily":"JetBrains Mono,monospace"}),
                    html.Span(e["assignee"],style={"color":C.NAVY,"fontWeight":"600","fontSize":"0.73rem","marginRight":"8px"}),
                    html.Span(f"ETA: {e['eta']}" if e.get("eta") else "No ETA",
                              style={"color":C.RED if (e.get("eta","") < today and issue.get("status") not in ("Closed","Rejected")) else C.AMBER,
                                     "fontSize":"0.68rem","fontWeight":"700","marginRight":"8px"}),
                    html.Span("✓ Resolved" if e["status"]=="resolved" else ("🚨 Execution Variance" if (e.get("eta","")< today and issue.get("status") not in ("Closed","Rejected")) else ""),
                              style={"color":C.GREEN if e["status"]=="resolved" else C.RED,"fontSize":"0.67rem","fontWeight":"700"}),
                ], style={"display":"flex","alignItems":"center","flexWrap":"wrap","gap":"4px"}),
                html.Div(e["update"], style={"color":C.MUTED,"fontSize":"0.73rem","marginTop":"3px","lineHeight":"1.5","paddingLeft":"4px","borderLeft":f"3px solid {C.BORDER}","marginLeft":"4px"}),
                html.Div(f"Logged {e['logged_at']} by {e['logged_by']}",style={"color":"#B0BFDF","fontSize":"0.63rem","marginTop":"3px"}),
            ], style={"padding":"10px","background":C.SURFACE,"borderRadius":"8px","border":f"1px solid {C.BORDER}","marginBottom":"6px"}))

    log_panel = html.Div(log_rows) if log_rows else html.Div("No standup logs yet. Start logging above.", style={"color":C.MUTED,"fontSize":"0.78rem","padding":"20px 0"})

    return html.Div([
        html.Div([
            html.Div([
                log_form,
                html.Div(id="sl-reload"),
                C.section("🚨 Planning Variance Log", "ETA passed, issue still open"),
                C.card(broken_panel, pad="14px"),
            ], style={"flex":"1","minWidth":"0"}),
            html.Div([
                C.section("📋 Standup Log", "Last 30 days"),
                C.card(log_panel, pad="14px", style={"maxHeight":"70vh","overflowY":"auto"}),
            ], style={"width":"380px","flexShrink":"0"}),
        ], style={"display":"flex","gap":"16px","alignItems":"flex-start"}),
    ])


def register_callbacks(app, get_issues_fn):
    from dash import Output, Input, State, callback_context
    import store as ST, data as D

    @app.callback(
        Output("sl-feedback","children"),
        Output("sl-reload","children"),
        Input("sl-submit","n_clicks"),
        State("sl-issue","value"),
        State("sl-eta","value"),
        State("sl-text","value"),
        prevent_initial_call=True,
    )
    def log_update(n, issue_key, eta, text):
        if not issue_key or not text: return "Please select an issue and enter an update.", ""
        issues = get_issues_fn()
        key_map = {i["key"]:i for i in issues}
        issue = key_map.get(issue_key,{})
        assignee = issue.get("assignee","Unknown")
        # Save to local store
        entry = ST.add_log(issue_key, assignee, text, eta or "")
        # Post to Jira
        eta_str = f" · ETA: {eta}" if eta else ""
        comment = f"[STANDUP {entry['date']}] {text}{eta_str}"
        posted = D.post_jira_comment(issue_key, comment)
        jira_status = "✓ Posted to Jira" if posted else "(Jira post failed — saved locally)"
        return f"✓ Logged · {jira_status}", ""
