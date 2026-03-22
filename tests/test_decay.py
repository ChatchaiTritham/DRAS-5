"""Tests for dras5.decay — exponential risk decay (Eq. 5)."""

import math

import pytest
from dras5.decay import DecayTracker
from dras5.states import RiskState


class TestDecayTracker:
    def test_effective_risk_equals_raw_when_no_peak(self):
        dt = DecayTracker()
        dt.reset(RiskState.MONITOR)
        rho_eff = dt.effective_risk(0.35, t=100, state=RiskState.MONITOR)
        assert rho_eff == 0.35

    def test_effective_risk_decays_from_peak(self):
        dt = DecayTracker()
        dt.reset(RiskState.CRITICAL)
        dt.update_peak(0.85, t=0)

        # At t=0, rho_eff = max(0.30, 0.85 * exp(0)) = 0.85
        rho_eff = dt.effective_risk(0.30, t=0, state=RiskState.CRITICAL)
        assert abs(rho_eff - 0.85) < 1e-6

        # At t=693 (one half-life for S4, lambda=0.001), ~0.425
        rho_eff = dt.effective_risk(0.30, t=693, state=RiskState.CRITICAL)
        expected = 0.85 * math.exp(-0.001 * 693)
        assert abs(rho_eff - expected) < 0.01

    def test_decay_rate_matches_table2(self):
        """S4: lambda=0.001, half-life=693.1s."""
        dt = DecayTracker()
        dt.reset(RiskState.CRITICAL)
        dt.update_peak(1.0, t=0)

        hl = math.log(2) / 0.001
        rho_eff = dt.effective_risk(0.0, t=hl, state=RiskState.CRITICAL)
        assert abs(rho_eff - 0.5) < 0.01

    def test_raw_risk_dominates_when_above_decay(self):
        dt = DecayTracker()
        dt.reset(RiskState.MONITOR)
        dt.update_peak(0.40, t=0)

        # If raw rho > decayed peak, raw wins
        rho_eff = dt.effective_risk(0.45, t=500, state=RiskState.MONITOR)
        assert rho_eff == 0.45

    def test_safe_state_returns_raw(self):
        dt = DecayTracker()
        dt.reset(RiskState.SAFE)
        dt.update_peak(0.80, t=0)
        rho_eff = dt.effective_risk(0.10, t=100, state=RiskState.SAFE)
        assert rho_eff == 0.10  # no decay for S1

    def test_peak_tracking(self):
        dt = DecayTracker()
        dt.reset(RiskState.ALERT)
        dt.update_peak(0.55, t=10)
        dt.update_peak(0.65, t=20)
        dt.update_peak(0.60, t=30)  # not a new peak
        assert dt.rho_peak == 0.65
        assert dt.t_peak == 20

    def test_reset_clears_peak(self):
        dt = DecayTracker()
        dt.update_peak(0.80, t=0)
        dt.reset(RiskState.MONITOR)
        assert dt.rho_peak == 0.0
