"""Reach versus over-escalation frontier, long episodes, and premature step-down against a
noise-free truth (v1.6.0; answers the round-2 review items E-02, E-03 and E-04).

E-03  The C2 timeout lowers the share of true sustained peaks that are never reported, but it
      raises over-escalation (OER). Is that a benefit at matched OER, or a point on the same
      trade-off curve that a lower threshold would reach? Two knobs are swept:
        baselines  every reading is shifted up by delta before it is mapped to a level, which
                   is the same as lowering every threshold theta_k by delta
                   (delta = 0, 0.05, ..., 0.40); systems: stateless, max-hold, hysteresis,
                   timed-release max-hold, decayed max
        DRAS-5     every T_max multiplied by a factor (C2 removed at factor inf); shipped
                   thresholds, decay rates and cooling windows
      Settings: ward hourly / irregular / 4-hourly charting (as scripts/ward_timing.py, shipped
      DRAS-5 windows) and the vital-sign predictor and its site-shifted variant (as
      scripts/ml_wrapper_v2.py). The 10 s main cohort is not swept: there the truth is the
      input, so every system with memory has true-relative reach misses of 0.
      Matched comparison: for each DRAS-5 point, the lowest baseline reach-miss rate among all
      baseline points whose OER is not higher than that DRAS-5 point's OER.
E-04  The main cohort lasts 1,000 s, shorter than the 1,080 s minimum S4 -> S1 path of C5.
      The recoverable comparison of scripts/recoverable_baselines.py is re-run with 720-sample
      (7,200 s, two-hour) episodes: run_all.N_STEPS = 720, all other generator settings as
      shipped (spike at a quarter of the episode, per-sample spike decay unchanged).
E-02  In the main cohort the truth is the noisy input, so no system can step down below it.
      Premature step-downs are re-counted against the level of the noise-free trajectory
      (same seeds, every noise sigma set to 0), at 100 and 720 samples.

Outputs: results/tradeoff_frontier.csv, results/tradeoff_matched.csv,
         results/long_episodes.csv, results/long_episodes_summary.json,
         results/premature_noisefree.csv
Usage:   python scripts/tradeoff_frontier.py [--n 5000] [--seed 42]     (about 15 min)
"""
from __future__ import annotations

import argparse
import csv
import json
import logging
import math
import random
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np
from sklearn.ensemble import GradientBoostingRegressor

logging.disable(logging.CRITICAL)
REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))
sys.path.insert(0, str(REPO / "scripts"))

import ml_wrapper_v2 as mlw  # noqa: E402
import recoverable_baselines as rb  # noqa: E402
import run_all  # noqa: E402
import ward_timing as wt  # noqa: E402
from dras5.state_machine import DRAS5StateMachine  # noqa: E402
from dras5.states import RiskState, risk_to_state  # noqa: E402

DELTAS = [round(0.05 * k, 2) for k in range(9)]
WARD_TFAC = [1, 10, 30, 60, 120, 240, 480, math.inf]
WRAP_TFAC = [0.25, 0.5, 1, 2, 4, 8, 16, math.inf]
BASELINES = ("Stateless", "Max-hold", "Hysteresis", "Timed-release max-hold", "Decayed max")
LONG_STEPS = 720
NOISE_KEYS = ("MONO_NOISE", "OSC_NOISE", "SPIKEE_NOISE", "SPIKEC_NOISE")


def lvl(v, delta=0.0):
    return int(risk_to_state(min(1.0, v + delta)))


def dras(times, vals, tfac):
    """DRAS-5, shipped parameters except T_max x tfac; same request policy as the paper."""
    sm = DRAS5StateMachine(enable_audit=False, require_human_approval=False)
    sm.STATE_TIMEOUTS = {s: (v * tfac if math.isfinite(v) else v)
                         for s, v in DRAS5StateMachine.STATE_TIMEOUTS.items()}
    out = []
    for t, r in zip(times, vals):
        before = sm.current_state
        want = risk_to_state(r) < before and before not in (RiskState.SAFE, RiskState.EMERGENCY)
        out.append(int(sm.update(r, t=t, human_approved=True, deescalation_request=want, dual_approval=want)))
    return out


def maxhold(lv):
    out, h = [], lv[0]
    for x in lv:
        h = max(h, x)
        out.append(h)
    return out


def score(grid, truth, peak):
    return (int(max(grid) < peak), sum(a > b for a, b in zip(grid, truth)) / len(truth), int(grid[-1] < peak))


# ---------------------------------------------------------------- ward frontier
def ward_family(args):
    tt, per, seed = args
    acc = {}
    for j in range(per):
        tseed = run_all._traj_seed(seed, tt, j)
        rho = run_all.make_trajectory(tt, tseed)
        truth = run_all._level_series(rho)
        peak = run_all.sustained_peak_level(rho)
        for si, sch in enumerate(wt.SCHEDULES):
            times = wt.chart_times(sch, random.Random(tseed * 7 + si))
            vals = [rho[min(run_all.N_STEPS - 1, int(t // wt.GRID_S))] for t in times]
            pts = []
            for d in DELTAS:
                lv = [lvl(v, d) for v in vals]
                sv = [min(1.0, v + d) for v in vals]
                pts += [("Stateless", d, lv), ("Max-hold", d, maxhold(lv)),
                        ("Hysteresis", d, wt.hysteresis(times, lv)),
                        ("Timed-release max-hold", d, wt.timed_release(times, lv)),
                        ("Decayed max", d, wt.decayed_max(times, sv))]
            for f in WARD_TFAC:
                pts.append(("DRAS-5", f, dras(times, vals, f)))
            for name, knob, rep in pts:
                r = score(wt.to_grid(times, rep), truth, peak)
                a = acc.setdefault((sch, name, knob), [0, 0.0, 0, 0])
                a[0] += r[0]
                a[1] += r[1]
                a[2] += r[2]
                a[3] += 1
    return acc


# ---------------------------------------------------------------- wrapper frontier
def wrapper_rows(n, seed):
    per = n // len(run_all.TYPES)
    n_test = int(round(run_all.ML_TEST_FRACTION * per))
    train, test = [], []
    for tt in run_all.TYPES:
        for j in range(per):
            s = run_all._traj_seed(seed, tt, j)
            (test if j >= per - n_test else train).append((tt, s, run_all.make_trajectory(tt, s)))
    Xv, yv = [], []
    for _, s, rho in train:
        for v, r in zip(mlw.vitals(rho, random.Random(s + 17)), rho):
            Xv.append(v)
            yv.append(r)
    vm = GradientBoostingRegressor(random_state=seed, n_estimators=100, max_depth=3).fit(np.asarray(Xv), yv)
    acc = {}
    for kind in ("vital-sign", "vital-sign, shifted"):
        for tt, s, rho in test:
            pr = [run_all._clip(float(p)) for p in
                  vm.predict(np.asarray(mlw.vitals(rho, random.Random(s + 17), shift=(kind != "vital-sign"))))]
            truth = run_all._level_series(rho)
            peak = run_all.sustained_peak_level(rho)
            times = [i * run_all.DT_SECONDS for i in range(len(pr))]
            pts = []
            for d in DELTAS:
                lv = [lvl(v, d) for v in pr]
                pts += [("Stateless", d, lv), ("Max-hold", d, maxhold(lv)),
                        ("Hysteresis", d, rb.hysteresis(lv)), ("Timed-release max-hold", d, rb.timed_release(lv)),
                        ("Decayed max", d, rb.decayed_max([min(1.0, v + d) for v in pr]))]
            for f in WRAP_TFAC:
                pts.append(("DRAS-5", f, dras(times, pr, f)))
            for name, knob, rep in pts:
                r = score(rep, truth, peak)
                a = acc.setdefault((kind, name, knob), [0, 0.0, 0, 0])
                a[0] += r[0]
                a[1] += r[1]
                a[2] += r[2]
                a[3] += 1
    return acc


def to_rows(acc):
    rows = []
    for (setting, system, knob), (reach, oer, end, n) in acc.items():
        rows.append({"setting": setting, "system": system,
                     "knob": "T_max factor" if system == "DRAS-5" else "threshold shift delta",
                     "value": "inf" if knob == math.inf else knob, "n": n,
                     "mer_reach_true_pct": round(100 * reach / n, 2), "oer_pct": round(100 * oer / n, 2),
                     "mer_end_true_pct": round(100 * end / n, 2)})
    return rows


def matched(rows):
    out = []
    for setting in dict.fromkeys(r["setting"] for r in rows):
        sub = [r for r in rows if r["setting"] == setting]
        base = [r for r in sub if r["system"] != "DRAS-5"]
        for d in (r for r in sub if r["system"] == "DRAS-5"):
            ok = [b for b in base if b["oer_pct"] <= d["oer_pct"]]
            best = min(ok, key=lambda b: (b["mer_reach_true_pct"], b["oer_pct"])) if ok else None
            out.append({"setting": setting, "dras5_tmax_factor": d["value"],
                        "dras5_reach_pct": d["mer_reach_true_pct"], "dras5_oer_pct": d["oer_pct"],
                        "best_baseline": f'{best["system"]} delta={best["value"]}' if best else "",
                        "baseline_reach_pct": best["mer_reach_true_pct"] if best else "",
                        "baseline_oer_pct": best["oer_pct"] if best else "",
                        "dras5_minus_baseline_reach_pp": round(d["mer_reach_true_pct"] - best["mer_reach_true_pct"], 2)
                        if best else ""})
    return out


# ---------------------------------------------------------------- noise-free premature step-downs
def premature_family(args):
    tt, per, seed, steps = args
    run_all.N_STEPS = steps
    res = {}
    for j in range(per):
        s = run_all._traj_seed(seed, tt, j)
        rho = run_all.make_trajectory(tt, s)
        saved = {k: getattr(run_all, k) for k in NOISE_KEYS}
        for k in NOISE_KEYS:
            setattr(run_all, k, 0.0)
        clean = run_all._level_series(run_all.make_trajectory(tt, s))
        for k, v in saved.items():
            setattr(run_all, k, v)
        lv = run_all._level_series(rho)
        times = [i * run_all.DT_SECONDS for i in range(len(rho))]
        reps = {"Hysteresis": rb.hysteresis(lv), "Timed-release max-hold": rb.timed_release(lv),
                "Decayed max": rb.decayed_max(rho), "DRAS-5 (full)": dras(times, rho, 1)}
        for name, rep in reps.items():
            drops = [i for i in range(1, len(rep)) if rep[i] < rep[i - 1]]
            a = res.setdefault(name, [0, 0, 0])
            a[0] += len(drops)
            a[1] += sum(rep[i] < clean[i] for i in drops)
            a[2] += int(any(rep[i] < clean[i] for i in drops))
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=5000)
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()
    out = REPO / "results"
    per = args.n // len(run_all.TYPES)

    with ProcessPoolExecutor(max_workers=4) as ex:
        parts = list(ex.map(ward_family, [(tt, per, args.seed) for tt in run_all.TYPES]))
    acc = {}
    for p in parts:
        for k, v in p.items():
            a = acc.setdefault(k, [0, 0.0, 0, 0])
            for i in range(4):
                a[i] += v[i]
    rows = [dict(r, setting=f'ward {r["setting"]}') for r in to_rows(acc)]
    rows += to_rows(wrapper_rows(args.n, args.seed))
    with open(out / "tradeoff_frontier.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    mrows = matched(rows)
    with open(out / "tradeoff_matched.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(mrows[0]))
        w.writeheader()
        w.writerows(mrows)

    # E-04: long episodes through the unchanged recoverable_baselines evaluation.
    res = rb.run_cohort(args.n, args.seed, {"N_STEPS": LONG_STEPS})
    lrows = []
    for s in rb.SYSTEMS:
        for tt in list(run_all.TYPES) + ["OVERALL"]:
            data = res[tt][0][s] if tt != "OVERALL" else sum((res[t][0][s] for t in run_all.TYPES), [])
            lrows.append({"system": s, "trajectory_type": tt, "n": len(data), "n_steps": LONG_STEPS,
                          **rb._round(rb.aggregate(data))})
    with open(out / "long_episodes.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(lrows[0]))
        w.writeheader()
        w.writerows(lrows)
    pooled = {s: sum((res[t][0][s] for t in run_all.TYPES), []) for s in rb.SYSTEMS}
    d5 = pooled["DRAS-5 (full)"]
    summ = {"n_steps": LONG_STEPS, "episode_s": LONG_STEPS * run_all.DT_SECONDS, "paired_vs_dras5_full": {}}
    for s in ("Max-hold", "Hysteresis", "Timed-release max-hold", "Decayed max"):
        summ["paired_vs_dras5_full"][s] = {
            "end_excess_diff_ci95": rb.paired_ci([r["end_excess"] for r in d5], [r["end_excess"] for r in pooled[s]]),
            "oer_diff_pp_ci95": [100 * x for x in rb.paired_ci([r["oer"] for r in d5], [r["oer"] for r in pooled[s]])]}
    gb = {}
    for t in run_all.TYPES:
        for k, v in res[t][1]["grants_by_from"].items():
            gb[f"{t}:S{k}->S{k - 1}"] = v
    summ["c5_grants_by_family_and_step"] = gb
    (out / "long_episodes_summary.json").write_text(json.dumps(summ, indent=2) + "\n", encoding="utf-8")

    # E-02: premature step-downs against the noise-free level.
    prow = []
    for steps in (run_all.N_STEPS, LONG_STEPS):
        with ProcessPoolExecutor(max_workers=4) as ex:
            parts = list(ex.map(premature_family, [(tt, per, args.seed, steps) for tt in run_all.TYPES]))
        for name in ("Hysteresis", "Timed-release max-hold", "Decayed max", "DRAS-5 (full)"):
            d, p, tr = (sum(x[name][i] for x in parts) for i in range(3))
            prow.append({"n_steps": steps, "system": name, "stepdowns": d,
                         "premature_vs_noisefree": p,
                         "premature_pct_of_stepdowns": round(100 * p / d, 2) if d else "",
                         "trajectories_with_premature_pct": round(100 * tr / args.n, 2)})
    with open(out / "premature_noisefree.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(prow[0]))
        w.writeheader()
        w.writerows(prow)
    for r in mrows + prow:
        print(r)


if __name__ == "__main__":
    main()
