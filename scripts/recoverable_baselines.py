"""Recoverable baselines, time-to-registration, paired CIs, mixture and generator sensitivity.

Answers the 2026-10-12 review (D-04, D-05, D-07, D-12):

  * D-04  recovery-capable baselines that need no state machine:
          hysteresis   step down one level after N consecutive readings below the level,
                       N = T_cool(level)/dt (the same windows DRAS-5 uses)
          timed-release max-hold   hold a level for T_cool(level) after the last reading at
                       or above it, then drop to the current reading
          decayed max  report tau(d_t), d_t = max(rho_t, d_{t-1} exp(-lambda dt)), the C5
                       envelope with no approvals, no window, no single-step limit, no C2
          S5 is absorbing in every recoverable baseline, as in DRAS-5.
  * D-05  time to registration of the true sustained peak; failure to register within
          5 minutes; paired bootstrap CIs (DRAS-5 vs NEWS2 on MER_end; CI of DRAS-5 MER_end;
          DRAS-5 vs each baseline on end excess and OER).
  * D-07  per-family results; Dirichlet(1,1,1,1) mixture-weight sensitivity; generator
          hyperparameter sensitivity (noise sigma, spike heights, spike recovery speed);
          C5 grants broken down by family and by transition.
  * D-12  the C2 dwell clock: DRAS-5 with c2_clock='rewarrant' and DRAS-5 with C2 removed.

Definitions (as in the paper): sustained peak = highest level held for >= 2 consecutive
samples; MER_end = final reported level < sustained peak; MER_reach = reported level never
reaches the sustained peak; OER = fraction of samples above the true level; excess = mean
levels above the true level per sample; end excess = final reported minus final true level
(floored at 0); premature step-down = a fall that lands below the true level at that sample.

Outputs: results/recoverable_baselines.csv  (system x family)
         results/recoverable_summary.json    (paired CIs, registration delays, grants)
         results/mixture_sensitivity.csv
         results/generator_sensitivity.csv
Usage:   python scripts/recoverable_baselines.py [--n 5000] [--seed 42]
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

logging.disable(logging.CRITICAL)
REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))
sys.path.insert(0, str(REPO / "scripts"))

import run_all  # noqa: E402
from dras5.state_machine import DRAS5StateMachine  # noqa: E402
from dras5.states import STATE_CONFIG, RiskState, risk_to_state  # noqa: E402

DT = run_all.DT_SECONDS
TYPES = run_all.TYPES
REG_LIMIT_S = 300.0  # "registered within 5 minutes"
N_BOOT = 2000
SYSTEMS = ["Stateless (every sample)", "NEWS2 (every 2nd)", "Max-hold",
           "Timed-release max-hold", "Hysteresis", "Decayed max",
           "DRAS-5 (no C5)", "DRAS-5 (full)", "DRAS-5 (full, C2 clock restarts)",
           "DRAS-5 (full, no C2)"]


def _window(level: int) -> int:
    tc = STATE_CONFIG[RiskState(level)].get("t_cool")
    return int(round(tc / DT)) if tc else 0


def _lam(level: int) -> float:
    lvl = min(max(level, 2), 4)
    return STATE_CONFIG[RiskState(lvl)]["lam"]


def hysteresis(levels):
    out, cur, below = [], levels[0], 0
    for lvl in levels:
        if lvl >= cur:
            cur, below = lvl, 0
        elif cur < 5:
            below += 1
            if below >= _window(cur):
                cur, below = cur - 1, 0
        out.append(cur)
    return out


def timed_release(levels):
    out, cur, last = [], levels[0], 0
    for i, lvl in enumerate(levels):
        if lvl >= cur:
            cur, last = lvl, i
        elif cur < 5 and i - last >= _window(cur):
            cur, last = lvl, i
        out.append(cur)
    return out


def decayed_max(rho):
    out, d, cur = [], rho[0], int(risk_to_state(rho[0]))
    for r in rho:
        d = max(r, d * math.exp(-_lam(cur) * DT))
        lvl = int(risk_to_state(min(1.0, d)))
        cur = 5 if cur == 5 else lvl
        out.append(cur)
    return out


def run_machine(rho, c5=True, c2_clock="entry", no_c2=False):
    """DRAS-5 on one series, as in run_all.run_dras5, with grant and timeout bookkeeping."""
    sm = DRAS5StateMachine(enable_constraints=True, enable_audit=False,
                           require_human_approval=False, c2_clock=c2_clock)
    if no_c2:
        sm.STATE_TIMEOUTS = {s: float("inf") for s in RiskState}
    levels, grants, timeouts, requests, eligible = [], [], 0, 0, 0
    for i, r in enumerate(rho):
        t = i * DT
        before = sm.current_state
        want = c5 and risk_to_state(r) < before and before not in (RiskState.SAFE, RiskState.EMERGENCY)
        requests += int(want)
        new = sm.update(r, t=t, human_approved=True, deescalation_request=want, dual_approval=want)
        if want and new < before:
            grants.append(int(before))
        elif new > before and new > max(before, risk_to_state(r)):
            timeouts += 1
        levels.append(int(new))
    return levels, grants, timeouts, requests


def first_sustained_index(levels, peak):
    for i in range(len(levels) - 1):
        if levels[i] >= peak and levels[i + 1] >= peak:
            return i
    return None


def score(rep, truth, peak, audited):
    n = len(truth)
    t0 = first_sustained_index(truth, peak)
    reg = next((i for i in range(t0, n) if rep[i] >= peak), None) if t0 is not None else None
    delay = None if reg is None else (reg - t0) * DT
    drops = [i for i in range(1, n) if rep[i] < rep[i - 1]]
    return {
        "mer_end": int(rep[-1] < peak),
        "mer_reach": int(max(rep) < peak),
        "oer": sum(1 for a, b in zip(rep, truth) if a > b) / n,
        "excess": sum(max(0, a - b) for a, b in zip(rep, truth)) / n,
        "end_excess": max(0, rep[-1] - truth[-1]),
        "delay": delay,
        "late": int(delay is None or delay > REG_LIMIT_S),
        "stepdowns": len(drops),
        "premature": sum(1 for i in drops if rep[i] < truth[i]),
        "silent": int(bool(drops) and not audited),
        "first_down": drops[0] * DT if drops else None,
    }


def evaluate_family(args):
    tt, n_per, seed, params = args
    for k, v in (params or {}).items():
        setattr(run_all, k, v)
    out = {s: [] for s in SYSTEMS}
    extra = {"grants_by_from": {}, "grants_per_traj": [], "timeouts": {}, "requests": 0}
    for j in range(n_per):
        rho = run_all.make_trajectory(tt, run_all._traj_seed(seed, tt, j))
        truth = run_all._level_series(rho)
        peak = run_all.sustained_peak_level(rho)
        full, g, to_full, req = run_machine(rho)
        noc5, _, to_noc5, _ = run_machine(rho, c5=False)
        rew, _, to_rew, _ = run_machine(rho, c2_clock="rewarrant")
        noc2, _, to_noc2, _ = run_machine(rho, no_c2=True)
        extra["requests"] += req
        extra["grants_per_traj"].append(len(g))
        for k in g:
            extra["grants_by_from"][k] = extra["grants_by_from"].get(k, 0) + 1
        for name, c in (("full", to_full), ("no_c5", to_noc5), ("rewarrant", to_rew), ("no_c2", to_noc2)):
            extra["timeouts"][name] = extra["timeouts"].get(name, 0) + c
        reps = {
            "Stateless (every sample)": (run_all.stateless_reported_levels(rho, 1), False),
            "NEWS2 (every 2nd)": (run_all.stateless_reported_levels(rho, 2), False),
            "Max-hold": (_maxhold(truth), False),
            "Timed-release max-hold": (timed_release(truth), False),
            "Hysteresis": (hysteresis(truth), False),
            "Decayed max": (decayed_max(rho), False),
            "DRAS-5 (no C5)": (noc5, True),
            "DRAS-5 (full)": (full, True),
            "DRAS-5 (full, C2 clock restarts)": (rew, True),
            "DRAS-5 (full, no C2)": (noc2, True),
        }
        for s, (rep, aud) in reps.items():
            out[s].append(score(rep, truth, peak, aud))
    return tt, out, extra


def _maxhold(levels):
    out, held = [], levels[0]
    for lvl in levels:
        held = max(held, lvl)
        out.append(held)
    return out


def _mean(v):
    v = [x for x in v if x is not None]
    return sum(v) / len(v) if v else None


def _pct(v, q):
    v = sorted(x for x in v if x is not None)
    return v[min(len(v) - 1, int(q * len(v)))] if v else None


def paired_ci(a, b, rng_seed=42, n_boot=N_BOOT):
    """Mean of a-b and its seeded paired-bootstrap 95% CI (a, b per trajectory)."""
    d = [x - y for x, y in zip(a, b)]
    n = len(d)
    rng = random.Random(rng_seed)
    means = sorted(sum(d[rng.randrange(n)] for _ in range(n)) / n for _ in range(n_boot))
    return [sum(d) / n, means[int(0.025 * n_boot)], means[int(0.975 * n_boot)]]


def run_cohort(n, seed, params=None, workers=4):
    per = n // len(TYPES)
    with ProcessPoolExecutor(max_workers=workers) as ex:
        res = list(ex.map(evaluate_family, [(tt, per, seed, params) for tt in TYPES]))
    return {tt: (out, extra) for tt, out, extra in res}


def aggregate(rows):
    return {
        "mer_end_pct": 100 * _mean([r["mer_end"] for r in rows]),
        "mer_reach_pct": 100 * _mean([r["mer_reach"] for r in rows]),
        "oer_pct": 100 * _mean([r["oer"] for r in rows]),
        "excess_levels": _mean([r["excess"] for r in rows]),
        "end_excess_levels": _mean([r["end_excess"] for r in rows]),
        "median_delay_s": _pct([r["delay"] for r in rows], 0.5),
        "p90_delay_s": _pct([r["delay"] for r in rows], 0.9),
        "not_registered_5min_pct": 100 * _mean([r["late"] for r in rows]),
        "stepdowns": sum(r["stepdowns"] for r in rows),
        "premature_stepdowns": sum(r["premature"] for r in rows),
        "silent_pct": 100 * _mean([r["silent"] for r in rows]),
        "mean_first_stepdown_s": _mean([r["first_down"] for r in rows]),
    }


def _round(d):
    return {k: (round(v, 3) if isinstance(v, float) else v) for k, v in d.items()}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=5000)
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()
    res = run_cohort(args.n, args.seed)

    rows = []
    for s in SYSTEMS:
        for tt in list(TYPES) + ["OVERALL"]:
            data = res[tt][0][s] if tt != "OVERALL" else sum((res[t][0][s] for t in TYPES), [])
            rows.append({"system": s, "trajectory_type": tt, "n": len(data), **_round(aggregate(data))})
    out = REPO / "results"
    with open(out / "recoverable_baselines.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)

    pooled = {s: sum((res[t][0][s] for t in TYPES), []) for s in SYSTEMS}
    d5 = pooled["DRAS-5 (full)"]
    summary = {"seed": args.seed, "n": args.n, "bootstrap_resamples": N_BOOT,
               "registration_limit_s": REG_LIMIT_S}
    summary["dras5_mer_end_pct_ci95"] = [100 * x for x in paired_ci([r["mer_end"] for r in d5], [0] * len(d5))]
    summary["mer_end_dras5_minus_news2_pp_ci95"] = [100 * x for x in paired_ci(
        [r["mer_end"] for r in d5], [r["mer_end"] for r in pooled["NEWS2 (every 2nd)"]])]
    summary["paired_vs_dras5_full"] = {}
    for s in SYSTEMS:
        if s == "DRAS-5 (full)":
            continue
        summary["paired_vs_dras5_full"][s] = {
            "end_excess_diff_ci95": paired_ci([r["end_excess"] for r in d5], [r["end_excess"] for r in pooled[s]]),
            "oer_diff_pp_ci95": [100 * x for x in paired_ci([r["oer"] for r in d5], [r["oer"] for r in pooled[s]])],
            "excess_diff_ci95": paired_ci([r["excess"] for r in d5], [r["excess"] for r in pooled[s]]),
        }
    grants_by_from = {}
    for t in TYPES:
        for k, v in res[t][1]["grants_by_from"].items():
            grants_by_from[f"{t}:S{k}->S{k - 1}"] = v
    summary["c5_grants_by_family_and_step"] = grants_by_from
    summary["c5_grants_per_trajectory_histogram"] = {
        t: {str(k): res[t][1]["grants_per_traj"].count(k) for k in sorted(set(res[t][1]["grants_per_traj"]))}
        for t in TYPES}
    summary["c5_requests"] = sum(res[t][1]["requests"] for t in TYPES)
    summary["timeout_escalations"] = {k: sum(res[t][1]["timeouts"].get(k, 0) for t in TYPES)
                                      for k in ("full", "no_c5", "rewarrant", "no_c2")}

    # D-07: Dirichlet mixture-weight sensitivity on the per-family means.
    fam = {s: {t: aggregate(res[t][0][s]) for t in TYPES} for s in SYSTEMS}
    rng = random.Random(args.seed)
    mix_systems = ["NEWS2 (every 2nd)", "Max-hold", "Hysteresis", "Timed-release max-hold",
                   "Decayed max", "DRAS-5 (full)"]
    draws = []
    for _ in range(N_BOOT):
        g = [rng.gammavariate(1.0, 1.0) for _ in TYPES]
        draws.append([x / sum(g) for x in g])
    mix_rows = []
    for s in mix_systems:
        for metric in ("mer_end_pct", "oer_pct", "end_excess_levels", "excess_levels"):
            vals = sorted(sum(w * fam[s][t][metric] for w, t in zip(wt, TYPES)) for wt in draws)
            mix_rows.append({"system": s, "metric": metric,
                             "equal_weights": round(sum(fam[s][t][metric] for t in TYPES) / 4, 3),
                             "median": round(vals[len(vals) // 2], 3),
                             "p2_5": round(vals[int(0.025 * len(vals))], 3),
                             "p97_5": round(vals[int(0.975 * len(vals))], 3)})
    for other in ("Max-hold", "Hysteresis", "Timed-release max-hold", "Decayed max"):
        for metric in ("end_excess_levels", "oer_pct"):
            diffs = [sum(w * (fam["DRAS-5 (full)"][t][metric] - fam[other][t][metric])
                         for w, t in zip(wt, TYPES)) for wt in draws]
            ds = sorted(diffs)
            mix_rows.append({"system": f"DRAS-5 (full) minus {other}", "metric": metric,
                             "equal_weights": round(sum(fam["DRAS-5 (full)"][t][metric] - fam[other][t][metric]
                                                        for t in TYPES) / 4, 3),
                             "median": round(ds[len(ds) // 2], 3), "p2_5": round(ds[int(0.025 * len(ds))], 3),
                             "p97_5": round(ds[int(0.975 * len(ds))], 3)})
    with open(out / "mixture_sensitivity.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(mix_rows[0]))
        w.writeheader()
        w.writerows(mix_rows)

    # D-07: generator hyperparameter sensitivity.
    base_noise = {k: getattr(run_all, k) for k in ("MONO_NOISE", "OSC_NOISE", "SPIKEE_NOISE", "SPIKEC_NOISE")}
    configs = [("baseline", {}),
               ("noise x0.5", {k: v * 0.5 for k, v in base_noise.items()}),
               ("noise x2", {k: v * 2 for k, v in base_noise.items()}),
               ("spike-to-emergency peak 0.95", {"SPIKEE_PEAK": 0.95}),
               ("spike-to-critical peak 0.74", {"SPIKEC_PEAK": 0.74}),
               ("spike-to-critical peak 0.85", {"SPIKEC_PEAK": 0.85}),
               ("spike recovery x0.5 (longer spikes)", {"SPIKEE_DECAY": run_all.SPIKEE_DECAY * 0.5,
                                                         "SPIKEC_DECAY": run_all.SPIKEC_DECAY * 0.5}),
               ("spike recovery x2 (shorter spikes)", {"SPIKEE_DECAY": run_all.SPIKEE_DECAY * 2,
                                                        "SPIKEC_DECAY": run_all.SPIKEC_DECAY * 2})]
    gen_rows = []
    for name, params in configs:
        r = res if not params else run_cohort(args.n, args.seed, params)
        for s in ("NEWS2 (every 2nd)", "Max-hold", "Hysteresis", "DRAS-5 (full)"):
            a = aggregate(sum((r[t][0][s] for t in TYPES), []))
            grants = sum(sum(r[t][1]["grants_per_traj"]) for t in TYPES) if s == "DRAS-5 (full)" else ""
            gen_rows.append({"configuration": name, "system": s,
                             "mer_end_pct": round(a["mer_end_pct"], 2), "oer_pct": round(a["oer_pct"], 2),
                             "end_excess_levels": round(a["end_excess_levels"], 3),
                             "not_registered_5min_pct": round(a["not_registered_5min_pct"], 2),
                             "premature_stepdowns": a["premature_stepdowns"], "c5_grants": grants})
    with open(out / "generator_sensitivity.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(gen_rows[0]))
        w.writeheader()
        w.writerows(gen_rows)

    (out / "recoverable_summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    for r in rows:
        if r["trajectory_type"] == "OVERALL":
            print(r)
    print(json.dumps(summary, indent=1)[:3000])


if __name__ == "__main__":
    main()
