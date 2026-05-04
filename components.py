from dash import html, dcc
import dash_cytoscape as cyto

# ── Design tokens (light theme, dark navy accents) ─────────────
BG       = "#F8FAFF"
SURFACE  = "#FFFFFF"
NAVY     = "#0F2344"
NAVY2    = "#1A3A6E"
ACCENT   = "#1E6FDB"
ACCENT2  = "#E8F0FB"
BORDER   = "#DDE6F5"
TEXT     = "#0F2344"
MUTED    = "#6B7A99"
RED      = "#D93025"
ORANGE   = "#E8710A"
GREEN    = "#1E8A44"
AMBER    = "#B45309"

STATUS_CLR = {
    "Closed":                   ("#1E8A44", "#E6F4EC"),
    "QA Testing":               ("#1E6FDB", "#E8F0FB"),
    "Ready For QA Testing":     ("#1E6FDB", "#E8F0FB"),
    "Code Review":              ("#7C3AED", "#F3EFFE"),
    "Development In Progress":  ("#B45309", "#FEF3C7"),
    "Fixing in Progress":       ("#D93025", "#FEE8E8"),
    "Integration Testing":      ("#0F766E", "#E6FAFA"),
    "Groomed":                  ("#6B7A99", "#F1F4FB"),
    "To Do":                    ("#6B7A99", "#F1F4FB"),
    "Rejected":                 ("#D93025", "#FEE8E8"),
}
TYPE_CLR  = {"Task":"#1E6FDB","Story":"#7C3AED","Bug":"#D93025","Sub-task":"#B45309","Epic":"#0F766E"}
PRIO_CLR  = {"Highest":"#D93025","High":"#E8710A","Medium":"#B45309","Low":"#1E8A44"}

def sc(s): fg,bg = STATUS_CLR.get(s, (MUTED,"#F1F4FB")); return fg
def sc_bg(s): fg,bg = STATUS_CLR.get(s, (MUTED,"#F1F4FB")); return bg
def tc(t): return TYPE_CLR.get(t, MUTED)
def pc(p): return PRIO_CLR.get(p, MUTED)

def kpi(label, value, color=ACCENT, sub=None):
    return html.Div([
        html.Div(str(value), style={
            "fontSize":"2rem","fontWeight":"800","color":color,
            "lineHeight":"1","fontFamily":"'DM Mono', monospace",
        }),
        html.Div(label, style={
            "fontSize":"0.65rem","color":MUTED,"marginTop":"4px",
            "letterSpacing":"0.08em","textTransform":"uppercase","fontWeight":"600",
        }),
        html.Div(sub, style={"fontSize":"0.7rem","color":color,"marginTop":"2px","fontWeight":"600"}) if sub else None,
    ], style={
        "background":SURFACE,"borderRadius":"10px","padding":"18px 20px",
        "borderLeft":f"4px solid {color}","boxShadow":"0 1px 6px rgba(15,35,68,0.08)",
        "minWidth":"110px","flex":"1",
    })

def status_badge(s):
    fg, bg = STATUS_CLR.get(s, (MUTED, "#F1F4FB"))
    return html.Span(s, style={
        "background":bg,"color":fg,"borderRadius":"20px",
        "padding":"2px 10px","fontSize":"0.68rem","fontWeight":"600",
        "border":f"1px solid {fg}22","whiteSpace":"nowrap",
    })

def section(title, sub=None):
    return html.Div([
        html.Div(title, style={
            "fontSize":"0.6rem","fontWeight":"800","letterSpacing":"0.14em",
            "textTransform":"uppercase","color":NAVY2,"marginBottom":"2px",
        }),
        html.Div(sub, style={"fontSize":"0.72rem","color":MUTED}) if sub else None,
    ], style={"marginBottom":"14px","marginTop":"24px"})

def card(*children, cols=1, pad="18px"):
    return html.Div(children, style={
        "background":SURFACE,"borderRadius":"12px","padding":pad,
        "border":f"1px solid {BORDER}","gridColumn":f"span {cols}",
        "boxShadow":"0 1px 8px rgba(15,35,68,0.06)",
    })

def grid(*cards, cols=2, gap="16px"):
    return html.Div(cards, style={
        "display":"grid","gridTemplateColumns":f"repeat({cols},1fr)",
        "gap":gap,"marginTop":"16px",
    })

CYTO_STYLE = [
    {"selector":"node","style":{
        "label":"data(label)","font-size":"9px","color":TEXT,
        "background-color":"data(color)","border-color":"data(border)",
        "border-width":"2px","width":"data(size)","height":"data(size)",
        "text-valign":"bottom","text-halign":"center","text-margin-y":"5px",
        "font-family":"DM Mono, monospace","font-weight":"600",
    }},
    {"selector":"edge","style":{
        "line-color":BORDER,"target-arrow-color":MUTED,
        "target-arrow-shape":"triangle","curve-style":"bezier",
        "label":"data(label)","font-size":"8px","color":MUTED,"width":"1.5",
        "font-family":"DM Mono, monospace",
    }},
    {"selector":":selected","style":{"border-width":"3px","border-color":ACCENT}},
]

def cyto_elements(issues):
    nodes, edges, seen = [], [], set()
    key_map = {i["key"]: i for i in issues}
    for i in issues:
        sz = max(24, min(50, 24 + len(i["links"]) * 5))
        fg = sc(i["status"])
        nodes.append({"data":{
            "id":i["key"],"label":i["key"],
            "color":sc_bg(i["status"]),"border":fg,"size":sz,
            "type":i["type"],"status":i["status"],
            "assignee":i["assignee"],"summary":i["summary"][:60],
        }})
        for lnk in i["links"]:
            eid = f"{i['key']}-{lnk['key']}-{lnk['type']}"
            rev = f"{lnk['key']}-{i['key']}-{lnk['type']}"
            if eid not in seen and rev not in seen and lnk["key"] in key_map:
                edges.append({"data":{
                    "source":i["key"] if lnk["direction"]=="outward" else lnk["key"],
                    "target":lnk["key"] if lnk["direction"]=="outward" else i["key"],
                    "label":lnk["type"],
                }})
                seen.add(eid)
    return nodes + edges

def issue_drawer(issue):
    if not issue: return html.Div("Select a node to view details.", style={"color":MUTED,"padding":"24px","fontSize":"0.8rem"})
    rows = [
        ("Issue Type", issue["type"]),
        ("Status",     issue["status"]),
        ("Assignee",   issue["assignee"]),
        ("Priority",   issue["priority"]),
        ("Label",      issue["label_display"]),
        ("Created",    issue["created"]),
        ("Updated",    issue["updated"]),
        ("Due Date",   issue["due"] or "—"),
        ("Due Flag",   issue["due_flag"]),
        ("Days Stale", issue["days_stale"]),
        ("Comments",   issue["comments_count"]),
        ("Parent",     issue["parent"] or "—"),
    ]
    return html.Div([
        html.A(issue["key"], href=issue["url"], target="_blank", style={
            "fontSize":"0.9rem","fontWeight":"800","color":ACCENT,
            "textDecoration":"none","fontFamily":"DM Mono, monospace",
        }),
        html.Div(issue["summary"], style={
            "color":TEXT,"fontSize":"0.8rem","margin":"8px 0 16px",
            "lineHeight":"1.5","fontWeight":"500",
        }),
        html.Div([html.Div([
            html.Span(k, style={"color":MUTED,"fontSize":"0.65rem","fontWeight":"600",
                                "textTransform":"uppercase","letterSpacing":"0.06em",
                                "width":"90px","display":"inline-block"}),
            html.Span(str(v), style={"color":TEXT,"fontSize":"0.75rem","fontWeight":"500"}),
        ], style={"marginBottom":"8px","display":"flex","alignItems":"center"}) for k,v in rows]),
        html.Div("Latest Comment", style={"color":MUTED,"fontSize":"0.65rem","fontWeight":"600",
                                          "textTransform":"uppercase","letterSpacing":"0.06em",
                                          "marginTop":"16px","marginBottom":"6px"}),
        html.Div(issue["latest_comment"] or "No comments.", style={
            "color":MUTED,"fontSize":"0.75rem","lineHeight":"1.6",
            "background":"#F8FAFF","borderRadius":"8px","padding":"10px",
            "border":f"1px solid {BORDER}",
        }),
    ], style={"padding":"20px"})
