"""
intelligence_page.py — Operational Intelligence
Delivery Predictability Signal · Operational Risk Score · Dependency Propagation
"""
from dash import html, dcc, dash_table
import plotly.graph_objects as go
from collections import defaultdict, Counter
from datetime import date, timedelta
import numpy as np
import components as C
import store as ST

L = dict(paper_bgcolor=C.SURFACE, plot_bgcolor=C.SURFACE,
         font=dict(color=C.TEXT, size=11, family="JetBrains Mono, monospace"),
         margin=dict(l=8,r=8,t=40,b=8))
def _t(t): return dict(text=t, font=dict(size=11, color=C.NAVY2, weight="bold"))
def _g(fig, gid, h=260): return dcc.Graph(figure=fig, id=gid, style={"height":f"{h}px"}, config={"displayModeBar":False})


# ── 1. EXECUTION RELIABILITY INDEX ────────────────────────────────────────────
def delivery_predictability(issues):
    """
    Per-assignee predictability score based on standup log ETAs.
    ERI = (kept promises / total promises with ETA) * 100
    Adjusted by days-over on broken ones.
    """
    logs = ST._load()
    key_map = {i["key"]: i for i in issues}
    today = date.today().isoformat()

    stats = defaultdict(lambda: {"kept":0,"broken":0,"total_days_over":0,"promises":0})
    for e in logs:
        if not e.get("eta"): continue
        a = e.get("assignee","Unknown")
        stats[a]["promises"] += 1
        issue = key_map.get(e["issue_key"],{})
        closed = issue.get("status","") in ("Closed","Rejected") or e.get("status") == "resolved"
        if closed:
            stats[a]["kept"] += 1
        elif e["eta"] < today:
            stats[a]["broken"] += 1
            stats[a]["total_days_over"] += (date.today() - date.fromisoformat(e["eta"])).days

    rows = []
    for a, s in stats.items():
        if s["promises"] < 1: continue
        base = s["kept"] / max(1, s["promises"]) * 100
        penalty = min(30, s["total_days_over"] * 0.5)  # max 30pt penalty
        eri = round(max(0, base - penalty), 1)
        rows.append({
            "assignee": a, "eri": eri,
            "promises": s["promises"], "kept": s["kept"],
            "broken": s["broken"],
            "avg_days_over": round(s["total_days_over"] / max(1, s["broken"]), 1),
            "color": C.GREEN if eri >= 70 else (C.AMBER if eri >= 40 else C.RED),
        })
    return sorted(rows, key=lambda x: -x["eri"])


def _eri_chart(rows):
    if not rows:
        return go.Figure()
    colors = [r["color"] for r in rows]
    fig = go.Figure(go.Bar(
        x=[r["assignee"].split()[0] for r in rows],
        y=[r["eri"] for r in rows],
        marker_color=colors,
        text=[f"{r['eri']}%" for r in rows],
        textposition="outside",
        textfont=dict(size=10, weight="bold"),
        hovertemplate="<b>%{x}</b><br>ERI: %{y}%<extra></extra>",
    ))
    fig.add_hline(y=70, line_dash="dot", line_color=C.GREEN, annotation_text="Good (70%)", annotation_font_size=9)
    fig.add_hline(y=40, line_dash="dot", line_color=C.AMBER, annotation_text="Marginal (40%)", annotation_font_size=9)
    fig.update_layout(**L, title=_t("Delivery Predictability Signal by Assignee"),
        yaxis=dict(title="ERI %", gridcolor=C.BORDER, range=[0,115]),
        xaxis=dict(gridcolor=C.BORDER))
    return fig


# ── 2. OPERATIONAL RISK SCORE ─────────────────────────────────────────────────
def operational_risk_scores(issues):
    """
    Composite risk score per assignee combining:
    overdue rate, stale rate, blocker count, bug rate, ERI (inverted)
    Weights: overdue=0.30, stale=0.25, blockers=0.20, bugs=0.15, eri=0.10
    """
    eri_map = {r["assignee"]: r["eri"] for r in delivery_predictability(issues)}

    by_a = defaultdict(list)
    for i in issues: by_a[i["assignee"]].append(i)

    blocker_count = defaultdict(int)
    for i in issues:
        for lnk in i.get("links",[]):
            if "block" in lnk.get("type","").lower() and lnk["direction"]=="outward":
                blocker_count[i["assignee"]] += 1

    rows = []
    for a, items in by_a.items():
        if a == "Unassigned": continue
        open_i = [i for i in items if i["status"] != "Closed"]
        if not open_i: continue
        n = len(open_i)
        overdue  = sum(1 for i in open_i if "Past Due" in i.get("due_flag","")) / n
        stale    = sum(1 for i in open_i if i.get("days_stale",0) > 7) / n
        bugs     = sum(1 for i in items if i["type"] == "Bug") / max(1, len(items))
        bloc_n   = min(1.0, blocker_count[a] / 5)  # normalise, cap at 5
        eri_inv  = (100 - eri_map.get(a, 50)) / 100  # lower ERI = higher risk

        risk = (overdue*0.30 + stale*0.25 + bloc_n*0.20 + bugs*0.15 + eri_inv*0.10) * 100
        rows.append({
            "assignee": a, "risk": round(risk, 1),
            "open": n, "overdue": int(overdue*n),
            "stale": int(stale*n), "blockers": blocker_count[a],
            "eri": eri_map.get(a, "—"),
            "color": C.RED if risk>=60 else (C.AMBER if risk>=35 else C.GREEN),
        })
    return sorted(rows, key=lambda x: -x["risk"])


def _risk_chart(rows):
    if not rows: return go.Figure()
    fig = go.Figure(go.Bar(
        x=[r["assignee"].split()[0] for r in rows[:15]],
        y=[r["risk"] for r in rows[:15]],
        marker_color=[r["color"] for r in rows[:15]],
        text=[f"{r['risk']}" for r in rows[:15]],
        textposition="outside",
        hovertemplate="<b>%{x}</b><br>Risk Score: %{y}<extra></extra>",
    ))
    fig.add_hline(y=60, line_dash="dot", line_color=C.RED, annotation_text="High Risk", annotation_font_size=9)
    fig.add_hline(y=35, line_dash="dot", line_color=C.AMBER, annotation_text="Moderate", annotation_font_size=9)
    fig.update_layout(**L, title=_t("Operational Risk Score by Assignee"),
        yaxis=dict(title="Risk Score (0-100)", gridcolor=C.BORDER),
        xaxis=dict(gridcolor=C.BORDER))
    return fig


def _initiative_risk(issues):
    """Risk score per initiative/label."""
    by_label = defaultdict(list)
    for i in issues:
        for l in (i.get("labels",[]) or ["(No Label)"]): by_label[l].append(i)

    rows = []
    for label, items in by_label.items():
        open_i = [i for i in items if i["status"] != "Closed"]
        if not open_i: continue
        n = len(open_i)
        overdue = sum(1 for i in open_i if "Past Due" in i.get("due_flag","")) / n
        stale   = sum(1 for i in open_i if i.get("days_stale",0) > 7) / n
        bugs    = sum(1 for i in items if i["type"]=="Bug") / max(1,len(items))
        risk    = (overdue*0.40 + stale*0.35 + bugs*0.25) * 100
        rows.append({"label":label,"risk":round(risk,1),"open":n,
                     "overdue":int(overdue*n),"stale":int(stale*n),
                     "color":C.RED if risk>=60 else (C.AMBER if risk>=35 else C.GREEN)})
    return sorted(rows, key=lambda x: -x["risk"])


# ── 3. DEPENDENCY PROPAGATION ─────────────────────────────────────────────────
def dependency_propagation(issues, max_depth=3):
    """
    BFS from each blocked/blocker issue to estimate cascade impact.
    Returns top issues by downstream impact count.
    """
    import networkx as nx
    key_map = {i["key"]: i for i in issues}
    G = nx.DiGraph()
    for i in issues:
        for lnk in i.get("links",[]):
            if "block" in lnk.get("type","").lower() and lnk["direction"]=="outward":
                G.add_edge(i["key"], lnk["key"])

    results = []
    for node in G.nodes():
        if node not in key_map: continue
        issue = key_map[node]
        if issue.get("status") == "Closed": continue
        # BFS to count downstream affected nodes within max_depth
        try:
            descendants = nx.descendants(G, node)
            downstream = [d for d in descendants if d in key_map and key_map[d].get("status") != "Closed"]
        except: downstream = []

        if not downstream: continue

        # Estimate cascade delay: avg stale days of downstream issues
        cascade_days = round(np.mean([key_map[d].get("days_stale",0) for d in downstream if d in key_map]), 1)
        assignees_affected = len(set(key_map[d].get("assignee","") for d in downstream if d in key_map))

        results.append({
            "key":        node,
            "assignee":   issue.get("assignee",""),
            "summary":    issue.get("summary","")[:60],
            "status":     issue.get("status",""),
            "priority":   issue.get("priority",""),
            "downstream": len(downstream),
            "cascade_days": cascade_days,
            "assignees_affected": assignees_affected,
            "impact_score": round(len(downstream) * 10 + cascade_days * 0.5, 1),
        })
    return sorted(results, key=lambda x: -x["impact_score"])


def _propagation_chart(prop_rows):
    if not prop_rows: return go.Figure()
    top = prop_rows[:12]
    fig = go.Figure()
    fig.add_trace(go.Bar(
        name="Downstream Issues",
        x=[r["key"] for r in top],
        y=[r["downstream"] for r in top],
        marker_color=C.RED, opacity=0.85,
        hovertemplate="<b>%{x}</b><br>Downstream: %{y}<extra></extra>",
    ))
    fig.add_trace(go.Scatter(
        name="Cascade Days",
        x=[r["key"] for r in top],
        y=[r["cascade_days"] for r in top],
        mode="lines+markers",
        line=dict(color=C.AMBER, width=2),
        marker=dict(size=7),
        yaxis="y2",
        hovertemplate="<b>%{x}</b><br>Avg Cascade Days: %{y}<extra></extra>",
    ))
    fig.update_layout(**L, title=_t("Dependency Cascade Impact"),
        xaxis=dict(tickangle=-30, gridcolor=C.BORDER),
        yaxis=dict(title="Downstream Issues", gridcolor=C.BORDER),
        yaxis2=dict(title="Avg Cascade Days", overlaying="y", side="right", gridcolor=C.BORDER),
        barmode="group")
    return fig


# ── 4. EXECUTIVE DECISION LAYER ───────────────────────────────────────────────
def executive_alerts(issues, risk_rows, prop_rows, eri_rows):
    """Generate ranked natural-language decision alerts."""
    alerts = []
    today = date.today().isoformat()

    # Blocker cascade alerts
    for r in prop_rows[:3]:
        alerts.append({
            "level": "CRITICAL",
            "message": f"{r['key']} ({r['assignee'].split()[0] if r['assignee'] else '?'}) is blocking {r['downstream']} downstream tasks across {r['assignees_affected']} assignees — avg cascade delay {r['cascade_days']}d",
            "color": C.RED,
        })

    # High-risk assignees
    critical_risk = [r for r in risk_rows if r["risk"] >= 60][:2]
    for r in critical_risk:
        alerts.append({
            "level": "HIGH",
            "message": f"{r['assignee'].split()[0]} — Risk Score {r['risk']}/100: {r['overdue']} overdue, {r['stale']} stale, {r['blockers']} blockers",
            "color": C.RED,
        })

    # Low predictability assignees
    low_eri = [r for r in eri_rows if r["eri"] < 40 and r["promises"] >= 2][:2]
    for r in low_eri:
        alerts.append({
            "level": "WATCH",
            "message": f"{r['assignee'].split()[0]} has {r['eri']}% execution predictability — {r['broken']} of {r['promises']} commitments missed",
            "color": C.AMBER,
        })

    # Overdue surge
    past_due = [i for i in issues if "Past Due" in i.get("due_flag","") and i["status"] != "Closed"]
    if len(past_due) > 10:
        alerts.append({
            "level": "HIGH",
            "message": f"{len(past_due)} open issues past due date — delivery timeline at risk",
            "color": C.ORANGE,
        })

    # Unassigned open
    unassigned = [i for i in issues if i["assignee"] == "Unassigned" and i["status"] != "Closed"]
    if unassigned:
        alerts.append({
            "level": "WATCH",
            "message": f"{len(unassigned)} open issues have no assignee — ownership gap",
            "color": C.AMBER,
        })

    if not alerts:
        alerts.append({"level":"OK","message":"No critical operational risks detected.","color":C.GREEN})

    return alerts


# ── PAGE LAYOUT ───────────────────────────────────────────────────────────────
def layout(issues):
    eri_rows  = delivery_predictability(issues)
    risk_rows = operational_risk_scores(issues)
    init_risk = _initiative_risk(issues)
    prop_rows = dependency_propagation(issues)
    exec_alerts = executive_alerts(issues, risk_rows, prop_rows, eri_rows)

    # ── Executive alert strip ──────────────────────────────────────────────────
    alert_cards = html.Div([
        html.Div("REQUIRES ATTENTION",
                 style={"fontSize":"0.55rem","fontWeight":"800","letterSpacing":"0.18em","color":C.NAVY2,"marginBottom":"10px"}),
        *[html.Div([
            html.Span(a["level"], style={"fontSize":"0.6rem","fontWeight":"900","color":a["color"],
                      "marginRight":"10px","fontFamily":"JetBrains Mono,monospace",
                      "minWidth":"60px","display":"inline-block"}),
            html.Span(a["message"], style={"fontSize":"0.74rem","color":C.TEXT}),
        ], style={"padding":"8px 12px","borderLeft":f"4px solid {a['color']}",
                  "marginBottom":"6px","background":C.BG,"borderRadius":"0 6px 6px 0"})
          for a in exec_alerts],
    ])

    # ── ERI section ────────────────────────────────────────────────────────────
    eri_table_rows = [
        html.Tr([
            html.Td(r["assignee"], style={"fontWeight":"700","fontSize":"0.72rem"}),
            html.Td(f"{r['eri']}%", style={"color":r["color"],"fontWeight":"900",
                    "fontFamily":"JetBrains Mono,monospace","fontSize":"0.8rem"}),
            html.Td(str(r["promises"]), style={"fontFamily":"JetBrains Mono,monospace","fontSize":"0.72rem"}),
            html.Td(str(r["kept"]),     style={"color":C.GREEN,"fontFamily":"JetBrains Mono,monospace","fontSize":"0.72rem"}),
            html.Td(str(r["broken"]),   style={"color":C.RED if r["broken"]>0 else C.MUTED,"fontFamily":"JetBrains Mono,monospace","fontSize":"0.72rem"}),
            html.Td(f"{r['avg_days_over']}d", style={"color":C.RED if r["avg_days_over"]>3 else C.MUTED,"fontFamily":"JetBrains Mono,monospace","fontSize":"0.72rem"}),
        ], style={"background":C.SURFACE if i%2==0 else C.BG})
        for i,r in enumerate(eri_rows)
    ]

    eri_section = C.card(
        html.Div("EXECUTION RELIABILITY INDEX",
                 style={"fontSize":"0.55rem","fontWeight":"800","letterSpacing":"0.18em","color":C.NAVY2,"marginBottom":"10px"}),
        html.Div("Measures commitment accuracy per assignee based on standup ETA logs. ERI = (Kept / Total) × 100 − staleness penalty.",
                 style={"fontSize":"0.68rem","color":C.MUTED,"marginBottom":"12px","fontStyle":"italic"}),
        _g(_eri_chart(eri_rows), "int-eri", 260),
        html.Table([
            html.Thead(html.Tr([html.Th(h) for h in ["Assignee","ERI","Promises","Kept","Broken","Avg Days Over"]],
                               style={"background":C.ACCENT2})),
            html.Tbody(eri_table_rows),
        ], style={"width":"100%","borderCollapse":"collapse","fontSize":"0.75rem","marginTop":"12px"}),
    ) if eri_rows else C.card(
        html.Div("EXECUTION RELIABILITY INDEX", style={"fontSize":"0.55rem","fontWeight":"800","letterSpacing":"0.18em","color":C.NAVY2,"marginBottom":"8px"}),
        html.Div("No standup ETA logs found. Start logging updates in the Standup Log page to build predictability data.",
                 style={"color":C.AMBER,"fontSize":"0.75rem"}),
    )

    # ── Risk score section ─────────────────────────────────────────────────────
    risk_table_rows = [
        html.Tr([
            html.Td(r["assignee"], style={"fontWeight":"700","fontSize":"0.72rem"}),
            html.Td(f"{r['risk']}", style={"color":r["color"],"fontWeight":"900",
                    "fontFamily":"JetBrains Mono,monospace","fontSize":"0.8rem"}),
            html.Td(str(r["open"]),     style={"fontFamily":"JetBrains Mono,monospace","fontSize":"0.72rem"}),
            html.Td(str(r["overdue"]),  style={"color":C.RED if r["overdue"]>0 else C.MUTED,"fontFamily":"JetBrains Mono,monospace","fontSize":"0.72rem"}),
            html.Td(str(r["stale"]),    style={"color":C.AMBER if r["stale"]>0 else C.MUTED,"fontFamily":"JetBrains Mono,monospace","fontSize":"0.72rem"}),
            html.Td(str(r["blockers"]),style={"color":C.RED if r["blockers"]>0 else C.MUTED,"fontFamily":"JetBrains Mono,monospace","fontSize":"0.72rem"}),
            html.Td(str(r["eri"]),      style={"color":C.MUTED,"fontSize":"0.72rem"}),
        ], style={"background":C.SURFACE if i%2==0 else C.BG})
        for i,r in enumerate(risk_rows[:20])
    ]

    init_risk_fig = go.Figure(go.Bar(
        x=[r["label"][:20] for r in init_risk[:12]],
        y=[r["risk"] for r in init_risk[:12]],
        marker_color=[r["color"] for r in init_risk[:12]],
        text=[f"{r['risk']}" for r in init_risk[:12]],
        textposition="outside",
    ))
    init_risk_fig.update_layout(**L, title=_t("Initiative Risk Score"),
        xaxis=dict(tickangle=-30, gridcolor=C.BORDER),
        yaxis=dict(gridcolor=C.BORDER))

    risk_section = C.card(
        html.Div("OPERATIONAL RISK SCORE",
                 style={"fontSize":"0.55rem","fontWeight":"800","letterSpacing":"0.18em","color":C.NAVY2,"marginBottom":"8px"}),
        html.Div("Composite score: Overdue×0.30 + Stale×0.25 + Blockers×0.20 + Bug Rate×0.15 + ERI(inv)×0.10",
                 style={"fontSize":"0.68rem","color":C.MUTED,"marginBottom":"12px","fontStyle":"italic"}),
        C.grid(_g(_risk_chart(risk_rows), "int-risk", 280),
               _g(init_risk_fig, "int-init-risk", 280), cols=2),
        html.Table([
            html.Thead(html.Tr([html.Th(h) for h in ["Assignee","Risk Score","Open","Overdue","Stale","Blockers","ERI"]],
                               style={"background":C.ACCENT2})),
            html.Tbody(risk_table_rows),
        ], style={"width":"100%","borderCollapse":"collapse","fontSize":"0.75rem","marginTop":"12px"}),
    )

    # ── Propagation section ────────────────────────────────────────────────────
    prop_table_rows = [
        html.Tr([
            html.Td(html.A(r["key"], href=f"https://solytics.atlassian.net/browse/{r['key']}",
                           target="_blank",
                           style={"color":C.ACCENT,"fontFamily":"JetBrains Mono,monospace",
                                  "fontSize":"0.72rem","fontWeight":"700","textDecoration":"none"})),
            html.Td(r["assignee"], style={"fontSize":"0.72rem"}),
            html.Td(r["summary"], style={"fontSize":"0.7rem","color":C.MUTED,"maxWidth":"280px",
                                          "overflow":"hidden","textOverflow":"ellipsis","whiteSpace":"nowrap"}),
            html.Td(C.status_badge(r["status"])),
            html.Td(str(r["downstream"]), style={"color":C.RED,"fontWeight":"800",
                    "fontFamily":"JetBrains Mono,monospace","fontSize":"0.78rem"}),
            html.Td(f"{r['cascade_days']}d", style={"color":C.ORANGE,"fontWeight":"700",
                    "fontFamily":"JetBrains Mono,monospace","fontSize":"0.72rem"}),
            html.Td(str(r["assignees_affected"]), style={"fontFamily":"JetBrains Mono,monospace","fontSize":"0.72rem"}),
            html.Td(f"{r['impact_score']}", style={"color":C.RED,"fontWeight":"900",
                    "fontFamily":"JetBrains Mono,monospace","fontSize":"0.78rem"}),
        ], style={"background":C.SURFACE if i%2==0 else C.BG})
        for i,r in enumerate(prop_rows[:20])
    ]

    prop_section = C.card(
        html.Div("DEPENDENCY PROPAGATION ANALYSIS",
                 style={"fontSize":"0.55rem","fontWeight":"800","letterSpacing":"0.18em","color":C.NAVY2,"marginBottom":"8px"}),
        html.Div("BFS traversal of issue dependency graph. Impact Score = Downstream Count × 10 + Cascade Days × 0.5",
                 style={"fontSize":"0.68rem","color":C.MUTED,"marginBottom":"12px","fontStyle":"italic"}),
        _g(_propagation_chart(prop_rows), "int-prop", 280),
        html.Table([
            html.Thead(html.Tr([html.Th(h) for h in ["Issue","Assignee","Summary","Status","Downstream","Cascade Days","Teams Affected","Impact Score"]],
                               style={"background":"#FEF2F2"})),
            html.Tbody(prop_table_rows),
        ], style={"width":"100%","borderCollapse":"collapse","fontSize":"0.75rem","marginTop":"12px"}),
    ) if prop_rows else C.card(
        html.Div("DEPENDENCY PROPAGATION ANALYSIS", style={"fontSize":"0.55rem","fontWeight":"800","letterSpacing":"0.18em","color":C.NAVY2,"marginBottom":"8px"}),
        html.Div("No active blocker chains found.", style={"color":C.GREEN,"fontSize":"0.75rem"}),
    )

    return html.Div([
        C.section("Operational Intelligence",
                  "Execution predictability  |  Risk scoring  |  Dependency propagation  |  Decision alerts"),

        # Executive alert strip
        C.card(alert_cards, pad="16px",
               style={"borderLeft":f"4px solid {C.RED}","marginBottom":"16px"}),

        # ERI
        eri_section,
        html.Div(style={"marginTop":"16px"}),

        # Risk scores
        risk_section,
        html.Div(style={"marginTop":"16px"}),

        # Dependency propagation
        prop_section,
    ])


def register_callbacks(app, get_issues_fn):
    pass
