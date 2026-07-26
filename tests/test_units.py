"""
Independent unit tests for DRAS-5 pure/deterministic functions.

Written by an external test engineer to verify the core logic described in the
manuscript (risk-to-state mapping, exponential decay, half-life, de-escalation
latency, and the C1/C5 safety constraints) against tiny hand-made inputs.

pytest.ini sets `pythonpath = src`, but we add the path defensively too.
"""

import math
import os
import sys

import pytest

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_SRC = os.path.join(_REPO_ROOT, "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

from dras5.states import (  # noqa: E402
    RiskState,
    STATE_CONFIG,
    risk_to_state,
    half_life,
    min_deescalation_latency,
)
from dras5.decay import DecayTracker  # noqa: E402
from dras5.constraints import check_c1, check_c5  # noqa: E402


# ---------------------------------------------------------------------------
# risk_to_state (Eq. 2) — boundary / monotonicity
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "rho, expected",
    [
        (0.0, RiskState.SAFE),
        (0.29, RiskState.SAFE),
        (0.30, RiskState.MONITOR),   # lower boundary inclusive
        (0.49, RiskState.MONITOR),
        (0.50, RiskState.ALERT),
        (0.70, RiskState.CRITICAL),
        (0.89, RiskState.CRITICAL),
        (0.90, RiskState.EMERGENCY),
        (1.00, RiskState.EMERGENCY),
    ],
)
def test_risk_to_state_boundaries(rho, expected):
    assert risk_to_state(rho) == expected


def test_risk_to_state_rejects_out_of_range():
    with pytest.raises(ValueError):
        risk_to_state(-0.01)
    with pytest.raises(ValueError):
        risk_to_state(1.01)


def test_risk_to_state_is_monotonic_nondecreasing():
    states = [int(risk_to_state(r / 100.0)) for r in range(0, 101)]
    assert states == sorted(states)


# ---------------------------------------------------------------------------
# half_life (Proposition 1): t_1/2 = ln(2)/lambda
# ---------------------------------------------------------------------------

def test_half_life_matches_formula_for_monitor():
    lam = STATE_CONFIG[RiskState.MONITOR]["lam"]
    assert half_life(RiskState.MONITOR) == pytest.approx(math.log(2) / lam)


def test_half_life_none_for_states_without_decay():
    # SAFE and EMERGENCY have lam=None -> no decay -> no half-life.
    assert half_life(RiskState.SAFE) is None
    assert half_life(RiskState.EMERGENCY) is None


# ---------------------------------------------------------------------------
# min_deescalation_latency (Proposition 2): sum of t_cool for j=2..k
# ---------------------------------------------------------------------------

def test_min_deescalation_latency_sums_cooling_periods():
    # From CRITICAL (S4): t_cool(S2)+t_cool(S3)+t_cool(S4) = 600+300+180 = 1080
    expected = 600.0 + 300.0 + 180.0
    assert min_deescalation_latency(RiskState.CRITICAL) == pytest.approx(expected)
    # From SAFE there is nothing to cool through.
    assert min_deescalation_latency(RiskState.SAFE) == 0.0
    # Latency must be non-decreasing as the start state climbs.
    lat = [min_deescalation_latency(RiskState(k)) for k in range(1, 6)]
    assert lat == sorted(lat)


# ---------------------------------------------------------------------------
# DecayTracker (Eq. 5): rho_eff = max(rho, rho_peak * exp(-lam*dt))
# ---------------------------------------------------------------------------

def test_decay_tracker_envelope_decreases_over_time():
    tr = DecayTracker()
    tr.update_peak(0.8, t=0.0)
    assert tr.rho_peak == 0.8 and tr.t_peak == 0.0

    lam = STATE_CONFIG[RiskState.MONITOR]["lam"]
    # At t=0 with low instantaneous risk, effective risk = the peak itself.
    assert tr.effective_risk(0.1, t=0.0, state=RiskState.MONITOR) == pytest.approx(0.8)
    # Later, the decayed envelope dominates and equals the closed form.
    t = 200.0
    expected = 0.8 * math.exp(-lam * t)
    assert tr.effective_risk(0.1, t=t, state=RiskState.MONITOR) == pytest.approx(expected)
    # Effective risk never drops below the instantaneous risk floor.
    assert tr.effective_risk(0.6, t=10_000.0, state=RiskState.MONITOR) == pytest.approx(0.6)


def test_decay_tracker_no_decay_states_return_raw_risk():
    # SAFE / EMERGENCY have lam=None -> effective risk == instantaneous risk.
    tr = DecayTracker()
    tr.update_peak(0.95, t=0.0)
    assert tr.effective_risk(0.2, t=500.0, state=RiskState.SAFE) == pytest.approx(0.2)
    assert tr.effective_risk(0.2, t=500.0, state=RiskState.EMERGENCY) == pytest.approx(0.2)


# ---------------------------------------------------------------------------
# C1 (Theorem 1): monotonic escalation, no downgrade without C5 approval
# ---------------------------------------------------------------------------

def test_check_c1_allows_escalation_and_blocks_unapproved_downgrade():
    ok, _ = check_c1(RiskState.MONITOR, RiskState.ALERT)
    assert ok is True
    ok, _ = check_c1(RiskState.ALERT, RiskState.ALERT)  # self-transition
    assert ok is True
    ok, _ = check_c1(RiskState.CRITICAL, RiskState.MONITOR)  # downgrade, no approval
    assert ok is False
    ok, _ = check_c1(RiskState.CRITICAL, RiskState.MONITOR, c5_approved=True)
    assert ok is True


# ---------------------------------------------------------------------------
# C5 (Theorem 5): bounded, approved, sustained de-escalation
# ---------------------------------------------------------------------------

def test_check_c5_grants_sustained_recovery():
    # check_c5 tests the series against the TARGET state's theta (S_{k-1}).
    # From ALERT (S3) the target is MONITOR whose theta=0.30, so a non-increasing
    # series entirely below 0.30 with both approvals must be granted.
    assert STATE_CONFIG[RiskState.MONITOR]["theta"] == 0.30
    ok, msg = check_c5(RiskState.ALERT, series=[0.25, 0.20, 0.15], alpha1=True, alpha2=True)
    assert ok is True, msg


def test_check_c5_denies_missing_approval_and_boundary_states():
    # Missing physician approval.
    ok, _ = check_c5(RiskState.MONITOR, series=[0.1, 0.05], alpha1=False, alpha2=True)
    assert ok is False
    # Already SAFE -> cannot de-escalate further.
    ok, _ = check_c5(RiskState.SAFE, series=[0.1])
    assert ok is False
    # EMERGENCY requires full clinical review.
    ok, _ = check_c5(RiskState.EMERGENCY, series=[0.1])
    assert ok is False
    # Values above target threshold (MONITOR theta=0.30) are rejected.
    ok, _ = check_c5(RiskState.ALERT, series=[0.25, 0.40])
    assert ok is False
    # Non-monotone (rising) series rejected even when below threshold.
    ok, _ = check_c5(RiskState.ALERT, series=[0.10, 0.20, 0.15])
    assert ok is False
