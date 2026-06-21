"""Pure layout engine for the Figure-1 lineage diagram.

No SVG/IO here — only geometry. Given a MilestoneGraph, compute year→x mapping
(with the largest empty stretch compressed for a ``···`` break), a dynamic
canvas height + lane Y positions (lanes grow the canvas so they stay a
comfortable distance apart), the fork point + elbow end, and per (branch, year)
node groups whose member labels are placed at the node's four corners with
greedy collision avoidance (no two label boxes overlap when the canvas has room).
"""

from collections import defaultdict

from src.figure1_models import FOUND

# Canvas defaults — width fixed; height grows with lane count (see _canvas_height)
W = 1460
H = 760                 # minimum / default height (kept for backward references)
PAD = {"l": 92, "r": 182, "t": 40, "b": 64}
GAP_MIN_YEARS = 3       # an empty stretch >= this many years gets a ··· break
GAP_COMPRESS = 0.45     # the gap interval's width relative to a normal interval
ELBOW_DEFAULT = 60      # default fork elbow width
ELBOW_MARGIN = 14       # elbow must end at least this far left of the first branch node

# --- Dynamic canvas height: grow so lanes keep comfortable spacing for labels ---
LANE_SPACING = 170      # vertical gap between adjacent lanes
H_MIN = 760             # minimum canvas height (few lanes)
V_PAD = 400             # combined top+bottom room for title, labels, era/foot band

# --- Label placement geometry (must match the renderer's text/knock-rect math) ---
V_OFFSET = 46           # first label's vertical offset from the node baseline
V_STEP = 46             # extra vertical offset per fallback push-out level
LABEL_H = 40            # label box height (name + meta + contrib lines)
H_GAP = 7               # label anchor gap from the node center
KNOCK_PAD = 4           # right-label knock-rect left padding (matches renderer)
COLLIDE_MARGIN = 4      # minimum gap enforced between any two label boxes
MAX_LEVEL = 4           # push-out levels to try before accepting the primary corner


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


def _canvas_height(n_lanes):
    """Grow the canvas so n lanes sit LANE_SPACING apart with room for corner labels."""
    return max(H_MIN, (max(n_lanes, 1) - 1) * LANE_SPACING + V_PAD)


def _lane_y(branches, milestones, base_y):
    """Map branch id -> y; lanes LANE_SPACING apart, centered on base_y."""
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
    for i, bid in enumerate(ordered):
        lane[bid] = base_y + (i - (n - 1) / 2) * LANE_SPACING
    return lane


def _label_w(m):
    """Estimate a label box width — matches the renderer's knock-rect width."""
    return max(len(m.name) * 7.2, len(m.authors) * 6 + 40, len(m.contrib) * 10.5) + 8


def _label_box(x, y, v_side, h_side, level, w):
    """Geometry for one corner placement.

    Returns (bbox, ty, tx, anchor) where bbox = (left, top, w, LABEL_H).
    v_side: -1 above / +1 below. h_side: +1 extends right / -1 extends left.
    """
    ty = y + v_side * (V_OFFSET + level * V_STEP)
    if h_side > 0:                                  # extends right, anchor start
        tx, left, anchor = x + H_GAP, x + H_GAP - KNOCK_PAD, "start"
    else:                                           # extends left, anchor end
        tx, left, anchor = x - H_GAP, x - H_GAP - w, "end"
    return (left, ty - 12, w, LABEL_H), ty, tx, anchor


def _boxes_overlap(a, b, margin=COLLIDE_MARGIN):
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    return not (ax + aw + margin <= bx or bx + bw + margin <= ax or
                ay + ah + margin <= by or by + bh + margin <= ay)


def _in_canvas(box, height):
    bx, by, bw, bh = box
    return bx >= 4 and by >= 4 and bx + bw <= W - 4 and by + bh <= height - 4


def _place_labels(groups, height):
    """Greedy collision-aware corner placement.

    Each member is placed at one of the node's four corners (top/bottom ×
    left/right); the first corner whose box is on-canvas and overlaps no
    already-placed box (labels, node dots, reserved chrome zones) wins. If all
    four corners collide, push the label outward one level and retry. Mutates
    each group with a ``placements`` list (one dict per member).
    """
    # reserved zones every label must avoid
    placed = [
        (W - PAD["r"] + 2, 0, PAD["r"], height),     # right margin: arrows + branch labels
        (0, height - 88, W, 88),                     # bottom band: era labels + footer
    ]
    for g in groups:                                 # node dots
        placed.append((g["x"] - 7, g["y"] - 7, 14, 14))

    # place left-to-right, top-to-bottom so earlier nodes anchor the layout
    order = sorted(range(len(groups)), key=lambda i: (groups[i]["x"], groups[i]["y"]))
    for gi in order:
        g = groups[gi]
        x, y = g["x"], g["y"]
        prim = -1 if g["_gyi"] % 2 == 0 else 1       # primary vertical side (alternates per lane)
        out = []
        for m in g["members"]:
            w = _label_w(m)
            pick = None
            for level in range(MAX_LEVEL + 1):
                for v_side in (prim, -prim):
                    for h_side in (1, -1):           # right before left
                        box, ty, tx, anchor = _label_box(x, y, v_side, h_side, level, w)
                        if not _in_canvas(box, height):
                            continue
                        if any(_boxes_overlap(box, p) for p in placed):
                            continue
                        pick = (box, ty, tx, anchor)
                        break
                    if pick:
                        break
                if pick:
                    break
            if pick is None:                         # dense fallback: accept the primary corner
                box, ty, tx, anchor = _label_box(x, y, prim, 1, 0, w)
            else:
                box, ty, tx, anchor = pick
            placed.append(box)
            out.append({"tx": tx, "ty": ty, "anchor": anchor, "bbox": box})
        g["placements"] = out
    return groups


def compute_layout(graph):
    milestones = graph.milestones
    years = [m.year for m in milestones if m.year]
    gap = largest_gap(years)
    xs = _build_xs(years, gap)

    # dynamic canvas height so the lanes (and their corner labels) have room
    n_lanes = len({m.branch for m in milestones if m.branch != FOUND})
    height = _canvas_height(n_lanes)
    base_y = (PAD["t"] + (height - PAD["b"])) / 2
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

    # group nodes; assign each group its year-index within its lane (drives the
    # primary corner side), then place all member labels with collision avoidance
    grouped = group_by_branch_year(milestones)
    lane_year_order = defaultdict(list)
    for (branch, year) in grouped:
        lane_year_order[branch].append(year)
    for branch in lane_year_order:
        lane_year_order[branch] = sorted(set(lane_year_order[branch]))

    groups = []
    for (branch, year), members in grouped.items():
        groups.append({
            "branch": branch,
            "year": year,
            "x": xs[year],
            "y": lane_y.get(branch, base_y),
            "members": members,
            "_gyi": lane_year_order[branch].index(year),
        })
    _place_labels(groups, height)

    return {
        "W": W, "H": height, "PAD": PAD,
        "base_y": base_y,
        "fork_x": fork_x,
        "elbow_end": elbow_end,
        "xs": xs,
        "lane_y": lane_y,
        "gap": (gap[0], gap[1], (xs[gap[0]] + xs[gap[1]]) / 2) if gap else None,
        "years": sorted(set(years)),
        "groups": groups,
    }
