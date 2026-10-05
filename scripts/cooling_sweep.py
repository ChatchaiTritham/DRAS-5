"""Cooling-window sweep for DRAS-5: when does C5 reduce over-escalation?

At the default parameters every cooling window T_cool is at least twice the state's
timeout T_max, so the C2 timeout fires before most windows can complete and C5 leaves
the over-escalation rate unchanged. This sweep scales every T_cool by a common factor,
re-runs the seeded cohort and reports, per factor, the missed-escalation rate, the
over-escalation rate with and without C5, and the C5 outcome counts.

Everything is recomputed from the released simulator and state machine.
Output: results/cooling_sweep.csv (and cooling_sweep.json).

Usage:  python scripts/cooling_sweep.py [--n 5000] [--seed 42]
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

from dras5 import states as states_mod  # noqa: E402

import run_all  # noqa: E402

SCALES = (0.10, 0.20, 0.30, 0.50, 0.75, 1.00)


def run_configuration(n_traj: int, seed: int, scale: float) -> dict:
    original = {}
    for name, spec in states_mod.STATE_CONFIG.items():
        if spec.get("t_cool") is not None:
            original[name] = spec["t_cool"]
            spec["t_cool"] = original[name] * scale
    try:
        out = run_all.evaluate(n_traj, seed)
    finally:
        for name, t_cool in original.items():
            states_mod.STATE_CONFIG[name]["t_cool"] = t_cool
    summary = out[-1] if isinstance(out, tuple) else out
    c5 = out[2] if isinstance(out, tuple) else {}
    cfg = states_mod.STATE_CONFIG
    ratios = {name: (cfg[name]["t_cool"] * scale) / cfg[name]["t_max"] for name in original}
    no_c5 = summary["oer_overall_pct"]["no_c5"]
    with_c5 = summary["oer_overall_pct"]["with_c5"]
    return {
        "t_cool_scale": scale,
        "min_tcool_over_tmax": round(min(ratios.values()), 3),
        "max_tcool_over_tmax": round(max(ratios.values()), 3),
        "mer_reach_pct": summary["mer_overall_pct"]["dras5"],
        "oer_no_c5_pct": no_c5,
        "oer_with_c5_pct": with_c5,
        "oer_reduction_pp": round(no_c5 - with_c5, 2),
        "c5_requests": sum(v for v in c5.values() if isinstance(v, int)),
        "c5_granted": c5.get("granted"),
        "c5_denied_cooling": c5.get("denied_cooling"),
        "c5_denied_decay": c5.get("denied_decay"),
    }


def main() -> None:
    ap = argparse.ArgumentParser(description="DRAS-5 cooling-window sweep")
    ap.add_argument("--n", type=int, default=5000)
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()
    rows = [run_configuration(args.n, args.seed, s) for s in SCALES]
    out_csv = REPO / "results" / "cooling_sweep.csv"
    with open(out_csv, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    (REPO / "results" / "cooling_sweep.json").write_text(json.dumps(rows, indent=2), encoding="utf-8")
    for r in rows:
        print(r)


if __name__ == "__main__":
    main()
