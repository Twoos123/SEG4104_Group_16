"""Draw the report figures that are computed from the plan data:
network diagram (AON), Level-0 DFD, risk severity matrix and the time-phased budget baseline.

Run:  python docs/diagrams/draw.py   (after sim/monte_carlo.py)
"""

import json
import sys
import textwrap
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.patches import FancyBboxPatch, Rectangle  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from sim import plan  # noqa: E402

FIGS = ROOT / "docs" / "figures"
INK, MUTED, GRID, BLUE, RED = "#16202b", "#5b6876", "#c9d2dc", "#2a78d6", "#b3261e"
SIM = json.loads((ROOT / "docs" / "sim_results.json").read_text())


def num(x: float) -> str:
    return f"{x:g}"


# ------------------------------------------------------------------ network diagram
POS = {  # activity -> (band, column, row)
    "A": (0, 0, 1),
    "B": (0, 1, 0),
    "C": (0, 1, 1),
    "D": (0, 2, 1),
    "H": (0, 2, 2),
    "F": (0, 2, 3),
    "G": (0, 2, 4),
    "E": (0, 3, 1),
    "I": (0, 3, 3),
    "J": (0, 4, 1),
    "K": (1, 0, 0),
    "L": (1, 1, 0),
    "N": (1, 1, 1),
    "M": (1, 2, 0),
    "O": (1, 3, 0),
    "P": (1, 4, 0),
}
CW, RH, BW, BH = 1.62, 1.12, 1.34, 0.84
BAND_Y = {0: 8.75, 1: 2.55}


def centre(a):
    band, col, row = POS[a]
    return 1.1 + col * CW, BAND_Y[band] - row * RH


def node(ax, a, crit):
    x, y = centre(a)
    t = SIM["cpm"]["table"][a]
    name, _, (_, m, _), *_ = plan.ACTIVITIES[a]
    edge = RED if crit else INK
    x0, y0 = x - BW / 2, y - BH / 2
    ax.add_patch(
        Rectangle(
            (x0, y0),
            BW,
            BH,
            facecolor="#fdecea" if crit else "white",
            edgecolor=edge,
            linewidth=1.6 if crit else 1.0,
            zorder=3,
        )
    )
    third = BH / 3
    for k in (1, 2):
        ax.plot([x0, x0 + BW], [y0 + k * third] * 2, color=edge, linewidth=0.6, zorder=4)
    side = 0.3
    for xs in (x0 + side, x0 + BW - side):
        ax.plot([xs, xs], [y0 + 2 * third, y0 + BH], color=edge, linewidth=0.6, zorder=4)
        ax.plot([xs, xs], [y0, y0 + third], color=edge, linewidth=0.6, zorder=4)
    ax.plot([x0 + side] * 2, [y0 + third, y0 + 2 * third], color=edge, linewidth=0.6, zorder=4)

    def put(px, py, s, **kw):
        ax.text(px, py, s, ha="center", va="center", fontsize=7.6, color=INK, zorder=5, **kw)

    top, mid, bot = y0 + 2.5 * third, y0 + 1.5 * third, y0 + 0.5 * third
    put(x0 + side / 2, top, num(t["es"]))
    put(x, top, a, fontweight="bold")
    put(x0 + BW - side / 2, top, num(t["ef"]))
    put(x0 + side / 2, mid, num(t["slack"]))
    ax.text(
        x0 + side + (BW - side) / 2,
        mid,
        "\n".join(textwrap.wrap(name, 19)[:2]),
        ha="center",
        va="center",
        fontsize=6.3,
        color=INK,
        zorder=5,
        linespacing=0.95,
    )
    put(x0 + side / 2, bot, num(t["ls"]))
    put(x, bot, num(m))
    put(x0 + BW - side / 2, bot, num(t["lf"]))


def edge(ax, a, b, crit):
    (x1, y1), (x2, y2) = centre(a), centre(b)
    colour, lw = (RED, 1.8) if crit else (MUTED, 1.0)
    start, end = (x1 + BW / 2, y1), (x2 - BW / 2, y2)
    if POS[a][0] != POS[b][0]:  # wrap from the top band to the bottom band
        lane = BAND_Y[1] + 0.95
        pts = [
            start,
            (start[0] + 0.14, y1),
            (start[0] + 0.14, lane),
            (end[0] - 0.2, lane),
            (end[0] - 0.2, y2),
            end,
        ]
    elif abs(y1 - y2) < 1e-9:
        pts = [start, end]
    else:
        turn = end[0] - (CW - BW) / 2
        pts = [start, (turn, y1), (turn, y2), end]
    xs, ys = zip(*pts[:-1], strict=True)
    ax.plot(xs, ys, color=colour, linewidth=lw, zorder=2, solid_joinstyle="round")
    ax.annotate(
        "",
        xy=pts[-1],
        xytext=pts[-2],
        zorder=2,
        arrowprops={"arrowstyle": "-|>", "color": colour, "lw": lw, "shrinkA": 0, "shrinkB": 0},
    )


def network():
    crit = set(SIM["cpm"]["critical_path"])
    fig, ax = plt.subplots(figsize=(8.7, 9.3), dpi=220)
    for b, (_, preds, *_rest) in plan.ACTIVITIES.items():
        for a in preds:
            edge(ax, a, b, a in crit and b in crit)
    for a in plan.ACTIVITIES:
        node(ax, a, a in crit)
    # legend node
    lx, ly = 0.3, 0.55
    ax.add_patch(Rectangle((lx, ly - 0.42), 1.5, 0.84, facecolor="white", edgecolor=INK, linewidth=1.0))
    for k in (1, 2):
        ax.plot([lx, lx + 1.5], [ly - 0.42 + k * 0.28] * 2, color=INK, linewidth=0.6)
    for xs in (lx + 0.36, lx + 1.14):
        ax.plot([xs, xs], [ly + 0.14, ly + 0.42], color=INK, linewidth=0.6)
        ax.plot([xs, xs], [ly - 0.42, ly - 0.14], color=INK, linewidth=0.6)
    ax.plot([lx + 0.36] * 2, [ly - 0.14, ly + 0.14], color=INK, linewidth=0.6)
    for px, py, s in [
        (lx + 0.18, ly + 0.28, "ES"),
        (lx + 0.75, ly + 0.28, "ID"),
        (lx + 1.32, ly + 0.28, "EF"),
        (lx + 0.18, ly, "SL"),
        (lx + 0.93, ly, "Description"),
        (lx + 0.18, ly - 0.28, "LS"),
        (lx + 0.75, ly - 0.28, "DUR"),
        (lx + 1.32, ly - 0.28, "LF"),
    ]:
        ax.text(px, py, s, ha="center", va="center", fontsize=6.6, color=INK)
    ax.text(
        2.0,
        0.76,
        "ES/EF = early start/finish, LS/LF = late start/finish, SL = slack, DUR = duration. "
        "All values in weeks.",
        fontsize=7.4,
        color=INK,
        va="center",
    )
    ax.plot([2.0, 2.5], [0.4, 0.4], color=RED, linewidth=1.8)
    ax.text(
        2.6,
        0.4,
        f"Critical path (zero slack): {' - '.join(SIM['cpm']['critical_path'])} = "
        f"{num(SIM['cpm']['duration_weeks'])} weeks",
        fontsize=7.4,
        color=INK,
        va="center",
    )
    ax.set_xlim(0, 8.7)
    ax.set_ylim(0, 9.3)
    ax.axis("off")
    fig.subplots_adjust(0, 0, 1, 1)
    fig.savefig(FIGS / "network.png")
    plt.close(fig)


# ------------------------------------------------------------------ context DFD
def dfd_context():
    fig, ax = plt.subplots(figsize=(9, 6.6), dpi=220)

    def entity(x, y, label, w=1.9, h=0.62):
        ax.add_patch(Rectangle((x - w / 2, y - h / 2), w, h, facecolor="white", edgecolor=INK, linewidth=1.3))
        ax.text(x, y, label, ha="center", va="center", fontsize=9.5, fontweight="bold", color=INK)

    def flow(p1, p2, label, lx, ly, ha="center"):
        ax.annotate(
            "",
            xy=p2,
            xytext=p1,
            arrowprops={"arrowstyle": "-|>", "color": "#444", "lw": 1.1, "shrinkA": 0, "shrinkB": 0},
        )
        ax.text(lx, ly, label, ha=ha, va="center", fontsize=8.2, color=INK)

    cx, w, top, bot = 5.0, 1.9, 5.5, 1.3
    ax.add_patch(
        FancyBboxPatch(
            (cx - w / 2, bot),
            w,
            top - bot,
            boxstyle="round,pad=0,rounding_size=0.3",
            facecolor="#e3eefb",
            edgecolor=BLUE,
            linewidth=1.8,
        )
    )
    ax.plot([cx - w / 2, cx + w / 2], [top - 0.5] * 2, color=BLUE, linewidth=1.1)
    ax.text(cx, top - 0.25, "0", ha="center", va="center", fontsize=9, color=MUTED)
    ax.text(cx, 3.45, "SmartIntake", ha="center", va="center", fontsize=12, fontweight="bold", color=INK)
    ax.text(cx, 3.15, "System", ha="center", va="center", fontsize=10, color=INK)
    left, right = cx - w / 2, cx + w / 2
    for x, y, name, inflow, outflow in [
        (1.15, 4.3, "Resident", "Service request", "Confirmation, status"),
        (1.15, 2.3, "311 Agent", "Entries, corrections", "Low-confidence queue"),
        (8.85, 4.3, "Work Mgmt System", "Work order status", "Work order"),
        (8.85, 2.3, "GIS Service", "Coordinates, ward", "Location query"),
    ]:
        entity(x, y, name)
        if x < cx:
            flow((x + 0.95, y + 0.13), (left, y + 0.13), inflow, (x + 0.95 + left) / 2, y + 0.3)
            flow((left, y - 0.13), (x + 0.95, y - 0.13), outflow, (x + 0.95 + left) / 2, y - 0.3)
        else:
            flow((right, y + 0.13), (x - 0.95, y + 0.13), outflow, (x - 0.95 + right) / 2, y + 0.3)
            flow((x - 0.95, y - 0.13), (right, y - 0.13), inflow, (x - 0.95 + right) / 2, y - 0.3)
    entity(cx, 6.45, "LLM Provider")
    flow((cx - 0.3, top), (cx - 0.3, 6.14), "Redacted text", cx - 0.42, 5.82, "right")
    flow((cx + 0.3, 6.14), (cx + 0.3, top), "Category, confidence", cx + 0.42, 5.82, "left")
    entity(cx, 0.35, "Ops Supervisor")
    flow((cx - 0.3, 0.66), (cx - 0.3, bot), "Routing rules", cx - 0.42, 0.98, "right")
    flow((cx + 0.3, bot), (cx + 0.3, 0.66), "KPI dashboard", cx + 0.42, 0.98, "left")
    ax.set_xlim(0, 10)
    ax.set_ylim(-0.1, 6.9)
    ax.axis("off")
    fig.subplots_adjust(0, 0, 1, 1)
    fig.savefig(FIGS / "dfd_context.png")
    plt.close(fig)


# ------------------------------------------------------------------ Level-0 DFD
def dfd_level0():
    fig, ax = plt.subplots(figsize=(11, 7.6), dpi=220)
    centres = {}

    def entity(key, x, y, label, w=1.7, h=0.6):
        ax.add_patch(
            Rectangle((x - w / 2, y - h / 2), w, h, facecolor="white", edgecolor=INK, linewidth=1.3, zorder=3)
        )
        ax.text(x, y, label, ha="center", va="center", fontsize=9, fontweight="bold", color=INK, zorder=4)
        centres[key] = (x, y, w, h)

    def process(key, x, y, number, label, w=1.9, h=1.0):
        ax.add_patch(
            FancyBboxPatch(
                (x - w / 2, y - h / 2),
                w,
                h,
                boxstyle="round,pad=0,rounding_size=0.18",
                facecolor="#e3eefb",
                edgecolor=BLUE,
                linewidth=1.6,
                zorder=3,
            )
        )
        ax.plot([x - w / 2, x + w / 2], [y + h / 2 - 0.28] * 2, color=BLUE, linewidth=1.0, zorder=4)
        ax.text(x, y + h / 2 - 0.15, number, ha="center", va="center", fontsize=8, color=MUTED, zorder=4)
        ax.text(
            x, y - 0.14, label, ha="center", va="center", fontsize=8.8, fontweight="bold", color=INK, zorder=4
        )
        centres[key] = (x, y, w, h)

    def store(key, x, y, number, label, w=2.0, h=0.5):
        x0, y0 = x - w / 2, y - h / 2
        ax.add_patch(Rectangle((x0, y0), w, h, facecolor="#f4f6f9", edgecolor="none", zorder=3))
        for yy in (y0, y0 + h):
            ax.plot([x0, x0 + w], [yy, yy], color=INK, linewidth=1.3, zorder=4)
        ax.plot([x0, x0], [y0, y0 + h], color=INK, linewidth=1.3, zorder=4)
        ax.plot([x0 + 0.42] * 2, [y0, y0 + h], color=INK, linewidth=1.0, zorder=4)
        ax.text(x0 + 0.21, y, number, ha="center", va="center", fontsize=8, color=MUTED, zorder=5)
        ax.text(
            x0 + 0.42 + (w - 0.42) / 2, y, label, ha="center", va="center", fontsize=8.6, color=INK, zorder=5
        )
        centres[key] = (x, y, w, h)

    def flow(p1, p2, label, lx=None, ly=None, ha="center", via=None):
        pts = [p1, *(via or []), p2]
        xs, ys = zip(*pts[:-1], strict=True)
        ax.plot(xs, ys, color="#444", linewidth=1.0, zorder=2)
        ax.annotate(
            "",
            xy=pts[-1],
            xytext=pts[-2],
            zorder=2,
            arrowprops={"arrowstyle": "-|>", "color": "#444", "lw": 1.0, "shrinkA": 0, "shrinkB": 0},
        )
        if lx is None:
            lx, ly = (p1[0] + p2[0]) / 2, (p1[1] + p2[1]) / 2
        ax.text(
            lx,
            ly,
            label,
            ha=ha,
            va="center",
            fontsize=7.4,
            color=INK,
            zorder=6,
            linespacing=0.95,
            bbox={"facecolor": "white", "edgecolor": "none", "pad": 1.2},
        )

    ye, yp, ys_, yq, yb = 7.0, 5.2, 3.3, 1.5, 0.0
    x1, x2, x3, x4 = 1.5, 4.9, 8.3, 11.6
    xs1, xs2, xs3 = 3.2, 6.6, 10.2
    entity("res", x1, ye, "Resident")
    entity("llm", x2, ye, "LLM Provider")
    entity("gis", x3, ye, "GIS Service")
    entity("wms", x4, ye, "Work Mgmt System")
    process("p1", x1, yp, "1.0", "Receive &\nredact request")
    process("p2", x2, yp, "2.0", "Classify\nrequest")
    process("p3", x3, yp, "3.0", "Locate & check\nduplicates")
    process("p4", x4, yp, "4.0", "Route & track\nwork orders")
    store("d1", xs1, ys_, "D1", "Service requests")
    store("d2", xs2, ys_, "D2", "Routing rules")
    store("d3", xs3, ys_, "D3", "Work orders")
    process("p5", xs1, yq, "5.0", "Review flagged\nrequests")
    process("p7", xs2, yq, "7.0", "Monitor &\nconfigure")
    process("p6", xs3, yq, "6.0", "Notify\nresident")
    entity("agent", xs1, yb, "311 Agent")
    entity("sup", xs2, yb, "Ops Supervisor")
    entity("res2", xs3, yb, "Resident")
    ax.plot([xs3 - 0.85, xs3 - 0.65], [yb - 0.1, yb + 0.3], color=INK, linewidth=1.0, zorder=5)
    ax.plot([x1 - 0.85, x1 - 0.65], [ye - 0.1, ye + 0.3], color=INK, linewidth=1.0, zorder=5)

    pt, pb, eb, st, sb = yp + 0.5, yp - 0.5, ye - 0.3, ys_ + 0.25, ys_ - 0.25
    qt, qb, bt = yq + 0.5, yq - 0.5, yb + 0.3
    # entity <-> top-row processes
    flow((x1, eb), (x1, pt), "Service\nrequest", x1 + 0.1, 6.2, "left")
    flow((x2 - 0.3, pt), (x2 - 0.3, eb), "Redacted\ntext", x2 - 0.4, 6.2, "right")
    flow((x2 + 0.3, eb), (x2 + 0.3, pt), "Category,\nconfidence", x2 + 0.4, 6.2, "left")
    flow((x3 - 0.3, pt), (x3 - 0.3, eb), "Address\nquery", x3 - 0.4, 6.2, "right")
    flow((x3 + 0.3, eb), (x3 + 0.3, pt), "Coordinates,\nward", x3 + 0.4, 6.2, "left")
    flow((x4 - 0.3, pt), (x4 - 0.3, eb), "New work\norder", x4 - 0.4, 6.2, "right")
    flow((x4 + 0.3, eb), (x4 + 0.3, pt), "Work order\nstatus", x4 + 0.4, 6.2, "left")
    # main chain
    flow((x1 + 0.95, yp), (x2 - 0.95, yp), "Redacted\nrequest")
    flow((x2 + 0.95, yp), (x3 - 0.95, yp), "Classified\nrequest")
    flow((x3 + 0.95, yp), (x4 - 0.95, yp), "Located\nrequest")
    # stores
    flow((x1 + 0.4, pb), (xs1 - 0.6, st), "Request\nrecord", 1.75, 4.05, "right")
    flow((x2 - 0.5, pb), (xs1 + 0.6, st), "Category,\nreview flag", 4.6, 4.15, "left")
    flow((xs1 + 1.0, ys_ + 0.1), (x3 - 0.8, pb), "Agent-confirmed requests", 6.05, 4.42)
    flow((xs2 - 0.55, st), (x2 + 0.6, pb), "Confidence\nthreshold", 6.2, 3.74, "left")
    flow((xs2 + 0.6, st), (x3 - 0.45, pb), "Duplicate\nradius", 7.5, 3.95, "left")
    flow((xs3 - 0.6, st), (x3 + 0.5, pb), "Open work\norders nearby", 9.3, 4.3, "right")
    flow((x4 - 0.1, pb), (xs3 + 0.6, st), "Work order\nrecord", 11.2, 4.1, "left")
    # second row
    flow((xs1 - 0.35, sb), (xs1 - 0.35, qt), "Flagged\nrequests", xs1 - 0.45, 2.5, "right")
    flow((xs1 + 0.35, qt), (xs1 + 0.35, sb), "Corrected\ncategory", xs1 + 0.45, 2.5, "left")
    flow((xs1 - 0.35, qb), (xs1 - 0.35, bt), "Review\nqueue", xs1 - 0.45, 0.65, "right")
    flow((xs1 + 0.35, bt), (xs1 + 0.35, qb), "Corrections", xs1 + 0.45, 0.65, "left")
    flow((xs2, qt), (xs2, sb), "Routing\nrules", xs2 + 0.1, 2.5, "left")
    flow((xs1 + 0.8, sb), (xs2 - 0.75, qt), "Request\ndata", 4.75, 2.42, "right")
    flow((xs3 - 0.8, sb), (xs2 + 0.75, qt), "Work order\ndata", 8.75, 2.42, "left")
    flow((xs2 - 0.35, bt), (xs2 - 0.35, qb), "Rule\nchanges", xs2 - 0.45, 0.65, "right")
    flow((xs2 + 0.35, qb), (xs2 + 0.35, bt), "KPI\ndashboard", xs2 + 0.45, 0.65, "left")
    flow((xs3, sb), (xs3, qt), "Status\nchanges", xs3 + 0.1, 2.5, "left")
    flow((xs3, qb), (xs3, bt), "Confirmation,\nstatus updates", xs3 + 0.1, 0.65, "left")
    # agent keys in phone requests
    flow((xs1 - 0.85, yb), (0.85, pb), "Phone request\nentry", 0.95, 2.4, "left", via=[(0.85, yb)])

    ax.set_xlim(0, 12.9)
    ax.set_ylim(-0.5, 7.5)
    ax.axis("off")
    fig.subplots_adjust(0, 0, 1, 1)
    fig.savefig(FIGS / "dfd_level0.png")
    plt.close(fig)


# ------------------------------------------------------------------ risk severity matrix
def severity_matrix():
    fig, ax = plt.subplots(figsize=(7.2, 4.9), dpi=220)
    cells = {}
    for rid, r in plan.RISKS.items():
        cells.setdefault((plan.probability_score(r[2]), r[4]), []).append(rid)
    for p in range(1, 6):
        for i in range(1, 6):
            score = p * i
            colour = "#f6c9c4" if score >= 15 else "#fbe3b4" if score >= 8 else "#d5ecd9"
            ax.add_patch(
                Rectangle((i - 0.5, p - 0.5), 1, 1, facecolor=colour, edgecolor="white", linewidth=2)
            )
            ax.text(i + 0.42, p - 0.4, str(score), ha="right", va="bottom", fontsize=7, color=MUTED)
            if (p, i) in cells:
                ax.text(
                    i,
                    p + 0.03,
                    "  ".join(cells[(p, i)]),
                    ha="center",
                    va="center",
                    fontsize=10.5,
                    fontweight="bold",
                    color=INK,
                )
    ax.set_xticks(
        range(1, 6), ["1\nNegligible", "2\nMinor", "3\nModerate", "4\nMajor", "5\nSevere"], fontsize=8.5
    )
    ax.set_yticks(
        range(1, 6),
        [
            "1  Rare (10% or less)",
            "2  Unlikely (11-20%)",
            "3  Possible (21-35%)",
            "4  Likely (36-50%)",
            "5  Almost certain (over 50%)",
        ],
        fontsize=8.5,
    )
    ax.set_xlabel("Impact", color=INK, fontsize=9.5, fontweight="bold")
    ax.set_ylabel("Probability", color=INK, fontsize=9.5, fontweight="bold")
    ax.set_xlim(0.5, 5.5)
    ax.set_ylim(0.5, 5.5)
    ax.tick_params(length=0, colors=INK)
    for s in ax.spines.values():
        s.set_visible(False)
    for colour, label, x in (
        ("#d5ecd9", "Low (1-7): accept and monitor", 0.24),
        ("#fbe3b4", "Medium (8-14): mitigate", 0.52),
        ("#f6c9c4", "High (15-25): act now", 0.76),
    ):
        fig.patches.append(
            Rectangle((x + 0.02, 0.025), 0.018, 0.026, transform=fig.transFigure, facecolor=colour)
        )
        fig.text(x + 0.045, 0.038, label, fontsize=7.8, color=INK, va="center")
    fig.subplots_adjust(left=0.27, right=0.98, top=0.97, bottom=0.24)
    fig.savefig(FIGS / "severity_matrix.png")
    plt.close(fig)


# ------------------------------------------------------------------ time-phased budget baseline
def weekly_baseline() -> list[float]:
    """Planned cost per week (early-start schedule), including contingency spread in proportion."""
    weeks = int(SIM["cpm"]["duration_weeks"])
    spend = [0.0] * weeks
    for a, (_, _, (_, m, _), labour, other) in plan.ACTIVITIES.items():
        start = int(SIM["cpm"]["table"][a]["es"])
        for w in range(start, start + m):
            spend[w] += (labour + other) / m
    for w in range(5, weeks):
        spend[w] += plan.CLOUD_BUILD / (weeks - 5)
    spend[24] += plan.CLOUD_OPERATIONS  # committed at go-live
    estimate = sum(spend)
    return [s * (1 + plan.CONTINGENCY_RESERVE / estimate) for s in spend]


def budget_curve():
    spend = weekly_baseline()
    cumulative = [sum(spend[: i + 1]) for i in range(len(spend))]
    weeks = list(range(1, len(spend) + 1))
    fig, ax = plt.subplots(figsize=(8, 3.9), dpi=220)
    ax.plot([0, *weeks], [0, *cumulative], color=BLUE, linewidth=2)
    ax.axhline(SIM["cost"]["budget"], color=RED, linewidth=1.2, linestyle="--")
    ax.text(
        0.3,
        SIM["cost"]["budget"] + 8,
        f"Total budget ${SIM['cost']['budget']}k (baseline + management reserve)",
        color=RED,
        fontsize=8.5,
    )
    ax.text(26.2, cumulative[-1], f"${cumulative[-1]:.0f}k", color=INK, fontsize=9, va="center")
    for wk in (5, 13, 20):
        ax.plot([wk], [cumulative[wk - 1]], "o", color=BLUE, markersize=5, markeredgecolor="white")
        ax.text(
            wk + 0.4, cumulative[wk - 1] - 16, f"Wk {wk}: ${cumulative[wk - 1]:.0f}k", fontsize=8.5, color=INK
        )
    ax.set_xlim(0, 28.5)
    ax.set_ylim(0, 560)
    ax.set_xlabel("Project week", color=MUTED)
    ax.set_ylabel("Cumulative planned cost ($k)", color=MUTED)
    ax.set_title(
        "Cost baseline (planned value): cumulative spend reaches $480k at week 26",
        loc="left",
        color=INK,
        fontsize=11,
        fontweight="bold",
    )
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color(GRID)
    ax.tick_params(colors=MUTED, length=0)
    ax.grid(axis="y", color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)
    fig.tight_layout()
    fig.savefig(FIGS / "budget_baseline.png")
    plt.close(fig)
    (ROOT / "docs" / "budget_baseline.json").write_text(
        json.dumps({"weekly": [round(s, 1) for s in spend], "cumulative": [round(c, 1) for c in cumulative]})
    )


if __name__ == "__main__":
    network()
    dfd_context()
    dfd_level0()
    severity_matrix()
    budget_curve()
    print("figures written to", FIGS)
