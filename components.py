from dash import html, dcc
import dash_cytoscape as cyto

BG="#F0F4FF"; SURFACE="#FFFFFF"; NAVY="#0B1D3A"; NAVY2="#1A3560"
ACCENT="#2563EB"; ACCENT2="#EEF4FF"; BORDER="#D4DFFF"; TEXT="#0B1D3A"
MUTED="#5A6E99"; RED="#DC2626"; ORANGE="#EA580C"; GREEN="#16A34A"
AMBER="#D97706"; PURPLE="#7C3AED"; TEAL="#0D9488"

EDGE_COLORS = {
    "blocks":"#DC2626","is blocked by":"#DC2626",
    "Blocks":"#DC2626","is blocked by":"#DC2626",
    "relates to":"#2563EB","Relates":"#2563EB",
    "duplicates":"#D97706","is duplicated by":"#D97706","Duplicate":"#D97706",
    "clones":"#7C3AED","is cloned by":"#7C3AED","Cloners":"#7C3AED",
    "causes":"#EA580C","is caused by":"#EA580C","Problem/Incident":"#EA580C",
    "implements":"#0D9488","is implemented by":"#0D9488",
}

STATUS_CLR = {
    "Closed":(GREEN,"#F0FDF4"), "QA Testing":(ACCENT,"#EEF4FF"),
    "Ready For QA Testing":(ACCENT,"#EEF4FF"), "Code Review":(PURPLE,"#F5F3FF"),
    "Development In Progress":(AMBER,"#FFFBEB"), "Fixing in Progress":(RED,"#FEF2F2"),
    "Integration Testing":(TEAL,"#F0FDFA"), "Groomed":(MUTED,"#F1F5F9"),
    "To Do":(MUTED,"#F1F5F9"), "Rejected":(RED,"#FEF2F2"),
}
TYPE_CLR={"Task":ACCENT,"Story":PURPLE,"Bug":RED,"Sub-task":AMBER,"Epic":TEAL}
PRIO_CLR={"Highest":RED,"High":ORANGE,"Medium":AMBER,"Low":GREEN}
PRIO_ICON={"Highest":"▲▲","High":"▲","Medium":"◆","Low":"▼"}

def sc(s): return STATUS_CLR.get(s,(MUTED,"#F1F5F9"))[0]
def sc_bg(s): return STATUS_CLR.get(s,(MUTED,"#F1F5F9"))[1]
def tc(t): return TYPE_CLR.get(t,MUTED)
def pc(p): return PRIO_CLR.get(p,MUTED)
def edge_color(ltype):
    for k,v in EDGE_COLORS.items():
        if k.lower() in ltype.lower(): return v
    return "#94A3B8"

def kpi(label, value, color=ACCENT, sub=None):
    return html.Div([
        html.Div(str(value),style={"fontSize":"2rem","fontWeight":"800","color":color,"lineHeight":"1","fontFamily":"'JetBrains Mono',monospace"}),
        html.Div(label,style={"fontSize":"0.62rem","color":MUTED,"marginTop":"5px","letterSpacing":"0.1em","textTransform":"uppercase","fontWeight":"700"}),
        html.Div(sub,style={"fontSize":"0.7rem","color":color,"marginTop":"3px","fontWeight":"700"}) if sub else None,
    ],style={"background":SURFACE,"borderRadius":"10px","padding":"16px 18px","borderLeft":f"4px solid {color}","boxShadow":"0 2px 8px rgba(11,29,58,0.08)","minWidth":"110px","flex":"1"})

def health_score(label, score, issues_count):
    color = GREEN if score>=70 else (AMBER if score>=40 else RED)
    return html.Div([
        html.Div([
            html.Div(f"{score}", style={"fontSize":"2.4rem","fontWeight":"900","color":color,"fontFamily":"JetBrains Mono,monospace","lineHeight":"1"}),
            html.Div("/100", style={"fontSize":"0.8rem","color":MUTED,"fontWeight":"600","marginTop":"4px"}),
        ]),
        html.Div(label, style={"fontWeight":"800","fontSize":"0.78rem","color":NAVY,"marginTop":"8px"}),
        html.Div(f"{issues_count} issues", style={"fontSize":"0.68rem","color":MUTED}),
        html.Div("●" * 5, style={"color":color,"fontSize":"0.6rem","letterSpacing":"2px","marginTop":"6px"}),
    ], style={
        "background":SURFACE,"borderRadius":"12px","padding":"20px","textAlign":"center",
        "border":f"2px solid {color}33","borderTop":f"4px solid {color}",
        "boxShadow":f"0 4px 16px {color}22","flex":"1","minWidth":"150px",
    })

def traffic_light(overdue, total):
    if total == 0: return "⚫"
    pct = overdue/total
    if pct == 0: return "🟢"
    elif pct < 0.3: return "🟡"
    else: return "🔴"

def status_badge(s):
    fg,bg = STATUS_CLR.get(s,(MUTED,"#F1F5F9"))
    return html.Span(s,style={"background":bg,"color":fg,"borderRadius":"4px","padding":"2px 8px","fontSize":"0.67rem","fontWeight":"700","border":f"1px solid {fg}33","whiteSpace":"nowrap","display":"inline-block"})

def section(title,sub=None):
    return html.Div([
        html.Div(title,style={"fontSize":"0.58rem","fontWeight":"800","letterSpacing":"0.16em","textTransform":"uppercase","color":NAVY2}),
        html.Div(sub,style={"fontSize":"0.72rem","color":MUTED,"marginTop":"2px"}) if sub else None,
    ],style={"marginBottom":"12px","marginTop":"22px"})

def card(*children,cols=1,pad="18px",style=None):
    base={"background":SURFACE,"borderRadius":"12px","padding":pad,"border":f"1px solid {BORDER}","gridColumn":f"span {cols}","boxShadow":"0 2px 10px rgba(11,29,58,0.06)"}
    if style: base.update(style)
    return html.Div(children,style=base)

def grid(*cards,cols=2,gap="16px"):
    return html.Div(cards,style={"display":"grid","gridTemplateColumns":f"repeat({cols},1fr)","gap":gap,"marginTop":"16px"})

CYTO_STYLE = [
    {"selector":"node","style":{
        "label":"data(label)","font-size":"9px","color":TEXT,
        "background-color":"data(bg)","border-color":"data(border)","border-width":"2px",
        "width":"data(size)","height":"data(size)",
        "text-valign":"bottom","text-halign":"center","text-margin-y":"5px",
        "font-family":"JetBrains Mono,monospace","font-weight":"600",
        "text-background-color":SURFACE,"text-background-opacity":"0.85","text-background-padding":"2px",
    }},
    {"selector":"node[type='Epic']","style":{"shape":"round-rectangle","width":"65","height":"32"}},
    {"selector":"node[type='Story']","style":{"shape":"round-hexagon"}},
    {"selector":"node[type='Bug']","style":{"shape":"diamond"}},
    {"selector":"node[type='Sub-task']","style":{"shape":"ellipse","border-style":"dashed"}},
    {"selector":"node[blocked='yes']","style":{"border-color":RED,"border-width":"3px"}},
    {"selector":"node[blocker='yes']","style":{"border-color":ORANGE,"border-width":"3px"}},
    {"selector":"edge","style":{
        "line-color":"data(color)","target-arrow-color":"data(color)",
        "target-arrow-shape":"triangle","curve-style":"bezier",
        "label":"data(label)","font-size":"8px","color":MUTED,"width":"data(width)",
        "font-family":"JetBrains Mono,monospace","text-rotation":"autorotate","text-margin-y":"-8px",
    }},
    {"selector":"edge[critical='yes']","style":{"width":"3","line-style":"solid"}},
    {"selector":":selected","style":{"border-width":"3px","border-color":ACCENT}},
]

def cyto_elements(issues):
    nodes, edges, seen = [], [], set()
    key_map = {i["key"]:i for i in issues}
    # Identify blockers/blocked
    blocking_keys = set()
    blocked_keys = set()
    for i in issues:
        for lnk in i["links"]:
            lt = lnk["type"].lower()
            if "block" in lt:
                if lnk["direction"]=="outward": blocking_keys.add(i["key"])
                else: blocked_keys.add(i["key"])

    for i in issues:
        sz = max(28,min(56,28+len(i["links"])*5))
        nodes.append({"data":{
            "id":i["key"],"label":i["key"],
            "bg":sc_bg(i["status"]),"border":sc(i["status"]),"size":sz,
            "type":i["type"],"status":i["status"],"assignee":i["assignee"],
            "summary":i["summary"][:60],"priority":i["priority"],"due_flag":i["due_flag"],
            "blocker":"yes" if i["key"] in blocking_keys else "no",
            "blocked":"yes" if i["key"] in blocked_keys else "no",
        }})
        for lnk in i["links"]:
            eid = tuple(sorted([i["key"],lnk["key"]]))+(lnk["type"],)
            is_block = "block" in lnk["type"].lower()
            if eid not in seen and lnk["key"] in key_map:
                src = i["key"] if lnk["direction"]=="outward" else lnk["key"]
                tgt = lnk["key"] if lnk["direction"]=="outward" else i["key"]
                edges.append({"data":{
                    "source":src,"target":tgt,
                    "label":lnk["type"],"color":edge_color(lnk["type"]),
                    "width":"2.5" if is_block else "1.5",
                    "critical":"yes" if is_block else "no",
                }})
                seen.add(eid)
    return nodes+edges

def issue_drawer(issue):
    if not issue:
        return html.Div([html.Div("◎",style={"fontSize":"2rem","color":BORDER,"marginBottom":"12px"}),
                         html.Div("Click a node to inspect",style={"color":MUTED,"fontSize":"0.8rem"})],
                        style={"padding":"32px","textAlign":"center"})
    blocking=[l for l in issue["links"] if "block" in l["type"].lower() and l["direction"]=="outward"]
    blocked_by=[l for l in issue["links"] if "block" in l["type"].lower() and l["direction"]=="inward"]
    related=[l for l in issue["links"] if "block" not in l["type"].lower()]
    return html.Div([
        html.Div([
            html.Span(issue["type"],style={"fontSize":"0.62rem","fontWeight":"800","color":tc(issue["type"]),"letterSpacing":"0.1em","textTransform":"uppercase"}),
            html.A(issue["key"],href=issue["url"],target="_blank",style={"fontSize":"0.92rem","fontWeight":"800","color":NAVY,"textDecoration":"none","fontFamily":"JetBrains Mono,monospace","display":"block","marginTop":"4px"}),
            html.Div(issue["summary"],style={"color":TEXT,"fontSize":"0.76rem","marginTop":"6px","lineHeight":"1.5"}),
        ],style={"borderBottom":f"1px solid {BORDER}","paddingBottom":"12px","marginBottom":"12px"}),
        # Impact row
        html.Div([
            html.Span(f"🔴 blocks {len(blocking)}",style={"background":"#FEF2F2","color":RED,"borderRadius":"4px","padding":"3px 8px","fontSize":"0.68rem","fontWeight":"700","marginRight":"6px"}) if blocking else None,
            html.Span(f"🟠 blocked by {len(blocked_by)}",style={"background":"#FFF7ED","color":ORANGE,"borderRadius":"4px","padding":"3px 8px","fontSize":"0.68rem","fontWeight":"700","marginRight":"6px"}) if blocked_by else None,
            html.Span(f"🔵 {len(related)} related",style={"background":ACCENT2,"color":ACCENT,"borderRadius":"4px","padding":"3px 8px","fontSize":"0.68rem","fontWeight":"700"}) if related else None,
        ],style={"marginBottom":"12px","display":"flex","flexWrap":"wrap","gap":"4px"}),
        html.Div([status_badge(issue["status"]),
                  html.Span(f" {PRIO_ICON.get(issue['priority'],'')} {issue['priority']}",style={"color":pc(issue["priority"]),"fontSize":"0.7rem","fontWeight":"700","marginLeft":"8px"})],
                 style={"marginBottom":"14px"}),
        *[html.Div([html.Span(k,style={"color":MUTED,"fontSize":"0.62rem","fontWeight":"700","textTransform":"uppercase","letterSpacing":"0.08em","width":"80px","display":"inline-block"}),
                    html.Span(str(v),style={"color":TEXT,"fontSize":"0.75rem","fontWeight":"500"})],style={"marginBottom":"7px"})
          for k,v in [("Assignee",issue["assignee"]),("Due",issue["due"] or "—"),("Due Flag",issue["due_flag"]),("Stale",f"{issue['days_stale']}d"),("Parent",issue["parent"] or "—")]],
        html.Div("Links",style={"color":MUTED,"fontSize":"0.62rem","fontWeight":"700","textTransform":"uppercase","letterSpacing":"0.08em","marginTop":"14px","marginBottom":"8px"}),
        *[html.Div([html.Span(l["type"],style={"color":edge_color(l["type"]),"fontSize":"0.65rem","fontWeight":"700","marginRight":"6px","width":"100px","display":"inline-block"}),
                    html.Span(l["key"],style={"color":ACCENT,"fontSize":"0.73rem","fontFamily":"JetBrains Mono,monospace","fontWeight":"600"})],style={"marginBottom":"5px"})
          for l in issue["links"][:8]],
        html.Div(issue["latest_comment"] or "No comments.",style={"color":MUTED,"fontSize":"0.72rem","lineHeight":"1.6","marginTop":"12px","fontStyle":"italic","borderTop":f"1px solid {BORDER}","paddingTop":"10px"}),
    ],style={"padding":"16px","overflowY":"auto","height":"100%"})
