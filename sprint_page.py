"""
sprint_page.py — Sprint Intelligence
Sprint Planner (AI-generated structure + Jira creation)
Sprint Confidence Analyzer (Monte Carlo + reallocation recommendations)
"""
from dash import html, dcc, Input, Output, State
import plotly.graph_objects as go
import numpy as np
from collections import defaultdict, Counter
from datetime import date, timedelta
import components as C
import data as D

L = dict(paper_bgcolor=C.SURFACE, plot_bgcolor=C.SURFACE,
         font=dict(color=C.TEXT, size=11, family="JetBrains Mono, monospace"),
         margin=dict(l=8,r=8,t=36,b=8))
def _t(t): return dict(text=t, font=dict(size=11, color=C.NAVY2, weight="bold"))
def _g(f,i,h=260): return dcc.Graph(figure=f,id=i,style={"height":f"{h}px"},config={"displayModeBar":False})

BTN = {"background":C.NAVY,"color":"#fff","border":"none","borderRadius":"6px",
       "padding":"10px 22px","cursor":"pointer","fontSize":"0.74rem","fontWeight":"800",
       "letterSpacing":"0.06em","marginRight":"10px"}
BTN2 = {**BTN, "background":C.SURFACE,"color":C.NAVY,"border":f"2px solid {C.BORDER}"}
INPUT_STYLE = {"width":"100%","padding":"8px 10px","border":f"1px solid {C.BORDER}",
               "borderRadius":"6px","fontSize":"0.74rem","fontFamily":"DM Sans,sans-serif",
               "marginTop":"4px","boxSizing":"border-box"}
LABEL = {"fontSize":"0.63rem","fontWeight":"700","color":C.MUTED,
         "textTransform":"uppercase","letterSpacing":"0.08em"}


def _get_assignee_stats(issues):
    by_a = defaultdict(lambda: {"open":0,"cycle_times":[],"eri":50})
    for i in issues:
        if i["status"] != "Closed":
            by_a[i["assignee"]]["open"] += 1
        if i["status"] == "Closed" and i.get("created") and i.get("updated"):
            try:
                ct = (date.fromisoformat(i["updated"]) - date.fromisoformat(i["created"])).days
                if 0 < ct <= 180:
                    by_a[i["assignee"]]["cycle_times"].append(ct)
            except: pass
    return by_a


def _cycle_time_stats(issues):
    by_type = defaultdict(list)
    for i in issues:
        if i["status"] == "Closed" and i.get("created") and i.get("updated"):
            try:
                ct = (date.fromisoformat(i["updated"]) - date.fromisoformat(i["created"])).days
                if 0 < ct <= 180:
                    by_type[i["type"]].append(ct)
            except: pass
    return {t: {"median": int(np.median(v)), "p75": int(np.percentile(v,75)), "count": len(v)}
            for t, v in by_type.items() if v}


def _recommend_assignee(issue_type, label, assignee_stats):
    """Pick assignee with lowest load and good throughput."""
    candidates = [(a, s) for a, s in assignee_stats.items()
                  if a not in ("Unassigned","Former user") and s["open"] < 6]
    if not candidates:
        candidates = list(assignee_stats.items())[:5]
    return min(candidates, key=lambda x: x[1]["open"])[0] if candidates else "Unassigned"


def layout(issues):
    assignee_opts = [{"label":a,"value":a} for a in D.get_assignees(issues) if a != "Unassigned"]
    label_opts    = [{"label":l,"value":l} for l in D.get_labels(issues)]
    ct_stats      = _cycle_time_stats(issues)
    a_stats       = _get_assignee_stats(issues)

    # Cycle time reference table
    ct_rows = []
    for t in ["Story","Task","Bug","Sub-task","Epic"]:
        s = ct_stats.get(t,{})
        if s:
            ct_rows.append(html.Tr([
                html.Td(t, style={"fontWeight":"700","fontSize":"0.72rem"}),
                html.Td(f"{s['median']}d", style={"fontFamily":"JetBrains Mono,monospace","color":C.ACCENT,"fontSize":"0.72rem"}),
                html.Td(f"{s['p75']}d",    style={"fontFamily":"JetBrains Mono,monospace","color":C.AMBER,"fontSize":"0.72rem"}),
                html.Td(str(s["count"]),   style={"color":C.MUTED,"fontSize":"0.72rem"}),
            ], style={"background":C.BG if i%2 else C.SURFACE})
            for i,_ in [(list(["Story","Task","Bug","Sub-task","Epic"]).index(t), None)])
    # flatten
    ct_rows_flat = []
    for t in ["Story","Task","Bug","Sub-task","Epic"]:
        s = ct_stats.get(t,{})
        if s:
            idx = ["Story","Task","Bug","Sub-task","Epic"].index(t)
            ct_rows_flat.append(html.Tr([
                html.Td(t,               style={"fontWeight":"700","fontSize":"0.72rem"}),
                html.Td(f"{s['median']}d",style={"fontFamily":"JetBrains Mono,monospace","color":C.ACCENT,"fontSize":"0.72rem","fontWeight":"700"}),
                html.Td(f"{s['p75']}d",  style={"fontFamily":"JetBrains Mono,monospace","color":C.AMBER,"fontSize":"0.72rem"}),
                html.Td(str(s["count"]), style={"color":C.MUTED,"fontSize":"0.72rem"}),
            ], style={"background":C.BG if idx%2 else C.SURFACE}))

    ref_card = C.card(
        html.Div("HISTORICAL CYCLE TIMES (REFERENCE)",
                 style={"fontSize":"0.55rem","fontWeight":"800","letterSpacing":"0.18em","color":C.NAVY2,"marginBottom":"10px"}),
        html.Div("Used for effort estimation and completion probability calculation.",
                 style={"fontSize":"0.65rem","color":C.MUTED,"marginBottom":"10px","fontStyle":"italic"}),
        html.Table([
            html.Thead(html.Tr([html.Th(h) for h in ["Type","Median","P75","Sample n"]],
                               style={"background":C.ACCENT2})),
            html.Tbody(ct_rows_flat),
        ], style={"width":"100%","borderCollapse":"collapse","fontSize":"0.75rem"}),
    )

    # ── Sprint Planner form ────────────────────────────────────────────────────
    planner_card = C.card(
        html.Div("SPRINT PLANNER",
                 style={"fontSize":"0.55rem","fontWeight":"800","letterSpacing":"0.18em","color":C.NAVY2,"marginBottom":"14px"}),
        html.Div("Describe the feature or goal. The system will generate a recommended Epic → Story → Task/Bug structure with effort estimates, assignee recommendations, and completion probability — then create the tickets in Jira.",
                 style={"fontSize":"0.68rem","color":C.MUTED,"marginBottom":"16px","lineHeight":"1.6"}),

        # Row 1: goal input
        html.Div([
            html.Label("Feature / Goal Description", style=LABEL),
            dcc.Textarea(id="sp-goal", placeholder="e.g. Build dataset versioning with rollback support and UI integration in Nimbus Grid module...",
                         style={**INPUT_STYLE, "minHeight":"80px","resize":"vertical"}),
        ], style={"marginBottom":"14px"}),

        # Row 2: config
        html.Div([
            html.Div([
                html.Label("Target Release / Label", style=LABEL),
                dcc.Dropdown(id="sp-label", options=label_opts, placeholder="Select label...",
                             style={"fontSize":"0.74rem","marginTop":"4px"}),
            ], style={"flex":"1"}),
            html.Div([
                html.Label("Target Deadline", style=LABEL),
                dcc.Input(id="sp-deadline", type="date",
                          style={**INPUT_STYLE,"width":"100%"}),
            ], style={"flex":"1"}),
            html.Div([
                html.Label("Team Size (approx)", style=LABEL),
                dcc.Input(id="sp-team-size", type="number", value=5, min=1, max=20,
                          style={**INPUT_STYLE,"width":"100%"}),
            ], style={"flex":"1"}),
        ], style={"display":"flex","gap":"14px","marginBottom":"14px","flexWrap":"wrap"}),

        html.Div([
            html.Button("Generate Sprint Plan", id="sp-generate-btn", n_clicks=0, style=BTN),
            html.Button("Create All Tickets in Jira", id="sp-create-btn", n_clicks=0, style=BTN2),
        ]),
        dcc.Loading(html.Div(id="sp-output"), type="circle", color=C.ACCENT),
        html.Div(id="sp-create-status",
                 style={"fontSize":"0.74rem","color":C.GREEN,"fontWeight":"700","marginTop":"8px"}),
        html.Store(id="sp-plan-store"),
    )

    # ── Sprint Confidence Analyzer ─────────────────────────────────────────────
    analyzer_card = C.card(
        html.Div("SPRINT CONFIDENCE ANALYZER",
                 style={"fontSize":"0.55rem","fontWeight":"800","letterSpacing":"0.18em","color":C.NAVY2,"marginBottom":"14px"}),
        html.Div("Analyze your current open issues to estimate sprint completion probability and identify reallocation opportunities.",
                 style={"fontSize":"0.68rem","color":C.MUTED,"marginBottom":"16px","lineHeight":"1.6"}),
        html.Div([
            html.Div([
                html.Label("Filter by Label (optional)", style=LABEL),
                dcc.Dropdown(id="sca-label", options=label_opts, multi=True,
                             placeholder="All labels...",
                             style={"fontSize":"0.74rem","marginTop":"4px"}),
            ], style={"flex":"2"}),
            html.Div([
                html.Label("Simulations", style=LABEL),
                dcc.Slider(id="sca-sims", min=100, max=2000, step=100, value=500,
                           marks={100:"100",500:"500",1000:"1k",2000:"2k"},
                           tooltip={"placement":"bottom","always_visible":True}),
            ], style={"flex":"2"}),
            html.Div([
                html.Button("Run Analysis", id="sca-run-btn", n_clicks=0, style=BTN),
            ], style={"flex":"1","display":"flex","alignItems":"flex-end"}),
        ], style={"display":"flex","gap":"14px","flexWrap":"wrap","marginBottom":"14px"}),
        dcc.Loading(html.Div(id="sca-output"), type="circle", color=C.ACCENT),
    )

    return html.Div([
        C.section("Sprint Intelligence",
                  "AI-assisted sprint planning  |  Monte Carlo confidence analysis  |  Jira ticket creation"),
        C.grid(planner_card, ref_card, cols=2),
        html.Div(style={"marginTop":"16px"}),
        analyzer_card,
    ])


def register_callbacks(app, get_issues_fn):
    from dash import Output, Input, State
    import json, requests as req, base64

    @app.callback(
        Output("sp-output","children"),
        Output("sp-plan-store","data"),
        Input("sp-generate-btn","n_clicks"),
        State("sp-goal","value"),
        State("sp-label","value"),
        State("sp-deadline","value"),
        State("sp-team-size","value"),
        prevent_initial_call=True,
    )
    def generate_plan(n, goal, label, deadline, team_size):
        if not n or not goal:
            return html.Div("Enter a feature description and click Generate.", style={"color":C.MUTED,"fontSize":"0.75rem"}), None

        issues = get_issues_fn()
        ct     = _cycle_time_stats(issues)
        a_stats= _get_assignee_stats(issues)

        # Build context for AI
        ct_summary = " | ".join(f"{t}: median {s['median']}d" for t,s in ct.items() if s)
        top_assignees = sorted(a_stats.items(), key=lambda x: x[1]["open"])[:8]
        assignee_summary = " | ".join(f"{a}: {s['open']} open" for a,s in top_assignees if a not in ("Unassigned","Former user"))

        prompt = f"""You are a Jira sprint planning expert. Generate a structured sprint plan.

Feature/Goal: {goal}
Target Label: {label or 'General'}
Deadline: {deadline or 'Not specified'}
Team size: {team_size or 5}

Historical cycle times: {ct_summary}
Current assignee load: {assignee_summary}

Generate a JSON sprint plan with this exact structure:
{{
  "epic": {{
    "summary": "Epic title",
    "description": "What this epic delivers"
  }},
  "stories": [
    {{
      "summary": "Story title",
      "description": "What this story delivers",
      "estimate_days": 5,
      "recommended_assignee": "Name from assignee list or Unassigned",
      "confidence_pct": 75,
      "tasks": [
        {{"type": "Task", "summary": "Task title", "estimate_days": 2, "recommended_assignee": "Name"}},
        {{"type": "Bug", "summary": "Expected bug: description", "estimate_days": 1, "recommended_assignee": "Name"}}
      ]
    }}
  ],
  "total_estimate_days": 14,
  "sprint_confidence_pct": 70,
  "risk_notes": "Key risks and assumptions"
}}

Return ONLY valid JSON. No markdown, no explanation."""

        try:
            resp = fetch("/v1/messages", {
                "model": "claude-sonnet-4-20250514",
                "max_tokens": 1500,
                "messages": [{"role":"user","content": prompt}]
            })
            text = resp["content"][0]["text"].strip()
            # Strip markdown fences if present
            if text.startswith("```"):
                text = text.split("```")[1]
                if text.startswith("json"): text = text[4:]
            plan = json.loads(text.strip())
            return _render_plan(plan, ct, a_stats, deadline), plan
        except Exception as e:
            return html.Div(f"Generation error: {str(e)[:200]}", style={"color":C.RED,"fontSize":"0.74rem"}), None

    @app.callback(
        Output("sp-create-status","children"),
        Input("sp-create-btn","n_clicks"),
        State("sp-plan-store","data"),
        prevent_initial_call=True,
    )
    def create_jira_tickets(n, plan):
        if not n or not plan:
            return "Generate a plan first."
        created = []
        errors  = []

        def _post(issue_type, summary, description, parent_key=None):
            body = {
                "fields": {
                    "project":   {"key": D.PROJECTS[0]},
                    "issuetype": {"name": issue_type},
                    "summary":   summary,
                    "description": {
                        "type":"doc","version":1,
                        "content":[{"type":"paragraph","content":[{"type":"text","text":description}]}]
                    },
                }
            }
            if parent_key and issue_type in ("Story","Sub-task","Task"):
                body["fields"]["parent"] = {"key": parent_key}

            basic = base64.b64encode(f"{D.EMAIL}:{D.TOKEN}".encode()).decode()
            r = req.post(
                f"https://api.atlassian.com/ex/jira/{D.CLOUD_ID}/rest/api/3/issue",
                headers={"Authorization":f"Basic {basic}","Content-Type":"application/json","Accept":"application/json"},
                json=body, timeout=15
            )
            if r.status_code == 201:
                return r.json().get("key","?")
            else:
                raise Exception(f"{r.status_code}: {r.text[:100]}")

        try:
            epic_key = _post("Epic", plan["epic"]["summary"], plan["epic"].get("description",""))
            created.append(epic_key)

            for story in plan.get("stories",[]):
                story_key = _post("Story", story["summary"], story.get("description",""), epic_key)
                created.append(story_key)
                for task in story.get("tasks",[]):
                    task_key = _post(task.get("type","Task"), task["summary"],
                                     f"Estimated: {task.get('estimate_days','')}d", story_key)
                    created.append(task_key)

            return f"Created {len(created)} tickets: {', '.join(created[:6])}{'...' if len(created)>6 else ''}"
        except Exception as e:
            return f"Error: {str(e)[:150]}"

    @app.callback(
        Output("sca-output","children"),
        Input("sca-run-btn","n_clicks"),
        State("sca-label","value"),
        State("sca-sims","value"),
        prevent_initial_call=True,
    )
    def run_confidence_analysis(n, labels, n_sims):
        if not n: return ""
        issues = get_issues_fn()
        if labels:
            filtered = [i for i in issues if any(l in i.get("labels",[]) for l in labels)]
        else:
            filtered = issues

        open_issues = [i for i in filtered if i["status"] != "Closed"]
        if not open_issues:
            return html.Div("No open issues found.", style={"color":C.MUTED})

        ct = _cycle_time_stats(issues)
        a_stats = _get_assignee_stats(issues)

        # Monte Carlo
        n_sims = int(n_sims or 500)
        results = []
        for _ in range(n_sims):
            completed = 0
            for issue in open_issues:
                dist = ct.get(issue["type"],{})
                median = dist.get("median", 14)
                std = max(2, median * 0.4)
                sampled = max(1, int(np.random.normal(median, std)))
                remaining = issue.get("days_stale", 0)
                total = remaining + sampled
                if issue.get("due"):
                    try:
                        days_left = (date.fromisoformat(issue["due"]) - date.today()).days
                        if total <= days_left: completed += 1
                    except: pass
                else:
                    # No due date — assume 50/50
                    if np.random.random() > 0.5: completed += 1
            results.append(completed / max(1, len(open_issues)))

        p_all = round(np.mean([r==1.0 for r in results])*100, 1)
        avg   = round(np.mean(results)*100, 1)

        # Reallocation analysis
        overloaded = [(a,s) for a,s in a_stats.items() if s["open"]>5 and a not in ("Unassigned","Former user")]
        underloaded= [(a,s) for a,s in a_stats.items() if s["open"]<3 and a not in ("Unassigned","Former user")]
        realloc_suggestion = None
        if overloaded and underloaded:
            from_a = max(overloaded, key=lambda x: x[1]["open"])
            to_a   = min(underloaded, key=lambda x: x[1]["open"])
            # Estimate confidence gain
            gain = min(15, (from_a[1]["open"] - to_a[1]["open"]) * 2)
            realloc_suggestion = {
                "from": from_a[0], "from_load": from_a[1]["open"],
                "to":   to_a[0],   "to_load":   to_a[1]["open"],
                "estimated_gain": gain,
                "new_confidence": min(100, p_all + gain),
            }

        # Distribution chart
        dist_fig = go.Figure(go.Histogram(
            x=[r*100 for r in results], nbinsx=20,
            marker_color=C.ACCENT, opacity=0.78,
        ))
        dist_fig.add_vline(x=avg, line_dash="dot", line_color=C.AMBER,
                           annotation_text=f"Mean {avg}%", annotation_font_size=9,
                           annotation_font_color=C.AMBER)
        dist_fig.add_vline(x=70, line_dash="dot", line_color=C.GREEN,
                           annotation_text="Target 70%", annotation_font_size=9,
                           annotation_font_color=C.GREEN)
        dist_fig.update_layout(**L, title=_t(f"Sprint Completion Distribution ({n_sims} simulations)"),
            xaxis=dict(title="% Issues Completed On Time", gridcolor=C.BORDER),
            yaxis=dict(title="Simulations", gridcolor=C.BORDER))

        # Assignee risk
        a_risk = []
        for a, s in a_stats.items():
            if a in ("Unassigned","Former user"): continue
            issues_due = [i for i in open_issues if i["assignee"]==a and i.get("due")]
            overdue_n  = sum(1 for i in issues_due if "Past Due" in i.get("due_flag",""))
            a_risk.append({"assignee":a, "open":s["open"], "overdue":overdue_n,
                           "risk": min(100, s["open"]*8 + overdue_n*20)})
        a_risk = sorted(a_risk, key=lambda x: -x["risk"])[:10]

        ar_fig = go.Figure(go.Bar(
            x=[r["assignee"].split()[0] for r in a_risk],
            y=[r["risk"] for r in a_risk],
            marker_color=[C.RED if r["risk"]>60 else (C.AMBER if r["risk"]>30 else C.GREEN) for r in a_risk],
            text=[f"{r['risk']}" for r in a_risk], textposition="outside",
        ))
        ar_fig.update_layout(**L, title=_t("Assignee Risk Score"),
            yaxis=dict(gridcolor=C.BORDER), xaxis=dict(gridcolor=C.BORDER))

        realloc_card = html.Div()
        if realloc_suggestion:
            r = realloc_suggestion
            realloc_card = html.Div([
                html.Div("REALLOCATION RECOMMENDATION",
                         style={"fontSize":"0.55rem","fontWeight":"800","letterSpacing":"0.18em","color":C.NAVY2,"margin":"14px 0 8px"}),
                html.Div([
                    html.Span(f"Move tasks from {r['from']} ({r['from_load']} open)",
                              style={"color":C.RED,"fontWeight":"700","fontSize":"0.74rem"}),
                    html.Span(" → ", style={"color":C.MUTED,"margin":"0 8px"}),
                    html.Span(f"{r['to']} ({r['to_load']} open)",
                              style={"color":C.GREEN,"fontWeight":"700","fontSize":"0.74rem"}),
                    html.Span(f"  Estimated confidence gain: +{r['estimated_gain']}% → {r['new_confidence']}%",
                              style={"color":C.ACCENT,"fontWeight":"700","fontSize":"0.72rem","marginLeft":"12px",
                                     "fontFamily":"JetBrains Mono,monospace"}),
                ], style={"padding":"10px 14px","background":C.ACCENT2,"borderRadius":"6px",
                          "border":f"1px solid {C.BORDER}","display":"flex","flexWrap":"wrap","alignItems":"center","gap":"4px"}),
            ])

        return html.Div([
            html.Div([
                _kpi_box("Full Completion Prob.", f"{p_all}%",
                         C.GREEN if p_all>=70 else (C.AMBER if p_all>=45 else C.RED)),
                _kpi_box("Avg Completion", f"{avg}%", C.ACCENT),
                _kpi_box("Open Issues", str(len(open_issues)), C.NAVY),
                _kpi_box("Simulations", str(n_sims), C.MUTED),
            ], style={"display":"flex","gap":"10px","flexWrap":"wrap","marginBottom":"14px"}),
            C.grid(C.card(_g(dist_fig,"sca-dist",260)), C.card(_g(ar_fig,"sca-risk",260)), cols=2),
            realloc_card,
        ])


def _render_plan(plan, ct, a_stats, deadline):
    """Render the AI-generated sprint plan."""
    from components import SURFACE, BG, BORDER, NAVY, NAVY2, MUTED, ACCENT, GREEN, AMBER, RED, PURPLE, TEAL

    conf = plan.get("sprint_confidence_pct", 0)
    conf_color = GREEN if conf>=70 else (AMBER if conf>=45 else RED)

    story_cards = []
    for sidx, story in enumerate(plan.get("stories",[])):
        task_rows = [
            html.Tr([
                html.Td(t.get("type","Task"), style={"color":ACCENT,"fontWeight":"700","fontSize":"0.7rem"}),
                html.Td(t.get("summary",""), style={"fontSize":"0.72rem","color":NAVY}),
                html.Td(f"{t.get('estimate_days','')}d", style={"fontFamily":"JetBrains Mono,monospace","color":AMBER,"fontSize":"0.7rem","fontWeight":"700"}),
                html.Td(t.get("recommended_assignee","Unassigned"), style={"fontSize":"0.7rem","color":MUTED}),
            ], style={"background":BG if idx%2 else SURFACE})
            for idx, t in enumerate(story.get("tasks",[]))
        ]
        story_cards.append(html.Div([
            html.Div([
                html.Span(f"Story {sidx+1}", style={"fontSize":"0.6rem","fontWeight":"800","color":PURPLE,
                          "textTransform":"uppercase","letterSpacing":"0.1em","marginRight":"8px"}),
                html.Span(story.get("summary",""), style={"fontWeight":"700","fontSize":"0.78rem","color":NAVY}),
                html.Span(f"  {story.get('estimate_days','')}d · {story.get('confidence_pct','')}% confidence",
                          style={"color":MUTED,"fontSize":"0.68rem","marginLeft":"8px","fontFamily":"JetBrains Mono,monospace"}),
                html.Span(f"  Assignee: {story.get('recommended_assignee','')}",
                          style={"color":ACCENT,"fontSize":"0.68rem","marginLeft":"8px","fontWeight":"700"}),
            ], style={"marginBottom":"8px"}),
            html.Table([
                html.Thead(html.Tr([html.Th(h) for h in ["Type","Task","Estimate","Assignee"]],
                                   style={"background":"#F5F3FF"})),
                html.Tbody(task_rows),
            ], style={"width":"100%","borderCollapse":"collapse","fontSize":"0.74rem"}),
        ], style={"background":SURFACE,"borderRadius":"8px","padding":"14px",
                  "border":f"1px solid {BORDER}","marginBottom":"10px",
                  "borderLeft":f"4px solid {PURPLE}"}))

    return html.Div([
        # Header
        html.Div([
            html.Div([
                html.Div("GENERATED SPRINT PLAN", style={"fontSize":"0.55rem","fontWeight":"800",
                          "letterSpacing":"0.18em","color":NAVY2,"marginBottom":"4px"}),
                html.Div(plan["epic"]["summary"], style={"fontWeight":"900","fontSize":"1rem","color":NAVY}),
                html.Div(plan["epic"].get("description",""), style={"color":MUTED,"fontSize":"0.74rem","marginTop":"4px"}),
            ], style={"flex":"1"}),
            html.Div([
                html.Div(f"{conf}%", style={"fontSize":"2.2rem","fontWeight":"900","color":conf_color,
                          "fontFamily":"JetBrains Mono,monospace","lineHeight":"1"}),
                html.Div("SPRINT CONFIDENCE", style={"fontSize":"0.58rem","color":MUTED,
                          "fontWeight":"700","textTransform":"uppercase","letterSpacing":"0.1em"}),
                html.Div(f"Total estimate: {plan.get('total_estimate_days','')}d",
                         style={"fontSize":"0.68rem","color":ACCENT,"marginTop":"4px",
                                "fontFamily":"JetBrains Mono,monospace","fontWeight":"700"}),
            ], style={"textAlign":"right"}),
        ], style={"display":"flex","justifyContent":"space-between","alignItems":"flex-start",
                  "padding":"16px","background":BG,"borderRadius":"8px","marginBottom":"14px",
                  "border":f"1px solid {BORDER}"}),

        # Stories
        html.Div(story_cards),

        # Risk notes
        html.Div([
            html.Div("RISK NOTES", style={"fontSize":"0.55rem","fontWeight":"800","letterSpacing":"0.18em",
                      "color":NAVY2,"marginBottom":"6px"}),
            html.Div(plan.get("risk_notes",""), style={"color":MUTED,"fontSize":"0.74rem","lineHeight":"1.6"}),
        ], style={"padding":"12px 14px","background":"#FFF7ED","borderRadius":"6px",
                  "border":f"1px solid {AMBER}33","borderLeft":f"3px solid {AMBER}"}),
    ])


def _kpi_box(label, value, color):
    return html.Div([
        html.Div(value, style={"fontSize":"1.4rem","fontWeight":"900","color":color,
                                "fontFamily":"JetBrains Mono,monospace","lineHeight":"1"}),
        html.Div(label, style={"fontSize":"0.6rem","color":C.MUTED,"marginTop":"3px",
                                "textTransform":"uppercase","letterSpacing":"0.08em"}),
    ], style={"background":C.BG,"borderRadius":"8px","padding":"12px 14px","borderLeft":f"3px solid {color}"})


def fetch(endpoint, body):
    """Call Anthropic API."""
    import requests as req
    r = req.post(f"https://api.anthropic.com{endpoint}",
                 headers={"Content-Type":"application/json"},
                 json=body, timeout=60)
    return r.json()
