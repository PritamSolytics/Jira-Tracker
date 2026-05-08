"""
analytics_page.py — Advanced Analytics
Velocity forecasting (ARIMA/SARIMA), statistical tests, survival analysis,
trend decomposition, delivery distribution analysis.
"""
from dash import html, dcc, Input, Output, State
import plotly.graph_objects as go
import pandas as pd
import numpy as np
from collections import Counter, defaultdict
from datetime import date, timedelta
import components as C

L = dict(paper_bgcolor=C.SURFACE, plot_bgcolor=C.SURFACE,
         font=dict(color=C.TEXT, size=11, family="JetBrains Mono, monospace"),
         margin=dict(l=8,r=8,t=40,b=8),
         legend=dict(bgcolor=C.SURFACE, bordercolor=C.BORDER, borderwidth=1))

def _t(text): return dict(text=text, font=dict(size=11, color=C.NAVY2, weight="bold"))
def _g(fig, gid, h=300): return dcc.Graph(figure=fig, id=gid, style={"height":f"{h}px"}, config={"displayModeBar":False})


def layout(issues):
    import ml_engine as ML

    # ── Velocity forecast ──────────────────────────────────────────────────────
    fc = ML.forecast_velocity(issues, periods=8)
    forecast_card = _build_forecast_card(fc)

    # ── Statistical tests ──────────────────────────────────────────────────────
    tests = ML.run_statistical_tests(issues)
    tests_card = _build_tests_card(tests)

    # ── Survival analysis proxy ────────────────────────────────────────────────
    survival_card = _build_survival_card(issues)

    # ── Throughput trend ───────────────────────────────────────────────────────
    throughput_card = _build_throughput_card(issues)

    # ── Bug injection rate ─────────────────────────────────────────────────────
    bug_card = _build_bug_rate_card(issues)

    # ── Cycle time percentiles ─────────────────────────────────────────────────
    cycle_card = _build_cycle_percentiles_card(issues)

    # ── WIP (Work In Progress) over time ──────────────────────────────────────
    wip_card = _build_wip_card(issues)

    # ── Assignee efficiency radar ──────────────────────────────────────────────
    radar_card = _build_assignee_radar(issues)

    return html.Div([
        C.section("Advanced Analytics", "Forecasting · Statistical tests · Delivery analysis · Throughput intelligence"),

        # Forecast + tests
        C.grid(forecast_card, tests_card, cols=2),
        html.Div(style={"marginTop":"16px"}),

        # Throughput + WIP
        C.grid(throughput_card, wip_card, cols=2),
        html.Div(style={"marginTop":"16px"}),

        # Survival + cycle percentiles
        C.grid(survival_card, cycle_card, cols=2),
        html.Div(style={"marginTop":"16px"}),

        # Bug rate + radar
        C.grid(bug_card, radar_card, cols=2),
    ])


def _build_forecast_card(fc):
    if "error" in fc:
        content = html.Div([
            html.Div("Forecast unavailable", style={"fontWeight":"700","color":C.AMBER,"fontSize":"0.78rem"}),
            html.Div(fc["error"], style={"color":C.MUTED,"fontSize":"0.72rem","marginTop":"6px"}),
        ], style={"padding":"12px"})
        return C.card(
            html.Div("VELOCITY FORECAST", style={"fontSize":"0.58rem","fontWeight":"800","letterSpacing":"0.16em","color":C.NAVY2,"marginBottom":"10px"}),
            content)

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=fc["actual_weeks"], y=fc["actual_values"],
        mode="lines+markers", name="Actual",
        line=dict(color=C.ACCENT, width=2.5),
        marker=dict(size=6, color=C.ACCENT),
        hovertemplate="Week: %{x}<br>Closed: %{y}<extra></extra>",
    ))
    fig.add_trace(go.Scatter(
        x=fc["forecast_weeks"], y=fc["forecast_values"],
        mode="lines+markers", name="Forecast",
        line=dict(color=C.AMBER, width=2, dash="dot"),
        marker=dict(size=7, color=C.AMBER, symbol="diamond"),
        hovertemplate="Week: %{x}<br>Forecast: %{y}<extra></extra>",
    ))
    # CI band
    x_band = fc["forecast_weeks"] + fc["forecast_weeks"][::-1]
    y_band = fc["ci_upper"] + fc["ci_lower"][::-1]
    fig.add_trace(go.Scatter(
        x=x_band, y=y_band,
        fill="toself", fillcolor="rgba(217,119,6,0.12)",
        line=dict(color="rgba(0,0,0,0)"), name="80% CI", showlegend=True,
    ))
    fig.update_layout(**L, title=_t(f"Velocity Forecast — {fc.get('model_name','ARIMA')}"),
        xaxis=dict(gridcolor=C.BORDER), yaxis=dict(title="Issues Closed / Week", gridcolor=C.BORDER))

    meta_info = html.Div([
        html.Span(f"Model: {fc.get('model_name','')}", style={"fontSize":"0.65rem","color":C.MUTED,"marginRight":"12px","fontFamily":"JetBrains Mono,monospace"}),
        html.Span(f"AIC: {fc.get('aic','')}", style={"fontSize":"0.65rem","color":C.MUTED,"marginRight":"12px","fontFamily":"JetBrains Mono,monospace"}),
        html.Span(f"ADF p={fc.get('adf_pvalue','')}", style={"fontSize":"0.65rem","color":C.MUTED,"marginRight":"12px","fontFamily":"JetBrains Mono,monospace"}),
        html.Span("Stationary" if fc.get("is_stationary") else "Non-stationary",
                  style={"fontSize":"0.65rem","color":C.GREEN if fc.get("is_stationary") else C.AMBER,
                         "fontWeight":"700","fontFamily":"JetBrains Mono,monospace"}),
    ], style={"marginTop":"6px","display":"flex","flexWrap":"wrap"})

    return C.card(
        html.Div("VELOCITY FORECAST", style={"fontSize":"0.58rem","fontWeight":"800","letterSpacing":"0.16em","color":C.NAVY2,"marginBottom":"10px"}),
        _g(fig, "an-forecast", 300),
        meta_info,
    )


def _build_tests_card(tests):
    rows = []
    for key, result in tests.items():
        if "error" in result:
            rows.append(html.Div(f"{result.get('test',key)}: Error — {result['error'][:60]}",
                                 style={"color":C.MUTED,"fontSize":"0.68rem","padding":"6px 0","borderBottom":f"1px solid {C.BORDER}"}))
            continue
        pval = result.get("p_value", 1.0)
        sig  = pval < 0.05
        rows.append(html.Div([
            html.Div(result.get("test", key), style={"fontWeight":"700","fontSize":"0.72rem","color":C.NAVY,"marginBottom":"4px"}),
            html.Div([
                html.Span(f"Statistic: {result.get('statistic','')}", style={"color":C.MUTED,"fontSize":"0.68rem","marginRight":"12px","fontFamily":"JetBrains Mono,monospace"}),
                html.Span(f"p-value: {pval}", style={"color":C.RED if sig else C.GREEN,"fontWeight":"700","fontSize":"0.68rem","marginRight":"12px","fontFamily":"JetBrains Mono,monospace"}),
                html.Span("*" if sig else "ns", style={"fontWeight":"900","color":C.RED if sig else C.MUTED,"fontSize":"0.75rem"}),
            ]),
            html.Div(result.get("conclusion",""), style={"color":C.GREEN if sig else C.MUTED,"fontSize":"0.68rem","marginTop":"3px","fontStyle":"italic"}),
            # Extra stats if present
            *([html.Div([
                html.Span(f"Mean: {result.get('mean_days','')}d", style={"color":C.MUTED,"fontSize":"0.65rem","marginRight":"8px","fontFamily":"JetBrains Mono,monospace"}),
                html.Span(f"Median: {result.get('median_days','')}d", style={"color":C.MUTED,"fontSize":"0.65rem","marginRight":"8px","fontFamily":"JetBrains Mono,monospace"}),
                html.Span(f"Std: {result.get('std_days','')}d", style={"color":C.MUTED,"fontSize":"0.65rem","fontFamily":"JetBrains Mono,monospace"}),
            ])] if "mean_days" in result else []),
            *([html.Div([
                html.Span(f"High median: {result.get('high_median','')}d", style={"color":C.RED,"fontSize":"0.65rem","marginRight":"8px","fontFamily":"JetBrains Mono,monospace"}),
                html.Span(f"Medium median: {result.get('medium_median','')}d", style={"color":C.AMBER,"fontSize":"0.65rem","fontFamily":"JetBrains Mono,monospace"}),
            ])] if "high_median" in result else []),
        ], style={"padding":"10px 0","borderBottom":f"1px solid {C.BORDER}"}))

    if not tests or all("error" in v for v in tests.values()):
        no_data = html.Div("Train the model first (Predictive Analytics page) to enable Shapiro-Wilk, Mann-Whitney and Kruskal-Wallis tests. ADF runs on live data only.",
                           style={"color":C.AMBER,"fontSize":"0.73rem","padding":"8px 0"})
        return C.card(
            html.Div("STATISTICAL TESTS", style={"fontSize":"0.58rem","fontWeight":"800","letterSpacing":"0.16em","color":C.NAVY2,"marginBottom":"12px"}),
            no_data)
    return C.card(
        html.Div("STATISTICAL TESTS", style={"fontSize":"0.58rem","fontWeight":"800","letterSpacing":"0.16em","color":C.NAVY2,"marginBottom":"12px"}),
        html.Div("*p<0.05 = significant at 5% level  |  ns = not significant", style={"fontSize":"0.62rem","color":C.MUTED,"marginBottom":"10px","fontStyle":"italic"}),
        html.Div(rows),
    )


def _build_survival_card(issues):
    """Kaplan-Meier proxy: fraction of issues still open by age bucket."""
    open_issues = [i for i in issues if i["status"] != "Closed"]
    age_buckets = [7, 14, 21, 30, 45, 60, 90, 120]
    survival = []
    n_total = len(open_issues)
    for bucket in age_buckets:
        still_open = sum(1 for i in open_issues if i["days_since_progress"] >= bucket)
        survival.append(round(still_open / max(1, n_total) * 100, 1))

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=age_buckets, y=survival,
        mode="lines+markers",
        line=dict(color=C.RED, width=2.5),
        marker=dict(size=8, color=C.RED),
        fill="tozeroy", fillcolor="rgba(220,38,38,0.07)",
        hovertemplate="Age: %{x}d<br>Still Open: %{y}%<extra></extra>",
        name="% Still Open",
    ))
    fig.update_layout(**L, title=_t("Issue Survival Curve (% Still Open by Age)"),
        xaxis=dict(title="Days Since Last Update", gridcolor=C.BORDER),
        yaxis=dict(title="% Still Open", gridcolor=C.BORDER, range=[0,105]))
    return C.card(_g(fig, "an-survival", 280))


def _build_throughput_card(issues):
    """Weekly throughput: opened vs closed."""
    by_week_opened = Counter()
    by_week_closed = Counter()
    for i in issues:
        try:
            d = date.fromisoformat(i["created"])
            w = str(d - timedelta(days=d.weekday()))
            by_week_opened[w] += 1
        except: pass
        if i["status"] == "Closed" and i.get("updated"):
            try:
                d = date.fromisoformat(i["updated"])
                w = str(d - timedelta(days=d.weekday()))
                by_week_closed[w] += 1
            except: pass

    all_weeks = sorted(set(list(by_week_opened.keys()) + list(by_week_closed.keys())))[-20:]
    fig = go.Figure()
    fig.add_trace(go.Bar(name="Opened", x=all_weeks, y=[by_week_opened.get(w,0) for w in all_weeks],
        marker_color=C.RED, opacity=0.75))
    fig.add_trace(go.Bar(name="Closed", x=all_weeks, y=[by_week_closed.get(w,0) for w in all_weeks],
        marker_color=C.GREEN, opacity=0.75))
    fig.update_layout(**L, barmode="group", title=_t("Weekly Throughput: Opened vs Closed"),
        xaxis=dict(tickangle=-30, gridcolor=C.BORDER),
        yaxis=dict(title="Issues", gridcolor=C.BORDER))
    return C.card(_g(fig, "an-throughput", 280))


def _build_bug_rate_card(issues):
    """Bug injection rate over time."""
    by_week_bugs  = Counter()
    by_week_total = Counter()
    for i in issues:
        try:
            d = date.fromisoformat(i["created"])
            w = str(d - timedelta(days=d.weekday()))
            by_week_total[w] += 1
            if i["type"] == "Bug": by_week_bugs[w] += 1
        except: pass
    weeks = sorted(by_week_total)[-16:]
    rates = [round(by_week_bugs.get(w,0)/max(1,by_week_total.get(w,1))*100,1) for w in weeks]

    fig = go.Figure()
    fig.add_trace(go.Scatter(x=weeks, y=rates, mode="lines+markers",
        line=dict(color=C.ORANGE, width=2.5),
        marker=dict(size=6, color=C.ORANGE),
        fill="tozeroy", fillcolor="rgba(234,88,12,0.07)",
        hovertemplate="Week: %{x}<br>Bug Rate: %{y}%<extra></extra>"))
    fig.add_hline(y=np.mean(rates), line_dash="dot", line_color=C.RED,
                  annotation_text=f"Mean {round(np.mean(rates),1)}%",
                  annotation_font_color=C.RED, annotation_font_size=9)
    fig.update_layout(**L, title=_t("Bug Injection Rate (% of Issues Created)"),
        xaxis=dict(tickangle=-30, gridcolor=C.BORDER),
        yaxis=dict(title="Bug Rate %", gridcolor=C.BORDER))
    return C.card(_g(fig, "an-bugrate", 280))


def _build_cycle_percentiles(issues):
    closed = [i for i in issues if i["status"] == "Closed" and i.get("created") and i.get("updated")]
    cycles = []
    for i in closed:
        try:
            ct = (date.fromisoformat(i["updated"]) - date.fromisoformat(i["created"])).days
            if 0 <= ct <= 365: cycles.append(ct)
        except: pass
    return cycles


def _build_cycle_percentiles_card(issues):
    cycles = _build_cycle_percentiles(issues)
    if not cycles:
        return C.card(html.Div("Insufficient closed issues for cycle time analysis.", style={"color":C.MUTED,"fontSize":"0.75rem"}))

    pcts = [10, 25, 50, 75, 85, 90, 95]
    vals = [round(float(np.percentile(cycles, p)),1) for p in pcts]

    fig = go.Figure()
    colors = [C.GREEN, C.TEAL, C.ACCENT, C.AMBER, C.ORANGE, C.RED, C.RED]
    fig.add_trace(go.Bar(
        x=[f"P{p}" for p in pcts], y=vals,
        marker_color=colors,
        text=[f"{v}d" for v in vals], textposition="outside",
        textfont=dict(color=C.NAVY2, size=10, weight="bold"),
        hovertemplate="<b>%{x}</b><br>%{y} days<extra></extra>",
    ))
    fig.add_hline(y=np.mean(cycles), line_dash="dot", line_color=C.MUTED,
                  annotation_text=f"Mean {round(np.mean(cycles),1)}d",
                  annotation_font_size=9)
    fig.update_layout(**L, title=_t(f"Cycle Time Percentiles (n={len(cycles)})"),
        yaxis=dict(title="Days", gridcolor=C.BORDER),
        xaxis=dict(gridcolor=C.BORDER))
    return C.card(_g(fig, "an-cycle-pct", 280))


def _build_wip_card(issues):
    """Work In Progress by status bucket per week — approximation."""
    # Count open issues as of each week (created <= week, not yet closed)
    # Simplified: use current status distribution trend via created date
    by_week = defaultdict(lambda: defaultdict(int))
    for i in issues:
        try:
            d = date.fromisoformat(i["created"])
            w = str(d - timedelta(days=d.weekday()))
            if i["status"] != "Closed":
                by_week[w][i["status"]] += 1
        except: pass

    weeks = sorted(by_week)[-16:]
    statuses = ["Development In Progress", "Code Review", "QA Testing", "Integration Testing", "Groomed"]
    colors   = [C.AMBER, C.PURPLE, C.ACCENT, C.TEAL, C.MUTED]

    fig = go.Figure()
    for idx, s in enumerate(statuses):
        fig.add_trace(go.Scatter(
            x=weeks, y=[by_week[w].get(s, 0) for w in weeks],
            stackgroup="one", name=s[:20],
            line=dict(color=colors[idx]),
            hovertemplate=f"<b>{s}</b><br>Week: %{{x}}<br>Count: %{{y}}<extra></extra>",
        ))
    fig.update_layout(**L, title=_t("Work In Progress by Stage (Stacked)"),
        xaxis=dict(tickangle=-30, gridcolor=C.BORDER),
        yaxis=dict(title="Open Issues", gridcolor=C.BORDER))
    return C.card(_g(fig, "an-wip", 280))


def _build_assignee_radar(issues):
    """Top 6 assignees radar: throughput, quality, speed, predictability."""
    by_a = defaultdict(list)
    for i in issues: by_a[i["assignee"]].append(i)

    top_assignees = [a for a, _ in sorted(by_a.items(), key=lambda x: -len(x[1])) if a != "Unassigned"][:6]
    if not top_assignees:
        return C.card(html.Div("Insufficient assignee data.", style={"color":C.MUTED}))

    fig = go.Figure()
    colors = [C.ACCENT, C.RED, C.GREEN, C.PURPLE, C.ORANGE, C.TEAL]
    categories = ["Volume", "Closure Rate", "On-Time Rate", "Bug-Free Rate", "Avg Speed"]

    for idx, a in enumerate(top_assignees):
        items = by_a[a]
        total = len(items)
        closed = sum(1 for i in items if i["status"] == "Closed")
        bugs   = sum(1 for i in items if i["type"] == "Bug")
        on_time = sum(1 for i in items if i["status"] == "Closed" and i.get("due") and
                      i.get("updated","") <= i.get("due","9999"))
        cycles = []
        for i in items:
            if i["status"] == "Closed" and i.get("created") and i.get("updated"):
                try:
                    ct = (date.fromisoformat(i["updated"]) - date.fromisoformat(i["created"])).days
                    if 0 <= ct <= 365: cycles.append(ct)
                except: pass

        # Normalize to 0-100
        vol_score = min(100, total * 3)
        close_rate = round(closed / max(1, total) * 100, 0)
        on_time_rate = round(on_time / max(1, closed) * 100, 0) if closed else 0
        bug_free = round((1 - bugs / max(1, total)) * 100, 0)
        speed = round(max(0, 100 - (np.mean(cycles) if cycles else 50)), 0)

        vals = [vol_score, close_rate, on_time_rate, bug_free, speed]
        vals_closed = vals + [vals[0]]
        cats_closed = categories + [categories[0]]

        fig.add_trace(go.Scatterpolar(
            r=vals_closed, theta=cats_closed,
            fill="toself", name=a.split()[0] if " " in a else a,
            line=dict(color=colors[idx]),
            fillcolor="rgba(37,99,235,0.08)" if idx==0 else ("rgba(220,38,38,0.08)" if idx==1 else ("rgba(22,163,74,0.08)" if idx==2 else ("rgba(124,58,237,0.08)" if idx==3 else ("rgba(234,88,12,0.08)" if idx==4 else "rgba(13,148,136,0.08)")))),
        ))

    fig.update_layout(**L, title=_t("Assignee Performance Profile"),
        polar=dict(
            radialaxis=dict(visible=True, range=[0,100], gridcolor=C.BORDER, color=C.MUTED),
            angularaxis=dict(gridcolor=C.BORDER, color=C.MUTED),
            bgcolor=C.SURFACE,
        ), height=340)
    return C.card(_g(fig, "an-radar", 340))


def register_callbacks(app, get_issues_fn):
    pass  # All charts are server-side rendered on page load
