"""Max-hold baseline: the cheapest way to get MER = 0% without any of DRAS-5's machinery.

A reviewer's obvious objection to Theorem 1 is that a running maximum over the observed levels
also never misses an escalation, so the guarantee cannot be what distinguishes DRAS-5. This
script measures that baseline on the same seeded cohort as scripts/run_all.py and reports what
the naive version costs: it has no way back down, so its over-escalation grows with the episode
and it can never express recovery.

Three systems are compared over the same trajectories:
  max-hold(1)   running maximum of the level, re-read every sample
  max-hold(2)   the same, re-read every second sample (NEWS2's cadence)
  DRAS-5        read from results/summary.json (produced by run_all.py)

Output: results/maxhold_baseline.csv|json
Usage:  python scripts/maxhold_baseline.py [--n 5000] [--seed 42]
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))
sys.path.insert(0, str(REPO / "scripts"))

import run_all  # noqa: E402
from run_all import (TYPES, _level_series, make_trajectory, sustained_peak_level,  # noqa: E402
                     _traj_seed, run_dras5)


def maxhold_levels(rho, interval: int):
    """Level reported by a running maximum that is re-read every ``interval`` samples."""
    levels = _level_series(rho)
    out, cur, held = [], levels[0], levels[0]
    for i, lvl in enumerate(levels):
        if i % interval == 0:
            cur = lvl
            held = max(held, cur)
        out.append(held)
    return out


def _blank():
    # mer_end  : level at the episode's decision point is below the sustained peak
    #            (Definition 11, the definition used for the stateless baselines)
    # mer_ever : the system never reached the sustained peak at any point
    #            (the definition under which Theorem 1 gives DRAS-5 0%)
    return {"mer_end": [], "mer_ever": [], "oer": [], "over": 0, "steps": 0,
            "late_over": 0, "late_steps": 0}


def evaluate(n_traj: int, base_seed: int, intervals=(1, 2)):
    arms = [f"max-hold({iv})" for iv in intervals] + ["DRAS-5 (full)", "DRAS-5 (no C5)"]
    per_type = {arm: {tt: _blank() for tt in TYPES} for arm in arms}
    per_traj = max(1, n_traj // len(TYPES))

    for tt in TYPES:
        for j in range(per_traj):
            rho = make_trajectory(tt, _traj_seed(base_seed, tt, j))
            truth = _level_series(rho)
            peak = sustained_peak_level(rho)
            half = len(truth) // 2
            reports = {f"max-hold({iv})": maxhold_levels(rho, iv) for iv in intervals}
            # DRAS-5 on the identical trajectory, scored in the identical windows.
            reports["DRAS-5 (full)"] = [int(x) for x in run_dras5(rho, enable_c5=True)[0]]
            reports["DRAS-5 (no C5)"] = [int(x) for x in run_dras5(rho, enable_c5=False)[0]]
            for arm, rep in reports.items():
                d = per_type[arm][tt]
                d["mer_end"].append(1 if rep[-1] < peak else 0)
                d["mer_ever"].append(1 if max(rep) < peak else 0)
                over = sum(1 for t in range(len(truth)) if rep[t] > truth[t])
                d["oer"].append(over / len(truth))
                d["over"] += over
                d["steps"] += len(truth)
                d["late_over"] += sum(1 for t in range(half, len(truth)) if rep[t] > truth[t])
                d["late_steps"] += len(truth) - half
    return per_type


def main() -> None:
    ap = argparse.ArgumentParser(description="max-hold baseline for DRAS-5")
    ap.add_argument("--n", type=int, default=5000)
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()

    per_type = evaluate(args.n, args.seed)
    rows = []
    for arm, types in per_type.items():
        tot_over = sum(d["over"] for d in types.values())
        tot_steps = sum(d["steps"] for d in types.values())
        tot_end = sum(sum(d["mer_end"]) for d in types.values())
        tot_ever = sum(sum(d["mer_ever"]) for d in types.values())
        tot_n = sum(len(d["mer_end"]) for d in types.values())
        late_over = sum(d["late_over"] for d in types.values())
        late_steps = sum(d["late_steps"] for d in types.values())
        for tt, d in types.items():
            rows.append({"system": arm, "trajectory_type": tt,
                         "n": len(d["mer_end"]),
                         "mer_end_pct": round(100 * sum(d["mer_end"]) / len(d["mer_end"]), 2),
                         "mer_ever_pct": round(100 * sum(d["mer_ever"]) / len(d["mer_ever"]), 2),
                         "oer_pct": round(100 * d["over"] / d["steps"], 2)})
        rows.append({"system": arm, "trajectory_type": "OVERALL", "n": tot_n,
                     "mer_end_pct": round(100 * tot_end / tot_n, 2),
                     "mer_ever_pct": round(100 * tot_ever / tot_n, 2),
                     "oer_pct": round(100 * tot_over / tot_steps, 2)})
        rows.append({"system": arm, "trajectory_type": "OVERALL_second_half",
                     "n": tot_n, "mer_end_pct": round(100 * tot_end / tot_n, 2),
                     "mer_ever_pct": round(100 * tot_ever / tot_n, 2),
                     "oer_pct": round(100 * late_over / late_steps, 2)})

    summary_path = REPO / "results" / "summary.json"
    dras = json.loads(summary_path.read_text(encoding="utf-8")) if summary_path.exists() else {}

    out_csv = REPO / "results" / "maxhold_baseline.csv"
    with open(out_csv, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    (REPO / "results" / "maxhold_baseline.json").write_text(json.dumps({
        "seed": args.seed, "n_trajectories": args.n, "rows": rows,
        "dras5_reference": {"mer_pct": dras.get("mer_overall_pct", {}).get("dras5"),
                            "oer_with_c5_pct": dras.get("oer_overall_pct", {}).get("with_c5"),
                            "c5_grants": dras.get("c5_outcomes", {}).get("granted")},
    }, indent=2) + "\n", encoding="utf-8")

    print(f"{'system':>16} {'type':>22} {'MERend%':>8} {'MERever%':>9} {'OER%':>7}")
    for r in rows:
        print(f"{r['system']:>16} {r['trajectory_type']:>22} {r['mer_end_pct']:>8.2f} "
              f"{r['mer_ever_pct']:>9.2f} {r['oer_pct']:>7.2f}")
    print(f"\nDRAS-5 (results/summary.json): MER {dras.get('mer_overall_pct', {}).get('dras5')}%, "
          f"OER {dras.get('oer_overall_pct', {}).get('with_c5')}%, "
          f"{dras.get('c5_outcomes', {}).get('granted')} C5 grants")
    print("wrote", out_csv.relative_to(REPO))


if __name__ == "__main__":
    main()
