from dash import html, dcc, Input, Output, State
import plotly.graph_objects as go
import numpy as np
from collections import defaultdict, Counter
from datetime import date, timedelta
import components as C
import data as D

L = dict(paper_bgcolor=C.SURFACE, plot_bgcolor=C.SURFACE,
         font=dict(color=C.TEXT, size=11, family="JetBrains Mono, monospace"),
         margin=dict(l=8,r=8,t=40,b=8))
def _t(t): return dict(text=t, font=dict(size=11, color=C.NAVY2, weight="bold"))
def _g(f,i,h=260): return dcc.Graph(figure=f,id=i,style={"height":f"{h}px"},config={"displayModeBar":False})

LABEL = {"fontSize":"0.63rem","fontWeight":"700","color":C.MUTED,
         "textTransform":"uppercase","letterSpacing":"0.08em","marginBottom":"4px","display":"block"}
INP = {"width":"100%","padding":"8px 10px","border":f"1px solid {C.BORDER}",
       "borderRadius":"6px","fontSize":"0.74rem","fontFamily":"DM Sans,sans-serif","boxSizing":"border-box"}
BTN = {"background":C.NAVY,"color":"#fff","border":"none","borderRadius":"6px",
       "padding":"10px 22px","cursor":"pointer","fontSize":"0.74rem","fontWeight":"800","marginRight":"10px"}
BTN2 = {**BTN,"background":C.SURFACE,"color":C.NAVY,"border":f"2px solid {C.BORDER}"}

TOOLTIP = {"fontSize":"0.62rem","color":C.MUTED,"fontStyle":"italic","marginTop":"3px","lineHeight":"1.5"}


def _cycle_stats(issues):
    by_type = defaultdict(list)
    for i in issues:
        if i["status"]=="Closed" and i.get("created") and i.get("updated"):
            try:
                ct=(date.fromisoformat(i["updated"])-date.fromisoformat(i["created"])).days
                if 0<ct<=180: by_type[i["type"]].append(ct)
            except: pass
    return {t:{"median":int(np.median(v)),"p75":int(np.percentile(v,75)),
               "std":round(float(np.std(v)),1),"n":len(v)}
            for t,v in by_type.items() if v}


def _assignee_stats(issues):
    stats=defaultdict(lambda:{"open":0,"closed":0,"avg_ct":None,"cts":[]})
    for i in issues:
        a=i["assignee"]
        if i["status"]!="Closed": stats[a]["open"]+=1
        else:
            stats[a]["closed"]+=1
            if i.get("created") and i.get("updated"):
                try:
                    ct=(date.fromisoformat(i["updated"])-date.fromisoformat(i["created"])).days
                    if 0<ct<=180: stats[a]["cts"].append(ct)
                except: pass
    for a,s in stats.items():
        if s["cts"]: s["avg_ct"]=round(float(np.mean(s["cts"])),1)
    return stats


def layout(issues):
    ct    = _cycle_stats(issues)
    a_stats = _assignee_stats(issues)
    labels  = [{"label":l,"value":l} for l in D.get_labels(issues)]
    assignees=[{"label":a,"value":a} for a in D.get_assignees(issues) if a!="Unassigned"]

    ct_rows=[html.Tr([
        html.Td(t,style={"fontWeight":"700","fontSize":"0.72rem"}),
        html.Td(f"{s['median']}d",style={"fontFamily":"JetBrains Mono,monospace","color":C.ACCENT,"fontWeight":"700","fontSize":"0.72rem"}),
        html.Td(f"{s['p75']}d",style={"fontFamily":"JetBrains Mono,monospace","color":C.AMBER,"fontSize":"0.72rem"}),
        html.Td(f"±{s['std']}d",style={"fontFamily":"JetBrains Mono,monospace","color":C.MUTED,"fontSize":"0.72rem"}),
        html.Td(str(s["n"]),style={"color":C.MUTED,"fontSize":"0.72rem"}),
    ],style={"background":C.BG if i%2 else C.SURFACE})
    for i,(t,s) in enumerate((t,ct[t]) for t in ["Story","Task","Bug","Sub-task","Epic"] if t in ct)]

    ref_panel=C.card(
        html.Div("HISTORICAL DELIVERY BENCHMARKS",style={"fontSize":"0.55rem","fontWeight":"800","letterSpacing":"0.18em","color":C.NAVY2,"marginBottom":"6px"}),
        html.Div("Derived from all closed issues. Used as defaults in the simulation engine.",style=TOOLTIP),
        html.Table([
            html.Thead(html.Tr([html.Th(h) for h in ["Type","Median","P75","Std Dev","Sample"]],style={"background":C.ACCENT2})),
            html.Tbody(ct_rows),
        ],style={"width":"100%","borderCollapse":"collapse","fontSize":"0.75rem","marginTop":"10px"}),
    )

    planner_panel=C.card(
        html.Div("SPRINT STRUCTURE PLANNER",style={"fontSize":"0.55rem","fontWeight":"800","letterSpacing":"0.18em","color":C.NAVY2,"marginBottom":"6px"}),
        html.Div("Describe a feature or delivery goal. The system generates a recommended issue hierarchy with effort estimates, capacity recommendations, and probabilistic completion assessment.",style=TOOLTIP),
        html.Div(style={"height":"12px"}),

        html.Label("Delivery Goal / Feature Description",style=LABEL),
        dcc.Textarea(id="sp-goal",placeholder="e.g. Implement dataset versioning with rollback capability and UI integration in the Grid module...",
                     style={**INP,"minHeight":"72px","resize":"vertical","marginBottom":"12px"}),

        html.Div([
            html.Div([
                html.Label("Target Release Label",style=LABEL),
                dcc.Dropdown(id="sp-label",options=labels,placeholder="Select...",clearable=True,style={"fontSize":"0.74rem"}),
            ],style={"flex":"1"}),
            html.Div([
                html.Label("Deadline",style=LABEL),
                dcc.Input(id="sp-deadline",type="date",style={**INP}),
            ],style={"flex":"1"}),
            html.Div([
                html.Label("Team Size",style=LABEL),
                dcc.Input(id="sp-team-size",type="number",value=5,min=1,max=20,style={**INP}),
                html.Div("Number of engineers available",style=TOOLTIP),
            ],style={"flex":"1"}),
        ],style={"display":"flex","gap":"14px","marginBottom":"16px","flexWrap":"wrap"}),

        html.Div("SIMULATION PARAMETERS",style={"fontSize":"0.55rem","fontWeight":"800","letterSpacing":"0.18em","color":C.MUTED,"marginBottom":"8px","marginTop":"4px"}),
        html.Div([
            html.Div([
                html.Label("Simulations",style=LABEL),
                dcc.Slider(id="sp-sims",min=100,max=2000,step=100,value=500,
                           marks={100:"100",500:"500",1000:"1k",2000:"2k"},
                           tooltip={"placement":"bottom","always_visible":True}),
                html.Div("More simulations = higher confidence in probability estimate",style=TOOLTIP),
            ],style={"flex":"2"}),
            html.Div([
                html.Label("Cycle Time Uncertainty (σ multiplier)",style=LABEL),
                dcc.Slider(id="sp-sigma",min=0.2,max=1.5,step=0.1,value=0.5,
                           marks={0.2:"Low",0.5:"Default",1.0:"High",1.5:"Very High"},
                           tooltip={"placement":"bottom","always_visible":True}),
                html.Div("Controls variability in sampled cycle times per simulation run",style=TOOLTIP),
            ],style={"flex":"2"}),
            html.Div([
                html.Label("Bug Buffer Rate",style=LABEL),
                dcc.Slider(id="sp-bug-rate",min=0.0,max=0.5,step=0.05,value=0.2,
                           marks={0:"0%",0.2:"20%",0.5:"50%"},
                           tooltip={"placement":"bottom","always_visible":True}),
                html.Div("Expected proportion of additional bug items per planned task",style=TOOLTIP),
            ],style={"flex":"2"}),
        ],style={"display":"flex","gap":"20px","flexWrap":"wrap","marginBottom":"16px"}),

        html.Div([
            html.Button("Generate Plan",id="sp-generate-btn",n_clicks=0,style=BTN),
            html.Button("Create Tickets in Jira",id="sp-create-btn",n_clicks=0,style=BTN2),
            dcc.Download(id="sp-export"),
        ]),
        dcc.Loading(html.Div(id="sp-output"),type="circle",color=C.ACCENT),
        html.Div(id="sp-create-status",style={"fontSize":"0.74rem","color":C.GREEN,"fontWeight":"700","marginTop":"8px"}),
        dcc.Store(id="sp-plan-store"),
    )

    analyzer_panel=C.card(
        html.Div("DELIVERY CONFIDENCE ANALYZER",style={"fontSize":"0.55rem","fontWeight":"800","letterSpacing":"0.18em","color":C.NAVY2,"marginBottom":"6px"}),
        html.Div("Monte Carlo simulation of current open issues. Samples historical cycle time distributions to estimate the probability of completing all in-scope items before their due dates.",style=TOOLTIP),
        html.Div(style={"height":"12px"}),

        html.Div([
            html.Div([
                html.Label("Scope Filter (Label)",style=LABEL),
                dcc.Dropdown(id="sca-label",options=labels,multi=True,placeholder="All labels...",style={"fontSize":"0.74rem"}),
            ],style={"flex":"2"}),
            html.Div([
                html.Label("Simulations",style=LABEL),
                dcc.Slider(id="sca-sims",min=100,max=2000,step=100,value=500,
                           marks={100:"100",500:"500",1000:"1k",2000:"2k"},
                           tooltip={"placement":"bottom","always_visible":True}),
            ],style={"flex":"2"}),
            html.Div([
                html.Label("Velocity Adjustment",style=LABEL),
                dcc.Slider(id="sca-velocity",min=0.5,max=1.5,step=0.1,value=1.0,
                           marks={0.5:"−50%",1.0:"Default",1.5:"+50%"},
                           tooltip={"placement":"bottom","always_visible":True}),
                html.Div("Scale historical throughput up/down to model capacity changes",style=TOOLTIP),
            ],style={"flex":"2"}),
            html.Div([
                html.Button("Run Simulation",id="sca-run-btn",n_clicks=0,style=BTN),
            ],style={"flex":"1","display":"flex","alignItems":"flex-end"}),
        ],style={"display":"flex","gap":"14px","flexWrap":"wrap","marginBottom":"12px"}),

        dcc.Loading(html.Div(id="sca-output"),type="circle",color=C.ACCENT),
    )

    return html.Div([
        C.section("Sprint Intelligence","Structured delivery planning  |  Probabilistic completion assessment  |  Capacity analysis"),
        C.grid(planner_panel,ref_panel,cols=2),
        html.Div(style={"marginTop":"16px"}),
        analyzer_panel,
    ])


def register_callbacks(app,get_issues_fn):
    from dash import Output,Input,State
    import json,requests as req,base64

    @app.callback(
        Output("sp-output","children"),
        Output("sp-plan-store","data"),
        Input("sp-generate-btn","n_clicks"),
        State("sp-goal","value"),
        State("sp-label","value"),
        State("sp-deadline","value"),
        State("sp-team-size","value"),
        State("sp-sims","value"),
        State("sp-sigma","value"),
        State("sp-bug-rate","value"),
        prevent_initial_call=True,
    )
    def generate(n,goal,label,deadline,team_size,n_sims,sigma,bug_rate):
        if not n or not goal:
            return html.Div("Enter a delivery goal and click Generate Plan.",style={"color":C.MUTED,"fontSize":"0.75rem"}),None
        issues=get_issues_fn()
        ct=_cycle_stats(issues)
        a_stats=_assignee_stats(issues)
        ct_str=" | ".join(f"{t}: median {s['median']}d ±{s['std']}d" for t,s in ct.items())
        top_a=sorted([(a,s) for a,s in a_stats.items() if a not in ("Unassigned","Former user")],key=lambda x:x[1]["open"])[:8]
        a_str=" | ".join(f"{a}: {s['open']} active" for a,s in top_a)
        prompt=f"""You are a delivery planning expert generating a Jira sprint structure.

Goal: {goal}
Label: {label or 'General'}
Deadline: {deadline or 'Not specified'}
Team size: {team_size or 5}
Historical cycle times: {ct_str}
Team workload: {a_str}

Return ONLY valid JSON, no markdown:
{{"epic":{{"summary":"string","description":"string"}},"stories":[{{"summary":"string","description":"string","estimate_days":5,"assignee":"string","tasks":[{{"type":"Task","summary":"string","estimate_days":2}},{{"type":"Bug","summary":"string","estimate_days":1}}]}}],"total_days":14,"risk_notes":"string"}}"""
        try:
            r=req.post("https://api.anthropic.com/v1/messages",
                       headers={"Content-Type":"application/json"},
                       json={"model":"claude-sonnet-4-20250514","max_tokens":1500,
                             "messages":[{"role":"user","content":prompt}]},timeout=60)
            text=r.json()["content"][0]["text"].strip()
            if "```" in text: text=text.split("```")[1]; text=text[4:] if text.startswith("json") else text
            plan=json.loads(text.strip())
            rendered=_render_plan(plan,ct,a_stats,deadline,int(n_sims or 500),float(sigma or 0.5),float(bug_rate or 0.2))
            return rendered,plan
        except Exception as e:
            return html.Div(f"Generation error: {str(e)[:200]}",style={"color":C.RED,"fontSize":"0.74rem"}),None

    @app.callback(
        Output("sp-create-status","children"),
        Input("sp-create-btn","n_clicks"),
        State("sp-plan-store","data"),
        prevent_initial_call=True,
    )
    def create_tickets(n,plan):
        if not n or not plan: return "Generate a plan first."
        created,errors=[],[]
        def _post(itype,summary,desc,parent=None):
            body={"fields":{"project":{"key":D.PROJECTS[0]},"issuetype":{"name":itype},"summary":summary,
                  "description":{"type":"doc","version":1,"content":[{"type":"paragraph","content":[{"type":"text","text":desc}]}]}}}
            if parent and itype in ("Story","Task","Sub-task"): body["fields"]["parent"]={"key":parent}
            basic=base64.b64encode(f"{D.EMAIL}:{D.TOKEN}".encode()).decode()
            r=req.post(f"https://api.atlassian.com/ex/jira/{D.CLOUD_ID}/rest/api/3/issue",
                       headers={"Authorization":f"Basic {basic}","Content-Type":"application/json","Accept":"application/json"},
                       json=body,timeout=15)
            if r.status_code==201: return r.json().get("key","?")
            raise Exception(f"{r.status_code}: {r.text[:80]}")
        try:
            ek=_post("Epic",plan["epic"]["summary"],plan["epic"].get("description",""))
            created.append(ek)
            for s in plan.get("stories",[]):
                sk=_post("Story",s["summary"],s.get("description",""),ek)
                created.append(sk)
                for t in s.get("tasks",[]):
                    tk=_post(t.get("type","Task"),t["summary"],f"Estimate: {t.get('estimate_days','')}d",sk)
                    created.append(tk)
            return f"Created {len(created)} items: {', '.join(created[:6])}{'…' if len(created)>6 else ''}"
        except Exception as e:
            return f"Error: {str(e)[:150]}"

    @app.callback(
        Output("sca-output","children"),
        Input("sca-run-btn","n_clicks"),
        State("sca-label","value"),
        State("sca-sims","value"),
        State("sca-velocity","value"),
        prevent_initial_call=True,
    )
    def run_analyzer(n,labels,n_sims,velocity):
        if not n: return ""
        issues=get_issues_fn()
        scoped=[i for i in issues if not labels or any(l in i.get("labels",[]) for l in labels)]
        open_i=[i for i in scoped if i["status"]!="Closed"]
        if not open_i: return html.Div("No open issues in scope.",style={"color":C.MUTED})
        ct=_cycle_stats(issues)
        a_stats=_assignee_stats(issues)
        nsims=int(n_sims or 500)
        vel=float(velocity or 1.0)
        results=[]
        for _ in range(nsims):
            done=0
            for issue in open_i:
                s=ct.get(issue["type"],{"median":14,"std":5})
                sampled=max(1,int(np.random.normal(s["median"]/vel,s.get("std",5)*0.5)))
                remaining=issue.get("days_stale",0)
                total=remaining+sampled
                if issue.get("due"):
                    try:
                        left=(date.fromisoformat(issue["due"])-date.today()).days
                        if total<=left: done+=1
                    except: pass
                else:
                    if np.random.random()>0.5: done+=1
            results.append(min(1.0,done/max(1,len(open_i))))
        p_all=round(np.mean([r==1.0 for r in results])*100,1)
        avg=round(np.mean(results)*100,1)
        pct_dist=[r*100 for r in results]
        dist_fig=go.Figure(go.Histogram(x=pct_dist,nbinsx=20,marker_color=C.ACCENT,opacity=0.78,
            hovertemplate="Completion: %{x:.0f}%<br>Count: %{y}<extra></extra>"))
        dist_fig.add_vline(x=avg,line_dash="dot",line_color=C.AMBER,
            annotation_text=f"Mean {avg}%",annotation_font_color=C.AMBER,annotation_font_size=9)
        dist_fig.add_vline(x=70,line_dash="dot",line_color=C.GREEN,
            annotation_text="Target 70%",annotation_font_color=C.GREEN,annotation_font_size=9)
        dist_fig.update_layout(**L,title=_t(f"Completion Distribution — {nsims} simulations"),
            xaxis=dict(title="% Issues Completed On Time",gridcolor=C.BORDER,range=[0,100]),
            yaxis=dict(title="Simulation Count",gridcolor=C.BORDER))
        # Workstream risk
        a_risk=[]
        for a,s in a_stats.items():
            if a in ("Unassigned","Former user"): continue
            a_open=[i for i in open_i if i["assignee"]==a]
            if not a_open: continue
            ov=sum(1 for i in a_open if "Past Due" in i.get("due_flag",""))
            risk=min(100,s["open"]*7+ov*18)
            a_risk.append({"a":a,"open":s["open"],"ov":ov,"risk":risk})
        a_risk=sorted(a_risk,key=lambda x:-x["risk"])[:10]
        ar_fig=go.Figure(go.Bar(
            x=[r["a"].split()[0] for r in a_risk],y=[r["risk"] for r in a_risk],
            marker_color=[C.RED if r["risk"]>60 else(C.AMBER if r["risk"]>30 else C.GREEN) for r in a_risk],
            text=[f"{r['risk']}" for r in a_risk],textposition="outside"))
        ar_fig.update_layout(**L,title=_t("Workstream Capacity Pressure"),
            yaxis=dict(title="Pressure Index (0–100)",gridcolor=C.BORDER),
            xaxis=dict(gridcolor=C.BORDER))
        # Reallocation
        capacity concentrated=[(r["a"],r["open"]) for r in a_risk if r["open"]>5]
        underloaded=[(a,s["open"]) for a,s in a_stats.items() if s["open"]<3 and a not in ("Unassigned","Former user")]
        realloc=None
        if capacity concentrated and underloaded:
            fr=max(capacity concentrated,key=lambda x:x[1])
            to=min(underloaded,key=lambda x:x[1])
            gain=min(15,(fr[1]-to[1])*2)
            realloc=html.Div([
                html.Div("CAPACITY REBALANCING OPPORTUNITY",style={"fontSize":"0.55rem","fontWeight":"800","letterSpacing":"0.18em","color":C.NAVY2,"margin":"14px 0 8px"}),
                html.Div([
                    html.Span(f"Redistributing tasks from {fr[0].split()[0]} ({fr[1]} active)",style={"color":C.RED,"fontWeight":"700","fontSize":"0.74rem"}),
                    html.Span(" → ",style={"color":C.MUTED,"margin":"0 8px"}),
                    html.Span(f"{to[0].split()[0]} ({to[1]} active)",style={"color":C.GREEN,"fontWeight":"700","fontSize":"0.74rem"}),
                    html.Span(f"  Projected confidence improvement: +{gain}% → {min(100,p_all+gain)}%",
                              style={"color":C.ACCENT,"fontWeight":"700","fontSize":"0.72rem","marginLeft":"12px","fontFamily":"JetBrains Mono,monospace"}),
                ],style={"padding":"10px 14px","background":C.ACCENT2,"borderRadius":"6px","border":f"1px solid {C.BORDER}",
                         "display":"flex","flexWrap":"wrap","alignItems":"center","gap":"6px"}),
            ])
        kpis=html.Div([
            _kpi("Full Completion",f"{p_all}%",C.GREEN if p_all>=70 else(C.AMBER if p_all>=45 else C.RED),
                 "Probability all in-scope issues complete on time"),
            _kpi("Mean Completion",f"{avg}%",C.ACCENT,"Average completion rate across all simulations"),
            _kpi("Issues in Scope",str(len(open_i)),C.NAVY,"Open issues included in simulation"),
            _kpi("Simulations Run",str(nsims),C.MUTED,"Monte Carlo sample count"),
        ],style={"display":"flex","gap":"10px","flexWrap":"wrap","marginBottom":"14px"})
        return html.Div([kpis,C.grid(C.card(_g(dist_fig,"sca-dist",260)),C.card(_g(ar_fig,"sca-risk",260)),cols=2),realloc or html.Div()])


def _render_plan(plan,ct,a_stats,deadline,n_sims,sigma,bug_rate):
    issues_est=[]
    for s in plan.get("stories",[]):
        for t in s.get("tasks",[]):
            issues_est.append({"type":t.get("type","Task"),"estimate":t.get("estimate_days",7)})
        issues_est.append({"type":"Story","estimate":s.get("estimate_days",5)})
    # Monte Carlo on the plan
    results=[]
    for _ in range(n_sims):
        total_days=0
        for item in issues_est:
            s=ct.get(item["type"],{"median":item["estimate"],"std":item["estimate"]*0.4})
            std=s.get("std",3)*sigma
            sampled=max(1,int(np.random.normal(s["median"],std)))
            total_days+=sampled
        # Add bug buffer
        bug_extra=int(total_days*bug_rate*0.5)
        total_days+=bug_extra
        if deadline:
            try:
                days_avail=(date.fromisoformat(deadline)-date.today()).days
                results.append(1 if total_days<=days_avail else 0)
            except: results.append(0.5)
        else:
            results.append(0.5)
    conf=round(np.mean(results)*100,1) if results else 0
    conf_color=C.GREEN if conf>=70 else(C.AMBER if conf>=45 else C.RED)
    total_est=plan.get("total_days",sum(s.get("estimate_days",0) for s in plan.get("stories",[])))
    story_cards=[_story_card(sidx,s,ct) for sidx,s in enumerate(plan.get("stories",[]))]
    dist_vals=results
    if dist_vals:
        dist_fig=go.Figure(go.Histogram(x=[v*100 for v in dist_vals],nbinsx=15,
            marker_color=C.ACCENT,opacity=0.78,hovertemplate="Completion Prob: %{x:.0f}%<br>Count: %{y}<extra></extra>"))
        dist_fig.update_layout(**L,title=_t(f"Simulated Delivery Probability Distribution ({n_sims} runs)"),
            xaxis=dict(title="On-Time Completion %",gridcolor=C.BORDER,range=[0,110]),
            yaxis=dict(title="Simulations",gridcolor=C.BORDER))
        dist_card=C.card(_g(dist_fig,"sp-dist",220))
    else: dist_card=html.Div()
    return html.Div([
        html.Div([
            html.Div([
                html.Div("GENERATED DELIVERY PLAN",style={"fontSize":"0.55rem","fontWeight":"800","letterSpacing":"0.18em","color":C.NAVY2,"marginBottom":"4px"}),
                html.Div(plan["epic"]["summary"],style={"fontWeight":"900","fontSize":"0.95rem","color":C.NAVY}),
                html.Div(plan["epic"].get("description",""),style={"color":C.MUTED,"fontSize":"0.73rem","marginTop":"4px","lineHeight":"1.5"}),
            ],style={"flex":"1"}),
            html.Div([
                html.Div(f"{conf}%",style={"fontSize":"2rem","fontWeight":"900","color":conf_color,"fontFamily":"JetBrains Mono,monospace","lineHeight":"1","textAlign":"right"}),
                html.Div("DELIVERY CONFIDENCE",style={"fontSize":"0.55rem","color":C.MUTED,"fontWeight":"700","textTransform":"uppercase","letterSpacing":"0.1em","textAlign":"right"}),
                html.Div(f"Estimated scope: {total_est}d  |  Bug buffer: {int(bug_rate*100)}%",style={"fontSize":"0.65rem","color":C.ACCENT,"marginTop":"4px","fontFamily":"JetBrains Mono,monospace","textAlign":"right"}),
                html.Div(f"σ multiplier: {sigma}  |  Simulations: {n_sims}",style={"fontSize":"0.62rem","color":C.MUTED,"fontFamily":"JetBrains Mono,monospace","textAlign":"right"}),
            ]),
        ],style={"display":"flex","justifyContent":"space-between","alignItems":"flex-start","padding":"16px","background":C.BG,"borderRadius":"8px","marginBottom":"14px","border":f"1px solid {C.BORDER}"}),
        dist_card,
        html.Div(style={"height":"10px"}),
        *story_cards,
        html.Div([
            html.Div("RISK ASSESSMENT",style={"fontSize":"0.55rem","fontWeight":"800","letterSpacing":"0.18em","color":C.NAVY2,"marginBottom":"6px"}),
            html.Div(plan.get("risk_notes",""),style={"color":C.MUTED,"fontSize":"0.73rem","lineHeight":"1.6"}),
        ],style={"padding":"12px 14px","background":"#FFFBEB","borderRadius":"6px","border":f"1px solid {C.AMBER}33","borderLeft":f"3px solid {C.AMBER}"}),
    ])


def _story_card(sidx,story,ct):
    task_rows=[html.Tr([
        html.Td(t.get("type","Task"),style={"color":C.ACCENT,"fontWeight":"700","fontSize":"0.7rem"}),
        html.Td(t.get("summary",""),style={"fontSize":"0.72rem","color":C.NAVY}),
        html.Td(f"{t.get('estimate_days','')}d",style={"fontFamily":"JetBrains Mono,monospace","color":C.AMBER,"fontWeight":"700","fontSize":"0.7rem"}),
    ],style={"background":C.BG if idx%2 else C.SURFACE})
    for idx,t in enumerate(story.get("tasks",[]))]
    return html.Div([
        html.Div([
            html.Span(f"S{sidx+1}",style={"fontSize":"0.6rem","fontWeight":"900","color":C.PURPLE,"fontFamily":"JetBrains Mono,monospace","marginRight":"8px","background":"#F5F3FF","padding":"2px 6px","borderRadius":"4px"}),
            html.Span(story.get("summary",""),style={"fontWeight":"700","fontSize":"0.78rem","color":C.NAVY}),
            html.Span(f"  {story.get('estimate_days','')}d",style={"color":C.AMBER,"fontWeight":"700","fontSize":"0.7rem","marginLeft":"8px","fontFamily":"JetBrains Mono,monospace"}),
            html.Span(f"  {story.get('assignee','')}",style={"color":C.ACCENT,"fontSize":"0.7rem","marginLeft":"8px"}),
        ],style={"marginBottom":"8px"}),
        html.Table([
            html.Thead(html.Tr([html.Th(h) for h in ["Type","Task","Estimate"]],style={"background":"#F5F3FF"})),
            html.Tbody(task_rows),
        ],style={"width":"100%","borderCollapse":"collapse","fontSize":"0.73rem"}) if task_rows else html.Div(),
    ],style={"background":C.SURFACE,"borderRadius":"8px","padding":"14px","border":f"1px solid {C.BORDER}",
             "marginBottom":"8px","borderLeft":f"4px solid {C.PURPLE}"})


def _kpi(label,value,color,tooltip=""):
    return html.Div([
        html.Div(value,style={"fontSize":"1.4rem","fontWeight":"900","color":color,"fontFamily":"JetBrains Mono,monospace","lineHeight":"1"}),
        html.Div(label,style={"fontSize":"0.6rem","color":C.MUTED,"marginTop":"3px","textTransform":"uppercase","letterSpacing":"0.08em"}),
        html.Div(tooltip,style={"fontSize":"0.6rem","color":C.MUTED,"fontStyle":"italic","marginTop":"2px","lineHeight":"1.4"}) if tooltip else None,
    ],style={"background":C.BG,"borderRadius":"8px","padding":"12px 14px","borderLeft":f"3px solid {color}","minWidth":"120px"})
