"""Stateless-baseline missed-escalation rate as a function of the observation interval.

The NEWS2 and MEWS baselines in run_all.py differ only in how often the stateless score is
re-read (every 2nd and every 3rd sample). This sweep re-reads it every k-th sample for
k = 1..6 on the same seeded cohort and reports, per k, MER_end (Definition 11: level at the
last sample below the sustained peak) and MER_reach (level never reached the sustained peak),
overall and per trajectory family, with a seeded bootstrap 95% CI for the overall MER_end.

Output: results/interval_sweep.csv.   Usage: python scripts/interval_sweep.py [--n 5000] [--seed 42]
"""
from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))
sys.path.insert(0, str(REPO / "scripts"))

from run_all import (TYPES, _bootstrap_ci, _traj_seed, make_trajectory,  # noqa: E402
                     stateless_reported_levels, sustained_peak_level)

INTERVALS = (1, 2, 3, 4, 5, 6)


def main() -> None:
    ap = argparse.ArgumentParser(description="stateless-baseline observation-interval sweep")
    ap.add_argument("--n", type=int, default=5000)
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()
    per = args.n // len(TYPES)
    end = {k: {tt: [] for tt in TYPES} for k in INTERVALS}
    reach = {k: {tt: [] for tt in TYPES} for k in INTERVALS}
    for tt in TYPES:
        for j in range(per):
            rho = make_trajectory(tt, _traj_seed(args.seed, tt, j))
            peak = sustained_peak_level(rho)
            for k in INTERVALS:
                rep = stateless_reported_levels(rho, k)
                end[k][tt].append(1 if rep[-1] < peak else 0)
                reach[k][tt].append(1 if max(rep) < peak else 0)
    rows = []
    for k in INTERVALS:
        all_end = [v for tt in TYPES for v in end[k][tt]]
        all_reach = [v for tt in TYPES for v in reach[k][tt]]
        lo, hi = _bootstrap_ci(all_end)
        row = {"obs_interval": k, "n": len(all_end),
               "mer_end_pct": round(100 * sum(all_end) / len(all_end), 2),
               "mer_end_ci_lo": lo, "mer_end_ci_hi": hi,
               "mer_reach_pct": round(100 * sum(all_reach) / len(all_reach), 2)}
        for tt in TYPES:
            row[f"mer_end_{tt}_pct"] = round(100 * sum(end[k][tt]) / per, 2)
        rows.append(row)
    out = REPO / "results" / "interval_sweep.csv"
    with open(out, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    for r in rows:
        print(r)


if __name__ == "__main__":
    main()
