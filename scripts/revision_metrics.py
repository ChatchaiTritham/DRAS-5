"""Like-for-like MER, upstream-bias, C4-cap, magnitude-OER and bounded exhaustive checks.

Answers the objections a reviewer raises against the headline claim:

  1. MER must be scored with ONE definition for every system (end and reach, both against
     the sustained peak), including the stateless scorers read at every sample.
  2. MER_reach is a statement about the observations DRAS-5 receives (input-relative), not
     about the true patient level: a biased upstream shows the difference.
  3. C4 caps an unapproved move into S5 at S4, so reach against the true level is not 0 on the
     spike-to-emergency family when approval is withheld.
  4. Binary OER cannot see a single-step C5 grant; a magnitude OER (excess levels per sample)
     does, and is swept over the cooling-window scale.
  5. Bounded exhaustive check of C1/C4 and input-relative reach on the released state machine
     over every input sequence of length L from a band-representative alphabet.

Output: results/revision_metrics.json (+ csv per section). Usage: python scripts/revision_metrics.py
"""
from __future__ import annotations

import csv
import itertools
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))
sys.path.insert(0, str(REPO / "scripts"))

import run_all  # noqa: E402
from run_all import (TYPES, _level_series, _traj_seed, make_trajectory,  # noqa: E402
                     run_dras5, stateless_reported_levels, sustained_peak_level, DT_SECONDS)
from maxhold_baseline import maxhold_levels  # noqa: E402
from dras5 import states as states_mod  # noqa: E402
from dras5.state_machine import DRAS5StateMachine  # noqa: E402
from dras5.states import RiskState, risk_to_state, STATE_CONFIG  # noqa: E402

import logging  # noqa: E402
logging.disable(logging.CRITICAL)  # the machine logs every blocked move
N, SEED = 5000, 42
PER = N // len(TYPES)
RESULTS = REPO / "results"


def pct(a, b):
    return round(100.0 * a / b, 2)


# ---------------------------------------------------------------- 1. like-for-like MER
def like_for_like():
    arms = ["NEWS2 (every 2nd)", "MEWS (every 3rd)", "Stateless (every sample)",
            "Max-hold (every sample)", "DRAS-5 (no C5)", "DRAS-5 (full)"]
    acc = {a: {tt: {"end": 0, "reach": 0} for tt in TYPES} for a in arms}
    for tt in TYPES:
        for j in range(PER):
            rho = make_trajectory(tt, _traj_seed(SEED, tt, j))
            peak = sustained_peak_level(rho)
            rep = {
                "NEWS2 (every 2nd)": stateless_reported_levels(rho, 2),
                "MEWS (every 3rd)": stateless_reported_levels(rho, 3),
                "Stateless (every sample)": stateless_reported_levels(rho, 1),
                "Max-hold (every sample)": maxhold_levels(rho, 1),
                "DRAS-5 (no C5)": [int(x) for x in run_dras5(rho, False)[0]],
                "DRAS-5 (full)": [int(x) for x in run_dras5(rho, True)[0]],
            }
            for a, r in rep.items():
                acc[a][tt]["end"] += int(r[-1] < peak)
                acc[a][tt]["reach"] += int(max(r) < peak)
    rows = []
    for a in arms:
        row = {"system": a}
        for k in ("end", "reach"):
            for tt in TYPES:
                row[f"mer_{k}_{tt}"] = pct(acc[a][tt][k], PER)
            row[f"mer_{k}_overall"] = pct(sum(acc[a][tt][k] for tt in TYPES), N)
        rows.append(row)
    return rows


# ---------------------------------------------------------------- 2. biased upstream
def biased_upstream(factors=(1.0, 0.8, 0.6, 0.4)):
    rows = []
    for f in factors:
        miss_true = miss_in = 0
        for tt in TYPES:
            for j in range(PER):
                rho = make_trajectory(tt, _traj_seed(SEED, tt, j))
                true_peak = sustained_peak_level(rho)
                rho_in = [min(1.0, f * r) for r in rho]       # what the upstream model emits
                in_peak = sustained_peak_level(rho_in)
                reach = max(int(x) for x in run_dras5(rho_in, True)[0])
                miss_true += int(reach < true_peak)
                miss_in += int(reach < in_peak)
        rows.append({"upstream_gain": f, "mer_reach_vs_true_pct": pct(miss_true, N),
                     "mer_reach_vs_input_pct": pct(miss_in, N)})
    return rows


# ---------------------------------------------------------------- 3. C4 cap
def c4_cap():
    out = {}
    for approved in (True, False):
        miss_true = n = 0
        for j in range(PER):
            rho = make_trajectory("spike_emergency", _traj_seed(SEED, "spike_emergency", j))
            sm = DRAS5StateMachine(enable_constraints=True, enable_audit=False,
                                   require_human_approval=True)
            reach = 0
            for i, r in enumerate(rho):
                reach = max(reach, int(sm.update(risk_score=r, t=i * DT_SECONDS,
                                                 human_approved=approved)))
            miss_true += int(reach < sustained_peak_level(rho))
            n += 1
        out["approval_given" if approved else "approval_withheld"] = pct(miss_true, n)
    return out


# ---------------------------------------------------------------- 4. magnitude OER
def magnitude_oer(scales=(0.1, 0.25, 0.5, 1.0)):
    rows = []
    original = {k: v["t_cool"] for k, v in STATE_CONFIG.items() if v.get("t_cool") is not None}
    try:
        for s in scales:
            for k, v in original.items():
                STATE_CONFIG[k]["t_cool"] = v * s
            tot = {True: [0, 0, 0], False: [0, 0, 0]}   # excess levels, over samples, steps
            grants = 0
            for tt in TYPES:
                for j in range(PER):
                    rho = make_trajectory(tt, _traj_seed(SEED, tt, j))
                    truth = [int(risk_to_state(r)) for r in rho]
                    for c5 in (True, False):
                        st, c = run_dras5(rho, c5)
                        if c5:
                            grants += c["granted"]
                        for a, b in zip(st, truth):
                            tot[c5][0] += max(0, int(a) - b)
                            tot[c5][1] += int(int(a) > b)
                            tot[c5][2] += 1
            rows.append({
                "t_cool_scale": s, "c5_grants": grants,
                "excess_levels_per_sample_no_c5": round(tot[False][0] / tot[False][2], 4),
                "excess_levels_per_sample_c5": round(tot[True][0] / tot[True][2], 4),
                "binary_oer_no_c5_pct": pct(tot[False][1], tot[False][2]),
                "binary_oer_c5_pct": pct(tot[True][1], tot[True][2]),
            })
    finally:
        for k, v in original.items():
            STATE_CONFIG[k]["t_cool"] = v
    return rows


# ---------------------------------------------------------------- 5. bounded exhaustive check
BANDS = (0.15, 0.40, 0.60, 0.80, 0.95)    # one representative per tau band


def exhaustive(length: int, dt: float):
    """Every sequence of `length` steps over {band} x {alpha} x {deesc request with dual}."""
    symbols = [(b, a, d) for b in BANDS for a in (0, 1) for d in (0, 1)]
    checked = viol_c1 = viol_c4 = viol_reach = 0
    for seq in itertools.product(symbols, repeat=length):
        sm = DRAS5StateMachine(enable_constraints=True, enable_audit=False,
                               require_human_approval=True)
        prev, reach, need = RiskState.SAFE, 0, 0
        for i, (rho, alpha, d) in enumerate(seq):
            new = sm.update(risk_score=rho, t=i * dt, human_approved=bool(alpha),
                            deescalation_request=bool(d), dual_approval=bool(d))
            tau = int(risk_to_state(rho))
            registered = tau if (tau < 5 or alpha) else 4           # C4 caps unapproved S5 at S4
            need = max(need, registered)
            if new < prev and not d:                                # C1: decrease only on a C5 request
                viol_c1 += 1
            if new < prev and prev - new != 1:                      # C5(c): single step only
                viol_c1 += 1
            if new == RiskState.EMERGENCY and prev != RiskState.EMERGENCY and not alpha:
                viol_c4 += 1                                        # C4: no entry to S5 unapproved
            reach = max(reach, int(new))
            prev = new
        viol_reach += int(reach < need)                             # reach vs registered input
        checked += 1
    return {"length": length, "dt_s": dt, "sequences": checked, "alphabet": len(symbols),
            "c1_c5c_violations": viol_c1, "c4_violations": viol_c4,
            "input_relative_reach_violations": viol_reach}


def write_csv(name, rows):
    with open(RESULTS / name, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)


def main():
    out = {"seed": SEED, "n": N}
    out["like_for_like"] = like_for_like()
    write_csv("revision_like_for_like.csv", out["like_for_like"])
    out["biased_upstream"] = biased_upstream()
    write_csv("revision_biased_upstream.csv", out["biased_upstream"])
    out["c4_cap_mer_vs_sustained_peak_pct"] = c4_cap()
    out["magnitude_oer"] = magnitude_oer()
    write_csv("revision_magnitude_oer.csv", out["magnitude_oer"])
    out["exhaustive"] = [exhaustive(4, dt) for dt in (10.0, 70.0, 250.0, 700.0)]
    write_csv("revision_exhaustive.csv", out["exhaustive"])
    (RESULTS / "revision_metrics.json").write_text(json.dumps(out, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
