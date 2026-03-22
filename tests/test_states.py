"""Tests for dras5.states — state definitions and risk-to-state mapping."""

import math

import pytest
from dras5.states import (
    STATE_CONFIG,
    RiskState,
    half_life,
    min_deescalation_latency,
    risk_to_state,
)


class TestRiskStateOrdering:
    """Verify Eq. 1: S1 < S2 < S3 < S4 < S5."""

    def test_ordering(self):
        assert RiskState.SAFE < RiskState.MONITOR < RiskState.ALERT
        assert RiskState.ALERT < RiskState.CRITICAL < RiskState.EMERGENCY

    def test_int_values(self):
        assert int(RiskState.SAFE) == 1
        assert int(RiskState.EMERGENCY) == 5


class TestRiskToState:
    """Verify Eq. 2: tau(rho) mapping."""

    @pytest.mark.parametrize(
        "rho,expected",
        [
            (0.00, RiskState.SAFE),
            (0.15, RiskState.SAFE),
            (0.29, RiskState.SAFE),
            (0.30, RiskState.MONITOR),
            (0.49, RiskState.MONITOR),
            (0.50, RiskState.ALERT),
            (0.69, RiskState.ALERT),
            (0.70, RiskState.CRITICAL),
            (0.89, RiskState.CRITICAL),
            (0.90, RiskState.EMERGENCY),
            (1.00, RiskState.EMERGENCY),
        ],
    )
    def test_mapping(self, rho, expected):
        assert risk_to_state(rho) == expected

    def test_out_of_range(self):
        with pytest.raises(ValueError):
            risk_to_state(-0.01)
        with pytest.raises(ValueError):
            risk_to_state(1.01)


class TestTableTwoParameters:
    """Cross-check all Table 2 parameters against the manuscript."""

    def test_thresholds(self):
        assert STATE_CONFIG[RiskState.SAFE]["theta"] == 0.00
        assert STATE_CONFIG[RiskState.MONITOR]["theta"] == 0.30
        assert STATE_CONFIG[RiskState.ALERT]["theta"] == 0.50
        assert STATE_CONFIG[RiskState.CRITICAL]["theta"] == 0.70
        assert STATE_CONFIG[RiskState.EMERGENCY]["theta"] == 0.90

    def test_t_max(self):
        assert STATE_CONFIG[RiskState.SAFE]["t_max"] == float("inf")
        assert STATE_CONFIG[RiskState.MONITOR]["t_max"] == 300.0
        assert STATE_CONFIG[RiskState.ALERT]["t_max"] == 120.0
        assert STATE_CONFIG[RiskState.CRITICAL]["t_max"] == 60.0
        assert STATE_CONFIG[RiskState.EMERGENCY]["t_max"] == float("inf")

    def test_decay_rates(self):
        assert STATE_CONFIG[RiskState.MONITOR]["lam"] == 0.005
        assert STATE_CONFIG[RiskState.ALERT]["lam"] == 0.003
        assert STATE_CONFIG[RiskState.CRITICAL]["lam"] == 0.001
        # S1 and S5 have no decay
        assert STATE_CONFIG[RiskState.SAFE]["lam"] is None
        assert STATE_CONFIG[RiskState.EMERGENCY]["lam"] is None

    def test_cooling_periods(self):
        assert STATE_CONFIG[RiskState.MONITOR]["t_cool"] == 600.0
        assert STATE_CONFIG[RiskState.ALERT]["t_cool"] == 300.0
        assert STATE_CONFIG[RiskState.CRITICAL]["t_cool"] == 180.0

    def test_decay_ordering(self):
        """Higher acuity -> smaller lambda (slower decay)."""
        lam2 = STATE_CONFIG[RiskState.MONITOR]["lam"]
        lam3 = STATE_CONFIG[RiskState.ALERT]["lam"]
        lam4 = STATE_CONFIG[RiskState.CRITICAL]["lam"]
        assert lam2 > lam3 > lam4


class TestHalfLife:
    """Proposition 1: t_{1/2} = ln(2) / lambda_k."""

    def test_monitor(self):
        assert abs(half_life(RiskState.MONITOR) - 138.6) < 0.1

    def test_alert(self):
        assert abs(half_life(RiskState.ALERT) - 231.0) < 0.1

    def test_critical(self):
        assert abs(half_life(RiskState.CRITICAL) - 693.1) < 0.1

    def test_s4_five_times_s2(self):
        """Manuscript claim: S4 decays ~5x slower than S2."""
        ratio = half_life(RiskState.CRITICAL) / half_life(RiskState.MONITOR)
        assert abs(ratio - 5.0) < 0.1

    def test_none_for_safe_and_emergency(self):
        assert half_life(RiskState.SAFE) is None
        assert half_life(RiskState.EMERGENCY) is None


class TestMinDeescalationLatency:
    """Proposition 2: T_min(S_k -> S1)."""

    def test_monitor_to_s1(self):
        assert min_deescalation_latency(RiskState.MONITOR) == 600.0

    def test_alert_to_s1(self):
        assert min_deescalation_latency(RiskState.ALERT) == 900.0

    def test_critical_to_s1(self):
        lat = min_deescalation_latency(RiskState.CRITICAL)
        assert lat == 1080.0  # 18 minutes
