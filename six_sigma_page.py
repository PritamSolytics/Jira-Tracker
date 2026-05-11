"""
six_sigma_page.py — Six Sigma Black Belt Dashboard
====================================================
Full DMAIC implementation rendered as a Dash page.

Sections:
  1. Command Strip — Sigma level, DPMO, RTY, Yield %
  2. XmR Control Charts — Weekly velocity + Cycle time
  3. Process Capability (Cpk / Cp) — per issue type vs SLA
  4. DPMO by Workstream — project / label breakdown
  5. FMEA Register — RPN table with recommended actions
  6. Rolled Throughput Yield — stage-by-stage funnel
  7. MSA Audit — measurement system quality
"""
from dash import html, dcc, dash_table
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import components as C
import six_sigma_engine as SS
import data as D

# ── Layout constants ──────────────────────────────────────────────────────────
L = dict(
    paper_bgcolor=C.SURFACE, plot_bgcolor=C.SURFACE,
    font=dict(color=C.TEXT, size=11, family="JetBrains Mono, monospace"),
    margin=dict(l=10, r=10, t=44, b=10),
    legend=dict(bgcolor=C.SURFACE, bordercolor=C.BORDER, borderwidth=1),
)

SIGMA_COLOR = {
    "World Class":   C.GREEN,
    "Excellent":     C.TEAL,
    "Good":          C.ACCENT,
    "Average":       C.AMBER,
    "Below Average": C.ORANGE,
    "Poor":          C.RED,
}

RPN_COLOR = {
    "Critical": C.RED,
    "High":     C.ORANGE,
    "Medium":   C.AMBER,
    "Low":      C.GREEN,
}

CPK_COLOR = lambda cpk: (
    C.GREEN  if cpk >= 1.67 else
    C.ACCENT if cpk >= 1.33 else
    C.AMBER  if cpk >= 1.00 else
    C.RED
)

def _g(fig, gid, h=300):
    return dcc.Graph(figure=fig, id=gid, style={"height": f"{h}px"}, config={"displayModeBar": False})

def _t(text):
    return dict(text=text, font=dict(size=11, color=C.NAVY2, weight="bold"))


# ── Main layout ───────────────────────────────────────────────────────────────
def layout(issues):
    # Fetch changelog for real RTY — served from 24h cache after first load
    # On cold start this may be empty (background thread still fetching)
    changelog = D.get_changelog()
    rty_mode  = "changelog" if changelog else "approximation"
    changelog_cold = not bool(changelog)

    summary   = SS.dmaic_summary(issues, changelog_data=changelog)
    cap       = SS.process_capability(issues)
    dpmo_data = SS.dpmo_sigma(issues, group_by="label")
    fmea      = SS.build_fmea(issues)
    rty_data  = SS.rolled_throughput_yield(issues, changelog_data=changelog)
    rty_data["cold"] = changelog_cold
    rty_data["mode"] = rty_mode
    msa       = SS.msa_audit(issues)
    xmr_vel   = SS.xmr_control_chart(issues, metric="weekly_closed")
    xmr_ct    = SS.xmr_control_chart(issues, metric="cycle_time")
    dpmo_proj = SS.dpmo_sigma(issues, group_by="project")

    return html.Div([
        C.section(
            "Six Sigma Black Belt — DMAIC Intelligence",
            "DPMO · Sigma Level · Cpk · XmR Control Charts · FMEA · RTY · MSA"
        ),

        # ── 1. Command Strip ─────────────────────────────────────────────────
        _command_strip(summary),

        html.Div(style={"marginTop": "16px"}),

        # ── 2. XmR Control Charts ────────────────────────────────────────────
        C.grid(
            C.card(_build_xmr_chart(xmr_vel, "ss-xmr-vel"), cols=1),
            C.card(_build_xmr_chart(xmr_ct,  "ss-xmr-ct"),  cols=1),
            cols=2
        ),

        html.Div(style={"marginTop": "16px"}),

        # ── 3. Process Capability + DPMO by workstream ───────────────────────
        C.grid(
            C.card(_build_cpk_table(cap),           cols=1),
            C.card(_build_dpmo_chart(dpmo_data),    cols=1),
            cols=2
        ),

        html.Div(style={"marginTop": "16px"}),

        # ── 4. FMEA Register ─────────────────────────────────────────────────
        C.card(_build_fmea_table(fmea), cols=1),

        html.Div(style={"marginTop": "16px"}),

        # ── 5. RTY Funnel + MSA Audit ────────────────────────────────────────
        C.grid(
            C.card(_build_rty_section(rty_data),    cols=1),
            C.card(_build_msa_section(msa),         cols=1),
            cols=2
        ),

        html.Div(style={"marginTop": "16px"}),

        # ── 6. DPMO by Project ───────────────────────────────────────────────
        C.card(_build_dpmo_project_table(dpmo_proj), cols=1),

        html.Div(style={"marginTop": "40px"}),
    ])


# ── 1. Command Strip ──────────────────────────────────────────────────────────
def _command_strip(s):
    sigma    = s["sigma_level"]
    grade    = s["grade"]
    color    = SIGMA_COLOR.get(grade, C.MUTED)
    dpmo     = s["dpmo"]
    yield_p  = s["yield_pct"]
    rty      = s["rty"]
    defects  = s["defects"]
    n        = s["n_issues"]
    msa_hits = len(s["msa_critical"])
    fmea_crit= len(s["fmea_critical"])

    # Gauge
    gauge = go.Figure(go.Indicator(
        mode="gauge+number+delta",
        value=sigma,
        delta={"reference": 3.0, "valueformat": ".2f"},
        number={"suffix": "σ", "font": {"size": 42, "color": color, "family": "JetBrains Mono,monospace"}},
        gauge={
            "axis":  {"range": [0, 6], "tickwidth": 1, "tickcolor": C.BORDER,
                      "tickvals": [0, 1, 2, 3, 4, 5, 6],
                      "ticktext": ["0σ","1σ","2σ","3σ","4σ","5σ","6σ"]},
            "bar":   {"color": color, "thickness": 0.3},
            "bgcolor": C.SURFACE,
            "borderwidth": 0,
            "steps": [
                {"range": [0, 2],  "color": "#FEF2F2"},
                {"range": [2, 3],  "color": "#FFF7ED"},
                {"range": [3, 4],  "color": "#FFFBEB"},
                {"range": [4, 5],  "color": "#F0FDF4"},
                {"range": [5, 6],  "color": "#ECFDF5"},
            ],
            "threshold": {"line": {"color": C.NAVY, "width": 2}, "thickness": 0.75, "value": sigma},
        },
        title={"text": f"Process Sigma Level<br><span style='font-size:11px;color:{C.MUTED}'>{grade}</span>"},
    ))
    gauge.update_layout(
        paper_bgcolor=C.SURFACE, plot_bgcolor=C.SURFACE,
        margin=dict(l=20, r=20, t=60, b=10),
        height=220,
        font=dict(color=C.TEXT, family="JetBrains Mono,monospace"),
    )

    kpis = html.Div([
        C.kpi("DPMO",           f"{dpmo:,.1f}",  C.RED   if dpmo > 66807 else (C.AMBER if dpmo > 6210 else C.GREEN)),
        C.kpi("Process Yield",  f"{yield_p}%",   C.GREEN if yield_p > 99 else (C.AMBER if yield_p > 93 else C.RED)),
        C.kpi("RTY",            f"{rty}%",        C.GREEN if rty > 90 else (C.AMBER if rty > 70 else C.RED)),
        C.kpi("Defects Found",  defects,          C.RED   if defects > 20 else C.AMBER),
        C.kpi("Issues Measured",n,                C.NAVY),
        C.kpi("MSA Findings",   msa_hits,         C.RED   if msa_hits > 1 else C.AMBER, "High severity"),
        C.kpi("FMEA Critical",  fmea_crit,        C.RED   if fmea_crit > 2 else C.ORANGE),
    ], style={"display": "flex", "gap": "10px", "flexWrap": "wrap", "alignItems": "stretch"})

    # Top 3 FMEA risks as action strip
    top_risks = s.get("top_risks", [])
    risk_strip = html.Div([
        html.Div("TOP FMEA RISKS", style={
            "fontSize": "0.55rem", "fontWeight": "800", "color": C.MUTED,
            "letterSpacing": "0.16em", "marginBottom": "8px",
        }),
        html.Div([
            html.Div([
                html.Span(f"RPN {r['rpn']}", style={
                    "background": RPN_COLOR.get(r['rpn_class'], C.MUTED),
                    "color": "#fff", "borderRadius": "4px", "padding": "2px 7px",
                    "fontSize": "0.64rem", "fontWeight": "800", "marginRight": "8px",
                    "fontFamily": "JetBrains Mono,monospace",
                }),
                html.Span(r["failure_mode"], style={
                    "color": C.NAVY, "fontSize": "0.73rem", "fontWeight": "700",
                }),
                html.Div(f"→ {r['recommended_action']}", style={
                    "color": C.MUTED, "fontSize": "0.67rem", "marginTop": "2px", "paddingLeft": "72px",
                }),
            ], style={
                "padding": "8px 10px", "borderLeft": f"3px solid {RPN_COLOR.get(r['rpn_class'],C.MUTED)}",
                "marginBottom": "6px", "background": C.BG, "borderRadius": "4px",
            })
            for r in top_risks
        ]),
    ], style={"marginTop": "12px"})

    return html.Div([
        html.Div([
            dcc.Graph(figure=gauge, config={"displayModeBar": False},
                      style={"width": "260px", "flexShrink": "0"}),
            html.Div([kpis, risk_strip], style={"flex": "1", "minWidth": "0"}),
        ], style={
            "display": "flex", "gap": "16px", "alignItems": "flex-start",
            "background": C.SURFACE, "borderRadius": "12px", "padding": "16px",
            "border": f"2px solid {color}44", "borderTop": f"4px solid {color}",
            "boxShadow": f"0 4px 20px {color}22",
        }),
    ])


# ── 2. XmR Control Chart ──────────────────────────────────────────────────────
def _build_xmr_chart(xmr, graph_id):
    if "error" in xmr:
        return html.Div([
            html.Div("XmR Control Chart", style={"fontSize": "0.62rem", "fontWeight": "800",
                     "color": C.NAVY2, "letterSpacing": "0.12em", "marginBottom": "8px"}),
            html.Div(xmr["error"], style={"color": C.MUTED, "fontSize": "0.75rem", "padding": "20px 0"}),
        ])

    labels   = xmr["labels"]
    x_vals   = xmr["x_values"]
    mr_vals  = xmr["mr_values"]
    x_bar    = xmr["x_bar"]
    x_ucl    = xmr["x_ucl"]
    x_lcl    = xmr["x_lcl"]
    mr_bar   = xmr["mr_bar"]
    mr_ucl   = xmr["mr_ucl"]
    ooc      = xmr["ooc_indices"]
    ooc_idx  = set(i for i, _ in ooc)

    fig = make_subplots(
        rows=2, cols=1, shared_xaxes=True,
        subplot_titles=["Individuals (X) Chart", "Moving Range (mR) Chart"],
        vertical_spacing=0.12,
        row_heights=[0.65, 0.35],
    )

    # ── X Chart ──
    # In-control points
    in_x  = [v if i not in ooc_idx else None for i, v in enumerate(x_vals)]
    out_x = [v if i in ooc_idx else None for i, v in enumerate(x_vals)]

    fig.add_trace(go.Scatter(
        x=labels, y=in_x, mode="lines+markers", name="In Control",
        line=dict(color=C.ACCENT, width=2),
        marker=dict(size=7, color=C.ACCENT, line=dict(color=C.SURFACE, width=1.5)),
        connectgaps=True,
    ), row=1, col=1)

    fig.add_trace(go.Scatter(
        x=labels, y=out_x, mode="markers", name="Out of Control",
        marker=dict(size=11, color=C.RED, symbol="x", line=dict(color=C.RED, width=2)),
    ), row=1, col=1)

    # UCL / CL / LCL lines
    for val, label, color, dash in [
        (x_ucl, f"UCL={x_ucl}", C.RED,   "dash"),
        (x_bar, f"CL={x_bar}", C.GREEN,  "solid"),
        (x_lcl, f"LCL={x_lcl}", C.RED,  "dash"),
    ]:
        fig.add_hline(y=val, line_color=color, line_dash=dash, line_width=1.5,
                      annotation_text=label,
                      annotation_font=dict(size=9, color=color),
                      annotation_position="right",
                      row=1, col=1)

    # ── mR Chart ──
    fig.add_trace(go.Bar(
        x=labels, y=mr_vals, name="Moving Range",
        marker_color=C.ACCENT2, marker_line_color=C.ACCENT, marker_line_width=1,
        opacity=0.8,
    ), row=2, col=1)
    fig.add_hline(y=mr_ucl, line_color=C.RED,   line_dash="dash", line_width=1.5,
                  annotation_text=f"UCL={mr_ucl}", annotation_font=dict(size=9, color=C.RED),
                  annotation_position="right", row=2, col=1)
    fig.add_hline(y=mr_bar, line_color=C.GREEN, line_dash="solid", line_width=1.5,
                  annotation_text=f"CL={mr_bar}", annotation_font=dict(size=9, color=C.GREEN),
                  annotation_position="right", row=2, col=1)

    fig.update_layout(
        **L,
        title=_t(xmr["title"]),
        height=380,
        showlegend=True,
        xaxis2=dict(tickangle=-30, gridcolor=C.BORDER),
        yaxis=dict(title=xmr["y_label"], gridcolor=C.BORDER),
        yaxis2=dict(title="Moving Range", gridcolor=C.BORDER),
    )

    ooc_summary = html.Div()
    if ooc:
        ooc_summary = html.Div([
            html.Span("⚠ Out-of-Control Points Detected: ", style={
                "fontSize": "0.65rem", "fontWeight": "800", "color": C.RED,
            }),
            html.Span(f"{len(ooc)} point(s) violate Western Electric rules", style={
                "fontSize": "0.65rem", "color": C.MUTED,
            }),
        ], style={"marginTop": "6px", "padding": "6px 10px", "background": "#FEF2F2",
                  "borderRadius": "4px", "border": f"1px solid {C.RED}33"})

    return html.Div([_g(fig, graph_id, h=380), ooc_summary])


# ── 3. Process Capability Table ───────────────────────────────────────────────
def _build_cpk_table(cap):
    if not cap:
        return html.Div("Insufficient closed issues for Cpk calculation.",
                        style={"color": C.MUTED, "fontSize": "0.75rem"})

    header = html.Div("PROCESS CAPABILITY (Cpk / Cp)", style={
        "fontSize": "0.58rem", "fontWeight": "800", "letterSpacing": "0.16em",
        "color": C.NAVY2, "marginBottom": "12px",
    })

    rows = []
    for r in cap:
        cpk_color = CPK_COLOR(r["cpk"])
        rows.append(html.Tr([
            html.Td(r["type"],        style={"fontWeight": "700", "color": C.NAVY, "fontSize": "0.73rem"}),
            html.Td(f"{r['sla_days']}d", style={"color": C.MUTED, "fontSize": "0.72rem"}),
            html.Td(f"{r['n']}",      style={"fontFamily": "JetBrains Mono,monospace", "fontSize": "0.72rem"}),
            html.Td(f"{r['mean']}d",  style={"fontFamily": "JetBrains Mono,monospace", "fontSize": "0.72rem"}),
            html.Td(f"{r['std']}d",   style={"fontFamily": "JetBrains Mono,monospace", "fontSize": "0.72rem"}),
            html.Td(html.Span(f"{r['cpk']}", style={
                "color": cpk_color, "fontWeight": "800",
                "fontFamily": "JetBrains Mono,monospace", "fontSize": "0.8rem",
            })),
            html.Td(f"{r['cp']}",     style={"fontFamily": "JetBrains Mono,monospace", "fontSize": "0.72rem", "color": C.MUTED}),
            html.Td(f"{r['pct_within']}%", style={"color": C.GREEN if r['pct_within'] > 90 else C.RED, "fontWeight": "700", "fontSize": "0.72rem"}),
            html.Td(html.Span(r["capability"], style={
                "background": cpk_color + "22",
                "color": cpk_color,
                "borderRadius": "4px", "padding": "2px 7px",
                "fontSize": "0.65rem", "fontWeight": "700", "border": f"1px solid {cpk_color}33",
            })),
        ], style={"borderBottom": f"1px solid {C.BORDER}"}))

    # Cpk bar chart
    fig = go.Figure()
    for r in cap:
        color = CPK_COLOR(r["cpk"])
        fig.add_trace(go.Bar(
            x=[r["type"]], y=[r["cpk"]],
            marker_color=color, opacity=0.85,
            name=r["type"],
            text=[f"Cpk={r['cpk']}"], textposition="outside",
            textfont=dict(size=9, color=C.NAVY2, weight="bold"),
            hovertemplate=f"<b>{r['type']}</b><br>Cpk={r['cpk']}<br>Cp={r['cp']}<br>Within SLA: {r['pct_within']}%<extra></extra>",
        ))

    # Reference lines
    for val, label, color in [(1.67, "6σ Target (1.67)", C.GREEN), (1.33, "Capable (1.33)", C.ACCENT), (1.0, "Minimum (1.0)", C.AMBER)]:
        fig.add_hline(y=val, line_color=color, line_dash="dash", line_width=1.5,
                      annotation_text=label, annotation_font=dict(size=9, color=color),
                      annotation_position="right")

    fig.update_layout(**L, title=_t("Process Capability Index (Cpk) by Issue Type"),
                      showlegend=False, barmode="group",
                      xaxis=dict(gridcolor=C.BORDER), yaxis=dict(gridcolor=C.BORDER, title="Cpk"),
                      height=240)

    return html.Div([
        header,
        _g(fig, "ss-cpk-bar", h=240),
        html.Div(style={"marginTop": "12px"}),
        html.Table([
            html.Thead(html.Tr([
                html.Th(h) for h in ["Type", "SLA", "n", "Mean", "Std", "Cpk", "Cp", "% In SLA", "Status"]
            ], style={"background": C.ACCENT2})),
            html.Tbody(rows),
        ], style={"width": "100%", "borderCollapse": "collapse", "fontSize": "0.75rem"}),
    ])


# ── 4. DPMO Chart by Workstream ───────────────────────────────────────────────
def _build_dpmo_chart(dpmo_data):
    if not dpmo_data:
        return html.Div("No DPMO data available.", style={"color": C.MUTED, "fontSize": "0.75rem"})

    header = html.Div("DPMO BY WORKSTREAM (Label)", style={
        "fontSize": "0.58rem", "fontWeight": "800", "letterSpacing": "0.16em",
        "color": C.NAVY2, "marginBottom": "12px",
    })

    top = dpmo_data[:12]
    colors = [C.GREEN if r["sigma_level"] >= 4 else (C.AMBER if r["sigma_level"] >= 3 else C.RED) for r in top]

    fig = go.Figure(go.Bar(
        x=[r["dpmo"] for r in top],
        y=[r["group"] for r in top],
        orientation="h",
        marker_color=colors, opacity=0.88,
        text=[f"{r['dpmo']:,.0f} DPMO  ({r['sigma_level']}σ)" for r in top],
        textposition="outside",
        textfont=dict(size=9, color=C.NAVY2, weight="bold"),
        hovertemplate="<b>%{y}</b><br>DPMO: %{x:,.0f}<extra></extra>",
    ))

    # Reference lines
    for dpmo_val, sigma_label, color in [
        (3.4,    "6σ",  C.GREEN),
        (6_210,  "4σ",  C.ACCENT),
        (66_807, "3σ",  C.ORANGE),
        (308_538,"2σ",  C.RED),
    ]:
        fig.add_vline(x=dpmo_val, line_color=color, line_dash="dash", line_width=1.5,
                      annotation_text=sigma_label, annotation_font=dict(size=9, color=color),
                      annotation_position="top")

    fig.update_layout(**L, title=_t("DPMO by Workstream"),
                      xaxis=dict(title="DPMO", gridcolor=C.BORDER, type="log"),
                      yaxis=dict(autorange="reversed", gridcolor=C.BORDER),
                      height=340)

    # Summary table
    rows = []
    for r in top:
        sc = C.GREEN if r["sigma_level"] >= 4 else (C.AMBER if r["sigma_level"] >= 3 else C.RED)
        rows.append(html.Tr([
            html.Td(r["group"][:22], style={"fontWeight": "700", "fontSize": "0.71rem", "color": C.NAVY}),
            html.Td(str(r["n_issues"]), style={"fontSize": "0.71rem", "fontFamily": "JetBrains Mono,monospace"}),
            html.Td(str(r["defects"]), style={"color": C.RED, "fontWeight": "700", "fontSize": "0.71rem", "fontFamily": "JetBrains Mono,monospace"}),
            html.Td(f"{r['dpmo']:,.0f}", style={"fontFamily": "JetBrains Mono,monospace", "fontSize": "0.71rem"}),
            html.Td(html.Span(f"{r['sigma_level']}σ", style={
                "color": sc, "fontWeight": "800", "fontFamily": "JetBrains Mono,monospace",
            })),
            html.Td(f"{r['yield_pct']}%", style={"color": sc, "fontWeight": "700", "fontSize": "0.71rem"}),
        ], style={"borderBottom": f"1px solid {C.BORDER}"}))

    return html.Div([
        header,
        _g(fig, "ss-dpmo-bar", h=340),
        html.Div(style={"marginTop": "10px"}),
        html.Table([
            html.Thead(html.Tr([
                html.Th(h) for h in ["Workstream", "Issues", "Defects", "DPMO", "Sigma", "Yield"]
            ], style={"background": C.ACCENT2})),
            html.Tbody(rows),
        ], style={"width": "100%", "borderCollapse": "collapse", "fontSize": "0.75rem"}),
    ])


# ── 5. FMEA Register ──────────────────────────────────────────────────────────
def _build_fmea_table(fmea):
    header = html.Div([
        html.Div("FMEA REGISTER — Ranked by Risk Priority Number (RPN = Severity × Occurrence × Detection)", style={
            "fontSize": "0.58rem", "fontWeight": "800", "letterSpacing": "0.14em",
            "color": C.NAVY2, "marginBottom": "4px",
        }),
        html.Div("Actions with highest RPN must be addressed first. Target: reduce all RPNs below 60.", style={
            "fontSize": "0.67rem", "color": C.MUTED,
        }),
    ], style={"marginBottom": "12px"})

    rows = []
    for i, r in enumerate(fmea):
        rpn_color = RPN_COLOR.get(r["rpn_class"], C.MUTED)
        rows.append(html.Tr([
            html.Td(r["id"], style={"fontFamily": "JetBrains Mono,monospace", "fontSize": "0.68rem", "color": C.MUTED}),
            html.Td(r["process_step"], style={"fontSize": "0.71rem", "fontWeight": "700", "color": C.NAVY}),
            html.Td(r["failure_mode"], style={"fontSize": "0.71rem", "color": C.TEXT, "maxWidth": "180px"}),
            html.Td(str(r["severity"]),   style={"textAlign": "center", "color": C.RED, "fontWeight": "800", "fontFamily": "JetBrains Mono,monospace", "fontSize": "0.8rem"}),
            html.Td(str(r["occurrence"]), style={"textAlign": "center", "color": C.ORANGE, "fontWeight": "800", "fontFamily": "JetBrains Mono,monospace", "fontSize": "0.8rem"}),
            html.Td(str(r["detection"]),  style={"textAlign": "center", "color": C.AMBER, "fontWeight": "800", "fontFamily": "JetBrains Mono,monospace", "fontSize": "0.8rem"}),
            html.Td(
                html.Div(str(r["rpn"]), style={
                    "background": rpn_color, "color": "#fff",
                    "borderRadius": "5px", "padding": "3px 8px",
                    "fontWeight": "900", "fontSize": "0.82rem",
                    "fontFamily": "JetBrains Mono,monospace", "textAlign": "center",
                })
            ),
            html.Td(html.Span(r["rpn_class"], style={
                "background": rpn_color + "22", "color": rpn_color,
                "borderRadius": "4px", "padding": "2px 6px",
                "fontSize": "0.63rem", "fontWeight": "700",
            })),
            html.Td(f"({r['count']})", style={"fontSize": "0.68rem", "color": C.MUTED, "fontFamily": "JetBrains Mono,monospace"}),
            html.Td(r["recommended_action"], style={"fontSize": "0.67rem", "color": C.TEXT, "maxWidth": "250px", "lineHeight": "1.4"}),
        ], style={
            "background": "#FEF2F222" if r["rpn_class"] == "Critical" else C.SURFACE,
            "borderBottom": f"1px solid {C.BORDER}",
            "borderLeft": f"3px solid {rpn_color}" if i < 3 else "3px solid transparent",
        }))

    # RPN bar chart
    fig = go.Figure(go.Bar(
        x=[r["rpn"] for r in fmea],
        y=[f"{r['id']}: {r['failure_mode'][:35]}" for r in fmea],
        orientation="h",
        marker_color=[RPN_COLOR.get(r["rpn_class"], C.MUTED) for r in fmea],
        opacity=0.85,
        text=[str(r["rpn"]) for r in fmea],
        textposition="outside",
        textfont=dict(size=9, color=C.NAVY2, weight="bold"),
        hovertemplate="<b>%{y}</b><br>RPN: %{x}<extra></extra>",
    ))
    fig.add_vline(x=120, line_color=C.RED,   line_dash="dash", line_width=1.5,
                  annotation_text="Critical (120)", annotation_font=dict(size=9, color=C.RED))
    fig.add_vline(x=60,  line_color=C.AMBER, line_dash="dash", line_width=1.5,
                  annotation_text="Medium (60)",  annotation_font=dict(size=9, color=C.AMBER))
    fig.update_layout(**L, title=_t("FMEA — Risk Priority Number (RPN)"),
                      xaxis=dict(title="RPN", gridcolor=C.BORDER),
                      yaxis=dict(autorange="reversed", gridcolor=C.BORDER),
                      height=280)

    return html.Div([
        header,
        _g(fig, "ss-fmea-bar", h=280),
        html.Div(style={"marginTop": "12px"}),
        html.Div([
        html.Table([
            html.Thead(html.Tr([
                html.Th(h) for h in ["ID", "Process Step", "Failure Mode", "SEV", "OCC", "DET", "RPN", "Class", "Count", "Recommended Action"]
            ], style={"background": C.ACCENT2})),
            html.Tbody(rows),
        ], style={"width": "100%", "borderCollapse": "collapse", "fontSize": "0.73rem"})
        ], style={"overflowX": "auto"}),
    ])


# ── 6. RTY Section ────────────────────────────────────────────────────────────
def _build_rty_section(rty_data):
    rty    = rty_data.get("rty", 0)
    stages = rty_data.get("stages", [])
    cold   = rty_data.get("cold", False)
    color  = C.GREEN if rty > 90 else (C.AMBER if rty > 70 else C.RED)

    cold_banner = html.Div([
        html.Span("⏳ ", style={"fontSize": "0.8rem"}),
        html.Span(
            "Changelog data is loading in the background (first load only). "
            "RTY is currently showing approximation. Refresh in ~60 seconds for real stage-level data.",
            style={"fontSize": "0.67rem", "color": C.AMBER, "fontWeight": "600"},
        ),
    ], style={
        "padding": "8px 12px", "background": "#FFFBEB",
        "borderRadius": "6px", "border": f"1px solid {C.AMBER}44",
        "marginBottom": "10px",
    }) if cold else html.Div()

    mode_label = rty_data.get("mode", "approximation")
    mode_color = C.GREEN if mode_label == "changelog" else C.AMBER
    mode_text  = "Real (Jira Changelog)" if mode_label == "changelog" else "Approximation — changelog pending"

    header = html.Div([
        html.Div([
            html.Span("ROLLED THROUGHPUT YIELD", style={
                "fontSize": "0.58rem", "fontWeight": "800", "letterSpacing": "0.16em", "color": C.NAVY2,
            }),
            html.Span(f"  [{mode_text}]", style={
                "fontSize": "0.58rem", "color": mode_color, "fontWeight": "700",
                "fontFamily": "JetBrains Mono,monospace", "marginLeft": "8px",
            }),
        ], style={"display": "flex", "alignItems": "center"}),
        html.Div([
            html.Span(f"{rty}%", style={
                "fontSize": "2rem", "fontWeight": "900", "color": color,
                "fontFamily": "JetBrains Mono,monospace",
            }),
            html.Span(" end-to-end first-pass quality", style={"fontSize": "0.7rem", "color": C.MUTED, "marginLeft": "6px"}),
        ], style={"marginTop": "4px"}),
    ], style={"marginBottom": "12px"})

    if not stages:
        return html.Div([header, html.Div("No stage data.", style={"color": C.MUTED, "fontSize": "0.75rem"})])

    fig = go.Figure(go.Funnel(
        y=[s["stage"] for s in stages],
        x=[s["count"] for s in stages],
        textinfo="value+percent initial",
        marker=dict(
            color=[C.sc_bg(s["stage"]) for s in stages],
            line=dict(color=[C.sc(s["stage"]) for s in stages], width=2),
        ),
        connector=dict(line=dict(color=C.BORDER, width=1)),
        hovertemplate="<b>%{y}</b><br>Issues: %{x}<br>FY: " + "%{customdata}%<extra></extra>",
        customdata=[s["fy"] for s in stages],
    ))
    fig.update_layout(**L, title=_t("Workflow RTY Funnel — First-Pass Yield per Stage"), height=320)

    stage_rows = []
    for s in stages:
        fy_color = C.GREEN if s["fy"] >= 95 else (C.AMBER if s["fy"] >= 80 else C.RED)
        stage_rows.append(html.Tr([
            html.Td(s["stage"], style={"fontSize": "0.71rem", "fontWeight": "700"}),
            html.Td(str(s["count"]), style={"fontFamily": "JetBrains Mono,monospace", "fontSize": "0.71rem"}),
            html.Td(str(s["defects"]), style={"color": C.RED if s["defects"] > 0 else C.GREEN, "fontFamily": "JetBrains Mono,monospace", "fontSize": "0.71rem"}),
            html.Td(f"{s['fy']}%", style={"color": fy_color, "fontWeight": "700", "fontFamily": "JetBrains Mono,monospace", "fontSize": "0.71rem"}),
        ], style={"borderBottom": f"1px solid {C.BORDER}"}))

    return html.Div([
        header,
        _g(fig, "ss-rty-funnel", h=320),
        html.Div(style={"marginTop": "10px"}),
        html.Table([
            html.Thead(html.Tr([html.Th(h) for h in ["Stage", "Issues", "Defects", "FY%"]], style={"background": C.ACCENT2})),
            html.Tbody(stage_rows),
        ], style={"width": "100%", "borderCollapse": "collapse", "fontSize": "0.73rem"}),
    ])


# ── 7. MSA Audit ─────────────────────────────────────────────────────────────
def _build_msa_section(msa):
    header = html.Div("MEASUREMENT SYSTEM ANALYSIS (MSA)", style={
        "fontSize": "0.58rem", "fontWeight": "800", "letterSpacing": "0.16em",
        "color": C.NAVY2, "marginBottom": "12px",
    })

    if not msa:
        return html.Div([
            header,
            html.Div("✓ No measurement issues detected.", style={"color": C.GREEN, "fontSize": "0.78rem", "padding": "20px 0"}),
        ])

    cards = []
    for f in msa:
        sev_color = C.RED if f["severity"] == "High" else C.AMBER
        examples  = f.get("examples", [])
        cards.append(html.Div([
            html.Div([
                html.Span(f["severity"], style={
                    "background": sev_color, "color": "#fff",
                    "borderRadius": "4px", "padding": "2px 7px",
                    "fontSize": "0.62rem", "fontWeight": "800", "marginRight": "8px",
                }),
                html.Span(f["finding"], style={"fontWeight": "700", "color": C.NAVY, "fontSize": "0.74rem"}),
                html.Span(f"  {f['count']} issues ({f['pct']}%)", style={
                    "color": sev_color, "fontSize": "0.68rem", "fontWeight": "700",
                    "fontFamily": "JetBrains Mono,monospace", "marginLeft": "6px",
                }),
            ], style={"marginBottom": "4px"}),
            html.Div(f"Impact: {f['impact']}", style={"color": C.MUTED, "fontSize": "0.67rem", "marginBottom": "3px"}),
            html.Div(f"→ {f['action']}", style={"color": C.ACCENT, "fontSize": "0.67rem", "fontWeight": "600"}),
            html.Div(f"Examples: {', '.join(examples)}", style={"color": C.MUTED, "fontSize": "0.65rem", "marginTop": "2px"}) if examples else None,
        ], style={
            "padding": "10px 12px", "background": sev_color + "08",
            "borderRadius": "8px", "border": f"1px solid {sev_color}33",
            "borderLeft": f"4px solid {sev_color}", "marginBottom": "8px",
        }))

    return html.Div([header] + cards)


# ── 8. DPMO by Project Table ──────────────────────────────────────────────────
def _build_dpmo_project_table(dpmo_proj):
    header = html.Div("DPMO BY PROJECT — Baseline Sigma Measurement", style={
        "fontSize": "0.58rem", "fontWeight": "800", "letterSpacing": "0.16em",
        "color": C.NAVY2, "marginBottom": "12px",
    })

    if not dpmo_proj:
        return html.Div([header, html.Div("No project data.", style={"color": C.MUTED, "fontSize": "0.75rem"})])

    rows = []
    for r in dpmo_proj:
        sc = C.GREEN if r["sigma_level"] >= 4 else (C.AMBER if r["sigma_level"] >= 3 else C.RED)
        defect_breakdown = ", ".join(f"{k}: {v}" for k, v in r.get("defect_types", {}).items())
        rows.append(html.Tr([
            html.Td(r["group"], style={"fontWeight": "700", "color": C.NAVY, "fontSize": "0.73rem",
                                       "fontFamily": "JetBrains Mono,monospace"}),
            html.Td(str(r["n_issues"]),     style={"fontSize": "0.72rem", "fontFamily": "JetBrains Mono,monospace"}),
            html.Td(str(r["defects"]),      style={"color": C.RED, "fontWeight": "700", "fontFamily": "JetBrains Mono,monospace"}),
            html.Td(str(r["opportunities"]),style={"fontSize": "0.72rem", "fontFamily": "JetBrains Mono,monospace", "color": C.MUTED}),
            html.Td(f"{r['dpmo']:,.1f}",    style={"fontFamily": "JetBrains Mono,monospace", "fontWeight": "700"}),
            html.Td(html.Span(f"{r['sigma_level']}σ", style={
                "color": sc, "fontWeight": "900", "fontSize": "0.9rem",
                "fontFamily": "JetBrains Mono,monospace",
            })),
            html.Td(f"{r['yield_pct']}%",  style={"color": sc, "fontWeight": "700", "fontSize": "0.72rem"}),
            html.Td(defect_breakdown or "—", style={"fontSize": "0.65rem", "color": C.MUTED}),
        ], style={"borderBottom": f"1px solid {C.BORDER}"}))

    return html.Div([
        header,
        html.Table([
            html.Thead(html.Tr([
                html.Th(h) for h in ["Project", "Issues", "Defects", "Opportunities", "DPMO", "Sigma", "Yield", "Defect Breakdown"]
            ], style={"background": C.ACCENT2})),
            html.Tbody(rows),
        ], style={"width": "100%", "borderCollapse": "collapse", "fontSize": "0.73rem"}),
        html.Div([
            html.Div("SIGMA SCALE REFERENCE", style={"fontSize": "0.55rem", "fontWeight": "800", "color": C.MUTED, "letterSpacing": "0.12em", "marginBottom": "6px"}),
            html.Div([
                html.Span(s, style={
                    "background": c + "22", "color": c, "borderRadius": "4px",
                    "padding": "3px 10px", "fontSize": "0.67rem", "fontWeight": "700",
                    "marginRight": "8px", "border": f"1px solid {c}44",
                    "fontFamily": "JetBrains Mono,monospace",
                })
                for s, c in [("6σ = 3.4 DPMO", C.GREEN), ("5σ = 233 DPMO", C.TEAL),
                              ("4σ = 6,210 DPMO", C.ACCENT), ("3σ = 66,807 DPMO", C.ORANGE),
                              ("2σ = 308,538 DPMO", C.RED)]
            ]),
        ], style={"marginTop": "14px", "padding": "10px 12px", "background": C.BG, "borderRadius": "6px"}),
    ])


def register_callbacks(app, get_issues_fn):
    pass
