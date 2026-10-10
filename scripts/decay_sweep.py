"""Does the decay rate lambda change DRAS-5's behaviour? A lambda x T_cool sweep.

At the default parameters lambda has no measurable effect on binary over-escalation (Table
tab:cool and the +/-15% sensitivity sweep). This sweep asks whether the decay guard binds in
any regime: every decay rate lambda_k is scaled by a common factor (0.25x .. 16x) and every
cooling window T_cool by a common factor, including regimes where T_cool < T_max for every
state (scale 0.3 and 0.1). For each configuration it reports, on the seeded cohort:

  c5_granted / denied_decay / denied_cooling / denied_monotone   C5 request outcomes
  binary_oer_pct                               fraction of samples above the true level
  excess_levels_per_sample                     mean levels above the true level per sample
  end_excess_levels                            mean final reported level minus final true level
  mean_first_grant_s                           mean time from episode start to the first grant
  premature_grants                             grants that land below the true level (unsafe)

and the half-lives ln2/lambda_k of S2..S4 so the regime can be read clinically.

Output: results/decay_sweep.csv.   Usage: python scripts/decay_sweep.py [--n 5000] [--seed 42]
"""
from __future__ import annotations

import argparse
import csv
import logging
import math
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))
sys.path.insert(0, str(REPO / "scripts"))

from dras5 import states as states_mod  # noqa: E402
from dras5.states import RiskState  # noqa: E402
from run_all import (DT_SECONDS, TYPES, _level_series, _traj_seed,  # noqa: E402
                     make_trajectory, run_dras5)

DEFAULTS = {st: dict(spec) for st, spec in states_mod.STATE_CONFIG.items()}
LAMBDA_SCALES = (0.25, 0.5, 1.0, 2.0, 4.0, 8.0, 16.0)
TCOOL_SCALES = (1.0, 0.3, 0.1)


def run_configuration(args):
    n, seed, lam_scale, tc_scale = args
    logging.disable(logging.CRITICAL)
    cfg = states_mod.STATE_CONFIG
    # Worker processes are reused across configurations, so scale from the shipped
    # defaults every time (never from a previously scaled value).
    for state, spec in cfg.items():
        if spec.get("lam") is not None:
            spec["lam"] = DEFAULTS[state]["lam"] * lam_scale
        if spec.get("t_cool") is not None:
            spec["t_cool"] = DEFAULTS[state]["t_cool"] * tc_scale
    per = n // len(TYPES)
    tot = {"granted": 0, "denied_decay": 0, "denied_cooling": 0, "denied_monotone": 0}
    over = excess = steps = end_excess = premature = 0
    first_grant_t, n_granted_traj = 0.0, 0
    for tt in TYPES:
        for j in range(per):
            rho = make_trajectory(tt, _traj_seed(seed, tt, j))
            truth = _level_series(rho)
            states, c5 = run_dras5(rho, enable_c5=True)
            rep = [int(s) for s in states]
            for k in tot:
                tot[k] += c5[k]
            steps += len(rep)
            over += sum(1 for a, b in zip(rep, truth) if a > b)
            excess += sum(max(0, a - b) for a, b in zip(rep, truth))
            end_excess += max(0, rep[-1] - truth[-1])
            drops = [t for t in range(1, len(rep)) if rep[t] < rep[t - 1]]
            premature += sum(1 for t in drops if rep[t] < truth[t])
            if drops:
                first_grant_t += drops[0] * DT_SECONDS
                n_granted_traj += 1
    m = per * len(TYPES)
    row = {
        "lambda_scale": lam_scale, "t_cool_scale": tc_scale,
        "half_life_s2_s": round(math.log(2) / cfg[RiskState.MONITOR]["lam"], 1),
        "half_life_s3_s": round(math.log(2) / cfg[RiskState.ALERT]["lam"], 1),
        "half_life_s4_s": round(math.log(2) / cfg[RiskState.CRITICAL]["lam"], 1),
        "t_cool_s4_s": cfg[RiskState.CRITICAL]["t_cool"],
        "c5_granted": tot["granted"], "c5_denied_decay": tot["denied_decay"],
        "c5_denied_cooling": tot["denied_cooling"],
        "c5_denied_monotone": tot["denied_monotone"],
        "trajectories_with_grant": n_granted_traj,
        "premature_grants": premature,
        "binary_oer_pct": round(100.0 * over / steps, 2),
        "excess_levels_per_sample": round(excess / steps, 4),
        "end_excess_levels": round(end_excess / m, 3),
        "mean_first_grant_s": round(first_grant_t / n_granted_traj, 1) if n_granted_traj else None,
    }
    return row


def main() -> None:
    ap = argparse.ArgumentParser(description="DRAS-5 decay-rate x cooling-window sweep")
    ap.add_argument("--n", type=int, default=5000)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--workers", type=int, default=8)
    args = ap.parse_args()
    grid = [(args.n, args.seed, lam, tc) for tc in TCOOL_SCALES for lam in LAMBDA_SCALES]
    with ProcessPoolExecutor(max_workers=args.workers) as ex:
        rows = list(ex.map(run_configuration, grid))
    out = REPO / "results" / "decay_sweep.csv"
    with open(out, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    for r in rows:
        print(r)


if __name__ == "__main__":
    main()
