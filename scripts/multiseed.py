"""Headline metrics over several generator seeds, plus paired bootstrap CIs for DRAS-5 vs max-hold.

Every headline figure in the paper comes from one generator seed (42). This script regenerates
the cohort with ten generator seeds (42..51 by default) and reports, per seed and as mean and
sample SD across seeds:

  MER_end of NEWS2 (every 2nd) and MEWS (every 3rd)   end level below the sustained peak
  MER_reach and MER_end of DRAS-5 (full)
  binary OER of DRAS-5 (full) and max-hold (every sample)
  end-of-episode excess (levels) of DRAS-5 (full) and max-hold
  C5 grants

For the reference seed it also reports paired, seeded bootstrap 95% CIs (2,000 resamples of
trajectories) for the DRAS-5 minus max-hold difference in per-trajectory OER and in
end-of-episode excess.

Output: results/multiseed.csv, results/multiseed_summary.json, results/paired_bootstrap.json
Usage:  python scripts/multiseed.py [--n 5000] [--seeds 42-51] [--workers 8]
"""
from __future__ import annotations

import argparse
import csv
import json
import logging
import statistics
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))
sys.path.insert(0, str(REPO / "scripts"))

from run_all import (TYPES, _level_series, _traj_seed, make_trajectory,  # noqa: E402
                     run_dras5, stateless_reported_levels, sustained_peak_level)
from maxhold_baseline import maxhold_levels  # noqa: E402

PAIRED_RESAMPLES = 2000
PAIRED_SEED = 42
METRICS = ("mer_end_news2_pct", "mer_end_mews_pct", "mer_reach_dras5_pct", "mer_end_dras5_pct",
           "oer_dras5_pct", "oer_maxhold_pct", "end_excess_dras5", "end_excess_maxhold",
           "c5_granted")


def per_trajectory(n: int, seed: int):
    """Per-trajectory observations for one generator seed."""
    logging.disable(logging.CRITICAL)
    per = n // len(TYPES)
    obs = []
    for tt in TYPES:
        for j in range(per):
            rho = make_trajectory(tt, _traj_seed(seed, tt, j))
            truth = _level_series(rho)
            peak = sustained_peak_level(rho)
            states, c5 = run_dras5(rho, enable_c5=True)
            dras = [int(s) for s in states]
            mh = maxhold_levels(rho, 1)
            news2 = stateless_reported_levels(rho, 2)
            mews = stateless_reported_levels(rho, 3)
            steps = len(truth)
            obs.append({
                "news2_end": 1 if news2[-1] < peak else 0,
                "mews_end": 1 if mews[-1] < peak else 0,
                "dras_reach": 1 if max(dras) < max(truth) else 0,
                "dras_end": 1 if dras[-1] < peak else 0,
                "dras_oer": sum(1 for a, b in zip(dras, truth) if a > b) / steps,
                "mh_oer": sum(1 for a, b in zip(mh, truth) if a > b) / steps,
                "dras_excess": max(0, dras[-1] - truth[-1]),
                "mh_excess": max(0, mh[-1] - truth[-1]),
                "granted": c5["granted"],
            })
    return obs


def seed_row(args):
    n, seed = args
    obs = per_trajectory(n, seed)
    m = len(obs)

    def mean(key, scale=100.0, nd=2):
        return round(scale * sum(o[key] for o in obs) / m, nd)

    return seed, {
        "seed": seed, "n": m,
        "mer_end_news2_pct": mean("news2_end"),
        "mer_end_mews_pct": mean("mews_end"),
        "mer_reach_dras5_pct": mean("dras_reach"),
        "mer_end_dras5_pct": mean("dras_end"),
        "oer_dras5_pct": mean("dras_oer"),
        "oer_maxhold_pct": mean("mh_oer"),
        "end_excess_dras5": mean("dras_excess", 1.0, 3),
        "end_excess_maxhold": mean("mh_excess", 1.0, 3),
        "c5_granted": sum(o["granted"] for o in obs),
    }, obs


def paired_bootstrap(diffs, scale, n_boot=PAIRED_RESAMPLES, seed=PAIRED_SEED):
    import numpy as np
    d = np.asarray(diffs, dtype=float)
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, len(d), size=(n_boot, len(d)))
    means = d[idx].mean(axis=1) * scale
    return float(d.mean() * scale), float(np.percentile(means, 2.5)), float(np.percentile(means, 97.5))


def main() -> None:
    ap = argparse.ArgumentParser(description="multi-seed headline metrics for DRAS-5")
    ap.add_argument("--n", type=int, default=5000)
    ap.add_argument("--seeds", default="42-51")
    ap.add_argument("--workers", type=int, default=8)
    args = ap.parse_args()
    lo, hi = (int(x) for x in args.seeds.split("-"))
    seeds = list(range(lo, hi + 1))
    with ProcessPoolExecutor(max_workers=args.workers) as ex:
        results = list(ex.map(seed_row, [(args.n, s) for s in seeds]))
    rows = [r for _, r, _ in results]
    ref_seed = seeds[0]
    ref_obs = next(o for s, _, o in results if s == ref_seed)

    summary = {"n_trajectories_per_seed": args.n, "seeds": seeds, "sd": "sample SD (n-1)"}
    for k in METRICS:
        vals = [r[k] for r in rows]
        summary[k] = {"mean": round(statistics.mean(vals), 3), "sd": round(statistics.stdev(vals), 3),
                      "min": min(vals), "max": max(vals)}

    oer = paired_bootstrap([o["dras_oer"] - o["mh_oer"] for o in ref_obs], 100.0)
    exc = paired_bootstrap([o["dras_excess"] - o["mh_excess"] for o in ref_obs], 1.0)
    paired = {
        "seed": ref_seed, "n_trajectories": len(ref_obs), "resamples": PAIRED_RESAMPLES,
        "bootstrap_seed": PAIRED_SEED, "ci": "95% percentile, paired over trajectories",
        "oer_diff_dras5_minus_maxhold_pp": {"mean": round(oer[0], 2), "ci_lo": round(oer[1], 2),
                                            "ci_hi": round(oer[2], 2)},
        "end_excess_diff_dras5_minus_maxhold": {"mean": round(exc[0], 3), "ci_lo": round(exc[1], 3),
                                                "ci_hi": round(exc[2], 3)},
    }
    out = REPO / "results"
    with open(out / "multiseed.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    (out / "multiseed_summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    (out / "paired_bootstrap.json").write_text(json.dumps(paired, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=1))
    print(json.dumps(paired, indent=1))


if __name__ == "__main__":
    main()
