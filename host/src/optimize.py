"""Phase 5/8: deterministic optimizer, search comparison, verify and rollback.

Usage:
    python3 optimize.py                       # analyse results/experiments.csv (grid rows)
    python3 optimize.py deploy [seconds]      # verify the best config on the board, roll back if it fails
    python3 optimize.py rollback-demo [secs]  # deliberately deploy a failing config to show the rollback

Selection rule: minimize the normalized cost proxy subject to the hard QoS constraints
in experiment.LIMITS. The safe default is the fallback when nothing is feasible.
"""
import asyncio
import csv
import json
import random
import statistics
import sys

import experiment as ex

NUM = ["T", "N", "R", "n_packets", "span_ms", "injected", "detected", "recall", "false_events",
       "lat_mean_ms", "lat_max_ms", "loss_rate", "notify_err", "pps", "duty", "proc_us",
       "stack_min", "cost"]


def load(mode="grid"):
    """Latest row per (T, N, R) for the given mode, with numbers converted."""
    latest = {}
    with ex.RESULTS.open() as f:
        for r in csv.DictReader(f):
            if r["mode"] != mode or r["valid"] != "True":
                continue
            for k in NUM:
                r[k] = float(r[k]) if r.get(k) not in (None, "") else None
            r["qos_ok"] = r["qos_ok"] == "True"
            latest[(int(r["T"]), int(r["N"]), int(r["R"]))] = r
    return latest


def best_of(rows):
    feas = [r for r in rows if r["qos_ok"] and r["cost"] is not None]
    return min(feas, key=lambda r: r["cost"]) if feas else None


def describe(r):
    return (f"(T={int(r['T'])}, N={int(r['N'])}, R={int(r['R'])})  cost={r['cost']:.3f}  "
            f"recall={r['recall']:.2f}  latency={r['lat_mean_ms']:.0f} ms  "
            f"pps={r['pps']:.2f}  duty={r['duty']:.0f}")


def analyse():
    rows = load("grid")
    if not rows:
        print("No grid rows in", ex.RESULTS)
        return
    allrows = list(rows.values())
    base = rows.get(ex.BASELINE)
    safe = rows.get(ex.SAFE)
    best = best_of(allrows)

    print(f"{len(allrows)} configs measured, {sum(r['qos_ok'] for r in allrows)} satisfy the QoS constraints")
    print("Constraints:", ex.LIMITS, "\n")
    print("Top 5 feasible by cost:")
    for r in sorted((r for r in allrows if r["qos_ok"]), key=lambda r: r["cost"])[:5]:
        print("  ", describe(r))
    print("\nInfeasible but cheaper than the best (why they were rejected):")
    for r in sorted(allrows, key=lambda r: r["cost"]):
        if not r["qos_ok"] and best and r["cost"] < best["cost"]:
            why = []
            if r["recall"] is None or r["recall"] < ex.LIMITS["recall"]:
                why.append(f"recall {r['recall']:.2f}")
            if r["lat_mean_ms"] is None or r["lat_mean_ms"] > ex.LIMITS["lat_mean_ms"]:
                why.append(f"latency {r['lat_mean_ms']:.0f} ms")
            print(f"   (T={int(r['T'])}, N={int(r['N'])}, R={int(r['R'])}) cost={r['cost']:.3f}: " + ", ".join(why))

    print()
    if best:
        print("BEST:", describe(best))
        if base:
            print(f"  vs baseline {ex.BASELINE}: cost {best['cost']:.3f} vs 1.000 "
                  f"({(1 - best['cost']) * 100:.0f}% lower proxy cost)")
        if safe:
            print(f"  vs safe default {ex.SAFE}: cost {best['cost']:.3f} vs {safe['cost']:.3f} "
                  f"({(1 - best['cost'] / safe['cost']) * 100:.0f}% lower proxy cost)")
    else:
        print("No feasible config: keep the safe default", ex.SAFE)

    # Random search vs exhaustive grid, replayed on the measured data (no extra board time).
    fallback = safe["cost"] if safe and safe["qos_ok"] else 1.0
    rng = random.Random(7)
    print("\nRandom search with a budget of k evaluations (5000 replays on the measured grid):")
    print("   k   mean best cost   P(finds the grid optimum)")
    out = {}
    for k in sorted({3, 5, 8, 12, 16, 24, len(allrows)}):
        if k > len(allrows):
            continue
        costs, hits = [], 0
        for _ in range(5000):
            b = best_of(rng.sample(allrows, k))
            c = b["cost"] if b else fallback
            costs.append(c)
            hits += bool(best) and abs(c - best["cost"]) < 1e-9
        out[k] = (statistics.mean(costs), hits / 5000)
        print(f"  {k:>2}   {out[k][0]:.3f}            {out[k][1]:.2f}")
    print(f"  grid = {len(allrows)} evaluations, optimum cost {best['cost']:.3f}" if best else "")

    summary = {"limits": ex.LIMITS, "measured": len(allrows),
               "feasible": sum(r["qos_ok"] for r in allrows),
               "best": {k: best[k] for k in ("T", "N", "R", "cost", "recall", "lat_mean_ms", "pps", "duty")} if best else None,
               "baseline_cost": 1.0, "safe_cost": safe["cost"] if safe else None,
               "random_search": {str(k): {"mean_best_cost": v[0], "p_optimum": v[1]} for k, v in out.items()}}
    p = ex.RESULTS.parent / "optimizer_summary.json"
    p.write_text(json.dumps(summary, indent=2))
    print("\nSaved", p)


async def verify(cfg, duration_s, mode):
    """Deploy cfg, measure it on the synthetic source, keep it only if QoS holds.
    Otherwise roll back to the safe default. Returns True if cfg was kept."""
    from bleak import BleakClient
    rows = load("grid")
    base = rows.get(ex.BASELINE)
    if not base:
        raise SystemExit("Need the baseline row from a grid run first.")
    async with BleakClient(ex.ADDRESS) as client:
        link = ex.Link(client)
        await link.set_config(*ex.SAFE, 0)
        await client.start_notify(ex.TELEM_UUID, link.on_telemetry)
        try:
            print(f"Verifying {cfg} for {duration_s:.0f} s ...", flush=True)
            m = await link.measure(cfg, duration_s)
            ok = ex.qos_ok(m)
            ex.print_row(ex.write_row(mode, m, base))
            if ok:
                await link.set_config(*cfg, 0)           # deploy on the real sensor
                print(f"QoS verified: {cfg} stays deployed (real sensor).")
            else:
                await link.set_config(*ex.SAFE, 0)
                print(f"QoS violated: ROLLED BACK to safe default {ex.SAFE}.")
            print("Active config:", await link.get_config())
            return ok
        finally:
            await client.stop_notify(ex.TELEM_UUID)


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "analyse"
    if cmd == "analyse":
        analyse()
    elif cmd == "deploy":
        best = best_of(load("grid").values())
        if not best:
            raise SystemExit("No feasible config in the grid.")
        dur = float(sys.argv[2]) if len(sys.argv) > 2 else 120
        asyncio.run(verify((int(best["T"]), int(best["N"]), int(best["R"])), dur, "verify"))
    elif cmd == "rollback-demo":
        bad = min((r for r in load("grid").values() if not r["qos_ok"]), key=lambda r: r["cost"])
        dur = float(sys.argv[2]) if len(sys.argv) > 2 else 60
        asyncio.run(verify((int(bad["T"]), int(bad["N"]), int(bad["R"])), dur, "rollback-demo"))
    else:
        print(__doc__)


if __name__ == "__main__":
    main()