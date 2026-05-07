"""
task_linkage_page.py — Task Linkage Analysis
Floating tasks (not linked to any Story) vs Story-linked tasks.
Visibility into orphaned work items that lack traceability.
"""
from dash import html, dcc, dash_table
import plotly.graph_objects as go
from collections import Counter, defaultdict
import components as C

L = dict(paper_bgcolor=C.SURFACE, plot_bgcolor=C.SURFACE,
         font=dict(color=C.TEXT, size=11, family="JetBrains Mono, monospace"),
         margin=dict(l=8,r=8,t=40,b=8))

def _t(text): return dict(text=text, font=dict(size=11, color=C.NAVY2, weight="bold"))
def _g(fig, gid, h=260): return dcc.Graph(figure=fig, id=gid, style={"height":f"{h}px"}, config={"displayModeBar":False})


def _classify_issues(issues):
    """Separate issues into story-linked vs floating."""
    # Build story keys
    story_keys = {i["key"] for i in issues if i.get("type") in ("Story","Epic")}

    # An issue is story-linked if:
    # 1. It is a sub-task with a parent that is a Story/Epic
    # 2. It has a link to a Story/Epic
    # 3. Its fix_version matches a story's fix_version (weaker signal)

    parent_map = {i["key"]: i.get("parent","") for i in issues}

    def is_linked(issue):
        # Direct parent is a story/epic
        parent = issue.get("parent","")
        if parent and parent in story_keys: return True
        # Issue itself is a story/epic
        if issue.get("type") in ("Story","Epic"): return True
        # Has a link pointing to a story/epic
        for lnk in issue.get("links",[]):
            if lnk.get("key","") in story_keys: return True
        return False

    linked   = [i for i in issues if is_linked(i)]
    floating  = [i for i in issues if not is_linked(i) and i.get("type") not in ("Story","Epic")]
    stories   = [i for i in issues if i.get("type") in ("Story","Epic")]
    return linked, floating, stories


def layout(issues):
    linked, floating, stories = _classify_issues(issues)
    total = len(issues)

    # ── Summary strip ──────────────────────────────────────────────────────────
    n_linked   = len(linked)
    n_floating = len(floating)
    n_stories  = len(stories)
    float_pct  = round(n_floating / max(1, total) * 100, 1)

    summary_strip = html.Div([
        C.kpi("Total Issues",          total,      C.NAVY),
        C.kpi("Stories / Epics",        n_stories,  C.PURPLE),
        C.kpi("Story-Linked",           n_linked,   C.GREEN,  f"{round(n_linked/max(1,total)*100,1)}%"),
        C.kpi("Floating (Unlinked)",    n_floating, C.RED,    f"{float_pct}%"),
        C.kpi("Float Open",             sum(1 for i in floating if i["status"]!="Closed"), C.ORANGE),
        C.kpi("Float Past Due",         sum(1 for i in floating if "Past Due" in i["due_flag"]), C.RED),
    ], style={"display":"flex","gap":"10px","flexWrap":"wrap","marginBottom":"16px"})

    # ── Donut: linked vs floating ──────────────────────────────────────────────
    link_donut = go.Figure(go.Pie(
        labels=["Story-Linked","Floating","Stories/Epics"],
        values=[n_linked, n_floating, n_stories],
        marker_colors=[C.GREEN, C.RED, C.PURPLE],
        hole=0.58, textinfo="label+percent",
        textfont=dict(size=10),
    ))
    link_donut.update_layout(**L, title=_t("Linkage Coverage"))

    # ── Floating by assignee ────────────────────────────────────────────────────
    float_by_assignee = Counter(i["assignee"] for i in floating)
    top_float = float_by_assignee.most_common(15)
    float_assignee_fig = go.Figure(go.Bar(
        x=[a for a,_ in top_float], y=[c for _,c in top_float],
        marker_color=C.RED, opacity=0.82,
        text=[str(c) for _,c in top_float], textposition="outside",
        hovertemplate="<b>%{x}</b><br>Floating Issues: %{y}<extra></extra>",
    ))
    float_assignee_fig.update_layout(**L, title=_t("Floating Issues by Assignee"),
        xaxis=dict(tickangle=-30, gridcolor=C.BORDER),
        yaxis=dict(gridcolor=C.BORDER))

    # ── Floating by status ─────────────────────────────────────────────────────
    float_status = Counter(i["status"] for i in floating)
    float_status_fig = go.Figure(go.Bar(
        x=list(float_status.keys()), y=list(float_status.values()),
        marker_color=[C.sc_bg(s) for s in float_status.keys()],
        marker_line_color=[C.sc(s) for s in float_status.keys()],
        marker_line_width=2,
        text=list(float_status.values()), textposition="outside",
    ))
    float_status_fig.update_layout(**L, title=_t("Floating Issues by Status"),
        xaxis=dict(tickangle=-20, gridcolor=C.BORDER),
        yaxis=dict(gridcolor=C.BORDER))

    # ── Floating by type ───────────────────────────────────────────────────────
    float_type = Counter(i["type"] for i in floating)
    float_type_fig = go.Figure(go.Pie(
        labels=list(float_type.keys()), values=list(float_type.values()),
        marker_colors=[C.tc(t) for t in float_type.keys()],
        hole=0.5, textinfo="label+value",
    ))
    float_type_fig.update_layout(**L, title=_t("Floating Issues by Type"))

    # ── Story coverage: issues per story ──────────────────────────────────────
    issues_per_story = defaultdict(list)
    for i in issues:
        parent = i.get("parent","")
        if parent:
            issues_per_story[parent].append(i)
    for i in issues:
        for lnk in i.get("links",[]):
            if lnk.get("key","") in {s["key"] for s in stories}:
                issues_per_story[lnk["key"]].append(i)

    story_sizes = sorted([len(v) for v in issues_per_story.values()], reverse=True)[:20]
    story_names = [f"Story {i+1}" for i in range(len(story_sizes))]
    story_fig = go.Figure(go.Bar(
        x=story_names, y=story_sizes,
        marker_color=C.PURPLE, opacity=0.85,
        text=story_sizes, textposition="outside",
        hovertemplate="<b>%{x}</b><br>Linked Issues: %{y}<extra></extra>",
    ))
    story_fig.update_layout(**L, title=_t("Issues Linked per Story (Top 20)"),
        xaxis=dict(tickangle=-30, gridcolor=C.BORDER),
        yaxis=dict(title="Linked Issues", gridcolor=C.BORDER))

    # ── Floating table ─────────────────────────────────────────────────────────
    float_open = [i for i in floating if i["status"] != "Closed"]
    float_rows = sorted(float_open, key=lambda x: x["days_stale"], reverse=True)[:50]
    float_table = dash_table.DataTable(
        id="tl-float-table",
        data=[{
            "Key":      i["key"],
            "Summary":  i["summary"][:60],
            "Type":     i["type"],
            "Status":   i["status"],
            "Assignee": i["assignee"],
            "Priority": i["priority"],
            "Stale (d)":i["days_stale"],
            "Due":      i["due"] or "—",
            "Due Flag": i["due_flag"],
        } for i in float_rows],
        columns=[{"name":c,"id":c} for c in
                 ["Key","Summary","Type","Status","Assignee","Priority","Stale (d)","Due","Due Flag"]],
        page_size=20, filter_action="native", sort_action="native",
        export_format="csv",
        style_table={"overflowX":"auto","borderRadius":"8px","border":f"1px solid {C.BORDER}"},
        style_cell={"background":C.SURFACE,"color":C.TEXT,"border":f"1px solid {C.BORDER}",
                    "fontSize":"0.72rem","padding":"6px 10px","maxWidth":"200px",
                    "overflow":"hidden","textOverflow":"ellipsis"},
        style_header={"background":C.ACCENT2,"fontWeight":"800","color":C.NAVY,
                       "fontSize":"0.65rem","letterSpacing":"0.07em","textTransform":"uppercase"},
        style_data_conditional=[
            {"if":{"filter_query":"{Due Flag} contains 'Past Due'"},"color":C.RED,"fontWeight":"700"},
            {"if":{"filter_query":"{Stale (d)} > 14"},"backgroundColor":"#FFF7ED"},
            {"if":{"row_index":"odd"},"backgroundColor":C.BG},
        ],
    )

    # ── Linked table ───────────────────────────────────────────────────────────
    linked_open = [i for i in linked if i["status"] not in ("Closed",) and i["type"] not in ("Story","Epic")]
    linked_rows = sorted(linked_open, key=lambda x: x["days_stale"], reverse=True)[:50]
    linked_table = dash_table.DataTable(
        id="tl-linked-table",
        data=[{
            "Key":      i["key"],
            "Summary":  i["summary"][:60],
            "Type":     i["type"],
            "Status":   i["status"],
            "Assignee": i["assignee"],
            "Priority": i["priority"],
            "Parent":   i.get("parent","—") or "—",
            "Stale (d)":i["days_stale"],
            "Due Flag": i["due_flag"],
        } for i in linked_rows],
        columns=[{"name":c,"id":c} for c in
                 ["Key","Summary","Type","Status","Assignee","Priority","Parent","Stale (d)","Due Flag"]],
        page_size=20, filter_action="native", sort_action="native",
        export_format="csv",
        style_table={"overflowX":"auto","borderRadius":"8px","border":f"1px solid {C.BORDER}"},
        style_cell={"background":C.SURFACE,"color":C.TEXT,"border":f"1px solid {C.BORDER}",
                    "fontSize":"0.72rem","padding":"6px 10px","maxWidth":"200px",
                    "overflow":"hidden","textOverflow":"ellipsis"},
        style_header={"background":"#F0FDF4","fontWeight":"800","color":C.GREEN,
                       "fontSize":"0.65rem","letterSpacing":"0.07em","textTransform":"uppercase"},
        style_data_conditional=[
            {"if":{"filter_query":"{Due Flag} contains 'Past Due'"},"color":C.RED,"fontWeight":"700"},
            {"if":{"row_index":"odd"},"backgroundColor":C.BG},
        ],
    )

    return html.Div([
        C.section("Task Linkage Analysis",
                  "Floating tasks (no Story/Epic link) vs properly linked work items"),
        summary_strip,

        # Charts row 1
        C.grid(
            C.card(_g(link_donut,          "tl-donut",    240)),
            C.card(_g(float_type_fig,      "tl-type",     240)),
            cols=2
        ),
        html.Div(style={"marginTop":"16px"}),

        C.grid(
            C.card(_g(float_assignee_fig,  "tl-assignee", 280)),
            C.card(_g(float_status_fig,    "tl-status",   280)),
            cols=2
        ),
        html.Div(style={"marginTop":"16px"}),

        C.card(_g(story_fig, "tl-story", 260)),
        html.Div(style={"marginTop":"16px"}),

        C.section("Floating Issues — Open",
                  f"{len(float_open)} unlinked open issues · sorted by staleness"),
        C.card(float_table, pad="12px"),
        html.Div(style={"marginTop":"16px"}),

        C.section("Story-Linked Issues — Open",
                  f"{len(linked_open)} properly linked open issues"),
        C.card(linked_table, pad="12px"),
    ])


def register_callbacks(app, get_issues_fn):
    pass
