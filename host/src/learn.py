"""Phase 6: surrogate model and model-guided search, replayed on the measured grid.

    python3 learn.py            # leave-one-out accuracy, search comparison, figure, summary json

Question: can a model fitted on a few measured configs choose the next config to measure
well enough to find the optimum with fewer hardware experiments than random search?

Model: ridge regression (numpy only) from engineered features of (T, N, R) to
cost, mean latency and recall. Guided search: measure 4 random configs, fit, then repeatedly
measure the config with the lowest PREDICTED cost among those predicted to satisfy QoS
(with safety margins). Everything is replayed on the measured grid, so no extra board time.
Results are only as good as the 32 measured points; see the printed caveats.
"""
import json
import random
import statistics

import numpy as np

import experiment as ex
import optimize as op

INIT = 4                    # random configs measured before the model is first fitted
LAT_MARGIN = 0.85           # require predicted latency <= 85 % of the limit
RECALL_MARGIN = 0.95        # require predicted recall >= 0.95
SEEDS = 400
RIDGE = 1e-3


def feats(cfg):
    t, n, r = cfg
    d = t * n * r
    return [1.0, 1000.0 / t, 1000.0 / (t * n), 1000.0 / d, d / 1000.0, t * n / 1000.0]


def fit(keys, rows, field):
    X = np.array([feats(k) for k in keys])
    y = np.array([rows[k][field] for k in keys], dtype=float)
    A = X.T @ X + RIDGE * np.eye(X.shape[1])
    return np.linalg.solve(A, X.T @ y)


def predict(w, cfg):
    return float(np.array(feats(cfg)) @ w)


class Model:
    def __init__(self, keys, rows):
        self.w = {f: fit(keys, rows, f) for f in ("cost", "lat_mean_ms", "recall")}

    def __call__(self, cfg):
        return {f: predict(w, cfg) for f, w in self.w.items()}


def predicted_ok(p):
    return (p["lat_mean_ms"] <= ex.LIMITS["lat_mean_ms"] * LAT_MARGIN
            and p["recall"] >= RECALL_MARGIN)


def best_cost(measured, rows, fallback):
    b = op.best_of([rows[k] for k in measured])
    return b["cost"] if b else fallback


def guided(rows, budget, rng):
    keys = list(rows)
    measured = rng.sample(keys, INIT)
    while len(measured) < budget:
        m = Model(measured, rows)
        rest = [k for k in keys if k not in measured]
        ok = [k for k in rest if predicted_ok(m(k))]
        pick = min(ok, key=lambda k: m(k)["cost"]) if ok else rng.choice(rest)
        measured.append(pick)
    return measured


def loo(rows):
    """Leave-one-out prediction error of the surrogate on the full grid."""
    keys = list(rows)
    err = {"cost": [], "lat_mean_ms": [], "recall": []}
    for k in keys:
        m = Model([x for x in keys if x != k], rows)
        p = m(k)
        for f in err:
            err[f].append(abs(p[f] - rows[k][f]))
    return {f: statistics.mean(v) for f, v in err.items()}


def compare(rows):
    keys = list(rows)
    best = op.best_of(list(rows.values()))
    safe = rows.get(ex.SAFE)
    fallback = safe["cost"] if safe else 1.0
    out = {"random": {}, "guided": {}}
    for k in range(INIT, len(keys) + 1):
        for name in out:
            hits, costs = 0, []
            for seed in range(SEEDS):
                rng = random.Random(1000 * k + seed)
                meas = rng.sample(keys, k) if name == "random" else guided(rows, k, rng)
                c = best_cost(meas, rows, fallback)
                costs.append(c)
                hits += abs(c - best["cost"]) < 1e-9
            out[name][k] = {"p_optimum": hits / SEEDS, "mean_best_cost": statistics.mean(costs)}
    return out, best


def figure(res):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import plots
    ks = sorted(res["random"])
    fig, ax = plt.subplots(figsize=(7.4, 4.4), facecolor=plots.SURFACE)
    plots.style(ax)
    ax.plot(ks, [res["random"][k]["p_optimum"] for k in ks], color=plots.GRAY, lw=2,
            label="random search")
    ax.plot(ks, [res["guided"][k]["p_optimum"] for k in ks], color=plots.BLUE, lw=2,
            label="model-guided search")
    ax.set_ylim(0, 1.05)
    ax.set_xlabel("Evaluations (configs measured)", color=plots.INK2, fontsize=10)
    ax.set_ylabel("P(finds the grid optimum)", color=plots.INK2, fontsize=10)
    ax.set_title("Does a learned surrogate reduce hardware experiments?", loc="left",
                 color=plots.INK, fontsize=12, fontweight="bold")
    ax.legend(loc="lower right", frameon=False, fontsize=9, labelcolor=plots.INK2)
    fig.tight_layout()
    plots.OUT.mkdir(parents=True, exist_ok=True)
    fig.savefig(plots.OUT / "learning_curve.png", dpi=200, facecolor=plots.SURFACE)
    plt.close(fig)


def main():
    rows = {k: v for k, v in op.load("grid").items() if v["lat_mean_ms"] is not None}
    print(f"{len(rows)} measured configs\n")
    e = loo(rows)
    print("Surrogate leave-one-out mean absolute error on the full grid:")
    print(f"  cost    {e['cost']:.3f}   (cost range 0.07 to 1.0)")
    print(f"  latency {e['lat_mean_ms']:.0f} ms")
    print(f"  recall  {e['recall']:.2f}\n")
    res, best = compare(rows)
    print(f"Grid optimum cost {best['cost']:.3f}. P(finds optimum) and mean best cost, {SEEDS} seeds:")
    print("   k   random P / cost      guided P / cost")
    for k in sorted(res["random"]):
        if k in (4, 6, 8, 10, 12, 16, 20, 24, 32) or k == len(rows):
            r, g = res["random"][k], res["guided"][k]
            print(f"  {k:>2}   {r['p_optimum']:.2f} / {r['mean_best_cost']:.3f}      "
                  f"{g['p_optimum']:.2f} / {g['mean_best_cost']:.3f}")
    summary = {"configs": len(rows), "init": INIT, "seeds": SEEDS, "loo_mae": e,
               "optimum_cost": best["cost"],
               "random": res["random"], "guided": res["guided"]}
    p = ex.RESULTS.parent / "learning_summary.json"
    p.write_text(json.dumps(summary, indent=2))
    figure(res)
    print("\nSaved", p, "and figures/learning_curve.png")


if __name__ == "__main__":
    main()
