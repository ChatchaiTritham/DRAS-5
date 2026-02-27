"""
DRAS-5 State Machine Demo

Demonstrates all five constraints (C1--C5) and the exponential decay
de-escalation protocol.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from dras5 import (
    DRAS5StateMachine, RiskState, STATE_CONFIG,
    half_life, min_deescalation_latency, check_c5,
)


def header(text):
    print("\n" + "=" * 64)
    print(text.center(64))
    print("=" * 64)


def section(text):
    print("\n" + "-" * 64)
    print(text)
    print("-" * 64)


def main():
    header("DRAS-5 STATE MACHINE DEMO")

    # ---- 1. State parameters (Table 2) ----
    section("1. State Parameters (Table 2)")
    fmt = "  {:<12s} {:>6s}  {:>7s}  {:>8s}  {:>7s}  {:>7s}"
    print(fmt.format("State", "theta", "T_max", "lambda", "T_cool", "t_1/2"))
    for s in RiskState:
        cfg = STATE_CONFIG[s]
        t12 = half_life(s)
        print(fmt.format(
            s.name,
            f"{cfg['theta']:.2f}",
            f"{cfg['t_max']:.0f}" if cfg["t_max"] != float("inf") else "inf",
            f"{cfg['lam']}" if cfg["lam"] is not None else "---",
            f"{cfg['t_cool']:.0f}" if cfg["t_cool"] is not None else "---",
            f"{t12:.1f}" if t12 is not None else "---",
        ))

    # ---- 2. Gradual escalation ----
    section("2. Gradual Risk Escalation")
    sm = DRAS5StateMachine(require_human_approval=True)
    scenarios = [
        (0.15,  5.0, "Normal vitals"),
        (0.35, 15.0, "Slightly elevated"),
        (0.55, 25.0, "Moderate concern"),
        (0.75, 35.0, "Critical signs"),
    ]
    for rho, t, desc in scenarios:
        s = sm.update(risk_score=rho, t=t)
        print(f"  rho={rho:.2f}  t={t:5.1f}s  ->  {s.name:12s}  ({desc})")

    # ---- 3. C1: Monotonic escalation ----
    section("3. C1: Monotonic Escalation")
    s = sm.update(risk_score=0.20, t=36.0)
    print(f"  rho=0.20  ->  {s.name}  (C1 enforced: stays CRITICAL)")

    # ---- 4. C4: Human approval gate ----
    section("4. C4: Human Approval Gate (S4 -> S5)")
    s = sm.update(risk_score=0.95, t=40.0, human_approved=False)
    print(f"  rho=0.95  approved=False  ->  {s.name}  (blocked by C4)")
    s = sm.update(risk_score=0.95, t=41.0, human_approved=True)
    print(f"  rho=0.95  approved=True   ->  {s.name}  (C4 cleared)")

    # ---- 5. C3: Audit trail ----
    section("5. C3: Audit Trail")
    print(f"  Total transitions logged: {len(sm.get_history())}")
    for e in sm.get_history():
        print(f"    #{e.entry_id}  {e.from_state.name:10s} -> "
              f"{e.to_state.name:10s}  rho={e.risk_score:.3f}  "
              f"trigger={e.trigger}")

    # ---- 6. C5: Controlled de-escalation ----
    section("6. C5: Controlled De-escalation")
    sm2 = DRAS5StateMachine(require_human_approval=False)
    sm2.update(risk_score=0.55, t=0)
    print(f"  Entered ALERT at t=0")

    # Check with sustained decay below theta_2=0.30
    series_ok = [0.25, 0.22, 0.20, 0.18, 0.15]
    ok, msg = check_c5(RiskState.ALERT, series_ok, alpha1=True, alpha2=True)
    print(f"  C5 check (sustained decay, dual approval): {msg}")

    sm2.update(
        risk_score=0.15, t=50,
        deescalation_request=True,
        human_approved=True,
        dual_approval=True,
        rho_eff_series=series_ok,
    )
    print(f"  After C5: state = {sm2.current_state.name} (de-escalated)")

    # Check with missing approval
    series_bad = [0.25, 0.35, 0.20]
    ok, msg = check_c5(RiskState.MONITOR, series_bad, alpha1=True, alpha2=False)
    print(f"  C5 check (missing alpha2): {msg}")

    # ---- 7. C2: Timeout enforcement ----
    section("7. C2: Timeout Enforcement")
    sm3 = DRAS5StateMachine(require_human_approval=False)
    sm3.update(risk_score=0.35, t=0)
    print(f"  Entered MONITOR at t=0  (T_max=300s)")
    print(f"  check_timeout at t=200: {sm3.check_timeout(t=200)}")
    print(f"  check_timeout at t=302: {sm3.check_timeout(t=302)}")
    sm3.update(risk_score=0.35, t=302)
    print(f"  After timeout: state = {sm3.current_state.name} (auto-escalated)")

    # ---- 8. De-escalation latency ----
    section("8. Minimum De-escalation Latency (Proposition 2)")
    for s in [RiskState.MONITOR, RiskState.ALERT, RiskState.CRITICAL]:
        lat = min_deescalation_latency(s)
        print(f"  {s.name:10s} -> S1:  {lat:.0f}s  ({lat / 60:.1f} min)")

    # ---- 9. Statistics ----
    section("9. Session Statistics")
    stats = sm.get_statistics()
    for k, v in stats.items():
        print(f"  {k}: {v}")

    header("DEMO COMPLETE")
    print("\nNext steps:")
    print("  python -m pytest tests/ -v          # run 103 tests")
    print("  python -m dras5.cli                  # CLI demo")
    print("  jupyter lab notebooks/               # interactive notebook")
    print()


if __name__ == "__main__":
    main()
