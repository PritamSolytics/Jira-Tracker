"""
data_lab_page.py — Data Laboratory
Dataset inspection, EDA, preprocessing controls, feature engineering,
train/test split configuration, and dataset export.
Inspired by Nimbus UNO Data Management + EDA modules.
"""
from dash import html, dcc, Input, Output, State, dash_table
import plotly.graph_objects as go
import plotly.figure_factory as ff
import pandas as pd
import numpy as np
from collections import Counter
import components as C

L = dict(paper_bgcolor=C.SURFACE, plot_bgcolor=C.SURFACE,
         font=dict(color=C.TEXT, size=11, family="JetBrains Mono, monospace"),
         margin=dict(l=8,r=8,t=36,b=8))

def _t(text): return dict(text=text, font=dict(size=11, color=C.NAVY2, weight="bold"))


# ── Layout ─────────────────────────────────────────────────────────────────────
def layout(issues):
    import ml_engine as ML
    df = ML.get_dataset()

    if df is None:
        return html.Div([
            C.section("Data Laboratory", "No dataset found"),
            C.card(html.Div([
                html.Div("No dataset available.", style={"fontWeight":"700","color":C.AMBER,"fontSize":"0.82rem","marginBottom":"8px"}),
                html.Div("Navigate to the Predictive Analytics page and click Retrain to generate the dataset.", style={"color":C.MUTED,"fontSize":"0.75rem"}),
            ], style={"padding":"12px"})),
        ])

    numeric_cols = ["days_open","cycle_time","priority_score","type_risk","label_count",
                    "link_count","blocker_count","blocked_count","comment_count",
                    "degree_centrality","betweenness_centrality","assignee_load"]
    numeric_cols = [c for c in numeric_cols if c in df.columns]
    categorical_cols = ["status","priority","type","assignee"]
    target_col = "closed_on_time"

    train_df = df[df[target_col].notna()].copy()

    # ── Summary stats ──────────────────────────────────────────────────────────
    total   = len(df)
    labeled = int(train_df[target_col].notna().sum())
    slipped = int((train_df[target_col] == 0).sum())
    on_time = int((train_df[target_col] == 1).sum())
    missing = int(df.isnull().sum().sum())

    summary_strip = html.Div([
        C.kpi("Total Records",     total,   C.NAVY),
        C.kpi("Labeled (Training)",labeled, C.ACCENT),
        C.kpi("Slipped",           slipped, C.RED,    f"{round(slipped/max(1,labeled)*100,1)}%"),
        C.kpi("On Time",           on_time, C.GREEN,  f"{round(on_time/max(1,labeled)*100,1)}%"),
        C.kpi("Missing Values",    missing, C.AMBER),
        C.kpi("Features",          len(numeric_cols), C.PURPLE),
    ], style={"display":"flex","gap":"10px","flexWrap":"wrap","marginBottom":"16px"})

    # ── Dataset table (first 100 rows) ─────────────────────────────────────────
    preview_cols = ["key","status","assignee","priority","type","days_open",
                    "cycle_time","priority_score","blocker_count","closed_on_time"]
    preview_cols = [c for c in preview_cols if c in df.columns]

    dataset_table = dash_table.DataTable(
        id="dl-table",
        data=df[preview_cols].head(100).to_dict("records"),
        columns=[{"name":c,"id":c} for c in preview_cols],
        page_size=20, filter_action="native", sort_action="native",
        style_table={"overflowX":"auto","borderRadius":"8px","border":f"1px solid {C.BORDER}"},
        style_cell={"background":C.SURFACE,"color":C.TEXT,"border":f"1px solid {C.BORDER}",
                    "fontSize":"0.72rem","padding":"6px 10px","fontFamily":"JetBrains Mono,monospace",
                    "maxWidth":"180px","overflow":"hidden","textOverflow":"ellipsis"},
        style_header={"background":C.ACCENT2,"fontWeight":"800","color":C.NAVY,
                       "fontSize":"0.65rem","letterSpacing":"0.07em","textTransform":"uppercase"},
        style_data_conditional=[
            {"if":{"filter_query":"{closed_on_time} = 0"},"color":C.RED},
            {"if":{"filter_query":"{closed_on_time} = 1"},"color":C.GREEN},
            {"if":{"row_index":"odd"},"backgroundColor":C.BG},
        ],
        export_format="csv",
    )

    # ── Descriptive statistics ─────────────────────────────────────────────────
    desc = df[numeric_cols].describe().round(2)
    desc_rows = []
    for col in numeric_cols:
        row = desc[col] if col in desc.columns else {}
        desc_rows.append({
            "Feature":    col,
            "Count":      int(row.get("count",0)),
            "Mean":       round(row.get("mean",0),2),
            "Std":        round(row.get("std",0),2),
            "Min":        round(row.get("min",0),2),
            "25%":        round(row.get("25%",0),2),
            "Median":     round(row.get("50%",0),2),
            "75%":        round(row.get("75%",0),2),
            "Max":        round(row.get("max",0),2),
            "Missing":    int(df[col].isnull().sum()),
        })

    desc_table = dash_table.DataTable(
        data=desc_rows,
        columns=[{"name":c,"id":c} for c in ["Feature","Count","Mean","Std","Min","25%","Median","75%","Max","Missing"]],
        style_table={"overflowX":"auto","borderRadius":"8px","border":f"1px solid {C.BORDER}"},
        style_cell={"background":C.SURFACE,"color":C.TEXT,"border":f"1px solid {C.BORDER}",
                    "fontSize":"0.72rem","padding":"6px 10px","fontFamily":"JetBrains Mono,monospace","textAlign":"right"},
        style_header={"background":C.ACCENT2,"fontWeight":"800","color":C.NAVY,
                       "fontSize":"0.65rem","letterSpacing":"0.07em","textTransform":"uppercase","textAlign":"left"},
        style_data_conditional=[
            {"if":{"column_id":"Feature"},"textAlign":"left","fontWeight":"700"},
            {"if":{"filter_query":"{Missing} > 0","column_id":"Missing"},"color":C.AMBER,"fontWeight":"700"},
            {"if":{"row_index":"odd"},"backgroundColor":C.BG},
        ],
    )

    # ── Distribution chart (days_open) ─────────────────────────────────────────
    col_vals = df["days_open"].dropna().values
    dist_fig = go.Figure()
    dist_fig.add_trace(go.Histogram(x=col_vals, nbinsx=30, name="days_open",
        marker_color=C.ACCENT, opacity=0.78,
        hovertemplate="Range: %{x}<br>Count: %{y}<extra></extra>"))
    dist_fig.update_layout(**L, title=_t("Distribution: Days Open"),
        xaxis=dict(title="Days", gridcolor=C.BORDER),
        yaxis=dict(title="Count", gridcolor=C.BORDER))

    # ── Cycle time by type ─────────────────────────────────────────────────────
    cycle_fig = go.Figure()
    colors = [C.RED, C.ACCENT, C.PURPLE, C.AMBER, C.TEAL]
    for idx, itype in enumerate(["Bug","Task","Story","Sub-task"]):
        vals = df[(df["type"]==itype) & df["cycle_time"].notna()]["cycle_time"].values
        if len(vals) > 0:
            cycle_fig.add_trace(go.Box(y=vals, name=itype,
                marker_color=colors[idx % len(colors)], boxmean=True,
                hovertemplate=f"<b>{itype}</b><br>Cycle Time: %{{y}}d<extra></extra>"))
    cycle_fig.update_layout(**L, title=_t("Cycle Time Distribution by Issue Type"),
        yaxis=dict(title="Days", gridcolor=C.BORDER),
        xaxis=dict(gridcolor=C.BORDER))

    # ── Correlation heatmap ────────────────────────────────────────────────────
    corr_cols = [c for c in ["days_open","priority_score","type_risk","blocker_count",
                              "link_count","comment_count","assignee_load","closed_on_time"]
                 if c in df.columns]
    corr_df = df[corr_cols].dropna()
    if len(corr_df) > 5:
        corr_mat = corr_df.corr().round(2)
        z = corr_mat.values
        corr_fig = go.Figure(go.Heatmap(
            z=z, x=corr_mat.columns.tolist(), y=corr_mat.index.tolist(),
            text=[[f"{v:.2f}" for v in row] for row in z],
            texttemplate="%{text}",
            colorscale=[[0,"#DC2626"],[0.5,C.SURFACE],[1,"#2563EB"]],
            zmid=0, showscale=True,
            colorbar=dict(title="r", thickness=10),
            hovertemplate="Feature: %{y}<br>vs: %{x}<br>Correlation: %{z:.3f}<extra></extra>",
        ))
        corr_fig.update_layout(**L, title=_t("Pearson Correlation Matrix"),
            xaxis=dict(tickangle=-30), height=380)
    else:
        corr_fig = go.Figure()

    # ── Priority vs cycle time (bar) ───────────────────────────────────────────
    prio_cycle = []
    for p in ["Highest","High","Medium","Low","Lowest"]:
        vals = df[(df["priority"]==p) & df["cycle_time"].notna()]["cycle_time"].values
        if len(vals) > 0:
            prio_cycle.append({"priority":p, "median":round(float(np.median(vals)),1), "count":len(vals)})
    prio_fig = go.Figure()
    if prio_cycle:
        prio_fig.add_trace(go.Bar(
            x=[r["priority"] for r in prio_cycle],
            y=[r["median"] for r in prio_cycle],
            marker_color=[C.RED,C.ORANGE,C.AMBER,C.GREEN,C.TEAL][:len(prio_cycle)],
            text=[f"{r['median']}d (n={r['count']})" for r in prio_cycle],
            textposition="outside",
            textfont=dict(color=C.NAVY2, size=10, weight="bold"),
            hovertemplate="<b>%{x}</b><br>Median Cycle Time: %{y}d<extra></extra>",
        ))
    prio_fig.update_layout(**L, title=_t("Median Cycle Time by Priority"),
        xaxis=dict(gridcolor=C.BORDER), yaxis=dict(title="Days", gridcolor=C.BORDER))

    # ── Target class balance ───────────────────────────────────────────────────
    balance_fig = go.Figure(go.Pie(
        labels=["Slipped","On Time"],
        values=[slipped, on_time],
        marker_colors=[C.RED, C.GREEN],
        hole=0.55,
        textinfo="label+percent+value",
        textfont=dict(size=11),
    ))
    balance_fig.update_layout(**L, title=_t("Target Variable: Class Balance"))

    # ── Feature vs Target box plots ────────────────────────────────────────────
    feat_target_fig = go.Figure()
    feat_to_plot = "days_open"
    for label, val, color in [("Slipped",0,C.RED),("On Time",1,C.GREEN)]:
        vals = train_df[train_df[target_col]==val][feat_to_plot].dropna().values
        feat_target_fig.add_trace(go.Box(y=vals, name=label, marker_color=color, boxmean=True))
    feat_target_fig.update_layout(**L, title=_t("Days Open: Slipped vs On Time"),
        yaxis=dict(title="Days", gridcolor=C.BORDER))

    # ── Assignee volume ────────────────────────────────────────────────────────
    assignee_counts = df.groupby("assignee").size().sort_values(ascending=False).head(20)
    assignee_fig = go.Figure(go.Bar(
        x=assignee_counts.index.tolist(), y=assignee_counts.values.tolist(),
        marker_color=C.ACCENT, opacity=0.85,
        hovertemplate="<b>%{x}</b><br>Issues: %{y}<extra></extra>",
    ))
    assignee_fig.update_layout(**L, title=_t("Issue Count by Assignee (Top 20)"),
        xaxis=dict(tickangle=-35, gridcolor=C.BORDER),
        yaxis=dict(gridcolor=C.BORDER))

    # ── Train/Test split config panel ─────────────────────────────────────────
    split_panel = C.card(
        html.Div("TRAIN / TEST SPLIT CONFIGURATION",
                 style={"fontSize":"0.58rem","fontWeight":"800","letterSpacing":"0.16em","color":C.NAVY2,"marginBottom":"14px"}),
        html.Div([
            html.Div([
                html.Div([
                    html.Label("Test Size", style={"fontSize":"0.65rem","fontWeight":"700","color":C.MUTED,"textTransform":"uppercase","letterSpacing":"0.08em"}),
                    dcc.Slider(id="dl-test-size", min=0.1, max=0.4, step=0.05, value=0.2,
                               marks={0.1:"10%",0.2:"20%",0.3:"30%",0.4:"40%"},
                               tooltip={"placement":"bottom","always_visible":True}),
                ], style={"flex":"1","minWidth":"200px"}),
                html.Div([
                    html.Label("Stratification", style={"fontSize":"0.65rem","fontWeight":"700","color":C.MUTED,"textTransform":"uppercase","letterSpacing":"0.08em"}),
                    dcc.RadioItems(id="dl-stratify",
                        options=[{"label":"Stratified (recommended)","value":"yes"},{"label":"Random","value":"no"}],
                        value="yes",
                        labelStyle={"display":"block","fontSize":"0.73rem","marginTop":"6px"}),
                ], style={"flex":"1","minWidth":"160px"}),
                html.Div([
                    html.Label("Random Seed", style={"fontSize":"0.65rem","fontWeight":"700","color":C.MUTED,"textTransform":"uppercase","letterSpacing":"0.08em"}),
                    dcc.Input(id="dl-seed", type="number", value=42, min=0,
                              style={"width":"100%","padding":"6px","border":f"1px solid {C.BORDER}",
                                     "borderRadius":"6px","fontSize":"0.75rem","marginTop":"4px",
                                     "fontFamily":"JetBrains Mono,monospace"}),
                ], style={"flex":"1","minWidth":"120px"}),
            ], style={"display":"flex","gap":"20px","flexWrap":"wrap","alignItems":"flex-start"}),
            html.Div(id="dl-split-preview", style={"marginTop":"14px"}),
        ]),
        html.Div([
            html.Div(f"Training set: {labeled} records | Target: closed_on_time | Positive class: On-Time (1) | Negative: Slipped (0)",
                     style={"fontSize":"0.68rem","color":C.MUTED,"marginTop":"10px","fontFamily":"JetBrains Mono,monospace"}),
        ]),
    )

    # ── Preprocessing notes ────────────────────────────────────────────────────
    preprocess_card = C.card(
        html.Div("PREPROCESSING SUMMARY",
                 style={"fontSize":"0.58rem","fontWeight":"800","letterSpacing":"0.16em","color":C.NAVY2,"marginBottom":"12px"}),
        html.Div([
            C.stat_row("Missing value strategy", "Impute with 0 (structural missing = no value)"),
            C.stat_row("Scaling method",          "StandardScaler (zero mean, unit variance)"),
            C.stat_row("Target encoding",         "Binary: 1=On-Time, 0=Slipped"),
            C.stat_row("Categorical handling",    "Label not encoded; priority/type mapped to ordinal scores"),
            C.stat_row("Class imbalance",         f"Slipped={slipped} ({round(slipped/max(1,labeled)*100,1)}%) | Balanced via class_weight"),
            C.stat_row("Feature scope",           f"{len(numeric_cols)} numeric features used in model"),
            C.stat_row("Excluded columns",        "key, status, assignee, created, updated, due (non-numeric / leakage risk)"),
        ]),
    )

    # ── Download buttons ───────────────────────────────────────────────────────
    download_panel = html.Div([
        html.Button("Download Full Dataset (CSV)", id="dl-btn-full", n_clicks=0, style={
            "background":C.NAVY,"color":"#fff","border":"none","borderRadius":"6px",
            "padding":"9px 18px","cursor":"pointer","fontSize":"0.73rem","fontWeight":"700","marginRight":"10px"}),
        html.Button("Download Training Set (CSV)", id="dl-btn-train", n_clicks=0, style={
            "background":C.SURFACE,"color":C.NAVY,"border":f"2px solid {C.NAVY}","borderRadius":"6px",
            "padding":"9px 18px","cursor":"pointer","fontSize":"0.73rem","fontWeight":"700","marginRight":"10px"}),
        html.Button("Download Raw Issues (CSV)", id="dl-btn-raw", n_clicks=0, style={
            "background":C.SURFACE,"color":C.NAVY,"border":f"2px solid {C.BORDER}","borderRadius":"6px",
            "padding":"9px 18px","cursor":"pointer","fontSize":"0.73rem","fontWeight":"700"}),
        dcc.Download(id="dl-download-full"),
        dcc.Download(id="dl-download-train"),
        dcc.Download(id="dl-download-raw"),
    ], style={"marginBottom":"16px","display":"flex","flexWrap":"wrap","gap":"8px"})

    def _graph(fig, gid, h=280):
        return dcc.Graph(figure=fig, id=gid, style={"height":f"{h}px"}, config={"displayModeBar":False})

    return html.Div([
        C.section("Data Laboratory", "Dataset inspection · Descriptive statistics · Exploratory analysis · Export"),
        summary_strip,
        download_panel,

        # Row 1: class balance + feature target
        C.grid(
            C.card(_graph(balance_fig,   "dl-balance", 260)),
            C.card(_graph(feat_target_fig,"dl-feat-target", 260)),
            cols=2
        ),

        # Row 2: distribution + cycle time
        C.grid(
            C.card(_graph(dist_fig,   "dl-dist", 280)),
            C.card(_graph(cycle_fig,  "dl-cycle", 280)),
            cols=2
        ),

        # Row 3: correlation + priority
        C.grid(
            C.card(_graph(corr_fig,  "dl-corr", 380), cols=1),
            C.card(_graph(prio_fig,  "dl-prio", 380), cols=1),
            cols=2
        ),

        # Row 4: assignee
        C.card(_graph(assignee_fig, "dl-assignee", 300)),

        # Row 5: preprocessing + split config
        html.Div(style={"marginTop":"16px"}),
        C.grid(preprocess_card, split_panel, cols=2),

        # Row 6: descriptive stats table
        C.section("Descriptive Statistics", "Numeric features — all records"),
        C.card(desc_table, pad="14px"),

        # Row 7: dataset preview
        C.section("Dataset Preview", f"First 100 of {total} records — filterable and sortable"),
        C.card(dataset_table, pad="14px"),
    ])


def register_callbacks(app, get_issues_fn):
    from dash import Output, Input, State
    import ml_engine as ML

    @app.callback(
        Output("dl-split-preview","children"),
        Input("dl-test-size","value"),
        Input("dl-stratify","value"),
        Input("dl-seed","value"),
    )
    def update_split_preview(test_size, stratify, seed):
        df = ML.get_dataset()
        if df is None: return ""
        train_df = df[df["closed_on_time"].notna()]
        n = len(train_df)
        n_test  = int(n * (test_size or 0.2))
        n_train = n - n_test
        slipped = int((train_df["closed_on_time"]==0).sum())
        on_time = int((train_df["closed_on_time"]==1).sum())
        return html.Div([
            html.Span(f"Train: {n_train} records", style={"background":C.ACCENT2,"color":C.ACCENT,"borderRadius":"4px","padding":"3px 10px","fontSize":"0.72rem","fontWeight":"700","marginRight":"8px"}),
            html.Span(f"Test: {n_test} records",   style={"background":"#F0FDF4","color":C.GREEN,"borderRadius":"4px","padding":"3px 10px","fontSize":"0.72rem","fontWeight":"700","marginRight":"8px"}),
            html.Span(f"Slipped: {slipped} | On-Time: {on_time}",style={"color":C.MUTED,"fontSize":"0.68rem"}),
        ], style={"display":"flex","alignItems":"center","flexWrap":"wrap","gap":"6px"})

    @app.callback(Output("dl-download-full","data"), Input("dl-btn-full","n_clicks"), prevent_initial_call=True)
    def download_full(n):
        if not n: return None
        issues = get_issues_fn()
        path = ML.export_dataset_csv(issues)
        return dcc.send_file(path, filename="jira_full_dataset.csv")

    @app.callback(Output("dl-download-train","data"), Input("dl-btn-train","n_clicks"), prevent_initial_call=True)
    def download_train(n):
        if not n: return None
        import io
        df = ML.get_dataset()
        if df is None: return None
        train_df = df[df["closed_on_time"].notna()]
        return dcc.send_data_frame(train_df.to_csv, "jira_training_set.csv", index=False)

    @app.callback(Output("dl-download-raw","data"), Input("dl-btn-raw","n_clicks"), prevent_initial_call=True)
    def download_raw(n):
        if not n: return None
        issues = get_issues_fn()
        raw_df = pd.DataFrame([{
            "key": i.get("key",""), "summary": i.get("summary",""),
            "status": i.get("status",""), "assignee": i.get("assignee",""),
            "priority": i.get("priority",""), "type": i.get("type",""),
            "created": i.get("created",""), "updated": i.get("updated",""),
            "due": i.get("due",""), "labels": "|".join(i.get("labels",[])),
            "fix_version": i.get("fix_version",""),
        } for i in issues])
        return dcc.send_data_frame(raw_df.to_csv, "jira_raw_issues.csv", index=False)
