"""Pure layout engine for the Figure-1 lineage diagram.

No SVG/IO here — only geometry. Given a MilestoneGraph, compute year→x mapping
(with the largest empty stretch compressed for a ``···`` break), lane Y positions,
the fork point + elbow end (guaranteed left of the first branch node), and per
(branch, year) node groups with above/below sides.
"""

from collections import defaultdict

from src.figure1_models import FOUND

# Canvas defaults — kept in sync with docs/reference/figure1_embedded_prototype.html
W = 1460
H = 760
PAD = {"l": 92, "r": 182, "t": 40, "b": 64}
GAP_MIN_YEARS = 3       # an empty stretch >= this many years gets a ··· break
GAP_COMPRESS = 0.45     # the gap interval's width relative to a normal interval
ELBOW_DEFAULT = 60      # default fork elbow width
ELBOW_MARGIN = 14       # elbow must end at least this far left of the first branch node


def largest_gap(years):
    """Return (a, b) of the widest consecutive-year gap >= GAP_MIN_YEARS, else None."""
    ys = sorted({y for y in years if y})
    if len(ys) < 2:
        return None
    best, best_d = None, 0
    for a, b in zip(ys, ys[1:]):
        if b - a > best_d:
            best_d, best = b - a, (a, b)
    return best if best_d >= GAP_MIN_YEARS else None


def group_by_branch_year(milestones):
    """Group milestones by (branch, year). Same key -> one node carrying all members."""
    g = defaultdict(list)
    for m in milestones:
        g[(m.branch, m.year)].append(m)
    return dict(g)


def _build_xs(years, gap):
    """Piecewise year->x. The gap interval is compressed; others share equal width."""
    ys = sorted(set(years))
    inner = W - PAD["l"] - PAD["r"]
    if len(ys) == 1:
        return {ys[0]: PAD["l"] + inner / 2}
    weights = []
    for a, b in zip(ys, ys[1:]):
        is_gap = gap is not None and a == gap[0] and b == gap[1]
        weights.append(GAP_COMPRESS if is_gap else 1.0)
    total = sum(weights) or 1.0
    xs, acc = {ys[0]: PAD["l"]}, 0.0
    for i, w in enumerate(weights):
        acc += w
        xs[ys[i + 1]] = PAD["l"] + (acc / total) * inner
    return xs


def _lane_y(branches, milestones, base_y):
    """Map branch id -> y. Branches ordered by earliest milestone year."""
    earliest = {}
    for m in milestones:
        if m.branch != FOUND:
            earliest[m.branch] = min(earliest.get(m.branch, m.year), m.year)
    ordered = [b.id for b in branches if b.id in earliest]
    # include any branch ids that appear in milestones but not in branches list
    for bid in earliest:
        if bid not in ordered:
            ordered.append(bid)
    n = len(ordered)
    lane = {FOUND: base_y}
    if n == 0:
        return lane
    usable = H - PAD["t"] - PAD["b"] - 60
    spacing = min(176, usable / n)
    for i, bid in enumerate(ordered):
        lane[bid] = base_y + (i - (n - 1) / 2) * spacing
    return lane


def _sides_for_group(members, group_year_index):
    """Above/below side + stacking level for each member of a (branch,year) group."""
    base_side = -1 if group_year_index % 2 == 0 else 1
    sides, levels = [], []
    if len(members) == 1:
        return [base_side], [0]
    for k in range(len(members)):
        sides.append(-1 if k % 2 == 0 else 1)
        levels.append(k // 2)
    return sides, levels


def compute_layout(graph):
    milestones = graph.milestones
    years = [m.year for m in milestones if m.year]
    gap = largest_gap(years)
    xs = _build_xs(years, gap)
    base_y = (PAD["t"] + (H - PAD["b"])) / 2
    lane_y = _lane_y(graph.branches, milestones, base_y)

    found_years = [m.year for m in milestones if m.branch == FOUND and m.year]
    branch_years = [m.year for m in milestones if m.branch != FOUND and m.year]

    # fork position: between the last foundational year and the first branch year
    if found_years and branch_years:
        last_found, first_branch = max(found_years), min(branch_years)
        if last_found < first_branch:
            fork_x = (xs[last_found] + xs[first_branch]) / 2
        else:
            fork_x = xs[first_branch] - 30
    elif branch_years:
        fork_x = xs[min(branch_years)] - 30
    else:
        fork_x = xs[max(found_years)] if found_years else PAD["l"]

    if branch_years:
        first_branch_x = xs[min(branch_years)]
        elbow_end = min(fork_x + ELBOW_DEFAULT, first_branch_x - ELBOW_MARGIN)
    else:
        elbow_end = fork_x

    # group nodes; assign sides per lane using year ordering within each lane
    grouped = group_by_branch_year(milestones)
    lane_year_order = defaultdict(list)
    for (branch, year) in grouped:
        lane_year_order[branch].append(year)
    for branch in lane_year_order:
        lane_year_order[branch] = sorted(set(lane_year_order[branch]))

    groups = []
    for (branch, year), members in grouped.items():
        gyi = lane_year_order[branch].index(year)
        sides, levels = _sides_for_group(members, gyi)
        groups.append({
            "branch": branch,
            "year": year,
            "x": xs[year],
            "y": lane_y.get(branch, base_y),
            "members": members,
            "sides": sides,
            "levels": levels,
        })

    return {
        "W": W, "H": H, "PAD": PAD,
        "base_y": base_y,
        "fork_x": fork_x,
        "elbow_end": elbow_end,
        "xs": xs,
        "lane_y": lane_y,
        "gap": (gap[0], gap[1], (xs[gap[0]] + xs[gap[1]]) / 2) if gap else None,
        "years": sorted(set(years)),
        "groups": groups,
    }
