import plotly.graph_objects as go

from collections import Counter, defaultdict
from components import sc, tc, pc, STATUS_CLR, TYPE_CLR, PRIO_CLR

LAYOUT = dict(
    paper_bgcolor="#0f172a", plot_bgcolor="#0f172a",
    font=dict(color="#94a3b8", size=11, family="IBM Plex Mono, monospace"),
    margin=dict(l=8, r=8, t=32, b=8),
    legend=dict(bgcolor="#0f172a", bordercolor="#1e293b"),
)

def _fig(fig):
    fig.update_layout(**LAYOUT)
    return fig

def status_bar(issues):
    c = Counter(i["status"] for i in issues)
    statuses = sorted(c, key=lambda s: -c[s])
    fig = go.Figure(go.Bar(
        x=[c[s] for s in statuses], y=statuses, orientation="h",
        marker_color=[sc(s) for s in statuses],
        text=[c[s] for s in statuses], textposition="outside",
    ))
    fig.update_layout(**LAYOUT, title="Status Distribution", yaxis=dict(autorange="reversed"))
    return fig

def assignee_stacked(issues, labels):
    # Per assignee, per label stack
    a_l = defaultdict(Counter)
    for i in issues:
        for l in (i["labels"] or ["(No Label)"]):
            a_l[i["assignee"]][l] += 1
    assignees = sorted(a_l, key=lambda a: -sum(a_l[a].values()))[:20]
    all_labels = sorted(set(l for c in a_l.values() for l in c))
    colors = ["#3b82f6","#8b5cf6","#10b981","#f59e0b","#ef4444","#6366f1","#22c55e","#f97316","#ec4899","#14b8a6","#84cc16","#a855f7"]
    traces = [go.Bar(
        name=l, x=assignees, y=[a_l[a][l] for a in assignees],
        marker_color=colors[i % len(colors)],
    ) for i, l in enumerate(all_labels)]
    fig = go.Figure(traces)
    fig.update_layout(**LAYOUT, barmode="stack", title="Assignee Load by Label",
                      xaxis=dict(tickangle=-30))
    return fig

def bubble_chart(issues):
    from collections import defaultdict
    a = defaultdict(lambda: {"total":0,"stale":[],"overdue":0})
    for i in issues:
        if i["status"] == "Closed": continue
        a[i["assignee"]]["total"] += 1
        a[i["assignee"]]["stale"].append(i["days_stale"])
        if "Past Due" in i["due_flag"]: a[i["assignee"]]["overdue"] += 1
    names = list(a.keys())
    x = [a[n]["total"] for n in names]
    y = [round(sum(a[n]["stale"])/len(a[n]["stale"]),1) if a[n]["stale"] else 0 for n in names]
    sz = [max(10, a[n]["overdue"]*8+10) for n in names]
    fig = go.Figure(go.Scatter(
        x=x, y=y, mode="markers+text", text=names, textposition="top center",
        marker=dict(size=sz, color=y, colorscale="RdYlGn_r", showscale=True,
                    colorbar=dict(title="Avg Days Stale")),
        hovertemplate="<b>%{text}</b><br>Open: %{x}<br>Avg Stale: %{y}d<extra></extra>",
    ))
    fig.update_layout(**LAYOUT, title="Assignee: Open Issues vs Avg Days Stale (size = past due count)",
                      xaxis_title="Open Issues", yaxis_title="Avg Days Since Updated")
    return fig

def heatmap(issues):
    from components import STATUS_CLR
    assignees = sorted(set(i["assignee"] for i in issues if i["status"] != "Closed"))
    statuses  = list(STATUS_CLR.keys())
    grid = defaultdict(Counter)
    for i in issues:
        grid[i["assignee"]][i["status"]] += 1
    z = [[grid[a][s] for s in statuses] for a in assignees]
    fig = go.Figure(go.Heatmap(
        z=z, x=statuses, y=assignees,
        colorscale="Blues", showscale=True,
        hovertemplate="Assignee: %{y}<br>Status: %{x}<br>Count: %{z}<extra></extra>",
    ))
    fig.update_layout(**LAYOUT, title="Assignee × Status Heatmap",
                      xaxis=dict(tickangle=-30))
    return fig

def priority_donut(issues):
    c = Counter(i["priority"] for i in issues if i["status"] != "Closed")
    labels, values = zip(*c.items()) if c else ([],[])
    fig = go.Figure(go.Pie(
        labels=labels, values=values,
        marker_colors=[pc(l) for l in labels],
        hole=0.55, textinfo="label+percent",
    ))
    fig.update_layout(**LAYOUT, title="Priority Distribution (Open)")
    return fig

def type_donut(issues):
    c = Counter(i["type"] for i in issues)
    labels, values = zip(*c.items()) if c else ([],[])
    fig = go.Figure(go.Pie(
        labels=labels, values=values,
        marker_colors=[tc(l) for l in labels],
        hole=0.55, textinfo="label+percent",
    ))
    fig.update_layout(**LAYOUT, title="Issue Type Split")
    return fig

def age_histogram(issues):
    open_issues = [i for i in issues if i["status"] != "Closed"]
    from datetime import date
    today = date.today()
    ages = []
    for i in open_issues:
        try: ages.append((today - date.fromisoformat(i["created"])).days)
        except: pass
    fig = go.Figure(go.Histogram(x=ages, nbinsx=20, marker_color="#3b82f6"))
    fig.update_layout(**LAYOUT, title="Issue Age Distribution (days since created)",
                      xaxis_title="Days Open", yaxis_title="Count")
    return fig

def velocity_line(issues):
    from datetime import date, timedelta
    closed = [i for i in issues if i["status"] == "Closed" and i["updated"]]
    by_week = Counter()
    for i in closed:
        try:
            d = date.fromisoformat(i["updated"])
            week = d - timedelta(days=d.weekday())
            by_week[str(week)] += 1
        except: pass
    weeks = sorted(by_week)[-12:]
    fig = go.Figure(go.Scatter(
        x=weeks, y=[by_week[w] for w in weeks],
        mode="lines+markers+text",
        text=[by_week[w] for w in weeks], textposition="top center",
        line=dict(color="#22c55e", width=2),
        marker=dict(size=6, color="#22c55e"),
    ))
    fig.update_layout(**LAYOUT, title="Weekly Closed Issues (last 12 weeks)",
                      xaxis_title="Week", yaxis_title="Closed")
    return fig

def sankey(issues):
    labels_all, assignees_all, statuses_all = [], [], []
    lbl_set = sorted(set(i["label_display"] for i in issues))
    asgn_set = sorted(set(i["assignee"] for i in issues))
    stat_set = sorted(set(i["status"] for i in issues))
    nodes = lbl_set + asgn_set + stat_set
    node_idx = {n:i for i,n in enumerate(nodes)}
    colors = (["#3b82f6"]*len(lbl_set) + ["#8b5cf6"]*len(asgn_set) + ["#f59e0b"]*len(stat_set))

    source, target, value = [], [], []
    la = defaultdict(int)
    for i in issues:
        la[(i["label_display"], i["assignee"])] += 1
    for (l,a),v in la.items():
        source.append(node_idx[l]); target.append(node_idx[a]); value.append(v)

    ast = defaultdict(int)
    for i in issues:
        ast[(i["assignee"], i["status"])] += 1
    for (a,s),v in ast.items():
        source.append(node_idx[a]); target.append(node_idx[s]); value.append(v)

    fig = go.Figure(go.Sankey(
        node=dict(label=nodes, color=colors, pad=15, thickness=15),
        link=dict(source=source, target=target, value=value),
    ))
    fig.update_layout(**LAYOUT, title="Flow: Label → Assignee → Status")
    return fig
