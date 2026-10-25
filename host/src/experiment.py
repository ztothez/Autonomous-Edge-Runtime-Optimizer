"""Phase 3/4: measurement model and automated experiment runner.

Usage (board must be on, nothing else connected to it):
    python3 experiment.py baseline            # measure baseline and safe default
    python3 experiment.py grid [seconds]      # all pruned configs, default 40 s each
    python3 experiment.py random K [seconds]  # K random configs from the same space
    python3 experiment.py show                # print results/experiments.csv

Ground truth: the firmware injects a burst at device uptime 5000 * k ms (k >= 1)
when source = 1 (BURST_PERIOD_MS must match SYNTH_PERIOD_MS in sensors/sensor.c).
"""
import asyncio
import csv
import itertools
import random
import statistics
import struct
import sys
import time
from collections import namedtuple
from pathlib import Path

ADDRESS = "F4:58:6B:B4:FE:06"
TELEM_UUID = "e5a10002-4a1b-4c3d-8f00-0123456789ab"
CFG_UUID = "e5a10003-4a1b-4c3d-8f00-0123456789ab"

PKT = struct.Struct("<IIIIIIIHHHHhHHhHH")   # 48 bytes, must match telemetry_pkt in ble_svc.h
CFG = struct.Struct("<HHHH")                # T, N, R, source, must match config_pkt
Packet = namedtuple("Packet", "seq uptime_ms rms_mg proc_us events windows sent "
                              "notify_err duty stack period_ms "
                              "temp_c100 hum_c100 press_dhpa dht_temp_c100 dht_hum_c100 env_status")

BURST_PERIOD_MS = 5000
SAFE = (50, 16, 2)                    # safe default (real sensor)
BASELINE = (20, 8, 1)                 # deliberately inefficient: fastest, smallest, report every window

T_VALUES = [20, 50, 100, 200]
N_VALUES = [8, 16, 32, 64]
R_VALUES = [1, 2, 5, 10]
MAX_REPORT_INTERVAL_MS = 4000         # prune configs that report less often than this

# Hard QoS constraints (Phase 3)
LIMITS = {"recall": 0.90, "lat_mean_ms": 1500, "loss_rate": 0.02, "stack_min": 128}

FIELDS = ["time", "mode", "T", "N", "R", "valid", "n_packets", "span_ms", "injected",
          "detected", "recall", "false_events", "lat_mean_ms", "lat_max_ms", "loss_rate",
          "notify_err", "pps", "duty", "proc_us", "stack_min", "qos_ok", "cost"]

RESULTS = Path(__file__).resolve().parent.parent / "results" / "experiments.csv"


# ---------------------------------------------------------------- measurement model

def space():
    """All (T, N, R) configs with report interval R*N*T <= MAX_REPORT_INTERVAL_MS."""
    return [c for c in itertools.product(T_VALUES, N_VALUES, R_VALUES)
            if c[0] * c[1] * c[2] <= MAX_REPORT_INTERVAL_MS]


def injected_until(uptime_ms):
    """Number of bursts that have started by this device uptime."""
    return max(0, uptime_ms // BURST_PERIOD_MS)


def summarize(cfg, pk):
    """Turn the packets received during one measurement into metrics."""
    t, n, r = cfg
    m = {"T": t, "N": n, "R": r, "valid": False, "n_packets": len(pk)}
    if len(pk) < 3:
        return m
    first, last = pk[0], pk[-1]
    span_ms = last.uptime_ms - first.uptime_ms
    if span_ms <= 0:
        return m

    # Shift the injection window back by the nominal reporting delay so the bursts
    # counted are the ones whose events are reported inside the measurement window.
    delay = t * n * r
    injected = injected_until(last.uptime_ms - delay) - injected_until(first.uptime_ms - delay)
    detected = last.events - first.events
    recall = min(detected, injected) / injected if injected > 0 else None

    # Latency = device uptime of the packet that first shows a new event minus the start
    # of the most recent burst (valid while worst-case delay < BURST_PERIOD_MS, which the
    # pruning guarantees). Device-side time: BLE transport delay is not included.
    lats = [b.uptime_ms % BURST_PERIOD_MS for a, b in zip(pk, pk[1:]) if b.events > a.events]

    lost = sum(max(0, b.seq - a.seq - 1) for a, b in zip(pk, pk[1:]))
    steps = max(1, last.seq - first.seq)

    m.update(
        valid=True, span_ms=span_ms, injected=injected, detected=detected, recall=recall,
        false_events=max(0, detected - injected),
        lat_mean_ms=statistics.mean(lats) if lats else None,
        lat_max_ms=max(lats) if lats else None,
        loss_rate=lost / steps,
        notify_err=last.notify_err - first.notify_err,
        pps=(last.sent - first.sent) / (span_ms / 1000),           # BLE packets per second
        duty=statistics.median(p.duty for p in pk),                # CPU-load proxy
        proc_us=statistics.median(p.proc_us for p in pk),
        stack_min=min(p.stack for p in pk),
    )
    m["qos_ok"] = qos_ok(m)
    return m


def qos_ok(m):
    if not m.get("valid") or m.get("recall") is None or m.get("lat_mean_ms") is None:
        return False
    return (m["recall"] >= LIMITS["recall"]
            and m["lat_mean_ms"] <= LIMITS["lat_mean_ms"]
            and m["loss_rate"] <= LIMITS["loss_rate"]
            and m["stack_min"] >= LIMITS["stack_min"])


def cost(m, base):
    """Normalized cost proxy: 1.0 = baseline. Equal weights on CPU busy time and BLE
    packet rate. No power measurement hardware, so this is a proxy, not energy."""
    if not m.get("valid") or not base.get("valid") or not base["duty"] or not base["pps"]:
        return None
    return 0.5 * m["duty"] / base["duty"] + 0.5 * m["pps"] / base["pps"]


# ---------------------------------------------------------------- BLE link

class Link:
    def __init__(self, client):
        self.client = client
        self.pkts = []

    def on_telemetry(self, _sender, data):
        self.pkts.append(Packet(*PKT.unpack(data)))

    async def set_config(self, t, n, r, src):
        await self.client.write_gatt_char(CFG_UUID, CFG.pack(t, n, r, src), response=True)

    async def get_config(self):
        return CFG.unpack(await self.client.read_gatt_char(CFG_UUID))

    async def measure(self, cfg, duration_s):
        t, n, r = cfg
        await self.set_config(t, n, r, 1)                  # synthetic source
        settle_s = 3 + 2 * (t * n * r) / 1000              # let old-config packets drain
        await asyncio.sleep(settle_s)
        self.pkts.clear()
        await asyncio.sleep(duration_s)
        return summarize(cfg, list(self.pkts))


# ---------------------------------------------------------------- runner

def write_row(mode, m, base):
    RESULTS.parent.mkdir(parents=True, exist_ok=True)
    new = not RESULTS.exists()
    row = dict(m)
    row.update(time=time.strftime("%Y-%m-%d %H:%M:%S"), mode=mode, cost=cost(m, base) if base else None)
    with RESULTS.open("a", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS, extrasaction="ignore")
        if new:
            w.writeheader()
        w.writerow(row)
    return row


def fmt(x, nd=2):
    return "-" if x is None else (f"{x:.{nd}f}" if isinstance(x, float) else str(x))


def print_row(row):
    print(f"T={row['T']:>3} N={row['N']:>2} R={row['R']:>2} | pk={row['n_packets']:>3} "
          f"recall={fmt(row.get('recall'))} lat={fmt(row.get('lat_mean_ms'), 0):>5} ms "
          f"pps={fmt(row.get('pps'))} duty={fmt(row.get('duty'), 0)} "
          f"stack={fmt(row.get('stack_min'))} loss={fmt(row.get('loss_rate'), 3)} "
          f"| QoS={'OK ' if row.get('qos_ok') else 'FAIL'} cost={fmt(row.get('cost'))}", flush=True)


async def session(configs, mode, duration_s):
    from bleak import BleakClient
    async with BleakClient(ADDRESS) as client:
        link = Link(client)
        await link.set_config(*SAFE, 0)
        await client.start_notify(TELEM_UUID, link.on_telemetry)
        try:
            print(f"Baseline {BASELINE}, {duration_s} s ...", flush=True)
            base = await link.measure(BASELINE, duration_s)
            print_row(write_row(mode, base, base))
            for cfg in configs:
                if cfg == BASELINE:
                    continue
                m = await link.measure(cfg, duration_s)
                print_row(write_row(mode, m, base))
        finally:
            await link.set_config(*SAFE, 0)                # always end on the safe default
            await client.stop_notify(TELEM_UUID)


def show():
    with RESULTS.open() as f:
        rows = list(csv.DictReader(f))
    for r in rows:
        print(f"{r['mode']:>8} T={r['T']:>3} N={r['N']:>2} R={r['R']:>2} recall={r['recall'] or '-':>5} "
              f"lat={r['lat_mean_ms'] or '-':>7} qos={r['qos_ok'] or '-':>5} cost={r['cost'] or '-'}")


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "baseline"
    if cmd == "show":
        show()
        return
    if cmd == "baseline":
        dur = float(sys.argv[2]) if len(sys.argv) > 2 else 40
        asyncio.run(session([SAFE], "baseline", dur))
    elif cmd == "grid":
        dur = float(sys.argv[2]) if len(sys.argv) > 2 else 40
        asyncio.run(session(space(), "grid", dur))
    elif cmd == "random":
        k = int(sys.argv[2])
        dur = float(sys.argv[3]) if len(sys.argv) > 3 else 40
        rng = random.Random(1)
        asyncio.run(session(rng.sample(space(), k), "random", dur))
    elif cmd == "one":
        cfg = (int(sys.argv[2]), int(sys.argv[3]), int(sys.argv[4]))
        dur = float(sys.argv[5]) if len(sys.argv) > 5 else 60
        asyncio.run(session([cfg], "one", dur))
    else:
        print(__doc__)


if __name__ == "__main__":
    main()