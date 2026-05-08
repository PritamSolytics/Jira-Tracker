"""Sprint Intelligence — Delivery planning with statistical modelling."""
from dash import html, dcc, Input, Output, State
import plotly.graph_objects as go
import numpy as np
from collections import defaultdict
from datetime import date, timedelta
import components as C, data as D

L = dict(paper_bgcolor=C.SURFACE, plot_bgcolor=C.SURFACE,
         font=dict(color=C.TEXT, size=11, family="JetBrains Mono, monospace"),
         margin=dict(l=8,r=8,t=40,b=8))
def _t(t): return dict(text=t, font=dict(size=11, color=C.NAVY2, weight="bold"))
def _g(f,i,h=240): return dcc.Graph(figure=f,id=i,style={"height":f"{h}px"},config={"displayModeBar":False})
LB = {"fontSize":"0.63rem","fontWeight":"700","color":C.MUTED,"textTransform":"uppercase","letterSpacing":"0.08em","marginBottom":"4px","display":"block"}
INP = {"width":"100%","padding":"8px 10px","border":f"1px solid {C.BORDER}","borderRadius":"6px","fontSize":"0.74rem","fontFamily":"DM Sans,sans-serif","boxSizing":"border-box"}
BTN = {"background":C.NAVY,"color":"#fff","border":"none","borderRadius":"6px","padding":"10px 22px","cursor":"pointer","fontSize":"0.74rem","fontWeight":"800","marginRight":"10px"}
BTN2 = {**BTN,"background":C.SURFACE,"color":C.NAVY,"border":f"2px solid {C.BORDER}"}
TIP = {"fontSize":"0.61rem","color":C.MUTED,"fontStyle":"italic","marginTop":"3px","lineHeight":"1.5"}


# ── Statistical modelling ──────────────────────────────────────────────────────
def compute_cycle_stats(issues):
    """Fit distributions per issue type from historical closed issues."""
    by_type = defaultdict(list)
    for i in issues:
        if i["status"] == "Closed" and i.get("created") and i.get("updated"):
            try:
                ct = (date.fromisoformat(i["updated"]) - date.fromisoformat(i["created"])).days
                if 0 < ct <= 180:
                    by_type[i["type"]].append(ct)
            except: pass
    stats = {}
    for t, vals in by_type.items():
        v = np.array(vals)
        stats[t] = {
            "n": len(v), "median": round(float(np.median(v)), 1),
            "mean": round(float(np.mean(v)), 1), "std": round(float(np.std(v)), 1),
            "p25": round(float(np.percentile(v, 25)), 1),
            "p75": round(float(np.percentile(v, 75)), 1),
            "p90": round(float(np.percentile(v, 90)), 1),
            "raw": v.tolist(),
        }
    return stats


def compute_throughput(issues):
    """Stories/tasks closed per week per assignee."""
    by_a = defaultdict(lambda: {"closed": 0, "weeks": set()})
    for i in issues:
        if i["status"] == "Closed" and i.get("updated") and i["type"] in ("Story", "Task"):
            try:
                d = date.fromisoformat(i["updated"])
                w = str(d - timedelta(days=d.weekday()))
                by_a[i["assignee"]]["closed"] += 1
                by_a[i["assignee"]]["weeks"].add(w)
            except: pass
    result = {}
    for a, s in by_a.items():
        if a in ("Unassigned", "Former user"): continue
        weeks = max(1, len(s["weeks"]))
        result[a] = {"throughput_per_week": round(s["closed"] / weeks, 2), "total_closed": s["closed"]}
    return result


def monte_carlo_plan(stories, sprint_days, team_size, ct_stats, n_sim=500, sigma=0.5, bug_rate=0.2):
    """
    Monte Carlo simulation of a planned sprint.
    Each story contains sub-tasks. Sample cycle times, sum per story,
    check against sprint_days * team_size (capacity in person-days).
    Returns: p_complete, p_all_stories, distribution, per-story risk.
    """
    story_results = defaultdict(list)
    sprint_results = []

    for _ in range(n_sim):
        total_effort = 0
        stories_done = 0
        for story in stories:
            story_effort = 0
            for st in story.get("subtasks", []):
                dist = ct_stats.get(st["type"], ct_stats.get("Sub-task", {"mean": 3, "std": 1.5}))
                mu  = dist["mean"]
                std = max(0.5, dist["std"] * sigma)
                story_effort += max(0.5, np.random.normal(mu, std))
            # Bug buffer
            n_bugs = int(np.random.poisson(len(story.get("subtasks", [])) * bug_rate))
            bug_dist = ct_stats.get("Bug", {"mean": 2, "std": 1})
            for _ in range(n_bugs):
                story_effort += max(0.5, np.random.normal(bug_dist["mean"], bug_dist["std"] * sigma))
            story_results[story["id"]].append(story_effort)
            total_effort += story_effort
            capacity = sprint_days * team_size
            if total_effort <= capacity:
                stories_done += 1
        sprint_results.append(stories_done / max(1, len(stories)))

    per_story_risk = {}
    for story in stories:
        eff = story_results[story["id"]]
        capacity = sprint_days * team_size
        per_story_risk[story["id"]] = round(np.mean([e > capacity / max(1,len(stories)) for e in eff]) * 100, 1)

    p_all = round(np.mean([r == 1.0 for r in sprint_results]) * 100, 1)
    avg   = round(np.mean(sprint_results) * 100, 1)
    return {"p_all": p_all, "avg": avg, "distribution": sprint_results, "per_story_risk": per_story_risk}


# ── Charts ─────────────────────────────────────────────────────────────────────
def _cycle_dist_chart(ct_stats):
    """Overlay histograms of cycle times per type with fitted normal curve."""
    fig = go.Figure()
    colors = {"Story": C.PURPLE, "Sub-task": C.ACCENT, "Bug": C.RED, "Task": C.AMBER, "Epic": C.TEAL}
    for itype in ["Story", "Sub-task", "Bug", "Task"]:
        s = ct_stats.get(itype)
        if not s or s["n"] < 5: continue
        vals = s["raw"]
        fig.add_trace(go.Histogram(x=vals, nbinsx=20, name=itype,
            marker_color=colors.get(itype, C.MUTED), opacity=0.55,
            hovertemplate=f"{itype}: %{{x}}d<br>Count: %{{y}}<extra></extra>"))
        # Fitted normal curve
        x_range = np.linspace(max(0, s["mean"] - 3*s["std"]), s["mean"] + 3*s["std"], 80)
        from scipy.stats import norm
        y_norm = norm.pdf(x_range, s["mean"], s["std"]) * s["n"] * (max(vals) - min(vals)) / 20
        fig.add_trace(go.Scatter(x=x_range, y=y_norm, mode="lines", name=f"{itype} (fitted)",
            line=dict(color=colors.get(itype, C.MUTED), width=2, dash="dot"), showlegend=False))
    fig.update_layout(**L, barmode="overlay", title=_t("Cycle Time Distribution by Issue Type (Fitted Normal)"),
        xaxis=dict(title="Days", gridcolor=C.BORDER),
        yaxis=dict(title="Frequency", gridcolor=C.BORDER))
    return fig


def _throughput_chart(tp):
    top = sorted(tp.items(), key=lambda x: -x[1]["throughput_per_week"])[:12]
    fig = go.Figure(go.Bar(
        x=[a.split()[0] for a, _ in top],
        y=[s["throughput_per_week"] for _, s in top],
        marker_color=C.ACCENT, opacity=0.85,
        text=[f"{s['throughput_per_week']}" for _, s in top], textposition="outside",
        hovertemplate="<b>%{x}</b><br>Throughput: %{y} items/week<extra></extra>",
    ))
    fig.update_layout(**L, title=_t("Historical Throughput — Closed Stories & Tasks per Week"),
        yaxis=dict(title="Items/week", gridcolor=C.BORDER), xaxis=dict(gridcolor=C.BORDER))
    return fig


# ── Layout ─────────────────────────────────────────────────────────────────────
def layout(issues):
    ct    = compute_cycle_stats(issues)
    tp    = compute_throughput(issues)
    lbls  = [{"label": l, "value": l} for l in D.get_labels(issues)]
    asgns = [{"label": a, "value": a} for a in D.get_assignees(issues) if a != "Unassigned"]

    # Reference stats table
    stat_rows = []
    for t in ["Epic", "Story", "Sub-task", "Task", "Bug"]:
        s = ct.get(t)
        if not s: continue
        stat_rows.append(html.Tr([
            html.Td(t,                  style={"fontWeight":"700","fontSize":"0.72rem"}),
            html.Td(f"{s['median']}d",  style={"fontFamily":"JetBrains Mono,monospace","color":C.ACCENT,"fontWeight":"700","fontSize":"0.72rem"}),
            html.Td(f"{s['mean']}d",    style={"fontFamily":"JetBrains Mono,monospace","fontSize":"0.72rem"}),
            html.Td(f"±{s['std']}d",   style={"fontFamily":"JetBrains Mono,monospace","color":C.MUTED,"fontSize":"0.72rem"}),
            html.Td(f"{s['p75']}d",    style={"fontFamily":"JetBrains Mono,monospace","color":C.AMBER,"fontSize":"0.72rem"}),
            html.Td(f"{s['p90']}d",    style={"fontFamily":"JetBrains Mono,monospace","color":C.ORANGE,"fontSize":"0.72rem"}),
            html.Td(str(s["n"]),        style={"color":C.MUTED,"fontSize":"0.72rem"}),
        ], style={"background": C.BG if i%2 else C.SURFACE})
        for i, _ in [(["Epic","Story","Sub-task","Task","Bug"].index(t), None)])
    stat_rows_flat = []
    for idx, t in enumerate(["Epic","Story","Sub-task","Task","Bug"]):
        s = ct.get(t)
        if not s: continue
        stat_rows_flat.append(html.Tr([
            html.Td(t,               style={"fontWeight":"700","fontSize":"0.72rem"}),
            html.Td(f"{s['median']}d", style={"fontFamily":"JetBrains Mono,monospace","color":C.ACCENT,"fontWeight":"700","fontSize":"0.72rem"}),
            html.Td(f"{s['mean']}d", style={"fontFamily":"JetBrains Mono,monospace","fontSize":"0.72rem"}),
            html.Td(f"±{s['std']}d", style={"fontFamily":"JetBrains Mono,monospace","color":C.MUTED,"fontSize":"0.72rem"}),
            html.Td(f"{s['p75']}d",  style={"fontFamily":"JetBrains Mono,monospace","color":C.AMBER,"fontSize":"0.72rem"}),
            html.Td(f"{s['p90']}d",  style={"fontFamily":"JetBrains Mono,monospace","color":C.ORANGE,"fontSize":"0.72rem"}),
            html.Td(str(s["n"]),     style={"color":C.MUTED,"fontSize":"0.72rem"}),
        ], style={"background": C.BG if idx%2 else C.SURFACE}))

    ref_card = C.card(
        html.Div("HISTORICAL DELIVERY BENCHMARKS", style={"fontSize":"0.55rem","fontWeight":"800","letterSpacing":"0.18em","color":C.NAVY2,"marginBottom":"4px"}),
        html.Div("Cycle time statistics from all closed issues. Used as distribution parameters in the simulation engine.", style=TIP),
        html.Table([
            html.Thead(html.Tr([html.Th(h) for h in ["Type","Median","Mean","Std Dev","P75","P90","n"]],
                               style={"background":C.ACCENT2})),
            html.Tbody(stat_rows_flat),
        ], style={"width":"100%","borderCollapse":"collapse","fontSize":"0.75rem","marginTop":"10px"}),
        html.Div(style={"marginTop":"12px"}),
        C.grid(
            C.card(_g(_cycle_dist_chart(ct), "sp-cycle-dist", 260)),
            C.card(_g(_throughput_chart(tp), "sp-throughput", 260)),
            cols=2
        ),
    )

    # Simulation config
    sim_config = C.card(
        html.Div("SIMULATION PARAMETERS", style={"fontSize":"0.55rem","fontWeight":"800","letterSpacing":"0.18em","color":C.NAVY2,"marginBottom":"8px"}),
        html.Div([
            html.Div([
                html.Label("Simulations (n)", style=LB),
                dcc.Slider(id="sp-sims", min=100, max=2000, step=100, value=500,
                           marks={100:"100",500:"500",1000:"1k",2000:"2k"},
                           tooltip={"placement":"bottom","always_visible":True}),
                html.Div("Number of Monte Carlo runs. Higher = more stable probability estimate.", style=TIP),
            ], style={"flex":"2"}),
            html.Div([
                html.Label("Cycle Time Uncertainty (σ scale)", style=LB),
                dcc.Slider(id="sp-sigma", min=0.2, max=2.0, step=0.1, value=0.5,
                           marks={0.2:"Low",0.5:"Default",1.0:"High",2.0:"Very High"},
                           tooltip={"placement":"bottom","always_visible":True}),
                html.Div("Scales standard deviation of sampled cycle times. 1.0 = use historical std directly.", style=TIP),
            ], style={"flex":"2"}),
            html.Div([
                html.Label("Bug Buffer Rate", style=LB),
                dcc.Slider(id="sp-bug-rate", min=0.0, max=0.5, step=0.05, value=0.2,
                           marks={0:"0%",0.2:"20%",0.5:"50%"},
                           tooltip={"placement":"bottom","always_visible":True}),
                html.Div("Expected bugs per planned sub-task. Modelled as Poisson(λ = n_subtasks × rate).", style=TIP),
            ], style={"flex":"2"}),
            html.Div([
                html.Label("Sprint Duration (days)", style=LB),
                dcc.Input(id="sp-sprint-days", type="number", value=14, min=5, max=30, style={**INP}),
                html.Div("Working days in the sprint. Capacity = sprint_days × team_size.", style=TIP),
            ], style={"flex":"1"}),
            html.Div([
                html.Label("Team Size", style=LB),
                dcc.Input(id="sp-team-size", type="number", value=5, min=1, max=20, style={**INP}),
                html.Div("Engineers available. Capacity = sprint_days × team_size person-days.", style=TIP),
            ], style={"flex":"1"}),
        ], style={"display":"flex","gap":"20px","flexWrap":"wrap"}),
    )

    # Planner
    planner_card = C.card(
        html.Div("SPRINT STRUCTURE PLANNER", style={"fontSize":"0.55rem","fontWeight":"800","letterSpacing":"0.18em","color":C.NAVY2,"marginBottom":"4px"}),
        html.Div([
            html.Div("Structure: Epic (multi-sprint) → Story (sprint-sized) → Sub-task (granular work) + Bug buffer.", style=TIP),
            html.Div("Describe your delivery goal. The system generates a properly structured hierarchy with statistical effort estimates and Monte Carlo completion probability.", style={**TIP, "marginTop":"4px"}),
        ]),
        html.Div(style={"height":"10px"}),
        html.Label("Delivery Goal / Feature Description", style=LB),
        dcc.Textarea(id="sp-goal",
                     placeholder="e.g. Add dataset versioning with rollback capability and grid UI integration...",
                     style={**INP,"minHeight":"72px","resize":"vertical","marginBottom":"12px"}),
        html.Div([
            html.Div([
                html.Label("Target Label / Release", style=LB),
                dcc.Dropdown(id="sp-label", options=lbls, placeholder="Select...", style={"fontSize":"0.74rem"}),
            ], style={"flex":"1"}),
            html.Div([
                html.Label("Sprint End Date", style=LB),
                dcc.Input(id="sp-deadline", type="date", style={**INP}),
            ], style={"flex":"1"}),
            html.Div([
                html.Label("Epic Context (optional)", style=LB),
                dcc.Input(id="sp-epic-context", type="text",
                          placeholder="Name of the parent Epic if applicable",
                          style={**INP}),
            ], style={"flex":"2"}),
        ], style={"display":"flex","gap":"14px","marginBottom":"14px","flexWrap":"wrap"}),
        html.Div([
            html.Button("Generate Sprint Plan", id="sp-generate-btn", n_clicks=0, style=BTN),
            html.Button("Create Tickets in Jira", id="sp-create-btn", n_clicks=0, style=BTN2),
        ]),
        dcc.Loading(html.Div(id="sp-output"), type="circle", color=C.ACCENT),
        html.Div(id="sp-create-status", style={"fontSize":"0.74rem","color":C.GREEN,"fontWeight":"700","marginTop":"8px"}),
        dcc.Store(id="sp-plan-store"),
    )

    # Confidence Analyzer
    analyzer_card = C.card(
        html.Div("DELIVERY CONFIDENCE ANALYZER", style={"fontSize":"0.55rem","fontWeight":"800","letterSpacing":"0.18em","color":C.NAVY2,"marginBottom":"4px"}),
        html.Div("Applies Monte Carlo simulation to current open issues to estimate sprint completion probability given remaining capacity.", style=TIP),
        html.Div(style={"height":"10px"}),
        html.Div([
            html.Div([
                html.Label("Scope — Label Filter", style=LB),
                dcc.Dropdown(id="sca-label", options=lbls, multi=True,
                             placeholder="All labels...", style={"fontSize":"0.74rem"}),
            ], style={"flex":"2"}),
            html.Div([
                html.Label("Velocity Adjustment", style=LB),
                dcc.Slider(id="sca-velocity", min=0.5, max=1.5, step=0.1, value=1.0,
                           marks={0.5:"−50%",1.0:"Default",1.5:"+50%"},
                           tooltip={"placement":"bottom","always_visible":True}),
                html.Div("Scale historical cycle time mean to model team capacity changes.", style=TIP),
            ], style={"flex":"3"}),
            html.Div([
                html.Button("Run Analysis", id="sca-run-btn", n_clicks=0, style=BTN),
            ], style={"flex":"1","display":"flex","alignItems":"flex-end"}),
        ], style={"display":"flex","gap":"14px","flexWrap":"wrap","marginBottom":"12px"}),
        dcc.Loading(html.Div(id="sca-output"), type="circle", color=C.ACCENT),
    )

    return html.Div([
        C.section("Sprint Intelligence",
                  "Statistical sprint planning  |  Monte Carlo completion simulation  |  Jira ticket creation"),
        sim_config,
        html.Div(style={"height":"16px"}),
        C.grid(planner_card, ref_card, cols=2),
        html.Div(style={"height":"16px"}),
        analyzer_card,
    ])


# ── Callbacks ──────────────────────────────────────────────────────────────────
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
        State("sp-epic-context","value"),
        State("sp-sprint-days","value"),
        State("sp-team-size","value"),
        State("sp-sims","value"),
        State("sp-sigma","value"),
        State("sp-bug-rate","value"),
        prevent_initial_call=True,
    )
    def generate(n, goal, label, deadline, epic_ctx, sprint_days, team_size, n_sims, sigma, bug_rate):
        if not n or not goal:
            return html.Div("Enter a delivery goal and click Generate.", style={"color":C.MUTED,"fontSize":"0.75rem"}), None
        issues  = get_issues_fn()
        ct      = compute_cycle_stats(issues)
        tp      = compute_throughput(issues)
        ct_str  = " | ".join(f"{t}: median {s['median']}d ±{s['std']}d" for t, s in ct.items() if s["n"] >= 5)
        top_a   = sorted(tp.items(), key=lambda x: -x[1]["throughput_per_week"])[:6]
        a_str   = " | ".join(f"{a}: {s['throughput_per_week']}/week" for a, s in top_a)
        capacity = int(sprint_days or 14) * int(team_size or 5)

        prompt = f"""You are a Jira delivery planning expert. Generate a structured sprint plan following this exact Jira hierarchy:
- Epic: multi-sprint container (do not estimate days — it spans multiple sprints)
- Story: sprint-sized deliverable (should fit within one sprint)
- Sub-task: granular work item under a Story (1–3 days each typically)
- Bug: defect items (separate from Sub-tasks, added as buffer)

Goal: {goal}
Epic context: {epic_ctx or 'New Epic'}
Label: {label or 'General'}
Sprint end date: {deadline or 'Not specified'}
Sprint capacity: {capacity} person-days ({sprint_days} days x {team_size} engineers)
Historical cycle times: {ct_str}
Team throughput: {a_str}

Return ONLY valid JSON:
{{"epic":{{"summary":"string","description":"string","multi_sprint":true}},
  "stories":[
    {{"id":"s1","summary":"string","description":"string","estimate_days":5,
      "fits_in_sprint":true,
      "subtasks":[
        {{"type":"Sub-task","summary":"string","estimate_days":2,"assignee":"string"}},
        {{"type":"Sub-task","summary":"string","estimate_days":1,"assignee":"string"}}
      ]
    }}
  ],
  "total_subtask_days":12,
  "sprint_confidence_note":"string",
  "risk_notes":"string"
}}"""

        try:
            r = req.post("https://api.anthropic.com/v1/messages",
                         headers={"Content-Type":"application/json"},
                         json={"model":"claude-sonnet-4-20250514","max_tokens":2000,
                               "messages":[{"role":"user","content":prompt}]}, timeout=60)
            text = r.json()["content"][0]["text"].strip()
            if "```" in text:
                text = text.split("```")[1]
                text = text[4:] if text.startswith("json") else text
            plan = json.loads(text.strip())

            # Run Monte Carlo on generated plan
            mc = monte_carlo_plan(
                plan.get("stories", []),
                int(sprint_days or 14), int(team_size or 5), ct,
                int(n_sims or 500), float(sigma or 0.5), float(bug_rate or 0.2)
            )
            return _render_plan(plan, mc, ct, int(sprint_days or 14),
                                int(team_size or 5), int(n_sims or 500),
                                float(sigma or 0.5), float(bug_rate or 0.2)), plan
        except Exception as e:
            return html.Div(f"Error: {str(e)[:200]}", style={"color":C.RED,"fontSize":"0.74rem"}), None

    @app.callback(
        Output("sp-create-status","children"),
        Input("sp-create-btn","n_clicks"),
        State("sp-plan-store","data"),
        prevent_initial_call=True,
    )
    def create_tickets(n, plan):
        if not n or not plan: return "Generate a plan first."
        created = []
        def _post(itype, summary, desc, parent=None):
            body = {"fields":{"project":{"key":D.PROJECTS[0]},"issuetype":{"name":itype},
                              "summary":summary,
                              "description":{"type":"doc","version":1,
                                             "content":[{"type":"paragraph","content":[{"type":"text","text":desc}]}]}}}
            if parent and itype in ("Story","Sub-task","Task"): body["fields"]["parent"] = {"key":parent}
            basic = base64.b64encode(f"{D.EMAIL}:{D.TOKEN}".encode()).decode()
            r = req.post(f"https://api.atlassian.com/ex/jira/{D.CLOUD_ID}/rest/api/3/issue",
                         headers={"Authorization":f"Basic {basic}","Content-Type":"application/json","Accept":"application/json"},
                         json=body, timeout=15)
            if r.status_code == 201: return r.json().get("key","?")
            raise Exception(f"{r.status_code}: {r.text[:80]}")
        try:
            ek = _post("Epic", plan["epic"]["summary"], plan["epic"].get("description",""))
            created.append(ek)
            for s in plan.get("stories",[]):
                sk = _post("Story", s["summary"], s.get("description",""), ek)
                created.append(sk)
                for st in s.get("subtasks",[]):
                    tk = _post(st.get("type","Sub-task"), st["summary"],
                               f"Estimate: {st.get('estimate_days','')}d", sk)
                    created.append(tk)
            return f"Created {len(created)} items: {', '.join(created[:8])}{'…' if len(created)>8 else ''}"
        except Exception as e:
            return f"Error: {str(e)[:150]}"

    @app.callback(
        Output("sca-output","children"),
        Input("sca-run-btn","n_clicks"),
        State("sca-label","value"),
        State("sp-sims","value"),
        State("sp-sigma","value"),
        State("sp-bug-rate","value"),
        State("sp-sprint-days","value"),
        State("sp-team-size","value"),
        State("sca-velocity","value"),
        prevent_initial_call=True,
    )
    def run_analyzer(n, labels, n_sims, sigma, bug_rate, sprint_days, team_size, velocity):
        if not n: return ""
        issues  = get_issues_fn()
        scoped  = [i for i in issues if not labels or any(l in i.get("labels",[]) for l in labels)]
        open_i  = [i for i in scoped if i["status"] != "Closed"]
        if not open_i: return html.Div("No open issues in scope.", style={"color":C.MUTED})
        ct      = compute_cycle_stats(issues)
        nsims   = int(n_sims or 500)
        vel     = float(velocity or 1.0)
        cap     = int(sprint_days or 14) * int(team_size or 5)

        # Build story-like groups from open issues
        stories = [{"id":i["key"],"summary":i["summary"],
                    "subtasks":[{"type":i["type"],"estimate_days":ct.get(i["type"],{"mean":7})["mean"]}]}
                   for i in open_i]
        mc = monte_carlo_plan(stories, int(sprint_days or 14), int(team_size or 5),
                              ct, nsims, float(sigma or 0.5), float(bug_rate or 0.2))

        dist_fig = go.Figure(go.Histogram(
            x=[r*100 for r in mc["distribution"]], nbinsx=20,
            marker_color=C.ACCENT, opacity=0.78,
            hovertemplate="Completion: %{x:.0f}%<br>Count: %{y}<extra></extra>"))
        for pct, color, label in [(mc["avg"],"#D97706",f"Mean {mc['avg']}%"),(70,C.GREEN,"Target 70%")]:
            dist_fig.add_vline(x=pct, line_dash="dot", line_color=color,
                               annotation_text=label, annotation_font_color=color, annotation_font_size=9)
        dist_fig.update_layout(**L, title=_t(f"Sprint Completion Distribution — {nsims} simulations"),
            xaxis=dict(title="% Issues Completed On Time", gridcolor=C.BORDER, range=[0,100]),
            yaxis=dict(title="Simulation Count", gridcolor=C.BORDER))

        kpis = html.Div([
            _kpi("Full Completion", f"{mc['p_all']}%",
                 C.GREEN if mc['p_all']>=70 else (C.AMBER if mc['p_all']>=45 else C.RED),
                 "P(all issues complete on time)"),
            _kpi("Mean Completion", f"{mc['avg']}%", C.ACCENT, "Avg fraction completed across simulations"),
            _kpi("Capacity (person-days)", str(cap), C.NAVY, f"{sprint_days}d × {team_size} engineers"),
            _kpi("Issues in Scope", str(len(open_i)), C.MUTED, "Open issues included"),
        ], style={"display":"flex","gap":"10px","flexWrap":"wrap","marginBottom":"14px"})

        return html.Div([kpis, C.card(_g(dist_fig, "sca-dist", 280))])


def _render_plan(plan, mc, ct, sprint_days, team_size, n_sims, sigma, bug_rate):
    conf  = mc["p_all"]
    cc    = C.GREEN if conf>=70 else (C.AMBER if conf>=45 else C.RED)
    cap   = sprint_days * team_size

    dist_fig = go.Figure(go.Histogram(
        x=[r*100 for r in mc["distribution"]], nbinsx=15,
        marker_color=C.ACCENT, opacity=0.78,
        hovertemplate="Completion: %{x:.0f}%<br>Count: %{y}<extra></extra>"))
    dist_fig.add_vline(x=conf, line_dash="dot", line_color=cc,
                       annotation_text=f"P(all) {conf}%", annotation_font_color=cc, annotation_font_size=9)
    dist_fig.update_layout(**L, title=_t(f"Monte Carlo Distribution ({n_sims} simulations · σ={sigma} · bug rate={int(bug_rate*100)}%)"),
        xaxis=dict(title="% Stories Completed", gridcolor=C.BORDER, range=[0,110]),
        yaxis=dict(title="Simulations", gridcolor=C.BORDER))

    story_cards = [_story_card(s, mc["per_story_risk"].get(s["id"], 0)) for s in plan.get("stories",[])]

    return html.Div([
        # Header
        html.Div([
            html.Div([
                html.Div("GENERATED SPRINT PLAN",
                         style={"fontSize":"0.55rem","fontWeight":"800","letterSpacing":"0.18em","color":C.NAVY2,"marginBottom":"4px"}),
                html.Div(f"Epic: {plan['epic']['summary']}",
                         style={"fontWeight":"900","fontSize":"0.92rem","color":C.NAVY}),
                html.Div("Multi-sprint container — this sprint covers the stories below.",
                         style={"color":C.MUTED,"fontSize":"0.68rem","marginTop":"2px","fontStyle":"italic"}),
                html.Div(plan["epic"].get("description",""),
                         style={"color":C.TEXT,"fontSize":"0.73rem","marginTop":"6px","lineHeight":"1.5"}),
            ], style={"flex":"1"}),
            html.Div([
                html.Div(f"{conf}%",
                         style={"fontSize":"2rem","fontWeight":"900","color":cc,
                                "fontFamily":"JetBrains Mono,monospace","lineHeight":"1","textAlign":"right"}),
                html.Div("SPRINT COMPLETION PROBABILITY",
                         style={"fontSize":"0.55rem","color":C.MUTED,"fontWeight":"700","textTransform":"uppercase","letterSpacing":"0.1em","textAlign":"right"}),
                html.Div(f"Capacity: {cap} person-days  |  σ={sigma}  |  Bug buffer: {int(bug_rate*100)}%",
                         style={"fontSize":"0.63rem","color":C.ACCENT,"marginTop":"4px",
                                "fontFamily":"JetBrains Mono,monospace","textAlign":"right"}),
            ]),
        ], style={"display":"flex","justifyContent":"space-between","alignItems":"flex-start",
                  "padding":"16px","background":C.BG,"borderRadius":"8px","marginBottom":"12px",
                  "border":f"1px solid {C.BORDER}"}),

        # MC chart
        C.card(_g(dist_fig, "sp-plan-dist", 220)),
        html.Div(style={"height":"10px"}),

        # Stories
        *story_cards,

        # Risk note
        html.Div([
            html.Div("DELIVERY RISK ASSESSMENT",
                     style={"fontSize":"0.55rem","fontWeight":"800","letterSpacing":"0.18em","color":C.NAVY2,"marginBottom":"6px"}),
            html.Div(plan.get("sprint_confidence_note",""),
                     style={"color":C.TEXT,"fontSize":"0.73rem","lineHeight":"1.6","marginBottom":"6px"}),
            html.Div(plan.get("risk_notes",""),
                     style={"color":C.MUTED,"fontSize":"0.72rem","lineHeight":"1.6"}),
        ], style={"padding":"12px 14px","background":"#FFFBEB","borderRadius":"6px",
                  "border":f"1px solid {C.AMBER}33","borderLeft":f"3px solid {C.AMBER}"}),
    ])


def _story_card(story, slip_risk):
    risk_color = C.RED if slip_risk>=60 else (C.AMBER if slip_risk>=30 else C.GREEN)
    st_rows = [html.Tr([
        html.Td(st.get("type","Sub-task"), style={"color":C.ACCENT,"fontWeight":"700","fontSize":"0.7rem","width":"80px"}),
        html.Td(st.get("summary",""),     style={"fontSize":"0.72rem","color":C.NAVY}),
        html.Td(f"{st.get('estimate_days','')}d",
                style={"fontFamily":"JetBrains Mono,monospace","color":C.AMBER,"fontWeight":"700","fontSize":"0.7rem","width":"50px"}),
        html.Td(st.get("assignee",""),   style={"color":C.MUTED,"fontSize":"0.7rem","width":"120px"}),
    ], style={"background":C.BG if idx%2 else C.SURFACE})
    for idx, st in enumerate(story.get("subtasks",[]))]

    return html.Div([
        html.Div([
            html.Span("STORY", style={"fontSize":"0.58rem","fontWeight":"900","color":C.PURPLE,
                       "background":"#F5F3FF","padding":"2px 8px","borderRadius":"4px","marginRight":"8px",
                       "fontFamily":"JetBrains Mono,monospace"}),
            html.Span(story.get("summary",""), style={"fontWeight":"700","fontSize":"0.78rem","color":C.NAVY}),
            html.Span(f"  {story.get('estimate_days','')}d estimated",
                      style={"color":C.AMBER,"fontWeight":"700","fontSize":"0.68rem","marginLeft":"8px","fontFamily":"JetBrains Mono,monospace"}),
            html.Span(f"  Delivery Risk: {slip_risk}%",
                      style={"color":risk_color,"fontWeight":"700","fontSize":"0.68rem","marginLeft":"8px","fontFamily":"JetBrains Mono,monospace"}),
            html.Span(" Fits in sprint" if story.get("fits_in_sprint") else " May span sprint",
                      style={"fontSize":"0.65rem","color":C.GREEN if story.get("fits_in_sprint") else C.AMBER,"marginLeft":"8px"}),
        ], style={"marginBottom":"8px","display":"flex","alignItems":"center","flexWrap":"wrap","gap":"4px"}),
        html.Div(story.get("description",""),
                 style={"color":C.MUTED,"fontSize":"0.7rem","marginBottom":"8px","lineHeight":"1.5"}),
        html.Table([
            html.Thead(html.Tr([html.Th(h) for h in ["Type","Sub-task","Estimate","Assignee"]],
                               style={"background":"#F5F3FF"})),
            html.Tbody(st_rows),
        ], style={"width":"100%","borderCollapse":"collapse","fontSize":"0.73rem"}) if st_rows else html.Div(),
    ], style={"background":C.SURFACE,"borderRadius":"8px","padding":"14px",
              "border":f"1px solid {C.BORDER}","marginBottom":"8px",
              "borderLeft":f"4px solid {C.PURPLE}"})


def _kpi(label, value, color, tooltip=""):
    return html.Div([
        html.Div(value, style={"fontSize":"1.4rem","fontWeight":"900","color":color,
                                "fontFamily":"JetBrains Mono,monospace","lineHeight":"1"}),
        html.Div(label, style={"fontSize":"0.6rem","color":C.MUTED,"marginTop":"3px",
                                "textTransform":"uppercase","letterSpacing":"0.08em"}),
        html.Div(tooltip, style={"fontSize":"0.6rem","color":C.MUTED,"fontStyle":"italic",
                                  "marginTop":"2px","lineHeight":"1.4"}) if tooltip else None,
    ], style={"background":C.BG,"borderRadius":"8px","padding":"12px 14px",
               "borderLeft":f"3px solid {color}","minWidth":"130px"})
