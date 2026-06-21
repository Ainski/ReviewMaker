"""SVG renderer for the Figure-1 lineage diagram (Ivory Ledger, monochrome).

Pure string assembly from `compute_layout`. Produces a self-contained static SVG
(for the poster) plus a nodes_json list (for the GUI's click-to-detail panel).
Visual reference: docs/reference/figure1_embedded_prototype.html.
"""

from src.figure1_layout import compute_layout
from src.figure1_models import FOUND

INK = "#171717"
GRAPH = "#55514A"
GRAPHL = "#96918A"
SURF = "#FFFFFF"
WARM = "#FAFAF8"
PRIMARY = "#6D5DF6"

_STYLE = f"""
  .fig-bg {{ fill: {SURF}; }}
  .fig-line {{ stroke: {INK}; stroke-width: 1; fill: none; }}
  .fig-warm {{ fill: {WARM}; }}
  .fig-dot {{ fill: {INK}; stroke: {SURF}; stroke-width: 2; }}
  .fig-knock {{ fill: {SURF}; opacity: 0.92; }}
  text {{ font-family: Jost, "Noto Sans SC", system-ui, sans-serif; }}
  .t-kicker {{ font-family: "JetBrains Mono", monospace; font-size: 11px; letter-spacing: .18em; fill: {GRAPHL}; }}
  .t-title {{ font-weight: 300; font-size: 22px; fill: {INK}; }}
  .t-name {{ font-weight: 400; font-size: 13px; fill: {INK}; }}
  .t-meta {{ font-family: "JetBrains Mono", monospace; font-size: 8.5px; letter-spacing: .1em; fill: {GRAPHL}; }}
  .t-contrib {{ font-weight: 400; font-size: 10.5px; fill: {GRAPH}; }}
  .t-blabel {{ font-weight: 500; font-size: 13px; fill: {INK}; }}
  .t-bsub {{ font-family: "JetBrains Mono", monospace; font-size: 8.5px; letter-spacing: .08em; fill: {GRAPHL}; }}
  .t-era {{ font-weight: 500; font-size: 12px; fill: {GRAPH}; }}
  .t-eraen {{ font-family: "JetBrains Mono", monospace; font-size: 8.5px; letter-spacing: .14em; fill: {GRAPHL}; }}
  .t-gap {{ font-family: "JetBrains Mono", monospace; font-size: 18px; fill: {GRAPHL}; }}
  .t-foot {{ font-family: "JetBrains Mono", monospace; font-size: 10px; letter-spacing: .14em; fill: {GRAPHL}; }}
"""


def _esc(s):
    return (str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            .replace('"', "&quot;"))


def _xs_interp(xs, year):
    """Interpolate an x for an arbitrary year using the layout's anchor years."""
    ys = sorted(xs)
    if year in xs:
        return xs[year]
    if year <= ys[0]:
        return xs[ys[0]]
    if year >= ys[-1]:
        return xs[ys[-1]]
    for a, b in zip(ys, ys[1:]):
        if a <= year <= b:
            t = (year - a) / (b - a)
            return xs[a] + t * (xs[b] - xs[a])
    return xs[ys[-1]]


def _branch_name(graph, bid):
    if bid == FOUND:
        return "奠基 Foundational"
    for b in graph.branches:
        if b.id == bid:
            return b.name_zh
    return bid


def _era_name(graph, year):
    for e in graph.eras:
        if e.y0 <= year <= e.y1:
            return e.name_zh
    return ""


def render_figure1_svg(graph, embed=False):
    L = compute_layout(graph)
    W, H, PAD = L["W"], L["H"], L["PAD"]
    base = L["base_y"]
    xs = L["xs"]
    fork = L["fork_x"]
    ee = L["elbow_end"]
    gap = L["gap"]

    parts = [f'<svg viewBox="0 0 {W} {H}" xmlns="http://www.w3.org/2000/svg" '
             f'font-family="Jost, sans-serif"><style>{_STYLE}</style>']
    parts.append(f'<rect class="fig-bg" x="0" y="0" width="{W}" height="{H}"/>')

    # title chrome (top-left)
    if not embed:
        parts.append(f'<text class="t-kicker" x="{PAD["l"]}" y="22">ALGORITHM LINEAGE · 算法演进谱系</text>')
        parts.append(f'<text class="t-title" x="{PAD["l"]}" y="46">{_esc(graph.topic)}</text>')

    # warm band over the last (boom) era
    if len(graph.eras) >= 2:
        last = graph.eras[-1]
        x0 = _xs_interp(xs, last.y0) - 26
        x1 = W - PAD["r"] + 20
        parts.append(f'<rect class="fig-warm" x="{x0:.1f}" y="{PAD["t"]+18}" '
                     f'width="{x1-x0:.1f}" height="{H-PAD["t"]-PAD["b"]-6}"/>')

    # foundational spine (broken at the gap)
    if gap:
        gc = gap[2]
        gh = 22
        parts.append(f'<line class="fig-line" x1="{PAD["l"]}" y1="{base}" x2="{gc-gh:.1f}" y2="{base}"/>')
        parts.append(f'<line class="fig-line" x1="{gc+gh:.1f}" y1="{base}" x2="{fork:.1f}" y2="{base}"/>')
        parts.append(f'<text class="t-gap" x="{gc:.1f}" y="{base+5:.1f}" text-anchor="middle">···</text>')
    else:
        parts.append(f'<line class="fig-line" x1="{PAD["l"]}" y1="{base}" x2="{fork:.1f}" y2="{base}"/>')

    # lanes (fork elbow + straight line + arrow + branch label)
    x_right = W - PAD["r"]
    for b in graph.branches:
        ly = L["lane_y"].get(b.id)
        if ly is None:
            continue
        parts.append(f'<path class="fig-line" d="M{fork:.1f},{base} C{fork+30:.1f},{base} '
                     f'{fork+30:.1f},{ly:.1f} {ee:.1f},{ly:.1f}"/>')
        parts.append(f'<line class="fig-line" x1="{ee:.1f}" y1="{ly:.1f}" x2="{x_right}" y2="{ly:.1f}"/>')
        parts.append(f'<path class="fig-line" d="M{x_right},{ly:.1f} l-7,-3.5 M{x_right},{ly:.1f} l-7,3.5"/>')
        parts.append(f'<text class="t-blabel" x="{x_right+10}" y="{ly-3:.1f}">{_esc(b.name_zh)}</text>')
        parts.append(f'<text class="t-bsub" x="{x_right+10}" y="{ly+11:.1f}">{_esc(b.name_en)}</text>')

    # era labels — sit above the footer rule (H-46) so they never collide with chrome
    for e in graph.eras:
        cx = (_xs_interp(xs, e.y0) + _xs_interp(xs, e.y1)) / 2
        parts.append(f'<text class="t-era" x="{cx:.1f}" y="{H-82}" text-anchor="middle">{_esc(e.name_zh)}</text>')
        parts.append(f'<text class="t-eraen" x="{cx:.1f}" y="{H-68}" text-anchor="middle">{_esc(e.name_en)}</text>')

    # nodes + labels
    nodes_json = []
    for grp in L["groups"]:
        x, y = grp["x"], grp["y"]
        members = grp["members"]
        for m, p in zip(members, grp["placements"]):
            tx, ty, anchor = p["tx"], p["ty"], p["anchor"]
            bx, _top, w_est, _h = p["bbox"]
            meta = f"{m.authors.upper()} · {m.year}"
            parts.append(f'<line class="fig-line" style="stroke-opacity:.45" stroke-width="0.6" '
                         f'x1="{x:.1f}" y1="{y:.1f}" x2="{x:.1f}" y2="{ty+(12 if ty < y else -12):.1f}"/>')
            parts.append(f'<rect class="fig-knock" x="{bx:.1f}" y="{ty-12:.1f}" width="{w_est:.1f}" height="40" rx="5"/>')
            parts.append(f'<text class="t-name" x="{tx:.1f}" y="{ty:.1f}" text-anchor="{anchor}">{_esc(m.name)}</text>')
            parts.append(f'<text class="t-meta" x="{tx:.1f}" y="{ty+13:.1f}" text-anchor="{anchor}">{_esc(meta)}</text>')
            parts.append(f'<text class="t-contrib" x="{tx:.1f}" y="{ty+27:.1f}" text-anchor="{anchor}">{_esc(m.contrib)}</text>')
        # one dot per (branch, year) group
        key = f"{grp['branch']}|{grp['year']}"
        parts.append(f'<circle class="fig-dot" data-key="{key}" cx="{x:.1f}" cy="{y:.1f}" r="4"/>')
        parts.append(f'<circle class="fig-hit" data-key="{key}" cx="{x:.1f}" cy="{y:.1f}" r="16" '
                     f'fill="transparent" style="cursor:pointer"/>')
        nodes_json.append({
            "branch": grp["branch"], "year": grp["year"], "x": round(x, 1), "y": round(y, 1),
            "members": [{
                "name": m.name, "authors": m.authors, "year": m.year,
                "full_title": m.full_title, "venue": m.venue, "cited_by": m.cited_by,
                "has_code": m.has_code, "abstract": m.abstract, "contrib": m.contrib,
                "branch_name": _branch_name(graph, m.branch), "era_name": _era_name(graph, m.year),
            } for m in members],
        })

    # footer chrome
    if not embed:
        nf = sum(1 for m in graph.milestones if m.branch == FOUND)
        nb = len(graph.branches)
        parts.append(f'<line class="fig-line" x1="{PAD["l"]}" y1="{H-46}" x2="{W-PAD["r"]}" y2="{H-46}" style="stroke-opacity:.4"/>')
        parts.append(f'<text class="t-foot" x="{PAD["l"]}" y="{H-30}">FIG. 1 — METHOD EVOLUTION TIMELINE</text>')
        parts.append(f'<text class="t-foot" x="{W-PAD["r"]}" y="{H-30}" text-anchor="end">'
                     f'{len(graph.milestones)} MILESTONES · {nf} FOUNDATIONAL · {nb} LINEAGES</text>')

    parts.append("</svg>")
    return "".join(parts), nodes_json


def render_insufficient_svg(topic):
    W, H = 1460, 760
    return (f'<svg viewBox="0 0 {W} {H}" xmlns="http://www.w3.org/2000/svg"><style>{_STYLE}</style>'
            f'<rect class="fig-bg" x="0" y="0" width="{W}" height="{H}"/>'
            f'<text class="t-kicker" x="{W//2}" y="{H//2-20}" text-anchor="middle">{_esc(topic)}</text>'
            f'<text class="t-title" x="{W//2}" y="{H//2+16}" text-anchor="middle">'
            f'信息不足:有效里程碑不足,无法构建演进谱系</text></svg>')
