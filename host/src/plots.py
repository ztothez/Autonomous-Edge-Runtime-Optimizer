"""Phase 9: figures and result tables for the report.

    python3 plots.py

Reads host/results/experiments.csv and writes to host/results/figures/:
    tradeoff.png       cost vs detection latency for every measured config
    search_budget.png  random search vs exhaustive grid (replayed on measured data)
and host/results/results_table.md (top configs plus the verify / rollback rows).
Needs matplotlib:  pip install matplotlib
"""
import csv
import random
import statistics

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

import experiment as ex
import optimize as op

# Palette: blue = configs that satisfy the QoS constraints, gray = de-emphasized
# (violate a constraint). Text stays in ink tokens. Marker shape is the second encoding.
SURFACE = "#fcfcfb"
INK = "#0b0b0b"
INK2 = "#52514e"
GRID = "#e3e2de"
BLUE = "#2a78d6"
GRAY = "#8b8a85"

OUT = ex.RESULTS.parent / "figures"


def style(ax):
    ax.set_facecolor(SURFACE)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color(INK2)
    ax.tick_params(colors=INK2, labelsize=9)
    ax.grid(axis="y", color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)


def label(r):
    return f"({int(r['T'])}, {int(r['N'])}, {int(r['R'])})"


def tradeoff(rows, best):
    fig, ax = plt.subplots(figsize=(8.2, 5.0), facecolor=SURFACE)
    style(ax)
    ok = [r for r in rows if r["qos_ok"]]
    bad = [r for r in rows if not r["qos_ok"]]

    ax.axvspan(ex.LIMITS["lat_mean_ms"], 2700, color=GRID, alpha=0.5, lw=0)
    ax.axvline(ex.LIMITS["lat_mean_ms"], color=INK2, lw=1, ls=(0, (4, 3)))
    ax.text(ex.LIMITS["lat_mean_ms"] + 40, 0.9, "latency limit\n1500 ms", color=INK2,
            fontsize=8.5, va="top")

    ax.scatter([r["lat_mean_ms"] for r in bad], [r["cost"] for r in bad], s=46, marker="X",
               color=GRAY, linewidths=0.8, label="violates a QoS constraint", zorder=3)
    ax.scatter([r["lat_mean_ms"] for r in ok], [r["cost"] for r in ok], s=46, marker="o",
               color=BLUE, edgecolors=SURFACE, linewidths=1.2, label="satisfies all QoS constraints",
               zorder=4)

    by = {(int(r["T"]), int(r["N"]), int(r["R"])): r for r in rows}
    r = by.get(ex.BASELINE)
    if r:
        ax.annotate(f"baseline {label(r)}", (r["lat_mean_ms"], r["cost"]), xytext=(14, -4),
                    textcoords="offset points", ha="left", fontsize=9, color=INK)
    r = by.get(ex.SAFE)
    if r:   # two-line label with a leader so it cannot be read as the nearby gray marker
        ax.annotate(f"safe default\n{label(r)}", (r["lat_mean_ms"], r["cost"]),
                    xytext=(1020, 0.118), textcoords="data", ha="left", va="center",
                    fontsize=9, color=INK,
                    arrowprops=dict(arrowstyle="-", color=INK2, lw=0.8, shrinkA=2, shrinkB=4))
    if best:
        ax.scatter([best["lat_mean_ms"]], [best["cost"]], s=190, facecolors="none",
                   edgecolors=INK, linewidths=1.6, zorder=5)
        ax.annotate(f"optimizer pick {label(best)}\ncost {best['cost']:.2f}, {best['lat_mean_ms']:.0f} ms",
                    (best["lat_mean_ms"], best["cost"]), xytext=(18, -34),
                    textcoords="offset points", fontsize=9, color=INK,
                    arrowprops=dict(arrowstyle="-", color=INK2, lw=0.8))

    ax.set_yscale("log")
    ax.set_yticks([0.05, 0.1, 0.2, 0.5, 1.0])
    ax.set_yticklabels(["0.05", "0.1", "0.2", "0.5", "1.0"])
    ax.minorticks_off()
    ax.set_xlim(0, 2700)
    ax.set_ylim(0.045, 1.4)
    ax.set_xlabel("Mean detection latency (ms)", color=INK2, fontsize=10)
    ax.set_ylabel("Cost proxy (baseline = 1.0, log scale)", color=INK2, fontsize=10)
    ax.set_title("Cheaper configurations trade away latency or recall", loc="left",
                 color=INK, fontsize=12, fontweight="bold")
    leg = ax.legend(loc="upper right", frameon=False, fontsize=9, labelcolor=INK2,
                    bbox_to_anchor=(1.0, 0.82))
    fig.tight_layout()
    fig.savefig(OUT / "tradeoff.png", dpi=200, facecolor=SURFACE)
    plt.close(fig)


def search_budget(rows, best):
    rng = random.Random(7)
    ks = list(range(1, len(rows) + 1))
    safe = next((r for r in rows if (int(r["T"]), int(r["N"]), int(r["R"])) == ex.SAFE), None)
    fallback = safe["cost"] if safe else 1.0
    mean_cost, p_opt = [], []
    for k in ks:
        costs, hits = [], 0
        for _ in range(2000):
            b = op.best_of(rng.sample(rows, k))
            c = b["cost"] if b else fallback
            costs.append(c)
            hits += abs(c - best["cost"]) < 1e-9
        mean_cost.append(statistics.mean(costs))
        p_opt.append(hits / 2000)

    fig, (a1, a2) = plt.subplots(1, 2, figsize=(9.6, 4.0), facecolor=SURFACE)
    for ax in (a1, a2):
        style(ax)
        ax.set_xlabel("Evaluations (configs measured)", color=INK2, fontsize=10)
        ax.set_xlim(0, len(rows) + 1)
    a1.plot(ks, mean_cost, color=BLUE, lw=2)
    a1.axhline(best["cost"], color=INK2, lw=1, ls=(0, (4, 3)))
    a1.text(len(rows), best["cost"] + 0.012, f"grid optimum {best['cost']:.3f}", color=INK2,
            fontsize=8.5, ha="right", va="bottom")
    a1.set_ylabel("Mean best cost found (random search)", color=INK2, fontsize=10)
    a1.set_title("Cost found vs budget", loc="left", color=INK, fontsize=11, fontweight="bold")
    a2.plot(ks, p_opt, color=BLUE, lw=2)
    a2.set_ylim(0, 1.05)
    a2.set_ylabel("P(finds the grid optimum)", color=INK2, fontsize=10)
    a2.set_title("Chance of finding the optimum", loc="left", color=INK, fontsize=11, fontweight="bold")
    fig.tight_layout()
    fig.savefig(OUT / "search_budget.png", dpi=200, facecolor=SURFACE)
    plt.close(fig)


def table(rows, best):
    ok = sorted((r for r in rows if r["qos_ok"]), key=lambda r: r["cost"])[:8]
    lines = ["| config (T, N, R) | cost | recall | mean latency (ms) | packets/s | duty (0.01 %) |",
             "|---|---|---|---|---|---|"]
    for r in ok:
        lines.append(f"| {label(r)} | {r['cost']:.3f} | {r['recall']:.2f} | {r['lat_mean_ms']:.0f} | "
                     f"{r['pps']:.2f} | {r['duty']:.0f} |")
    lines += ["", "Verification and rollback runs:", "",
              "| run | config | recall | mean latency (ms) | QoS | outcome |", "|---|---|---|---|---|---|"]
    with ex.RESULTS.open() as f:
        for r in csv.DictReader(f):
            if r["mode"] in ("verify", "rollback-demo") and r["valid"] == "True":
                passed = r["qos_ok"] == "True"
                outcome = "kept (deployed)" if passed else "rolled back to safe default"
                lines.append(f"| {r['mode']} | ({r['T']}, {r['N']}, {r['R']}) | {float(r['recall']):.2f} | "
                             f"{float(r['lat_mean_ms']):.0f} | {'OK' if passed else 'FAIL'} | {outcome} |")
    (ex.RESULTS.parent / "results_table.md").write_text("\n".join(lines) + "\n")


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    rows = list(op.load("grid").values())
    best = op.best_of(rows)
    tradeoff(rows, best)
    search_budget(rows, best)
    table(rows, best)
    print("Wrote", OUT / "tradeoff.png", OUT / "search_budget.png", ex.RESULTS.parent / "results_table.md")


if __name__ == "__main__":
    main()
