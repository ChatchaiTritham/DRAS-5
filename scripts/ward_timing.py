"""Ward time scale: hourly / irregular charting over 24-hour episodes with missing charts (D-06).

The main cohort samples every 10 s for 1,000 s, which is a continuous-monitoring time scale.
Here the same four trajectory families are stretched over a 24-hour episode (the generator's
100 points become one point every 864 s = 14.4 min) and are observed only at charting times:

  hourly       a chart every 60 min
  irregular    gaps drawn uniformly from 30 to 120 min
  4-hourly     a chart every 240 min (a low-acuity ward round)

In every schedule 10% of charts are missing (dropped at random, seeded). Each system sees only
the charted values and its reported level is carried forward between charts; all metrics are
scored on the full 14.4-min truth grid against the TRUE level, so a peak that falls between
charts is a real miss for every system.

Systems: stateless chart (NEWS2-style), max-hold, hysteresis and timed-release max-hold with
the ward-scaled cooling windows, DRAS-5 with the shipped parameters (seconds), and DRAS-5 with
every timeout and cooling window multiplied by 60 and every decay rate divided by 60
(T_max 5 h / 2 h / 1 h; T_cool 10 h / 5 h / 3 h), a ward-scale configuration that is
illustrative, not calibrated.

Output: results/ward_timing.csv     Usage: python scripts/ward_timing.py [--n 5000] [--seed 42]
"""
from __future__ import annotations

import argparse
import csv
import logging
import math
import random
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

logging.disable(logging.CRITICAL)
REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))
sys.path.insert(0, str(REPO / "scripts"))

import run_all  # noqa: E402
from dras5 import states as states_mod  # noqa: E402
from dras5.state_machine import DRAS5StateMachine  # noqa: E402
from dras5.states import RiskState, risk_to_state  # noqa: E402

EPISODE_S = 24 * 3600.0
GRID_S = EPISODE_S / run_all.N_STEPS  # 864 s
MISSING = 0.10
SCALE = 60.0
REG_LIMIT_S = 3600.0
SCHEDULES = ("hourly", "irregular", "4-hourly")
SYSTEMS = ("Stateless chart", "Max-hold", "Hysteresis (ward windows)",
           "Timed-release max-hold (ward windows)", "DRAS-5 (shipped seconds)", "DRAS-5 (ward-scaled x60)")


def chart_times(schedule: str, rng: random.Random):
    times, t = [0.0], 0.0
    while True:
        gap = {"hourly": 3600.0, "4-hourly": 4 * 3600.0}.get(schedule) or rng.uniform(1800.0, 7200.0)
        t += gap
        if t >= EPISODE_S:
            break
        if rng.random() >= MISSING:
            times.append(t)
    return times


def _tcool(level, scale):
    tc = states_mod.STATE_CONFIG[RiskState(level)].get("t_cool")
    return tc * scale if tc else math.inf


def run_dras(times, vals, scale):
    cfg = states_mod.STATE_CONFIG
    saved = {s: (cfg[s]["t_cool"], cfg[s]["lam"]) for s in RiskState}
    try:
        for s in RiskState:
            if cfg[s]["t_cool"] is not None:
                cfg[s]["t_cool"] = saved[s][0] * scale
            if cfg[s]["lam"] is not None:
                cfg[s]["lam"] = saved[s][1] / scale
        sm = DRAS5StateMachine(enable_audit=False, require_human_approval=False)
        sm.STATE_TIMEOUTS = {s: v * scale for s, v in DRAS5StateMachine.STATE_TIMEOUTS.items()}
        levels, grants, requests = [], 0, 0
        for t, r in zip(times, vals):
            before = sm.current_state
            want = risk_to_state(r) < before and before not in (RiskState.SAFE, RiskState.EMERGENCY)
            requests += int(want)
            new = sm.update(r, t=t, human_approved=True, deescalation_request=want, dual_approval=want)
            grants += int(want and new < before)
            levels.append(int(new))
        return levels, grants, requests
    finally:
        for s in RiskState:
            cfg[s]["t_cool"], cfg[s]["lam"] = saved[s]


def hysteresis(times, lv):
    out, cur, since = [], lv[0], None
    for t, l in zip(times, lv):
        if l >= cur:
            cur, since = l, None
        elif cur < 5:
            since = t if since is None else since
            if t - since >= _tcool(cur, SCALE):
                cur, since = cur - 1, t
        out.append(cur)
    return out


def timed_release(times, lv):
    out, cur, last = [], lv[0], times[0]
    for t, l in zip(times, lv):
        if l >= cur:
            cur, last = l, t
        elif cur < 5 and t - last >= _tcool(cur, SCALE):
            cur, last = l, t
        out.append(cur)
    return out


def to_grid(times, levels):
    out, j = [], 0
    for k in range(run_all.N_STEPS):
        tk = k * GRID_S
        while j + 1 < len(times) and times[j + 1] <= tk:
            j += 1
        out.append(levels[j])
    return out


def family(args):
    tt, per, seed = args
    acc = {(sch, s): [] for sch in SCHEDULES for s in SYSTEMS}
    extra = {(sch, s): [0, 0, 0] for sch in SCHEDULES for s in SYSTEMS}  # grants, requests, charts
    for j in range(per):
        tseed = run_all._traj_seed(seed, tt, j)
        rho = run_all.make_trajectory(tt, tseed)
        truth = run_all._level_series(rho)
        peak = run_all.sustained_peak_level(rho)
        t0 = next(i for i in range(len(truth) - 1) if truth[i] >= peak and truth[i + 1] >= peak)
        for si, sch in enumerate(SCHEDULES):
            times = chart_times(sch, random.Random(tseed * 7 + si))
            vals = [rho[min(run_all.N_STEPS - 1, int(t // GRID_S))] for t in times]
            lv = [int(risk_to_state(v)) for v in vals]
            mh, cur = [], lv[0]
            for l in lv:
                cur = max(cur, l)
                mh.append(cur)
            d_s, g_s, r_s = run_dras(times, vals, 1.0)
            d_w, g_w, r_w = run_dras(times, vals, SCALE)
            reps = {"Stateless chart": (lv, 0, 0), "Max-hold": (mh, 0, 0),
                    "Hysteresis (ward windows)": (hysteresis(times, lv), 0, 0),
                    "Timed-release max-hold (ward windows)": (timed_release(times, lv), 0, 0),
                    "DRAS-5 (shipped seconds)": (d_s, g_s, r_s), "DRAS-5 (ward-scaled x60)": (d_w, g_w, r_w)}
            for s, (rep, g, r) in reps.items():
                grid = to_grid(times, rep)
                reg = next((k for k in range(t0, len(grid)) if grid[k] >= peak), None)
                delay = None if reg is None else (reg - t0) * GRID_S
                acc[(sch, s)].append({
                    "reach": int(max(grid) < peak), "end": int(grid[-1] < peak),
                    "oer": sum(a > b for a, b in zip(grid, truth)) / len(grid),
                    "end_excess": max(0, grid[-1] - truth[-1]),
                    "delay": delay, "late": int(delay is None or delay > REG_LIMIT_S)})
                e = extra[(sch, s)]
                e[0] += g
                e[1] += r
                e[2] += len(times)
    return acc, extra


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=5000)
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()
    per = args.n // len(run_all.TYPES)
    with ProcessPoolExecutor(max_workers=4) as ex:
        parts = list(ex.map(family, [(tt, per, args.seed) for tt in run_all.TYPES]))
    rows = []
    for sch in SCHEDULES:
        for s in SYSTEMS:
            data = sum((p[0][(sch, s)] for p in parts), [])
            g = sum(p[1][(sch, s)][0] for p in parts)
            r = sum(p[1][(sch, s)][1] for p in parts)
            charts = sum(p[1][(sch, s)][2] for p in parts)
            delays = sorted(d["delay"] for d in data if d["delay"] is not None)
            n = len(data)
            rows.append({
                "schedule": sch, "system": s, "n": n, "charts_per_patient": round(charts / n, 2),
                "mer_reach_true_pct": round(100 * sum(d["reach"] for d in data) / n, 2),
                "mer_end_true_pct": round(100 * sum(d["end"] for d in data) / n, 2),
                "oer_pct": round(100 * sum(d["oer"] for d in data) / n, 2),
                "end_excess_levels": round(sum(d["end_excess"] for d in data) / n, 3),
                "median_delay_min": round(delays[len(delays) // 2] / 60, 1) if delays else "",
                "not_registered_60min_pct": round(100 * sum(d["late"] for d in data) / n, 2),
                "c5_grants": g if s.startswith("DRAS") else "",
                "c5_requests_per_patient": round(r / n, 2) if s.startswith("DRAS") else ""})
    with open(REPO / "results" / "ward_timing.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    for r in rows:
        print(r)


if __name__ == "__main__":
    main()
