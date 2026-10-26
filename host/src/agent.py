"""Phase 7/8: closed-loop runtime agent with verification and rollback.

    python3 agent.py                  # run on the board (verify each proposal for 60 s)
    python3 agent.py --explore        # optimistic proposals first: shows a rollback happening
    python3 agent.py --dry-run        # replay the logic on the measured table, no board needed
    python3 agent.py --learn          # Phase 6 live: a surrogate model chooses what to measure next
    python3 agent.py --learn --dry-run  # same logic, measurements replayed from the table (no board)
    python3 agent.py [--seconds 90] [--budget 4] [--seed 1]

Loop:  OBSERVE (start from the safe default)
       PROPOSE the cheapest config the measured table predicts to be better than the
               currently deployed one (with --explore: optimistic about near-miss configs)
       VERIFY  on the board for a full measurement window
       DECIDE  keep it (new known-good) or ROLL BACK to the last known-good config
       repeat until the budget is spent or no cheaper candidate remains,
       then MONITOR system health on the real sensor and roll back on a violation.

--learn replaces the table lookup by a learned model (Phase 6). It starts from the safe default,
measures INIT random configs on the board, fits a ridge-regression surrogate (learn.py) on what it
has measured so far, then repeatedly measures the config with the lowest PREDICTED cost among those
predicted to satisfy QoS (with safety margins). Every measurement is verified on the board and
rolled back to the last known-good config if QoS is violated. The grid table is used only for the
baseline and safe-default reference rows (cost normalization), never to pick candidates.
Every decision is appended to host/results/agent_log.jsonl.
"""
import argparse
import asyncio
import json
import time

import experiment as ex
import optimize as op

LOG = ex.RESULTS.parent / "agent_log.jsonl"


def log(event, **kw):
    rec = {"ts": time.strftime("%Y-%m-%d %H:%M:%S"), "event": event, **kw}
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with LOG.open("a") as f:
        f.write(json.dumps(rec) + "\n")
    print(f"[{rec['ts']}] {event}: " + ", ".join(f"{k}={v}" for k, v in kw.items()), flush=True)


def predicted_ok(r, explore):
    """Does the table predict this config to satisfy QoS? With explore, be optimistic
    about near misses (within 0.1 recall and 25 % latency of the limits): the table is
    noisy, so a near miss may pass on a longer verification."""
    if r["qos_ok"]:
        return True
    if not explore or r["recall"] is None or r["lat_mean_ms"] is None:
        return False
    return (r["recall"] >= ex.LIMITS["recall"] - 0.10
            and r["lat_mean_ms"] <= ex.LIMITS["lat_mean_ms"] * 1.25
            and r["loss_rate"] <= ex.LIMITS["loss_rate"]
            and r["stack_min"] >= ex.LIMITS["stack_min"])


def key(r):
    return (int(r["T"]), int(r["N"]), int(r["R"]))


def propose(table, tried, deployed_cost, explore):
    cands = [r for r in table.values()
             if key(r) not in tried and r["cost"] < deployed_cost and predicted_ok(r, explore)]
    return min(cands, key=lambda r: r["cost"]) if cands else None


class DryLink:
    """Replays the measured table instead of using the board."""
    def __init__(self, table):
        self.table = table

    async def set_config(self, *a):
        pass

    async def measure(self, cfg, duration_s):
        m = dict(self.table[cfg])
        m["valid"] = True
        m["qos_ok"] = ex.qos_ok(m)
        return m

    async def monitor(self, seconds):
        return {"loss_rate": 0.0, "stack_min": 1392, "n_packets": 10}


class BoardLink(ex.Link):
    async def monitor(self, seconds):
        self.pkts.clear()
        await asyncio.sleep(seconds)
        pk = list(self.pkts)
        if len(pk) < 2:
            return {"loss_rate": 1.0, "stack_min": 0, "n_packets": len(pk)}
        lost = sum(max(0, b.seq - a.seq - 1) for a, b in zip(pk, pk[1:]))
        return {"loss_rate": lost / max(1, pk[-1].seq - pk[0].seq),
                "stack_min": min(p.stack for p in pk), "n_packets": len(pk)}


async def finish(link, args, deployed, deployed_cost, safe):
    await link.set_config(*deployed, 0)                     # deploy on the real sensor
    log("deploy", config=deployed, cost=round(deployed_cost, 3))

    h = await link.monitor(args.monitor)
    healthy = h["loss_rate"] <= ex.LIMITS["loss_rate"] and h["stack_min"] >= ex.LIMITS["stack_min"]
    log("monitor", seconds=args.monitor, packets=h["n_packets"], loss=h["loss_rate"],
        stack_min=h["stack_min"], healthy=healthy)
    if not healthy:
        await link.set_config(*ex.SAFE, 0)
        deployed, deployed_cost = ex.SAFE, safe["cost"]
        log("rollback", reason="health check failed", restored=deployed)

    log("done", final=deployed, final_cost=round(deployed_cost, 3),
        vs_safe=f"{(1 - deployed_cost / safe['cost']) * 100:.0f}% lower",
        vs_baseline=f"{(1 - deployed_cost) * 100:.0f}% lower")


async def agent(link, table, args):
    base = table[ex.BASELINE]
    safe = table[ex.SAFE]
    deployed, deployed_cost = ex.SAFE, safe["cost"]
    tried = {ex.SAFE, ex.BASELINE}
    await link.set_config(*ex.SAFE, 0)
    log("start", deployed=deployed, cost=round(deployed_cost, 3), explore=args.explore)

    for step in range(1, args.budget + 1):
        cand = propose(table, tried, deployed_cost, args.explore)
        if cand is None:
            log("converged", reason="no cheaper candidate predicted to pass", deployed=deployed)
            break
        cfg = key(cand)
        tried.add(cfg)
        log("propose", step=step, config=cfg, predicted_cost=round(cand["cost"], 3),
            predicted_latency_ms=round(cand["lat_mean_ms"]), predicted_recall=round(cand["recall"], 2))
        m = await link.measure(cfg, args.seconds)
        ok = ex.qos_ok(m)
        c = ex.cost(m, base) if m.get("valid") else None
        log("verify", config=cfg, recall=m.get("recall"), latency_ms=round(m["lat_mean_ms"]) if m.get("lat_mean_ms") else None,
            loss=m.get("loss_rate"), measured_cost=round(c, 3) if c else None, qos_ok=ok)
        if ok and c is not None and c < deployed_cost:
            deployed, deployed_cost = cfg, c
            log("accept", config=cfg, cost=round(c, 3))
        else:
            await link.set_config(*deployed, 1)            # back to the last known-good config
            reason = "QoS violated" if not ok else "not cheaper than the deployed config"
            log("rollback", rejected=cfg, reason=reason, restored=deployed)

    await finish(link, args, deployed, deployed_cost, safe)


def train_row(m, c):
    """Row for the surrogate. No detection at all counts as the worst case."""
    return {"cost": c,
            "lat_mean_ms": m["lat_mean_ms"] if m.get("lat_mean_ms") is not None
                           else float(ex.BURST_PERIOD_MS),
            "recall": m["recall"] if m.get("recall") is not None else 0.0}


async def agent_learn(link, table, args):
    """Phase 6 live: model-guided search. See the module docstring."""
    import random
    import learn                                        # needs numpy, only for --learn
    base, safe = table[ex.BASELINE], table[ex.SAFE]
    rng = random.Random(args.seed)
    deployed, deployed_cost = ex.SAFE, safe["cost"]
    cands = [k for k in ex.space() if k not in (ex.SAFE, ex.BASELINE)]
    tried, measured = set(), {}
    await link.set_config(*ex.SAFE, 0)
    log("start", mode="learn", deployed=deployed, cost=round(deployed_cost, 3),
        seed=args.seed, budget=args.budget, init=learn.INIT)

    for step in range(1, args.budget + 1):
        rest = [k for k in cands if k not in tried]
        if not rest:
            log("converged", reason="every candidate measured", deployed=deployed)
            break
        pred = None
        if len(measured) < learn.INIT:
            cfg, why = rng.choice(rest), "random initial sample"
        else:
            model = learn.Model(list(measured), measured)
            safe_pred = [k for k in rest if learn.predicted_ok(model(k))]
            if safe_pred:
                cfg = min(safe_pred, key=lambda k: model(k)["cost"])
                why = "lowest predicted cost among configs predicted to satisfy QoS"
            else:
                cfg, why = rng.choice(rest), "no config predicted safe: random sample"
            pred = model(cfg)
        tried.add(cfg)
        info = {"predicted_cost": round(pred["cost"], 3),
                "predicted_latency_ms": round(pred["lat_mean_ms"]),
                "predicted_recall": round(pred["recall"], 2)} if pred else {}
        log("propose", step=step, config=cfg, why=why, trained_on=len(measured), **info)

        m = await link.measure(cfg, args.seconds)
        ok = ex.qos_ok(m)
        c = ex.cost(m, base) if m.get("valid") else None
        if c is not None:
            measured[cfg] = train_row(m, c)
        log("verify", config=cfg, recall=m.get("recall"),
            latency_ms=round(m["lat_mean_ms"]) if m.get("lat_mean_ms") else None,
            loss=m.get("loss_rate"), measured_cost=round(c, 3) if c else None, qos_ok=ok)
        if ok and c is not None and c < deployed_cost:
            deployed, deployed_cost = cfg, c
            log("accept", config=cfg, cost=round(c, 3))
        else:
            await link.set_config(*deployed, 1)             # back to the last known-good config
            reason = "QoS violated" if not ok else "not cheaper than the deployed config"
            log("rollback", rejected=cfg, reason=reason, restored=deployed)

    await finish(link, args, deployed, deployed_cost, safe)


async def run_board(table, args):
    from bleak import BleakClient
    async with BleakClient(ex.ADDRESS) as client:
        link = BoardLink(client)
        await client.start_notify(ex.TELEM_UUID, link.on_telemetry)
        try:
            await (agent_learn if args.learn else agent)(link, table, args)
        finally:
            await client.stop_notify(ex.TELEM_UUID)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--explore", action="store_true")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--seconds", type=float, default=60, help="verification window per proposal")
    p.add_argument("--learn", action="store_true", help="Phase 6: model-guided search on the board")
    p.add_argument("--seed", type=int, default=1, help="random seed for the initial samples (--learn)")
    p.add_argument("--budget", type=int, default=None,
                   help="max proposals (default 4, or 12 with --learn)")
    p.add_argument("--monitor", type=float, default=20, help="health monitoring after deploy")
    args = p.parse_args()
    if args.budget is None:
        args.budget = 12 if args.learn else 4
    table = {key(r): r for r in op.load("grid").values()}
    if ex.BASELINE not in table or ex.SAFE not in table:
        raise SystemExit("Need baseline and safe default rows from a grid run first.")
    if args.dry_run:
        asyncio.run((agent_learn if args.learn else agent)(DryLink(table), table, args))
    else:
        asyncio.run(run_board(table, args))


if __name__ == "__main__":
    main()