import plotly.graph_objects as go
from collections import Counter, defaultdict
from components import sc, sc_bg, tc, pc, STATUS_CLR, NAVY, NAVY2, ACCENT, BORDER, MUTED, TEXT, BG, SURFACE

L = dict(paper_bgcolor=SURFACE, plot_bgcolor=SURFACE,
         font=dict(color=TEXT, size=11, family="JetBrains Mono, monospace"),
         margin=dict(l=8,r=8,t=36,b=8),
         legend=dict(bgcolor=SURFACE, bordercolor=BORDER, borderwidth=1, font=dict(size=10)))

def _t(text): return dict(text=text, font=dict(size=11, color=NAVY2, weight="bold"))

def status_bar(issues):
    c = Counter(i["status"] for i in issues)
    s = sorted(c, key=lambda x: -c[x])
    fig = go.Figure(go.Bar(x=[c[x] for x in s], y=s, orientation="h",
        marker_color=[sc_bg(x) for x in s], marker_line_color=[sc(x) for x in s], marker_line_width=2,
        text=[c[x] for x in s], textposition="outside", textfont=dict(color=NAVY2, size=10, weight="bold")))
    fig.update_layout(**L, title=_t("Status Distribution"), yaxis=dict(autorange="reversed", gridcolor=BORDER), xaxis=dict(gridcolor=BORDER))
    return fig

def assignee_stacked(issues, labels):
    a_l = defaultdict(Counter)
    for i in issues:
        for l in (i["labels"] or ["(No Label)"]): a_l[i["assignee"]][l] += 1
    assignees = sorted(a_l, key=lambda a: -sum(a_l[a].values()))[:20]
    all_labels = sorted(set(l for c in a_l.values() for l in c))
    colors = ["#2563EB","#DC2626","#16A34A","#D97706","#7C3AED","#0D9488","#EA580C","#0B1D3A","#5A6E99","#1A3560"]
    traces = [go.Bar(name=l, x=assignees, y=[a_l[a][l] for a in assignees], marker_color=colors[i%len(colors)], opacity=0.88)
              for i,l in enumerate(all_labels)]
    fig = go.Figure(traces)
    fig.update_layout(**L, barmode="stack", title=_t("Assignee Load by Label"), xaxis=dict(tickangle=-30, gridcolor=BORDER), yaxis=dict(gridcolor=BORDER))
    return fig

def bubble_chart(issues):
    a = defaultdict(lambda: {"total":0,"stale":[],"overdue":0})
    for i in issues:
        if i["status"]=="Closed": continue
        a[i["assignee"]]["total"] += 1
        a[i["assignee"]]["stale"].append(i["days_stale"])
        if "Past Due" in i["due_flag"]: a[i["assignee"]]["overdue"] += 1
    names = list(a.keys())
    x = [a[n]["total"] for n in names]
    y = [round(sum(a[n]["stale"])/len(a[n]["stale"]),1) if a[n]["stale"] else 0 for n in names]
    sz = [max(12, a[n]["overdue"]*10+12) for n in names]
    fig = go.Figure(go.Scatter(x=x, y=y, mode="markers+text", text=names, textposition="top center",
        textfont=dict(size=9, color=NAVY2),
        marker=dict(size=sz, color=y, colorscale=[[0,"#16A34A"],[0.5,"#D97706"],[1,"#DC2626"]],
                    showscale=True, colorbar=dict(title="Avg Stale d", thickness=10),
                    line=dict(color=BORDER, width=1)),
        hovertemplate="<b>%{text}</b><br>Open: %{x}<br>Avg Stale: %{y}d<extra></extra>"))
    fig.update_layout(**L, title=_t("Load vs Staleness (size = overdue)"),
                      xaxis=dict(title="Open Issues", gridcolor=BORDER), yaxis=dict(title="Avg Days Stale", gridcolor=BORDER))
    return fig

def heatmap(issues):
    assignees = sorted(set(i["assignee"] for i in issues if i["status"]!="Closed"))
    statuses = list(STATUS_CLR.keys())
    grid = defaultdict(Counter)
    for i in issues: grid[i["assignee"]][i["status"]] += 1
    z = [[grid[a][s] for s in statuses] for a in assignees]
    fig = go.Figure(go.Heatmap(z=z, x=statuses, y=assignees,
        colorscale=[[0,SURFACE],[0.5,ACCENT+"66"],[1,ACCENT]], showscale=True,
        hovertemplate="Assignee: %{y}<br>Status: %{x}<br>Count: %{z}<extra></extra>"))
    fig.update_layout(**L, title=_t("Assignee × Status Heatmap"), xaxis=dict(tickangle=-30))
    return fig

def priority_donut(issues):
    c = Counter(i["priority"] for i in issues if i["status"]!="Closed" and i["priority"])
    if not c: return go.Figure()
    labels, values = zip(*c.items())
    fig = go.Figure(go.Pie(labels=labels, values=values, marker_colors=[pc(l) for l in labels],
                           hole=0.6, textinfo="label+percent", textfont=dict(size=10)))
    fig.update_layout(**L, title=_t("Priority (Open)"))
    return fig

def type_donut(issues):
    c = Counter(i["type"] for i in issues)
    if not c: return go.Figure()
    labels, values = zip(*c.items())
    fig = go.Figure(go.Pie(labels=labels, values=values, marker_colors=[tc(l) for l in labels],
                           hole=0.6, textinfo="label+percent", textfont=dict(size=10)))
    fig.update_layout(**L, title=_t("Issue Type Split"))
    return fig

def velocity_line(issues):
    from datetime import date, timedelta
    closed = [i for i in issues if i["status"]=="Closed" and i["updated"]]
    by_week = Counter()
    for i in closed:
        try:
            d = date.fromisoformat(i["updated"]); week = d - timedelta(days=d.weekday()); by_week[str(week)] += 1
        except: pass
    weeks = sorted(by_week)[-12:]
    if not weeks: return go.Figure()
    fig = go.Figure(go.Scatter(x=weeks, y=[by_week[w] for w in weeks],
        mode="lines+markers+text", text=[by_week[w] for w in weeks], textposition="top center",
        textfont=dict(size=9, color=NAVY2, weight="bold"),
        line=dict(color=ACCENT, width=2.5), marker=dict(size=7, color=ACCENT, line=dict(color=SURFACE, width=2)),
        fill="tozeroy", fillcolor="rgba(37,99,235,0.07)"))
    fig.update_layout(**L, title=_t("Weekly Closed Issues"), xaxis=dict(gridcolor=BORDER), yaxis=dict(gridcolor=BORDER))
    return fig

def workflow_funnel(issues):
    ORDER = ["Groomed","To Do","Development In Progress","Code Review","Integration Testing","Fixing in Progress","Ready For QA Testing","QA Testing","Closed"]
    c = Counter(i["status"] for i in issues)
    vals = [c.get(s,0) for s in ORDER]
    colors = [sc_bg(s) for s in ORDER]
    borders = [sc(s) for s in ORDER]
    fig = go.Figure(go.Bar(x=ORDER, y=vals, marker_color=colors, marker_line_color=borders, marker_line_width=2,
        text=vals, textposition="outside", textfont=dict(color=NAVY2, size=11, weight="bold")))
    fig.update_layout(**L, title=_t("Workflow Gate — Issue Volume by Stage"),
                      xaxis=dict(tickangle=-20, gridcolor=BORDER), yaxis=dict(gridcolor=BORDER))
    return fig

def relationship_matrix(issues):
    # Assignee × Label matrix
    a_l = defaultdict(Counter)
    for i in issues:
        for l in (i["labels"] or ["(No Label)"]): a_l[i["assignee"]][l] += 1
    assignees = sorted(a_l, key=lambda a: -sum(a_l[a].values()))[:15]
    all_labels = sorted(set(l for c in a_l.values() for l in c), key=lambda l: -sum(a_l[a][l] for a in assignees))[:15]
    z = [[a_l[a][l] for l in all_labels] for a in assignees]
    text = [[str(a_l[a][l]) if a_l[a][l] else "" for l in all_labels] for a in assignees]
    fig = go.Figure(go.Heatmap(z=z, x=all_labels, y=assignees, text=text, texttemplate="%{text}",
        colorscale=[[0,SURFACE],[0.3,ACCENT+"33"],[0.7,ACCENT+"88"],[1,ACCENT]],
        showscale=True, colorbar=dict(title="Issues", thickness=10),
        hovertemplate="Assignee: %{y}<br>Label: %{x}<br>Issues: %{z}<extra></extra>"))
    fig.update_layout(**L, title=_t("Relationship Matrix: Assignee × Label"),
                      xaxis=dict(tickangle=-30), height=400)
    return fig
