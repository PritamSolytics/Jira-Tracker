"""
ml_page.py — Quant ML Dashboard page
Plug into app.py: import ml_page as ML, then add /ml route.
"""
from dash import html, dcc, Input, Output, State
import plotly.graph_objects as go
from collections import Counter
import components as C

# ── colour helpers (reuse from components) ─────────────────────────────────────
def _slip_color(prob):
    if prob >= 70: return C.RED
    if prob >= 40: return C.AMBER
    return C.GREEN

def _bar(value, max_val=100, color=C.ACCENT):
    pct = min(100, value / max_val * 100)
    return html.Div([
        html.Div(style={
            "width": f"{pct}%", "height": "6px",
            "background": color, "borderRadius": "3px",
            "transition": "width 0.4s ease",
        })
    ], style={"background": C.BORDER, "borderRadius": "3px", "height": "6px", "width": "100%"})


# ── Layout ─────────────────────────────────────────────────────────────────────
def layout(issues):
    import ml_engine as ML
    meta  = ML.get_meta()
    ready = ML.models_exist()

    # ── Model status card ──────────────────────────────────────────────────────
    if ready:
        trained_at = meta.get("trained_at", "")[:19].replace("T", " ")
        auc        = meta.get("auc_test", 0)
        cv_auc     = meta.get("auc_cv", 0)
        n_train    = meta.get("n_train", 0)
        slip_rate  = meta.get("slip_rate", 0)
        fi         = meta.get("feature_importance", {})

        status_card = C.card(
            html.Div([
                html.Div([
                    html.Div("MODEL STATUS", style={"fontSize":"0.55rem","fontWeight":"800","letterSpacing":"0.18em","color":C.MUTED,"marginBottom":"6px"}),
                    html.Div("🟢  TRAINED & LIVE", style={"fontSize":"0.82rem","fontWeight":"900","color":C.GREEN,"fontFamily":"JetBrains Mono,monospace"}),
                    html.Div(f"Last trained: {trained_at}", style={"fontSize":"0.65rem","color":C.MUTED,"marginTop":"4px"}),
                ], style={"flex":"1"}),
                html.Div([
                    _metric_block("AUC (test)",    f"{auc:.3f}",     C.ACCENT),
                    _metric_block("AUC (5-fold CV)", f"{cv_auc:.3f}", C.PURPLE),
                    _metric_block("Train samples", str(n_train),     C.TEAL),
                    _metric_block("Hist slip rate", f"{slip_rate}%", C.RED),
                ], style={"display":"flex","gap":"12px","flexWrap":"wrap"}),
            ], style={"display":"flex","gap":"24px","alignItems":"flex-start","flexWrap":"wrap"}),
            # Feature importance bar chart
            html.Div([
                html.Div("FEATURE IMPORTANCE", style={"fontSize":"0.55rem","fontWeight":"800","letterSpacing":"0.18em","color":C.MUTED,"margin":"16px 0 10px"}),
                *[html.Div([
                    html.Div(f, style={"fontSize":"0.65rem","color":C.TEXT,"fontFamily":"JetBrains Mono,monospace","width":"130px","flexShrink":"0"}),
                    html.Div(style={"flex":"1"}, children=_bar(v*100, color=C.ACCENT)),
                    html.Div(f"{v:.3f}", style={"fontSize":"0.65rem","color":C.NAVY2,"fontWeight":"700","width":"40px","textAlign":"right","fontFamily":"JetBrains Mono,monospace"}),
                ], style={"display":"flex","alignItems":"center","gap":"10px","marginBottom":"6px"})
                  for f, v in sorted(fi.items(), key=lambda x: -x[1])],
            ]) if fi else html.Div(),
        )
    else:
        status_card = C.card(
            html.Div("⚠  No trained model found. Click Retrain below.", style={"color":C.AMBER,"fontSize":"0.78rem","fontWeight":"700"})
        )

    # ── Retrain controls ───────────────────────────────────────────────────────
    retrain_card = C.card(
        html.Div("RETRAIN MODEL", style={"fontSize":"0.55rem","fontWeight":"800","letterSpacing":"0.18em","color":C.NAVY2,"marginBottom":"14px"}),
        html.Div([
            html.Div([
                html.Div("Triggers a full retrain on current Jira data.", style={"fontSize":"0.72rem","color":C.MUTED,"marginBottom":"12px"}),
                html.Div([
                    html.Div("• Fetches latest issues from Jira", style={"fontSize":"0.7rem","color":C.TEXT}),
                    html.Div("• Re-engineers features", style={"fontSize":"0.7rem","color":C.TEXT}),
                    html.Div("• Retrains RF slip predictor + K-Means + Isolation Forest", style={"fontSize":"0.7rem","color":C.TEXT}),
                    html.Div("• Overwrites model files on disk", style={"fontSize":"0.7rem","color":C.TEXT}),
                    html.Div("• Updates metrics immediately", style={"fontSize":"0.7rem","color":C.TEXT}),
                ], style={"display":"flex","flexDirection":"column","gap":"4px","marginBottom":"14px","paddingLeft":"8px","borderLeft":f"3px solid {C.BORDER}"}),
                html.Button(
                    "⟳  Retrain Now",
                    id="ml-retrain-btn", n_clicks=0,
                    style={"background":C.NAVY,"color":"#fff","border":"none","borderRadius":"6px",
                           "padding":"10px 22px","cursor":"pointer","fontSize":"0.75rem","fontWeight":"800",
                           "letterSpacing":"0.06em","marginRight":"12px"}
                ),
                html.Button(
                    "⬇  Export Dataset CSV",
                    id="ml-export-btn", n_clicks=0,
                    style={"background":C.SURFACE,"color":C.NAVY,"border":f"2px solid {C.NAVY}","borderRadius":"6px",
                           "padding":"10px 22px","cursor":"pointer","fontSize":"0.75rem","fontWeight":"800","letterSpacing":"0.06em"}
                ),
                dcc.Download(id="ml-download"),
            ], style={"flex":"1"}),
            html.Div([
                html.Div(id="ml-retrain-status", style={"fontSize":"0.75rem","color":C.GREEN,"fontWeight":"700","minHeight":"20px"}),
                dcc.Loading(id="ml-loading", children=html.Div(id="ml-loading-output"), type="circle", color=C.ACCENT),
            ], style={"flex":"1","paddingLeft":"20px"}),
        ], style={"display":"flex","gap":"16px","alignItems":"flex-start"}),
    )

    # ── Predictions table ──────────────────────────────────────────────────────
    if ready:
        preds = ML.predict_slip(issues)
        pred_rows = [
            html.Tr([
                html.Td(html.A(p["key"], href=f"https://solytics.atlassian.net/browse/{p['key']}",
                               target="_blank",
                               style={"color":C.ACCENT,"fontFamily":"JetBrains Mono,monospace","fontSize":"0.72rem","fontWeight":"700","textDecoration":"none"})),
                html.Td(p["assignee"], style={"fontSize":"0.72rem"}),
                html.Td(C.status_badge(p["status"])),
                html.Td(p["priority"], style={"color":C.pc(p["priority"]),"fontWeight":"700","fontSize":"0.72rem"}),
                html.Td([
                    html.Span(f"{p['slip_prob']}%",
                              style={"color":_slip_color(p['slip_prob']),"fontWeight":"900",
                                     "fontFamily":"JetBrains Mono,monospace","fontSize":"0.8rem"}),
                    _bar(p["slip_prob"], color=_slip_color(p["slip_prob"])),
                ], style={"width":"120px"}),
                html.Td(html.Span(p["cluster_label"], style={"fontSize":"0.72rem","fontWeight":"700"})),
                html.Td(html.Span("⚠ Anomaly" if p["is_anomaly"] else "—",
                                  style={"color":C.RED if p["is_anomaly"] else C.MUTED,
                                         "fontWeight":"700","fontSize":"0.7rem"})),
                html.Td(f"{p['days_open']}d", style={"fontFamily":"JetBrains Mono,monospace","fontSize":"0.72rem"}),
            ], style={"background": C.SURFACE if i%2==0 else C.BG})
            for i, p in enumerate(preds)
        ]

        pred_card = C.card(
            html.Div([
                html.Div("SLIP RISK PREDICTIONS — OPEN ISSUES",
                         style={"fontSize":"0.55rem","fontWeight":"800","letterSpacing":"0.18em","color":C.NAVY2}),
                html.Div(f"{len(preds)} open issues scored · RF classifier · AUC {meta.get('auc_test',0):.3f}",
                         style={"fontSize":"0.65rem","color":C.MUTED,"marginTop":"3px"}),
            ], style={"marginBottom":"12px"}),
            html.Table([
                html.Thead(html.Tr([
                    html.Th(h) for h in ["Issue","Assignee","Status","Priority","Slip Prob ↓","Risk Cluster","Anomaly","Stale"]
                ], style={"background":C.ACCENT2})),
                html.Tbody(pred_rows),
            ], style={"width":"100%","borderCollapse":"collapse","fontSize":"0.75rem"}),
        )

        # ── Cluster distribution donut ─────────────────────────────────────────
        cluster_counts = Counter(p["cluster_label"] for p in preds)
        donut_colors   = [C.RED if "Critical" in k else (C.AMBER if "Watch" in k else C.GREEN)
                          for k in cluster_counts.keys()]
        donut_fig = go.Figure(go.Pie(
            labels=list(cluster_counts.keys()),
            values=list(cluster_counts.values()),
            marker_colors=donut_colors, hole=0.62,
            textinfo="label+percent", textfont=dict(size=10),
        ))
        L = dict(paper_bgcolor=C.SURFACE, plot_bgcolor=C.SURFACE,
                 font=dict(color=C.TEXT, size=11, family="JetBrains Mono, monospace"),
                 margin=dict(l=8,r=8,t=36,b=8))
        donut_fig.update_layout(**L, title=dict(text="Risk Cluster Distribution",
                                                 font=dict(size=11,color=C.NAVY2,weight="bold")))

        anomaly_issues = [p for p in preds if p["is_anomaly"]]
        anomaly_card = C.card(
            html.Div("ANOMALY DETECTION — ISOLATION FOREST",
                     style={"fontSize":"0.55rem","fontWeight":"800","letterSpacing":"0.18em","color":C.RED,"marginBottom":"10px"}),
            html.Div(f"{len(anomaly_issues)} statistically abnormal open issues detected (contamination=10%)",
                     style={"fontSize":"0.68rem","color":C.MUTED,"marginBottom":"10px"}),
            html.Div([
                html.Div([
                    html.A(a["key"], href=f"https://solytics.atlassian.net/browse/{a['key']}",
                           target="_blank",
                           style={"color":C.ACCENT,"fontFamily":"JetBrains Mono,monospace","fontSize":"0.7rem","fontWeight":"700","textDecoration":"none","marginRight":"8px"}),
                    html.Span(a["assignee"], style={"color":C.TEXT,"fontSize":"0.7rem","marginRight":"8px"}),
                    html.Span(f"{a['slip_prob']}% slip", style={"color":C.RED,"fontWeight":"700","fontSize":"0.68rem"}),
                ], style={"padding":"6px 8px","background":"#FEF2F2","borderRadius":"4px","marginBottom":"4px","display":"flex","flexWrap":"wrap","gap":"4px"})
                for a in anomaly_issues[:15]
            ]) if anomaly_issues else html.Div("No anomalies in open issues.", style={"color":C.GREEN,"fontSize":"0.75rem"}),
        )

        charts_row = C.grid(
            C.card(dcc.Graph(figure=donut_fig, config={"displayModeBar":False}, style={"height":"260px"})),
            anomaly_card,
            cols=2
        )
    else:
        pred_card   = html.Div("Train the model first.", style={"color":C.MUTED,"padding":"20px"})
        charts_row  = html.Div()

    return html.Div([
        C.section("🤖 Quant ML Engine", "Slip predictor · Risk clustering · Anomaly detection"),
        C.grid(status_card, retrain_card, cols=2),
        html.Div(style={"marginTop":"16px"}),
        charts_row,
        html.Div(style={"marginTop":"16px"}),
        pred_card,
    ])


def _metric_block(label, value, color):
    return html.Div([
        html.Div(value, style={"fontSize":"1.3rem","fontWeight":"900","color":color,
                                "fontFamily":"JetBrains Mono,monospace","lineHeight":"1"}),
        html.Div(label, style={"fontSize":"0.58rem","color":C.MUTED,"marginTop":"3px",
                                "textTransform":"uppercase","letterSpacing":"0.1em","fontWeight":"700"}),
    ], style={"background":C.BG,"borderRadius":"8px","padding":"12px 14px",
               "borderLeft":f"3px solid {color}","minWidth":"90px"})


# ── Callbacks ──────────────────────────────────────────────────────────────────
def register_callbacks(app, get_issues_fn):
    from dash import Output, Input, State
    import ml_engine as ML

    @app.callback(
        Output("ml-retrain-status", "children"),
        Output("ml-loading-output", "children"),
        Input("ml-retrain-btn", "n_clicks"),
        prevent_initial_call=True,
    )
    def retrain(n):
        if not n:
            return "", ""
        try:
            issues = get_issues_fn(force=True)
            meta   = ML.train_models(issues)
            if "error" in meta:
                return f"❌ {meta['error']}", ""
            return (
                f"✓ Retrained {meta['trained_at'][:19]} · "
                f"AUC {meta['auc_test']} · "
                f"{meta['n_train']} samples",
                ""
            )
        except Exception as e:
            return f"❌ Error: {str(e)[:120]}", ""

    @app.callback(
        Output("ml-download", "data"),
        Input("ml-export-btn", "n_clicks"),
        prevent_initial_call=True,
    )
    def export_csv(n):
        if not n:
            return None
        import ml_engine as ML
        issues = get_issues_fn()
        path   = ML.export_dataset_csv(issues)
        return dcc.send_file(path, filename="nng_jira_dataset.csv")
