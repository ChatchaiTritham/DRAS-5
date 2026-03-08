"""
DRAS-5 Command-Line Interface

Provides two entry points:

    dras5-demo      Run an interactive demonstration
    dras5-validate  Validate constraint compliance on synthetic data
"""

from __future__ import annotations

import argparse
import sys

from .simulator import generate_trajectory, run_evaluation
from .state_machine import DRAS5StateMachine
from .states import STATE_CONFIG, RiskState, half_life, min_deescalation_latency


def _print_header(text: str) -> None:
    print("\n" + "=" * 64)
    print(text.center(64))
    print("=" * 64)


def _print_section(text: str) -> None:
    print("\n" + "-" * 64)
    print(text)
    print("-" * 64)


# ------------------------------------------------------------------
# dras5-demo
# ------------------------------------------------------------------


def demo() -> None:
    """Interactive demonstration of the DRAS-5 state machine."""
    _print_header("DRAS-5 STATE MACHINE DEMO")

    sm = DRAS5StateMachine(
        enable_constraints=True,
        enable_audit=True,
        require_human_approval=True,
        session_id="demo-session",
    )

    # 1. State parameters
    _print_section("1. State Parameters (Table 2)")
    fmt = "{:<12s}  {:>6s}  {:>8s}  {:>10s}  {:>8s}  {:>8s}"
    print(fmt.format("State", "theta", "T_max", "lambda", "T_cool", "t_1/2"))
    for s in RiskState:
        cfg = STATE_CONFIG[s]
        t12 = half_life(s)
        print(
            fmt.format(
                s.name,
                f"{cfg['theta']:.2f}",
                f"{cfg['t_max']:.0f}" if cfg["t_max"] != float("inf") else "inf",
                f"{cfg['lam']}" if cfg["lam"] is not None else "---",
                f"{cfg['t_cool']:.0f}" if cfg["t_cool"] is not None else "---",
                f"{t12:.1f}" if t12 is not None else "---",
            )
        )

    # 2. Gradual escalation
    _print_section("2. Gradual Risk Escalation")
    scenarios = [
        (0.15, 5.0, "Normal vitals"),
        (0.35, 15.0, "Slightly elevated"),
        (0.55, 25.0, "Moderate concern"),
        (0.75, 35.0, "Critical signs"),
    ]
    for rho, t, desc in scenarios:
        s = sm.update(risk_score=rho, t=t)
        print(f"  rho={rho:.2f}  t={t:5.1f}s  ->  {s.name:12s}  ({desc})")

    # 3. C4 gate
    _print_section("3. Human Approval Gate (C4)")
    s = sm.update(risk_score=0.95, t=45.0, human_approved=False)
    print(f"  rho=0.95  approved=False  ->  {s.name}  (blocked by C4)")
    s = sm.update(risk_score=0.95, t=46.0, human_approved=True)
    print(f"  rho=0.95  approved=True   ->  {s.name}  (C4 cleared)")

    # 4. Audit trail
    _print_section("4. Audit Trail (C3)")
    for i, entry in enumerate(sm.get_history(), 1):
        print(
            f"  #{i}  {entry.from_state.name:10s} -> "
            f"{entry.to_state.name:10s}  rho={entry.risk_score:.3f}  "
            f"trigger={entry.trigger}"
        )

    # 5. De-escalation latency
    _print_section("5. Minimum De-escalation Latency (Proposition 2)")
    for s in [RiskState.MONITOR, RiskState.ALERT, RiskState.CRITICAL]:
        lat = min_deescalation_latency(s)
        print(f"  {s.name:10s} -> S1:  {lat:.0f}s  ({lat / 60:.1f} min)")

    # 6. Statistics
    _print_section("6. Session Statistics")
    stats = sm.get_statistics()
    for k, v in stats.items():
        print(f"  {k}: {v}")

    _print_header("DEMO COMPLETE")


# ------------------------------------------------------------------
# dras5-validate
# ------------------------------------------------------------------


def validate() -> None:
    """Run constraint compliance validation on synthetic trajectories."""
    parser = argparse.ArgumentParser(description="DRAS-5 constraint validator")
    parser.add_argument(
        "-n",
        "--trajectories",
        type=int,
        default=5000,
        help="Number of trajectories (default: 5000)",
    )
    parser.add_argument(
        "--steps", type=int, default=100, help="Steps per trajectory (default: 100)"
    )
    parser.add_argument(
        "--dt", type=float, default=10.0, help="Time step in seconds (default: 10)"
    )
    parser.add_argument("--no-c5", action="store_true", help="Disable C5 de-escalation")
    args = parser.parse_args()

    _print_header("DRAS-5 CONSTRAINT VALIDATION")
    print(f"\n  Trajectories:  {args.trajectories}")
    print(f"  Steps/traj:    {args.steps}")
    print(f"  C5 enabled:    {not args.no_c5}")
    print(f"  Total evals:   {args.trajectories * args.steps}")

    result = run_evaluation(
        n_trajectories=args.trajectories,
        n_steps=args.steps,
        dt=args.dt,
        enable_c5=not args.no_c5,
    )

    _print_section("Results")
    print(f"  MER:  {result.mer * 100:.2f}%")
    print(f"  OER:  {result.oer * 100:.2f}%")
    print(f"\n  C1 violations:  {result.c1_violations}")
    print(f"  C2 violations:  {result.c2_violations}")
    print(f"  C3 violations:  {result.c3_violations}")
    print(f"  C4 violations:  {result.c4_violations}")

    _print_header("VALIDATION COMPLETE")


if __name__ == "__main__":
    demo()
