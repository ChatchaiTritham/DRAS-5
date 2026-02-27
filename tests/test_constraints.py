"""Tests for dras5.constraints — C1, C2, C4, C5 validators."""

import pytest
from dras5.states import RiskState
from dras5.constraints import check_c1, check_c2, check_c4, check_c5


class TestC1MonotonicEscalation:
    """Theorem 1: state level is non-decreasing unless C5-approved."""

    def test_escalation_allowed(self):
        ok, _ = check_c1(RiskState.SAFE, RiskState.MONITOR)
        assert ok

    def test_hold_allowed(self):
        ok, _ = check_c1(RiskState.ALERT, RiskState.ALERT)
        assert ok

    def test_downgrade_blocked(self):
        ok, _ = check_c1(RiskState.CRITICAL, RiskState.MONITOR)
        assert not ok

    def test_downgrade_with_c5_approval(self):
        ok, _ = check_c1(RiskState.CRITICAL, RiskState.ALERT, c5_approved=True)
        assert ok

    @pytest.mark.parametrize("from_s,to_s", [
        (RiskState.SAFE, RiskState.MONITOR),
        (RiskState.MONITOR, RiskState.ALERT),
        (RiskState.ALERT, RiskState.CRITICAL),
        (RiskState.CRITICAL, RiskState.EMERGENCY),
    ])
    def test_all_single_step_escalations(self, from_s, to_s):
        ok, _ = check_c1(from_s, to_s)
        assert ok

    def test_multi_step_escalation(self):
        ok, _ = check_c1(RiskState.SAFE, RiskState.EMERGENCY)
        assert ok


class TestC2TimeoutEnforcement:
    """Theorem 2: duration(S_k) <= T_max + epsilon."""

    def test_monitor_within_limit(self):
        fired, _ = check_c2(RiskState.MONITOR, 200.0)
        assert not fired

    def test_monitor_timeout(self):
        fired, _ = check_c2(RiskState.MONITOR, 301.0)
        assert fired

    def test_alert_timeout(self):
        fired, _ = check_c2(RiskState.ALERT, 121.0)
        assert fired

    def test_critical_timeout(self):
        fired, _ = check_c2(RiskState.CRITICAL, 61.0)
        assert fired

    def test_safe_no_timeout(self):
        fired, _ = check_c2(RiskState.SAFE, 999999.0)
        assert not fired

    def test_emergency_no_timeout(self):
        fired, _ = check_c2(RiskState.EMERGENCY, 999999.0)
        assert not fired

    def test_epsilon_tolerance(self):
        """Should not fire within tolerance."""
        fired, _ = check_c2(RiskState.MONITOR, 300.5, epsilon=1.0)
        assert not fired


class TestC4HumanApproval:
    """Theorem 4: S4 -> S5 requires alpha=1."""

    def test_blocked_without_approval(self):
        ok, _ = check_c4(RiskState.CRITICAL, RiskState.EMERGENCY, alpha=False)
        assert not ok

    def test_allowed_with_approval(self):
        ok, _ = check_c4(RiskState.CRITICAL, RiskState.EMERGENCY, alpha=True)
        assert ok

    def test_not_applicable_for_other_transitions(self):
        ok, _ = check_c4(RiskState.MONITOR, RiskState.ALERT, alpha=False)
        assert ok  # C4 only gates S4->S5


class TestC5ControlledDeescalation:
    """Theorem 5: bounded, approved, single-step de-escalation."""

    def test_grant_when_all_conditions_met(self):
        # CRITICAL -> ALERT: need rho_eff < theta_3=0.50
        series = [0.45, 0.42, 0.40, 0.38, 0.35]
        ok, msg = check_c5(RiskState.CRITICAL, series, alpha1=True, alpha2=True)
        assert ok
        assert "GRANT" in msg

    def test_deny_already_safe(self):
        ok, msg = check_c5(RiskState.SAFE, [0.1], alpha1=True, alpha2=True)
        assert not ok
        assert "already at S1" in msg

    def test_deny_emergency(self):
        ok, msg = check_c5(RiskState.EMERGENCY, [0.1], alpha1=True, alpha2=True)
        assert not ok
        assert "full clinical review" in msg

    def test_deny_missing_alpha1(self):
        series = [0.45, 0.42, 0.40]
        ok, msg = check_c5(RiskState.CRITICAL, series, alpha1=False, alpha2=True)
        assert not ok
        assert "alpha1" in msg

    def test_deny_missing_alpha2(self):
        series = [0.45, 0.42, 0.40]
        ok, msg = check_c5(RiskState.CRITICAL, series, alpha1=True, alpha2=False)
        assert not ok
        assert "alpha2" in msg

    def test_deny_decay_not_sustained(self):
        # rho_eff at sample 2 is above theta_3=0.50
        series = [0.45, 0.42, 0.55, 0.38]
        ok, msg = check_c5(RiskState.CRITICAL, series, alpha1=True, alpha2=True)
        assert not ok
        assert "decay not sustained" in msg

    def test_deny_empty_series(self):
        ok, msg = check_c5(RiskState.CRITICAL, [], alpha1=True, alpha2=True)
        assert not ok

    def test_alert_deescalation_target(self):
        # ALERT -> MONITOR: need rho_eff < theta_2=0.30
        series = [0.25, 0.22, 0.20]
        ok, _ = check_c5(RiskState.ALERT, series, alpha1=True, alpha2=True)
        assert ok

    def test_alert_deescalation_too_high(self):
        # rho_eff above theta_2=0.30
        series = [0.25, 0.32, 0.20]
        ok, _ = check_c5(RiskState.ALERT, series, alpha1=True, alpha2=True)
        assert not ok
