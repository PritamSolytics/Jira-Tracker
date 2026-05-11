import threading as _threading

_train_state = {"running": False, "result": None, "error": None}

"""
ml_page.py — Predictive Analytics Engine UI
Slip predictor, risk clustering, outlier pattern detection, customizable training.
"""
from dash import html, dcc, Input, Output, State
import plotly.graph_objects as go
from collections import Counter
import components as C

L = dict(paper_bgcolor=C.SURFACE, plot_bgcolor=C.SURFACE,
         font=dict(color=C.TEXT, size=11, family="JetBrains Mono, monospace"),
         margin=dict(l=8,r=8,t=36,b=8))

def _t(text): return dict(text=text, font=dict(size=11, color=C.NAVY2, weight="bold"))
def _g(fig, gid, h=280): return dcc.Graph(figure=fig, id=gid, style={"height":f"{h}px"}, config={"displayModeBar":False})

def _slip_color(prob):
    if prob >= 70: return C.RED
    if prob >= 40: return C.AMBER
    return C.GREEN

def _progress_bar(value, color=C.ACCENT):
    pct = min(100, max(0, value))
    return html.Div([
        html.Div(style={"width":f"{pct}%","height":"5px","background":color,
                        "borderRadius":"3px","transition":"width 0.3s"})
    ], style={"background":C.BORDER,"borderRadius":"3px","height":"5px","width":"100%","marginTop":"3px"})

def _metric(label, value, color=C.ACCENT):
    return html.Div([
        html.Div(str(value), style={"fontSize":"1.4rem","fontWeight":"900","color":color,
                                     "fontFamily":"JetBrains Mono,monospace","lineHeight":"1"}),
        html.Div(label, style={"fontSize":"0.58rem","color":C.MUTED,"marginTop":"3px",
                                "textTransform":"uppercase","letterSpacing":"0.1em","fontWeight":"700"}),
    ], style={"background":C.BG,"borderRadius":"8px","padding":"12px 14px",
               "borderLeft":f"3px solid {color}","minWidth":"90px"})


def layout(issues):
    import ml_engine as ML
    meta  = ML.get_meta()
    ready = ML.models_exist()

    # ── Model status card ──────────────────────────────────────────────────────
    if ready:
        trained_at = meta.get("trained_at","")[:19].replace("T"," ")
        fi = meta.get("feature_importance", {})
        cfg = meta.get("config", {})

        status_card = C.card(
            html.Div("MODEL STATUS", style={"fontSize":"0.55rem","fontWeight":"800","letterSpacing":"0.18em","color":C.MUTED,"marginBottom":"8px"}),
            html.Div([
                html.Div([
                    html.Div("TRAINED  —  LIVE",
                             style={"fontSize":"0.78rem","fontWeight":"900","color":C.GREEN,"fontFamily":"JetBrains Mono,monospace"}),
                    html.Div(f"Last trained: {trained_at}",
                             style={"fontSize":"0.63rem","color":C.MUTED,"marginTop":"3px"}),
                    html.Div(f"Algorithm: {cfg.get('model_type','random_forest').replace('_',' ').title()}",
                             style={"fontSize":"0.63rem","color":C.MUTED,"fontFamily":"JetBrains Mono,monospace"}),
                ], style={"flex":"1"}),
                html.Div([
                    _metric("AUC (Test)",    meta.get("auc_test","—"),   C.ACCENT),
                    _metric("AUC (5-CV)",    meta.get("auc_cv","—"),     C.PURPLE),
                    _metric("Train n",       meta.get("n_train","—"),    C.TEAL),
                    _metric("Hist Slip %",   f"{meta.get('slip_rate','—')}%", C.RED),
                ], style={"display":"flex","gap":"10px","flexWrap":"wrap"}),
            ], style={"display":"flex","gap":"20px","alignItems":"flex-start","flexWrap":"wrap"}),
            # Feature importance
            html.Div([
                html.Div("FEATURE IMPORTANCE", style={"fontSize":"0.55rem","fontWeight":"800",
                          "letterSpacing":"0.18em","color":C.MUTED,"margin":"16px 0 10px"}),
                *[html.Div([
                    html.Div(f, style={"fontSize":"0.63rem","color":C.TEXT,
                              "fontFamily":"JetBrains Mono,monospace","width":"180px","flexShrink":"0"}),
                    html.Div(style={"flex":"1"}, children=_progress_bar(v*100, color=C.ACCENT)),
                    html.Div(f"{v:.4f}", style={"fontSize":"0.63rem","color":C.NAVY2,"fontWeight":"700",
                              "width":"50px","textAlign":"right","fontFamily":"JetBrains Mono,monospace"}),
                ], style={"display":"flex","alignItems":"center","gap":"10px","marginBottom":"5px"})
                  for f, v in sorted(fi.items(), key=lambda x: -x[1]) if v > 0],
            ]) if fi else html.Div(),
        )
    else:
        status_card = C.card(
            html.Div("MODEL STATUS", style={"fontSize":"0.55rem","fontWeight":"800","letterSpacing":"0.18em","color":C.MUTED,"marginBottom":"8px"}),
            html.Div("No trained model found. Configure parameters below and click Train Model.",
                     style={"color":C.AMBER,"fontSize":"0.75rem","fontWeight":"600"}),
        )

    # ── Training configuration card ────────────────────────────────────────────
    train_card = C.card(
        html.Div("MODEL TRAINING CONFIGURATION",
                 style={"fontSize":"0.55rem","fontWeight":"800","letterSpacing":"0.18em","color":C.NAVY2,"marginBottom":"14px"}),
        html.Div([
            # Col 1: algorithm + estimators
            html.Div([
                html.Label("Algorithm", style={"fontSize":"0.63rem","fontWeight":"700","color":C.MUTED,
                             "textTransform":"uppercase","letterSpacing":"0.08em"}),
                dcc.Dropdown(id="ml-model-type",
                    options=[
                        {"label":"Random Forest","value":"random_forest"},
                        {"label":"Gradient Boosting","value":"gradient_boosting"},
                        {"label":"Logistic Regression","value":"logistic"},
                    ],
                    value="random_forest", clearable=False,
                    style={"fontSize":"0.74rem","marginTop":"4px","marginBottom":"12px"}),

                html.Label("Estimators (trees)", style={"fontSize":"0.63rem","fontWeight":"700","color":C.MUTED,
                             "textTransform":"uppercase","letterSpacing":"0.08em"}),
                dcc.Slider(id="ml-n-estimators", min=50, max=500, step=50, value=200,
                           marks={50:"50",200:"200",500:"500"},
                           tooltip={"placement":"bottom","always_visible":True}),
            ], style={"flex":"1","minWidth":"180px"}),

            # Col 2: test size + clusters
            html.Div([
                html.Label("Test Split Size", style={"fontSize":"0.63rem","fontWeight":"700","color":C.MUTED,
                             "textTransform":"uppercase","letterSpacing":"0.08em"}),
                dcc.Slider(id="ml-test-size", min=0.1, max=0.4, step=0.05, value=0.2,
                           marks={0.1:"10%",0.2:"20%",0.3:"30%",0.4:"40%"},
                           tooltip={"placement":"bottom","always_visible":True}),
                html.Div(style={"height":"10px"}),
                html.Label("Risk Clusters (K)", style={"fontSize":"0.63rem","fontWeight":"700","color":C.MUTED,
                             "textTransform":"uppercase","letterSpacing":"0.08em"}),
                dcc.Slider(id="ml-n-clusters", min=2, max=5, step=1, value=3,
                           marks={2:"2",3:"3",4:"4",5:"5"},
                           tooltip={"placement":"bottom","always_visible":True}),
            ], style={"flex":"1","minWidth":"180px"}),

            # Col 3: contamination + max depth
            html.Div([
                html.Label("Outlier Contamination %", style={"fontSize":"0.63rem","fontWeight":"700","color":C.MUTED,
                             "textTransform":"uppercase","letterSpacing":"0.08em"}),
                dcc.Slider(id="ml-contamination", min=0.05, max=0.3, step=0.05, value=0.1,
                           marks={0.05:"5%",0.1:"10%",0.2:"20%",0.3:"30%"},
                           tooltip={"placement":"bottom","always_visible":True}),
                html.Div(style={"height":"10px"}),
                html.Label("Max Tree Depth (blank = unlimited)", style={"fontSize":"0.63rem","fontWeight":"700",
                             "color":C.MUTED,"textTransform":"uppercase","letterSpacing":"0.08em"}),
                dcc.Input(id="ml-max-depth", type="number", min=2, max=20, placeholder="None",
                          style={"width":"100%","padding":"6px","border":f"1px solid {C.BORDER}",
                                 "borderRadius":"6px","fontSize":"0.74rem","marginTop":"4px",
                                 "fontFamily":"JetBrains Mono,monospace"}),
            ], style={"flex":"1","minWidth":"180px"}),
        ], style={"display":"flex","gap":"24px","flexWrap":"wrap","marginBottom":"16px"}),

        html.Div([
            html.Button("Train Model", id="ml-retrain-btn", n_clicks=0, style={
                "background":C.NAVY,"color":"#fff","border":"none","borderRadius":"6px",
                "padding":"10px 24px","cursor":"pointer","fontSize":"0.74rem",
                "fontWeight":"800","letterSpacing":"0.06em","marginRight":"10px"}),
            html.Button("Export Dataset CSV", id="ml-export-btn", n_clicks=0, style={
                "background":C.SURFACE,"color":C.NAVY,"border":f"2px solid {C.BORDER}",
                "borderRadius":"6px","padding":"10px 20px","cursor":"pointer",
                "fontSize":"0.74rem","fontWeight":"700"}),
            dcc.Download(id="ml-download"),
        ]),
        html.Div([
            dcc.Loading(html.Div(id="ml-loading-output"), type="circle", color=C.ACCENT),
            html.Div(id="ml-retrain-status",
                     style={"fontSize":"0.74rem","color":C.GREEN,"fontWeight":"700","minHeight":"20px","marginTop":"8px"}),
        ]),
    )

    # ── Predictions ────────────────────────────────────────────────────────────
    if ready:
        preds = ML.predict_slip(issues)

        # Cluster donut
        cluster_counts = Counter(p["cluster_label"] for p in preds)
        cluster_colors = [C.RED if "Critical" in k else (C.AMBER if "Elevated" in k else C.GREEN)
                          for k in cluster_counts.keys()]
        donut_fig = go.Figure(go.Pie(
            labels=list(cluster_counts.keys()), values=list(cluster_counts.values()),
            marker_colors=cluster_colors, hole=0.6, textinfo="label+percent",
        ))
        donut_fig.update_layout(**L, title=_t("Risk Cluster Distribution"))

        # Slip probability histogram
        probs = [p["delivery_risk_signal"] for p in preds]
        hist_fig = go.Figure(go.Histogram(
            x=probs, nbinsx=10,
            marker_color=C.ACCENT, opacity=0.8,
            hovertemplate="Slip Prob: %{x}%<br>Count: %{y}<extra></extra>",
        ))
        hist_fig.update_layout(**L, title=_t("Delivery Risk Signal Distribution"),
            xaxis=dict(title="Delivery Risk Signal %", gridcolor=C.BORDER),
            yaxis=dict(title="Count", gridcolor=C.BORDER))

        # Outlier panel
        outlier_issues = [p for p in preds if p["is_outlier"]]
        outlier_card = C.card(
            html.Div("OUTLIER PATTERN DETECTION — ISOLATION FOREST",
                     style={"fontSize":"0.55rem","fontWeight":"800","letterSpacing":"0.18em","color":C.RED,"marginBottom":"8px"}),
            html.Div(f"{len(outlier_issues)} statistically abnormal open issues detected "
                     f"(contamination={int(meta.get('contamination',0.1)*100)}%)",
                     style={"fontSize":"0.68rem","color":C.MUTED,"marginBottom":"10px"}),
            html.Div([
                html.Div([
                    html.A(a["key"], href=f"https://solytics.atlassian.net/browse/{a['key']}",
                           target="_blank",
                           style={"color":C.ACCENT,"fontFamily":"JetBrains Mono,monospace",
                                  "fontSize":"0.7rem","fontWeight":"700","textDecoration":"none","marginRight":"8px"}),
                    html.Span(a["assignee"], style={"color":C.TEXT,"fontSize":"0.7rem","marginRight":"8px"}),
                    C.status_badge(a["status"]),
                    html.Span(f"  Slip: {a['delivery_risk_signal']}%",
                              style={"color":_slip_color(a["delivery_risk_signal"]),"fontWeight":"700","fontSize":"0.68rem"}),
                ], style={"padding":"5px 8px","background":"#FEF2F2","borderRadius":"4px",
                          "marginBottom":"4px","display":"flex","flexWrap":"wrap","gap":"4px"})
                for a in outlier_issues[:15]
            ]) if outlier_issues else html.Div("No anomalies detected.", style={"color":C.GREEN,"fontSize":"0.75rem"}),
        )

        # Predictions table
        pred_table_rows = [
            html.Tr([
                html.Td(html.A(p["key"],
                    href=f"https://solytics.atlassian.net/browse/{p['key']}",
                    target="_blank",
                    style={"color":C.ACCENT,"fontFamily":"JetBrains Mono,monospace",
                           "fontSize":"0.72rem","fontWeight":"700","textDecoration":"none"})),
                html.Td(p["assignee"], style={"fontSize":"0.72rem"}),
                html.Td(C.status_badge(p["status"])),
                html.Td(p["priority"],
                        style={"color":C.pc(p["priority"]),"fontWeight":"700","fontSize":"0.72rem"}),
                html.Td([
                    html.Span(f"{p['delivery_risk_signal']}%",
                              style={"color":_slip_color(p["delivery_risk_signal"]),"fontWeight":"900",
                                     "fontFamily":"JetBrains Mono,monospace","fontSize":"0.8rem"}),
                    _progress_bar(p["delivery_risk_signal"], color=_slip_color(p["delivery_risk_signal"])),
                ], style={"width":"110px"}),
                html.Td(p["cluster_label"],
                        style={"fontSize":"0.72rem","fontWeight":"700",
                               "color":C.RED if "Critical" in p["cluster_label"]
                                       else (C.AMBER if "Elevated" in p["cluster_label"] else C.GREEN)}),
                html.Td("Yes" if p["is_outlier"] else "—",
                        style={"color":C.RED if p["is_outlier"] else C.MUTED,
                               "fontWeight":"700","fontSize":"0.7rem"}),
                html.Td(str(p["blocker_count"]),
                        style={"fontFamily":"JetBrains Mono,monospace","fontSize":"0.72rem",
                               "color":C.RED if p["blocker_count"]>0 else C.MUTED}),
                html.Td(f"{p['days_open']}d",
                        style={"fontFamily":"JetBrains Mono,monospace","fontSize":"0.72rem"}),
            ], style={"background":C.SURFACE if i%2==0 else C.BG})
            for i, p in enumerate(preds)
        ]

        pred_card = C.card(
            html.Div([
                html.Div("SLIP RISK PREDICTIONS — OPEN ISSUES",
                         style={"fontSize":"0.55rem","fontWeight":"800","letterSpacing":"0.18em","color":C.NAVY2}),
                html.Div(f"{len(preds)} open issues scored  |  Algorithm: {meta.get('model_type','—').replace('_',' ').title()}  |  AUC {meta.get('auc_test','—')}",
                         style={"fontSize":"0.63rem","color":C.MUTED,"marginTop":"3px","fontFamily":"JetBrains Mono,monospace"}),
            ], style={"marginBottom":"12px"}),
            html.Table([
                html.Thead(html.Tr([
                    html.Th(h) for h in
                    ["Issue","Assignee","Status","Priority","Delivery Risk Signal","Risk Cluster","Outlier","Blockers","Last Progress"]
                ], style={"background":C.ACCENT2})),
                html.Tbody(pred_table_rows),
            ], style={"width":"100%","borderCollapse":"collapse","fontSize":"0.75rem"}),
        )

        charts_row = C.grid(
            C.card(_g(donut_fig, "ml-donut", 260)),
            C.card(_g(hist_fig,  "ml-hist",  260)),
            cols=2
        )
    else:
        pred_card  = html.Div("Train the model to view predictions.", style={"color":C.MUTED,"padding":"20px","fontSize":"0.75rem"})
        charts_row = html.Div()
        outlier_card = html.Div()

    return html.Div([
        C.section("Predictive Analytics",
                  "Deadline slip predictor  |  Risk clustering  |  Outlier detection"),
        C.grid(status_card, train_card, cols=2),
        html.Div(style={"marginTop":"16px"}),
        charts_row,
        html.Div(style={"marginTop":"16px"}),
        outlier_card if ready else html.Div(),
        html.Div(style={"marginTop":"16px"}),
        pred_card,
    ])


def register_callbacks(app, get_issues_fn):
    from dash import Output, Input, State
    import ml_engine as ML

    @app.callback(
        Output("ml-retrain-status","children"),
        Output("ml-loading-output","children"),
        Input("ml-retrain-btn","n_clicks"),
        State("ml-model-type","value"),
        State("ml-n-estimators","value"),
        State("ml-test-size","value"),
        State("ml-n-clusters","value"),
        State("ml-contamination","value"),
        State("ml-max-depth","value"),
        prevent_initial_call=True,
    )
    def retrain(n, model_type, n_est, test_size, n_clusters, contamination, max_depth):
        if not n: return "", ""

        # If already running return status
        if _train_state["running"]:
            return "Training in progress...", ""

        # If previous run finished — return result and reset
        if _train_state["result"] is not None:
            msg = _train_state["result"]
            _train_state["result"] = None
            return msg, ""
        if _train_state["error"] is not None:
            msg = _train_state["error"]
            _train_state["error"] = None
            return msg, ""

        config = {
            "model_type":    model_type    or "random_forest",
            "n_estimators":  int(n_est)    if n_est else 200,
            "test_size":     float(test_size) if test_size else 0.2,
            "n_clusters":    int(n_clusters) if n_clusters else 3,
            "contamination": float(contamination) if contamination else 0.1,
            "max_depth":     int(max_depth) if max_depth else None,
        }

        def _run():
            _train_state["running"] = True
            _train_state["result"]  = None
            _train_state["error"]   = None
            try:
                issues = get_issues_fn(force=True)
                meta   = ML.train_models(issues, config=config)
                if "error" in meta:
                    _train_state["error"] = f"Error: {meta['error']}"
                else:
                    _train_state["result"] = (
                        f"✓ Trained {meta['trained_at'][:19]}  |  "
                        f"AUC {meta.get('auc_test','—')}  |  "
                        f"n={meta.get('n_train','—')}  |  "
                        f"Slip rate {meta.get('slip_rate','—')}%"
                    )
            except Exception as e:
                _train_state["error"] = f"Error: {str(e)[:120]}"
            finally:
                _train_state["running"] = False

        _threading.Thread(target=_run, daemon=True).start()
        return "⏳ Training started — click again in ~10 seconds to see result.", ""

    @app.callback(
        Output("ml-download","data"),
        Input("ml-export-btn","n_clicks"),
        prevent_initial_call=True,
    )
    def export(n):
        if not n: return None
        issues = get_issues_fn()
        path = ML.export_dataset_csv(issues)
        return dcc.send_file(path, filename="jira_ml_dataset.csv")
