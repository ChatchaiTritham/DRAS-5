"""Threshold and decay-rate sensitivity sweep for DRAS-5.

Re-runs the seeded evaluation cohort with the risk-to-state thresholds and the
per-state decay rates scaled by +/-15% (in 5% steps) and reports, for each
perturbed configuration, the missed-escalation rate (MER), the over-escalation
rate (OER) with and without C5, and the C5 grant count.

Everything is recomputed from the committed simulator and state machine; no
value is typed in. Output: results/sensitivity.csv (and sensitivity.json).

Usage:  python scripts/sensitivity_sweep.py [--n 5000] [--seed 42]
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
from dras5.state_machine import DRAS5StateMachine  # noqa: E402
from dras5.states import RiskState  # noqa: E402

import run_all  # noqa: E402

BASE_THRESHOLDS = (0.30, 0.50, 0.70, 0.90)  # tau boundaries S1|S2|S3|S4|S5
SCALES = (0.85, 0.90, 0.95, 1.00, 1.05, 1.10, 1.15)


def make_tau(scale: float):
    """Risk-to-state map with every boundary scaled by *scale* (clipped to 1.0)."""
    t1, t2, t3, t4 = (min(t * scale, 1.0) for t in BASE_THRESHOLDS)

    def tau(rho: float) -> RiskState:
        if rho < 0.0 or rho > 1.0:
            raise ValueError(f"Risk score must be in [0, 1], got {rho}")
        if rho >= t4:
            return RiskState.EMERGENCY
        if rho >= t3:
            return RiskState.CRITICAL
        if rho >= t2:
            return RiskState.ALERT
        if rho >= t1:
            return RiskState.MONITOR
        return RiskState.SAFE

    return tau, (t1, t2, t3, t4)


def scale_state_thresholds(scale: float) -> dict:
    """Scale the machine's own entry thresholds and the STATE_CONFIG boundaries.

    The state machine decides its target state from ``STATE_THRESHOLDS`` while the
    evaluation driver derives the patient's true level from ``risk_to_state``; both
    must move together, otherwise the machine and the ground truth would be scored
    against different thresholds.
    """
    original = {"machine": dict(DRAS5StateMachine.STATE_THRESHOLDS), "config": {}}
    DRAS5StateMachine.STATE_THRESHOLDS = {
        st: (min(v * scale, 1.0) if v > 0 else v)
        for st, v in DRAS5StateMachine.STATE_THRESHOLDS.items()
    }
    for st, spec in states_mod.STATE_CONFIG.items():
        original["config"][st] = (spec.get("theta"), spec.get("theta_upper"))
        for key in ("theta", "theta_upper"):
            v = spec.get(key)
            if isinstance(v, (int, float)) and v > 0:
                spec[key] = min(v * scale, 1.0)
    return original


def restore_state_thresholds(original: dict) -> None:
    DRAS5StateMachine.STATE_THRESHOLDS = original["machine"]
    for st, (theta, theta_upper) in original["config"].items():
        spec = states_mod.STATE_CONFIG[st]
        if theta is not None:
            spec["theta"] = theta
        if theta_upper is not None:
            spec["theta_upper"] = theta_upper


def scale_decay(scale: float) -> dict:
    """Scale every per-state decay rate lambda_k, returning the original values."""
    original = {}
    for name, spec in states_mod.STATE_CONFIG.items():
        if spec.get("lam") is not None:
            original[name] = spec["lam"]
            spec["lam"] = original[name] * scale
    return original


def restore_decay(original: dict) -> None:
    for name, lam in original.items():
        states_mod.STATE_CONFIG[name]["lam"] = lam


def run_configuration(n_traj: int, seed: int, tau_scale: float, lam_scale: float) -> dict:
    tau, bounds = make_tau(tau_scale)
    original_tau_states = states_mod.risk_to_state
    original_tau_runall = run_all.risk_to_state
    original_lams = scale_decay(lam_scale)
    original_thresholds = scale_state_thresholds(tau_scale)
    states_mod.risk_to_state = tau
    run_all.risk_to_state = tau
    try:
        out = run_all.evaluate(n_traj, seed)
    finally:
        states_mod.risk_to_state = original_tau_states
        run_all.risk_to_state = original_tau_runall
        restore_state_thresholds(original_thresholds)
        restore_decay(original_lams)

    # run_all.evaluate returns (mer_rows, oer_rows, c5_totals, oer_locator_rows, summary)
    summary = out[-1] if isinstance(out, tuple) else out
    c5_totals = out[2] if isinstance(out, tuple) else {}
    return {
        "threshold_scale": tau_scale,
        "decay_scale": lam_scale,
        "theta_1": round(bounds[0], 4),
        "theta_2": round(bounds[1], 4),
        "theta_3": round(bounds[2], 4),
        "theta_4": round(bounds[3], 4),
        "mer_dras5_pct": summary["mer_overall_pct"]["dras5"],
        "oer_no_c5_pct": summary["oer_overall_pct"]["no_c5"],
        "oer_with_c5_pct": summary["oer_overall_pct"]["with_c5"],
        "c5_granted": c5_totals.get("granted"),
    }


def main() -> None:
    ap = argparse.ArgumentParser(description="DRAS-5 sensitivity sweep")
    ap.add_argument("--n", type=int, default=5000, help="trajectories per configuration")
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()

    rows = []
    for scale in SCALES:  # thresholds perturbed, decay at nominal
        rows.append(run_configuration(args.n, args.seed, scale, 1.00))
    for scale in SCALES:  # decay perturbed, thresholds at nominal
        if scale == 1.00:
            continue
        rows.append(run_configuration(args.n, args.seed, 1.00, scale))

    out_csv = REPO / "results" / "sensitivity.csv"
    with open(out_csv, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    (REPO / "results" / "sensitivity.json").write_text(
        json.dumps({"seed": args.seed, "n_trajectories": args.n,
                    "threshold_scales": list(SCALES), "decay_scales": list(SCALES),
                    "rows": rows}, indent=2) + "\n", encoding="utf-8")

    print(f"{'thr':>5} {'lam':>5} {'MER%':>6} {'OER no-C5%':>11} {'OER C5%':>8} {'grants':>8}")
    for r in rows:
        print(f"{r['threshold_scale']:>5.2f} {r['decay_scale']:>5.2f} "
              f"{r['mer_dras5_pct']:>6.2f} {r['oer_no_c5_pct']:>11.2f} "
              f"{r['oer_with_c5_pct']:>8.2f} {str(r['c5_granted']):>8}")
    print("wrote", out_csv.relative_to(REPO))


if __name__ == "__main__":
    main()
