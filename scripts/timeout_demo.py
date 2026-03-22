"""
DRAS-5 Timeout Detection Demo (C2)

Demonstrates timeout enforcement and auto-escalation using
simulated time (no real-time sleep needed).
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from dras5 import STATE_CONFIG, DRAS5StateMachine, RiskState


def main():
    print("=" * 60)
    print("DRAS-5 Timeout Detection Demo (C2)".center(60))
    print("=" * 60)

    print("\nState Timeouts (Table 2):")
    for s in [RiskState.MONITOR, RiskState.ALERT, RiskState.CRITICAL]:
        print(f"  {s.name:10s}: {STATE_CONFIG[s]['t_max']:.0f}s")

    # Demo: MONITOR timeout at 300s
    print("\n" + "-" * 60)
    print("Demo: MONITOR state (T_max = 300s)")
    print("-" * 60)

    sm = DRAS5StateMachine(require_human_approval=False)
    sm.update(risk_score=0.35, t=0)
    print(f"\n  Entered {sm.current_state.name} at t=0")

    for t in [100, 200, 299, 301]:
        timed_out = sm.check_timeout(t=t)
        remaining = sm.get_time_remaining(t=t)
        rem_str = f"{remaining:.0f}s" if remaining is not None else "inf"
        print(f"  t={t:4d}s  timeout={str(timed_out):5s}  remaining={rem_str}")

    # Trigger auto-escalation
    sm.update(risk_score=0.35, t=302)
    print(f"\n  After t=302s: state = {sm.current_state.name} (auto-escalated)")

    # Demo: cascading timeouts
    print("\n" + "-" * 60)
    print("Demo: Cascading Timeouts (MONITOR -> ALERT -> CRITICAL -> EMERGENCY)")
    print("-" * 60)

    sm2 = DRAS5StateMachine(require_human_approval=False)
    sm2.update(risk_score=0.35, t=0)
    print(f"  t=  0s  {sm2.current_state.name}")

    # MONITOR times out at 301s -> ALERT
    sm2.update(risk_score=0.35, t=302)
    print(f"  t=302s  {sm2.current_state.name} (timeout)")

    # ALERT times out at 302+121=423s -> CRITICAL
    sm2.update(risk_score=0.35, t=425)
    print(f"  t=425s  {sm2.current_state.name} (timeout)")

    # CRITICAL times out at 425+61=486s -> EMERGENCY
    sm2.update(risk_score=0.35, t=487)
    print(f"  t=487s  {sm2.current_state.name} (timeout)")

    print(f"\n  Audit trail ({len(sm2.get_history())} transitions):")
    for e in sm2.get_history():
        print(
            f"    {e.from_state.name:10s} -> {e.to_state.name:10s}  "
            f"trigger={e.trigger:12s}  t={e.timestamp:.0f}s"
        )

    print("\n" + "=" * 60)
    print("Demo Complete")
    print("=" * 60)
    print("\nKey points:")
    print("  - S2 (MONITOR):  max 300s, then auto-escalates to ALERT")
    print("  - S3 (ALERT):    max 120s, then auto-escalates to CRITICAL")
    print("  - S4 (CRITICAL): max  60s, then auto-escalates to EMERGENCY")
    print("  - S1 and S5 have no timeout (absorbing states)")
    print()


if __name__ == "__main__":
    main()
