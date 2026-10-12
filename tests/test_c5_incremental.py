"""The O(1) incremental C5 window test equals the v1.4.0 window rescan (Theorem 6, D-10)."""
import random

from dras5.state_machine import DRAS5StateMachine
from dras5.states import RiskState


def _drive(seed, dt, n=400):
    rng = random.Random(seed)
    sm = DRAS5StateMachine(enable_audit=False, require_human_approval=False)
    level = rng.random()
    checked = 0
    for i in range(n):
        level = min(1.0, max(0.0, level + rng.gauss(0, 0.08) - (0.02 if rng.random() < 0.6 else -0.02)))
        t = i * dt
        # compare the two decisions on the state the next update will see
        before = sm.current_state
        new = sm.update(level, t=t, human_approved=True, deescalation_request=True, dual_approval=True)
        if before not in (RiskState.SAFE, RiskState.EMERGENCY) and new == before:
            assert sm._c5_window_ok(before, t) == sm._c5_window_ok_rescan(before, t)
            checked += 1
    return checked


def test_incremental_equals_rescan():
    total = 0
    for seed in range(60):
        for dt in (5.0, 10.0, 37.0, 60.0):
            total += _drive(seed, dt)
    assert total > 1000
