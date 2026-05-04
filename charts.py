import plotly.graph_objects as go
from collections import Counter, defaultdict
from components import sc, sc_bg, tc, pc, STATUS_CLR, NAVY, NAVY2, ACCENT, BORDER, MUTED, TEXT, BG

LAYOUT = dict(
    paper_bgcolor=BG, plot_bgcolor=BG,
    font=dict(color=TEXT, size=11, family="DM Mono, monospace"),
    margin=dict(l=8, r=8, t=36, b=8),
    legend=dict(bgcolor=BG, bordercolor=BORDER, borderwidth=1, font=dict(size=10)),
)

def _fig(fig, title="", h=None):
    fig.update_layout(**LAYOUT, title=dict(text=title, font=dict(size=12, color=NAVY2, weight=700)))
    if h: fig.update_layout(height=h)
    return fig

def status_bar(issues):
    c = Counter(i["status"] for i in issues)
    statuses = sorted(c, key=lambda s: -c[s])
    fig = go.Figure(go.Bar(
        x=[c[s] for s in statuses], y=statuses, orientation="h",
        marker_color=[sc_bg(s) for s in statuses],
        marker_line_color=[sc(s) for s in statuses], marker_line_width=2,
        text=[c[s] for s in statuses], textposition="outside",
        textfont=dict(color=NAVY2, size=11, weight=700),
    ))
    fig.update_layout(**LAYOUT, title=dict(text="Status Distribution", font=dict(size=12,color=NAVY2,weight=700)),
                      yaxis=dict(autorange="reversed", gridcolor=BORDER),
                      xaxis=dict(gridcolor=BORDER))
    return fig

def assignee_stacked(issues, labels):
    a_l = defaultdict(Counter)
    for i in issues:
        for l in (i["labels"] or ["(No Label)"]): a_l[i["assignee"]][l] += 1
    assignees = sorted(a_l, key=lambda a: -sum(a_l[a].values()))[:20]
    all_labels = sorted(set(l for c in a_l.values() for l in c))
    colors = ["#1E6FDB","#D93025","#1E8A44","#B45309","#7C3AED","#0F766E","#E8710A",
              "#0F2344","#6B7A99","#1A3A6E","#C2185B","#00796B"]
    traces = [go.Bar(
        name=l, x=assignees, y=[a_l[a][l] for a in assignees],
        marker_color=colors[i % len(colors)], opacity=0.9,
    ) for i, l in enumerate(all_labels)]
    fig = go.Figure(traces)
    fig.update_layout(**LAYOUT, barmode="stack",
                      title=dict(text="Assignee Load by Label", font=dict(size=12,color=NAVY2,weight=700)),
                      xaxis=dict(tickangle=-30, gridcolor=BORDER),
                      yaxis=dict(gridcolor=BORDER))
    return fig

def bubble_chart(issues):
    a = defaultdict(lambda: {"total":0,"stale":[],"overdue":0})
    for i in issues:
        if i["status"] == "Closed": continue
        a[i["assignee"]]["total"] += 1
        a[i["assignee"]]["stale"].append(i["days_stale"])
        if "Past Due" in i["due_flag"]: a[i["assignee"]]["overdue"] += 1
    names = list(a.keys())
    x = [a[n]["total"] for n in names]
    y = [round(sum(a[n]["stale"])/len(a[n]["stale"]),1) if a[n]["stale"] else 0 for n in names]
    sz = [max(12, a[n]["overdue"]*10+12) for n in names]
    fig = go.Figure(go.Scatter(
        x=x, y=y, mode="markers+text", text=names, textposition="top center",
        textfont=dict(size=9, color=NAVY2),
        marker=dict(size=sz, color=y, colorscale=[[0,"#1E8A44"],[0.5,"#B45309"],[1,"#D93025"]],
                    showscale=True, colorbar=dict(title="Avg Days Stale", thickness=12),
                    line=dict(color=BORDER, width=1)),
        hovertemplate="<b>%{text}</b><br>Open: %{x}<br>Avg Stale: %{y}d<extra></extra>",
    ))
    fig.update_layout(**LAYOUT,
                      title=dict(text="Load vs Staleness (bubble = overdue count)", font=dict(size=12,color=NAVY2,weight=700)),
                      xaxis=dict(title="Open Issues", gridcolor=BORDER),
                      yaxis=dict(title="Avg Days Since Updated", gridcolor=BORDER))
    return fig

def heatmap(issues):
    assignees = sorted(set(i["assignee"] for i in issues if i["status"] != "Closed"))
    statuses  = [s for s in STATUS_CLR.keys()]
    grid = defaultdict(Counter)
    for i in issues: grid[i["assignee"]][i["status"]] += 1
    z = [[grid[a][s] for s in statuses] for a in assignees]
    fig = go.Figure(go.Heatmap(
        z=z, x=statuses, y=assignees,
        colorscale=[[0,BG],[0.5,ACCENT+"55"],[1,ACCENT]],
        showscale=True,
        hovertemplate="Assignee: %{y}<br>Status: %{x}<br>Count: %{z}<extra></extra>",
    ))
    fig.update_layout(**LAYOUT,
                      title=dict(text="Assignee × Status Heatmap", font=dict(size=12,color=NAVY2,weight=700)),
                      xaxis=dict(tickangle=-30))
    return fig

def priority_donut(issues):
    c = Counter(i["priority"] for i in issues if i["status"] != "Closed" and i["priority"])
    if not c: return go.Figure()
    labels, values = zip(*c.items())
    fig = go.Figure(go.Pie(
        labels=labels, values=values,
        marker_colors=[pc(l) for l in labels],
        hole=0.6, textinfo="label+percent",
        textfont=dict(size=10, color=TEXT),
    ))
    fig.update_layout(**LAYOUT, title=dict(text="Priority (Open)", font=dict(size=12,color=NAVY2,weight=700)))
    return fig

def type_donut(issues):
    c = Counter(i["type"] for i in issues)
    if not c: return go.Figure()
    labels, values = zip(*c.items())
    fig = go.Figure(go.Pie(
        labels=labels, values=values,
        marker_colors=[tc(l) for l in labels],
        hole=0.6, textinfo="label+percent",
        textfont=dict(size=10, color=TEXT),
    ))
    fig.update_layout(**LAYOUT, title=dict(text="Issue Type Split", font=dict(size=12,color=NAVY2,weight=700)))
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
    if not weeks: return go.Figure()
    fig = go.Figure(go.Scatter(
        x=weeks, y=[by_week[w] for w in weeks],
        mode="lines+markers+text",
        text=[by_week[w] for w in weeks], textposition="top center",
        textfont=dict(size=10, color=NAVY2, weight=700),
        line=dict(color=ACCENT, width=2.5),
        marker=dict(size=7, color=ACCENT, line=dict(color=BG, width=2)),
        fill="tozeroy", fillcolor=ACCENT+"15",
    ))
    fig.update_layout(**LAYOUT,
                      title=dict(text="Weekly Closed Issues", font=dict(size=12,color=NAVY2,weight=700)),
                      xaxis=dict(gridcolor=BORDER), yaxis=dict(gridcolor=BORDER))
    return fig

def age_histogram(issues):
    from datetime import date
    today = date.today()
    ages = []
    for i in [i for i in issues if i["status"] != "Closed"]:
        try: ages.append((today - date.fromisoformat(i["created"])).days)
        except: pass
    if not ages: return go.Figure()
    fig = go.Figure(go.Histogram(
        x=ages, nbinsx=20,
        marker_color=ACCENT, marker_line_color=BG, marker_line_width=1, opacity=0.85,
    ))
    fig.update_layout(**LAYOUT,
                      title=dict(text="Issue Age (days open)", font=dict(size=12,color=NAVY2,weight=700)),
                      xaxis=dict(title="Days Open", gridcolor=BORDER),
                      yaxis=dict(title="Count", gridcolor=BORDER))
    return fig
