from dash import html, dcc
import dash_cytoscape as cyto

# ── Design tokens ──────────────────────────────────────────────
BG      = "#F0F4FF"
SURFACE = "#FFFFFF"
NAVY    = "#0B1D3A"
NAVY2   = "#1A3560"
ACCENT  = "#2563EB"
ACCENT2 = "#EEF4FF"
BORDER  = "#D4DFFF"
TEXT    = "#0B1D3A"
MUTED   = "#5A6E99"
RED     = "#DC2626"
ORANGE  = "#EA580C"
GREEN   = "#16A34A"
AMBER   = "#D97706"
PURPLE  = "#7C3AED"
TEAL    = "#0D9488"

# Edge colors (MRM-inspired)
EDGE_COLORS = {
    "Blocks":     "#DC2626",
    "is blocked by": "#DC2626",
    "Relates":    "#2563EB",
    "relates to": "#2563EB",
    "Duplicate":  "#D97706",
    "duplicates": "#D97706",
    "Clones":     "#7C3AED",
    "Polaris work item link": "#0D9488",
}

STATUS_CLR = {
    "Closed":                   ("#16A34A", "#F0FDF4"),
    "QA Testing":               ("#2563EB", "#EEF4FF"),
    "Ready For QA Testing":     ("#2563EB", "#EEF4FF"),
    "Code Review":              ("#7C3AED", "#F5F3FF"),
    "Development In Progress":  ("#D97706", "#FFFBEB"),
    "Fixing in Progress":       ("#DC2626", "#FEF2F2"),
    "Integration Testing":      ("#0D9488", "#F0FDFA"),
    "Groomed":                  ("#5A6E99", "#F1F5F9"),
    "To Do":                    ("#5A6E99", "#F1F5F9"),
    "Rejected":                 ("#DC2626", "#FEF2F2"),
}
TYPE_CLR  = {"Task":"#2563EB","Story":"#7C3AED","Bug":"#DC2626","Sub-task":"#D97706","Epic":"#0D9488"}
PRIO_CLR  = {"Highest":"#DC2626","High":"#EA580C","Medium":"#D97706","Low":"#16A34A"}
PRIO_ICON = {"Highest":"▲▲","High":"▲","Medium":"◆","Low":"▼"}

def sc(s): return STATUS_CLR.get(s, (MUTED,"#F1F5F9"))[0]
def sc_bg(s): return STATUS_CLR.get(s, (MUTED,"#F1F5F9"))[1]
def tc(t): return TYPE_CLR.get(t, MUTED)
def pc(p): return PRIO_CLR.get(p, MUTED)

def kpi(label, value, color=ACCENT, sub=None):
    return html.Div([
        html.Div(str(value), style={
            "fontSize":"2rem","fontWeight":"800","color":color,
            "lineHeight":"1","fontFamily":"'JetBrains Mono', monospace",
        }),
        html.Div(label, style={
            "fontSize":"0.62rem","color":MUTED,"marginTop":"5px",
            "letterSpacing":"0.1em","textTransform":"uppercase","fontWeight":"700",
        }),
        html.Div(sub, style={"fontSize":"0.7rem","color":color,"marginTop":"3px","fontWeight":"700"}) if sub else None,
    ], style={
        "background":SURFACE,"borderRadius":"10px","padding":"16px 18px",
        "borderLeft":f"4px solid {color}","boxShadow":"0 2px 8px rgba(11,29,58,0.08)",
        "minWidth":"110px","flex":"1",
    })

def status_badge(s):
    fg, bg = STATUS_CLR.get(s, (MUTED, "#F1F5F9"))
    return html.Span(s, style={
        "background":bg,"color":fg,"borderRadius":"4px",
        "padding":"2px 8px","fontSize":"0.67rem","fontWeight":"700",
        "border":f"1px solid {fg}33","whiteSpace":"nowrap","display":"inline-block",
    })

def impact_badge(label, value, color):
    return html.Span([
        html.Span(f"{value} ", style={"fontWeight":"800"}), label,
    ], style={
        "background":f"{color}15","color":color,"borderRadius":"4px",
        "padding":"3px 10px","fontSize":"0.7rem","fontWeight":"600",
        "border":f"1px solid {color}33","marginRight":"6px",
    })

def section(title, sub=None):
    return html.Div([
        html.Div(title, style={
            "fontSize":"0.58rem","fontWeight":"800","letterSpacing":"0.16em",
            "textTransform":"uppercase","color":NAVY2,
        }),
        html.Div(sub, style={"fontSize":"0.72rem","color":MUTED,"marginTop":"2px"}) if sub else None,
    ], style={"marginBottom":"12px","marginTop":"22px"})

def card(*children, cols=1, pad="18px", style=None):
    base = {
        "background":SURFACE,"borderRadius":"12px","padding":pad,
        "border":f"1px solid {BORDER}","gridColumn":f"span {cols}",
        "boxShadow":"0 2px 10px rgba(11,29,58,0.06)",
    }
    if style: base.update(style)
    return html.Div(children, style=base)

def grid(*cards, cols=2, gap="16px"):
    return html.Div(cards, style={
        "display":"grid","gridTemplateColumns":f"repeat({cols},1fr)",
        "gap":gap,"marginTop":"16px",
    })

# ── Cytoscape ─────────────────────────────────────────────────
def _edge_color(label):
    for k,v in EDGE_COLORS.items():
        if k.lower() in label.lower(): return v
    return "#94A3B8"

CYTO_STYLE = [
    {"selector":"node","style":{
        "label":"data(label)","font-size":"9px","color":TEXT,
        "background-color":"data(bg)","border-color":"data(border)",
        "border-width":"2px","width":"data(size)","height":"data(size)",
        "text-valign":"bottom","text-halign":"center","text-margin-y":"5px",
        "font-family":"JetBrains Mono, monospace","font-weight":"600",
        "text-background-color":SURFACE,"text-background-opacity":"0.85",
        "text-background-padding":"2px",
    }},
    {"selector":"node[type='Epic']","style":{"shape":"round-rectangle","width":"60px","height":"30px","font-size":"8px"}},
    {"selector":"node[type='Story']","style":{"shape":"round-hexagon"}},
    {"selector":"node[type='Bug']","style":{"shape":"diamond"}},
    {"selector":"node[type='Sub-task']","style":{"shape":"ellipse","border-style":"dashed"}},
    {"selector":"edge","style":{
        "line-color":"data(color)","target-arrow-color":"data(color)",
        "target-arrow-shape":"triangle","curve-style":"bezier",
        "label":"data(label)","font-size":"8px","color":MUTED,"width":"1.8",
        "font-family":"JetBrains Mono, monospace",
        "text-rotation":"autorotate","text-margin-y":"-8px",
    }},
    {"selector":":selected","style":{"border-width":"3px","border-color":ACCENT,"border-style":"solid"}},
    {"selector":"node:hover","style":{"border-width":"3px","border-color":NAVY}},
]

def cyto_elements(issues, depth=2, focus_key=None):
    nodes, edges, seen = [], [], set()
    key_map = {i["key"]: i for i in issues}

    def should_include(key):
        if focus_key is None: return True
        if depth == 0: return key == focus_key
        # BFS from focus
        visited, queue = set(), [focus_key]
        for _ in range(depth):
            next_q = []
            for k in queue:
                if k in visited: continue
                visited.add(k)
                issue = key_map.get(k)
                if issue:
                    for lnk in issue["links"]:
                        if lnk["key"] not in visited: next_q.append(lnk["key"])
            queue = next_q
        return key in visited or key == focus_key

    for i in issues:
        if not should_include(i["key"]): continue
        sz = max(28, min(55, 28 + len(i["links"]) * 5))
        nodes.append({"data":{
            "id":i["key"],"label":i["key"],
            "bg":sc_bg(i["status"]),"border":sc(i["status"]),"size":sz,
            "type":i["type"],"status":i["status"],
            "assignee":i["assignee"],"summary":i["summary"][:60],
            "priority":i["priority"],"due_flag":i["due_flag"],
        }})
        for lnk in i["links"]:
            eid = tuple(sorted([i["key"], lnk["key"]])) + (lnk["type"],)
            if eid not in seen and lnk["key"] in key_map:
                edges.append({"data":{
                    "source":i["key"] if lnk["direction"]=="outward" else lnk["key"],
                    "target":lnk["key"] if lnk["direction"]=="outward" else i["key"],
                    "label":lnk["type"],"color":_edge_color(lnk["type"]),
                }})
                seen.add(eid)
    return nodes + edges

def issue_drawer(issue):
    if not issue:
        return html.Div([
            html.Div("◎", style={"fontSize":"2rem","color":BORDER,"marginBottom":"12px"}),
            html.Div("Click a node to inspect", style={"color":MUTED,"fontSize":"0.8rem"}),
        ], style={"padding":"32px","textAlign":"center"})

    # Impact counts
    blocking = sum(1 for l in issue["links"] if "block" in l["type"].lower() and l["direction"]=="outward")
    blocked_by = sum(1 for l in issue["links"] if "block" in l["type"].lower() and l["direction"]=="inward")
    related = sum(1 for l in issue["links"] if "block" not in l["type"].lower())

    return html.Div([
        # Header
        html.Div([
            html.Div([
                html.Span(issue["type"], style={"fontSize":"0.62rem","fontWeight":"800","color":tc(issue["type"]),"letterSpacing":"0.1em","textTransform":"uppercase"}),
            ]),
            html.A(issue["key"], href=issue["url"], target="_blank", style={
                "fontSize":"0.95rem","fontWeight":"800","color":NAVY,
                "textDecoration":"none","fontFamily":"JetBrains Mono, monospace","display":"block","marginTop":"4px",
            }),
            html.Div(issue["summary"], style={"color":TEXT,"fontSize":"0.77rem","marginTop":"6px","lineHeight":"1.5","fontWeight":"500"}),
        ], style={"borderBottom":f"1px solid {BORDER}","paddingBottom":"12px","marginBottom":"12px"}),

        # Impact badges
        html.Div([
            impact_badge("blocks", blocking, RED) if blocking else None,
            impact_badge("blocked by", blocked_by, ORANGE) if blocked_by else None,
            impact_badge("related", related, ACCENT) if related else None,
        ], style={"marginBottom":"12px","display":"flex","flexWrap":"wrap","gap":"4px"}),

        # Status + Priority
        html.Div([
            status_badge(issue["status"]),
            html.Span(f"{PRIO_ICON.get(issue['priority'],'')} {issue['priority']}", style={
                "color":pc(issue["priority"]),"fontSize":"0.7rem","fontWeight":"700","marginLeft":"8px",
            }),
        ], style={"marginBottom":"14px"}),

        # Attributes
        *[html.Div([
            html.Span(k, style={"color":MUTED,"fontSize":"0.62rem","fontWeight":"700","textTransform":"uppercase","letterSpacing":"0.08em","width":"80px","display":"inline-block"}),
            html.Span(str(v), style={"color":TEXT,"fontSize":"0.75rem","fontWeight":"500"}),
        ], style={"marginBottom":"7px"}) for k,v in [
            ("Assignee", issue["assignee"]),
            ("Due Date", issue["due"] or "—"),
            ("Due Flag", issue["due_flag"]),
            ("Stale",    f"{issue['days_stale']} days"),
            ("Comments", issue["comments_count"]),
            ("Parent",   issue["parent"] or "—"),
        ]],

        # Links list
        html.Div("Linked Issues", style={"color":MUTED,"fontSize":"0.62rem","fontWeight":"700","textTransform":"uppercase","letterSpacing":"0.08em","marginTop":"14px","marginBottom":"8px"}),
        html.Div([
            html.Div([
                html.Span(l["type"], style={"color":_edge_color(l["type"]),"fontSize":"0.65rem","fontWeight":"700","marginRight":"6px"}),
                html.Span(l["key"], style={"color":ACCENT,"fontSize":"0.73rem","fontFamily":"JetBrains Mono, monospace","fontWeight":"600"}),
            ], style={"marginBottom":"5px"})
            for l in issue["links"][:8]
        ]) if issue["links"] else html.Div("No links", style={"color":MUTED,"fontSize":"0.73rem"}),

        # Comment
        html.Div("Latest Comment", style={"color":MUTED,"fontSize":"0.62rem","fontWeight":"700","textTransform":"uppercase","letterSpacing":"0.08em","marginTop":"14px","marginBottom":"6px"}),
        html.Div(issue["latest_comment"] or "No comments.", style={
            "color":MUTED,"fontSize":"0.73rem","lineHeight":"1.6","fontStyle":"italic",
        }),
    ], style={"padding":"16px","overflowY":"auto","height":"100%"})
