"""Silent down-classification vs audited recovery, and what recovery buys over max-hold.

MER_end counts every trajectory whose final level is below its sustained peak, so an approved,
dual-signed C5 step-down is scored as a miss and a system that can never recover scores 0.
This script separates the two events the intro cares about:

  silent down-classification   a reported level drops with no audit record (Patient-A failure)
  audited step-down            a C5 grant: logged, dual-approved, single level
  premature step-down          a grant that lands BELOW the true level at that sample (unsafe)
  end-of-episode excess        levels by which the final reported level exceeds the final true level
                               (what a recovered patient is still labelled with)

Systems: stateless every sample, NEWS2 (every 2nd), max-hold (every sample), DRAS-5 without C5,
DRAS-5 with C5. Output: results/recovery_metrics.csv|json.   Usage: python scripts/recovery_metrics.py
"""
from __future__ import annotations

import csv
import json
import logging
import sys
from pathlib import Path

logging.disable(logging.CRITICAL)
REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))
sys.path.insert(0, str(REPO / "scripts"))

from run_all import (TYPES, _level_series, _traj_seed, make_trajectory,  # noqa: E402
                     run_dras5, stateless_reported_levels)
from maxhold_baseline import maxhold_levels  # noqa: E402

N, SEED = 5000, 42
PER = N // len(TYPES)
ARMS = ["Stateless (every sample)", "NEWS2 (every 2nd)", "Max-hold", "DRAS-5 (no C5)", "DRAS-5 (full)"]


def main() -> None:
    acc = {a: {tt: dict(silent=0, audited_traj=0, stepdowns=0, premature=0, end_excess=0.0, n=0)
               for tt in TYPES} for a in ARMS}
    for tt in TYPES:
        for j in range(PER):
            rho = make_trajectory(tt, _traj_seed(SEED, tt, j))
            truth = _level_series(rho)
            reps = {
                "Stateless (every sample)": (stateless_reported_levels(rho, 1), False),
                "NEWS2 (every 2nd)": (stateless_reported_levels(rho, 2), False),
                "Max-hold": (maxhold_levels(rho, 1), False),
                "DRAS-5 (no C5)": ([int(x) for x in run_dras5(rho, False)[0]], True),
                "DRAS-5 (full)": ([int(x) for x in run_dras5(rho, True)[0]], True),
            }
            for arm, (rep, audited) in reps.items():
                d = acc[arm][tt]
                drops = [t for t in range(1, len(rep)) if rep[t] < rep[t - 1]]
                d["n"] += 1
                if drops and not audited:
                    d["silent"] += 1                      # no audit trail exists for these drops
                if drops and audited:
                    d["audited_traj"] += 1                # every DRAS-5 decrease is a logged C5 grant
                d["stepdowns"] += len(drops) if audited else 0
                d["premature"] += sum(1 for t in drops if audited and rep[t] < truth[t])
                d["end_excess"] += max(0, rep[-1] - truth[-1])
    rows = []
    for arm in ARMS:
        for tt in list(TYPES) + ["OVERALL"]:
            if tt == "OVERALL":
                parts = [acc[arm][t] for t in TYPES]
                d = {k: sum(p[k] for p in parts) for k in parts[0]}
            else:
                d = acc[arm][tt]
            rows.append({"system": arm, "trajectory_type": tt, "n": d["n"],
                         "silent_downclass_traj_pct": round(100 * d["silent"] / d["n"], 2),
                         "audited_stepdown_traj_pct": round(100 * d["audited_traj"] / d["n"], 2),
                         "stepdown_events": d["stepdowns"],
                         "premature_stepdowns": d["premature"],
                         "end_excess_levels_mean": round(d["end_excess"] / d["n"], 3)})
    out = REPO / "results"
    with open(out / "recovery_metrics.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    (out / "recovery_metrics.json").write_text(json.dumps(rows, indent=2) + "\n", encoding="utf-8")
    for r in rows:
        if r["trajectory_type"] in ("OVERALL", "spike_critical"):
            print(r)


if __name__ == "__main__":
    main()
