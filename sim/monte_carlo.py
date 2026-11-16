"""Critical path (CPM), PERT and Monte Carlo schedule/cost risk simulation for SmartIntake.

Open-source stack (NumPy + Matplotlib) in place of Crystal Ball or Primavera Risk Analysis.
Run:  python sim/monte_carlo.py     ->  docs/sim_results.json and charts in docs/figures/
"""

import json
import sys
from pathlib import Path

import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from sim import plan  # noqa: E402

DOCS = Path(__file__).resolve().parent.parent / "docs"
FIGS = DOCS / "figures"
BLUE, INK, MUTED, GRID, RED = "#2a78d6", "#16202b", "#5b6876", "#d7dee6", "#b3261e"


def forward_backward(durations: dict[str, float]) -> dict:
    """Classic CPM forward and backward pass. Activities are already in topological order."""
    es, ef = {}, {}
    for a, (_, preds, *_rest) in plan.ACTIVITIES.items():
        es[a] = max((ef[p] for p in preds), default=0.0)
        ef[a] = es[a] + durations[a]
    finish = max(ef.values())
    succs = {a: [b for b, v in plan.ACTIVITIES.items() if a in v[1]] for a in plan.ACTIVITIES}
    ls, lf = {}, {}
    for a in reversed(list(plan.ACTIVITIES)):
        lf[a] = min((ls[s] for s in succs[a]), default=finish)
        ls[a] = lf[a] - durations[a]
    return {
        "es": es,
        "ef": ef,
        "ls": ls,
        "lf": lf,
        "finish": finish,
        "slack": {a: round(ls[a] - es[a], 6) for a in es},
    }


def beta_pert(rng, a, m, b, size):
    """Beta-PERT sample: a smooth distribution with mean (a + 4m + b) / 6."""
    if a == b:
        return np.full(size, float(a))
    alpha = 1 + 4 * (m - a) / (b - a)
    beta = 1 + 4 * (b - m) / (b - a)
    return a + rng.beta(alpha, beta, size) * (b - a)


def simulate(n: int = 10_000, seed: int = 4105) -> dict:
    rng = np.random.default_rng(seed)
    ids = list(plan.ACTIVITIES)
    dur = {a: beta_pert(rng, *plan.ACTIVITIES[a][2], n) for a in ids}
    risk_cost = np.zeros(n)
    fired = {}
    for rid, (_, _, p, cost, _, act, delay, *_rest) in plan.RISKS.items():
        hit = rng.random(n) < p
        fired[rid] = hit
        # A risk that delays an activity already costs extra labour below, so only half of its
        # stated cost impact is charged directly; the rest arrives through the longer duration.
        direct = 0.5 * cost if act else cost
        risk_cost += hit * rng.triangular(0.5 * direct, direct, 1.5 * direct, n)
        if act:
            dur[act] = dur[act] + hit * rng.uniform(delay[0], delay[1], n)

    es, ef = {}, {}
    for a in ids:
        preds = plan.ACTIVITIES[a][1]
        es[a] = np.max([ef[p] for p in preds], axis=0) if preds else np.zeros(n)
        ef[a] = es[a] + dur[a]
    finish = np.max([ef[a] for a in ids], axis=0)

    # Criticality index: share of runs in which the activity sits on the longest path
    succs = {a: [b for b in ids if a in plan.ACTIVITIES[b][1]] for a in ids}
    lf, ls = {}, {}
    for a in reversed(ids):
        lf[a] = np.min([ls[s] for s in succs[a]], axis=0) if succs[a] else finish
        ls[a] = lf[a] - dur[a]
    criticality = {a: float(np.mean(np.abs(ls[a] - es[a]) < 1e-9)) for a in ids}

    # Cost: half of each work package's labour scales with how long it actually takes
    labour = sum(plan.ACTIVITIES[a][3] * (0.5 + 0.5 * dur[a] / plan.ACTIVITIES[a][2][1]) for a in ids)
    fixed = sum(v[4] for v in plan.ACTIVITIES.values()) + plan.CLOUD_BUILD + plan.CLOUD_OPERATIONS
    cost = labour + fixed + risk_cost
    return {"finish": finish, "cost": cost, "criticality": criticality, "risk_cost": risk_cost}


def pct(x, q):
    return round(float(np.percentile(x, q)), 1)


def style(ax):
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color(GRID)
    ax.tick_params(colors=MUTED, length=0)
    ax.grid(axis="y", color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)


def histogram(values, lines, xlabel, title, path, bins):
    fig, ax = plt.subplots(figsize=(8, 3.8), dpi=200)
    ax.hist(values, bins=bins, color=BLUE, edgecolor="white", linewidth=0.6)
    top = ax.get_ylim()[1]
    for i, (x, label, color) in enumerate(lines):
        ax.axvline(x, color=color, linewidth=1.6, linestyle="--")
        ax.text(x, top * (1.0 - 0.09 * i), f" {label}", color=color, fontsize=9, va="top", ha="left")
    ax.set_xlabel(xlabel, color=MUTED)
    ax.set_ylabel("Simulation runs", color=MUTED)
    ax.set_title(title, loc="left", color=INK, fontsize=11, fontweight="bold")
    style(ax)
    fig.tight_layout()
    fig.savefig(path)
    plt.close(fig)


def main() -> dict:
    FIGS.mkdir(parents=True, exist_ok=True)
    ids = list(plan.ACTIVITIES)
    likely = forward_backward({a: plan.ACTIVITIES[a][2][1] for a in ids})
    te = {a: (v[2][0] + 4 * v[2][1] + v[2][2]) / 6 for a, v in plan.ACTIVITIES.items()}
    var = {a: ((v[2][2] - v[2][0]) / 6) ** 2 for a, v in plan.ACTIVITIES.items()}
    pert = forward_backward(te)
    critical = [a for a in ids if abs(likely["slack"][a]) < 1e-9]
    pert_critical = [a for a in ids if abs(pert["slack"][a]) < 1e-9]
    pert_sd = sum(var[a] for a in pert_critical) ** 0.5

    sim = simulate()
    finish, cost = sim["finish"], sim["cost"]
    estimate = sum(v[3] + v[4] for v in plan.ACTIVITIES.values()) + plan.CLOUD_BUILD + plan.CLOUD_OPERATIONS
    baseline = estimate + plan.CONTINGENCY_RESERVE
    budget = baseline + plan.MANAGEMENT_RESERVE
    emv = {rid: round(r[2] * r[3], 2) for rid, r in plan.RISKS.items()}

    result = {
        "runs": int(len(finish)),
        "cpm": {
            "duration_weeks": likely["finish"],
            "critical_path": critical,
            "table": {
                a: {
                    "es": likely["es"][a],
                    "ef": likely["ef"][a],
                    "ls": likely["ls"][a],
                    "lf": likely["lf"][a],
                    "slack": likely["slack"][a],
                }
                for a in ids
            },
        },
        "pert": {
            "expected_weeks": round(pert["finish"], 2),
            "sd_weeks": round(pert_sd, 2),
            "critical_path": pert_critical,
            "te": {a: round(te[a], 2) for a in ids},
            "variance": {a: round(var[a], 3) for a in ids},
        },
        "schedule": {
            "mean": round(float(finish.mean()), 1),
            "p10": pct(finish, 10),
            "p50": pct(finish, 50),
            "p80": pct(finish, 80),
            "p90": pct(finish, 90),
            "prob_within_committed": round(float((finish <= plan.COMMITTED_WEEKS).mean()), 3),
            "prob_within_tolerated": round(float((finish <= plan.TOLERATED_WEEKS).mean()), 3),
        },
        "cost": {
            "estimate": estimate,
            "baseline": baseline,
            "budget": budget,
            "mean": round(float(cost.mean()), 1),
            "p50": pct(cost, 50),
            "p80": pct(cost, 80),
            "p90": pct(cost, 90),
            "prob_within_estimate": round(float((cost <= estimate).mean()), 3),
            "prob_within_baseline": round(float((cost <= baseline).mean()), 3),
            "prob_within_budget": round(float((cost <= budget).mean()), 3),
        },
        "criticality_index": {a: round(c, 3) for a, c in sim["criticality"].items()},
        "emv": emv,
        "emv_total": round(sum(emv.values()), 2),
    }
    (DOCS / "sim_results.json").write_text(json.dumps(result, indent=2))

    s = result["schedule"]
    histogram(
        finish,
        [
            (plan.COMMITTED_WEEKS, f"Committed: {plan.COMMITTED_WEEKS} wk", RED),
            (s["p80"], f"P80: {s['p80']} wk", INK),
        ],
        "Project duration (weeks)",
        f"Only {s['prob_within_committed']:.0%} of runs finish within 26 weeks; "
        f"{s['prob_within_tolerated']:.0%} finish within 30",
        FIGS / "mc_schedule.png",
        bins=np.arange(np.floor(finish.min()), np.ceil(finish.max()) + 0.5, 0.5),
    )
    c = result["cost"]
    histogram(
        cost,
        [(baseline, f"Cost baseline: ${baseline}k", INK), (budget, f"Budget: ${budget}k", RED)],
        "Total project cost ($ thousands CAD)",
        f"{c['prob_within_baseline']:.0%} of runs stay within the cost baseline; "
        f"{c['prob_within_budget']:.0%} within the total budget",
        FIGS / "mc_cost.png",
        bins=40,
    )

    order = sorted(ids, key=lambda a: sim["criticality"][a])
    fig, ax = plt.subplots(figsize=(8, 4.6), dpi=200)
    vals = [sim["criticality"][a] * 100 for a in order]
    ax.barh([f"{a}  {plan.ACTIVITIES[a][0]}" for a in order], vals, color=BLUE, height=0.62)
    for y, v in enumerate(vals):
        ax.text(v + 1.2, y, f"{v:.0f}%", va="center", fontsize=8.5, color=INK)
    ax.set_xlim(0, 112)
    ax.set_xlabel("Share of simulation runs on the critical path", color=MUTED)
    ax.set_title(
        f"WMS connector (H) is on the critical path in {sim['criticality']['H']:.0%} of runs",
        loc="left",
        color=INK,
        fontsize=11,
        fontweight="bold",
    )
    style(ax)
    ax.grid(axis="y", visible=False)
    ax.tick_params(axis="y", colors=INK, labelsize=8.5)
    fig.tight_layout()
    fig.savefig(FIGS / "mc_criticality.png")
    plt.close(fig)

    print(json.dumps({k: result[k] for k in ("cpm", "schedule", "cost", "emv_total")}, indent=1)[:1800])
    print("PERT:", result["pert"]["expected_weeks"], "sd", result["pert"]["sd_weeks"], pert_critical)
    print("CI:", result["criticality_index"])
    return result


if __name__ == "__main__":
    main()
