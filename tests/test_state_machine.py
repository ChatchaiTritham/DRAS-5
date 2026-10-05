"""Tests for dras5.state_machine — Algorithm 1 integration tests."""

import pytest
from dras5.state_machine import DRAS5StateMachine
from dras5.states import RiskState


class TestBasicEscalation:
    """Verify correct state assignment for monotonically increasing risk."""

    def test_full_escalation_sequence(self):
        sm = DRAS5StateMachine(require_human_approval=False)
        assert sm.update(risk_score=0.15, t=5) == RiskState.SAFE
        assert sm.update(risk_score=0.35, t=15) == RiskState.MONITOR
        assert sm.update(risk_score=0.55, t=25) == RiskState.ALERT
        assert sm.update(risk_score=0.75, t=35) == RiskState.CRITICAL
        assert sm.update(risk_score=0.95, t=45) == RiskState.EMERGENCY

    def test_initial_state(self):
        sm = DRAS5StateMachine()
        assert sm.current_state == RiskState.SAFE


class TestC1Enforcement:
    """Theorem 1: monotonic escalation."""

    def test_no_downgrade(self):
        sm = DRAS5StateMachine(require_human_approval=False)
        sm.update(risk_score=0.75, t=10)
        assert sm.current_state == RiskState.CRITICAL
        sm.update(risk_score=0.20, t=20)
        assert sm.current_state == RiskState.CRITICAL  # must NOT revert

    def test_hold_at_emergency(self):
        sm = DRAS5StateMachine(require_human_approval=False)
        sm.update(risk_score=0.95, t=10)
        sm.update(risk_score=0.10, t=20)
        assert sm.current_state == RiskState.EMERGENCY


class TestC2Timeout:
    """Theorem 2: auto-escalation on timeout."""

    def test_monitor_timeout(self):
        sm = DRAS5StateMachine(require_human_approval=False)
        sm.update(risk_score=0.35, t=0)
        assert sm.current_state == RiskState.MONITOR
        # Simulate 301s later — should auto-escalate
        sm.update(risk_score=0.35, t=302)
        assert sm.current_state == RiskState.ALERT

    def test_alert_timeout(self):
        sm = DRAS5StateMachine(require_human_approval=False)
        sm.update(risk_score=0.55, t=0)
        sm.update(risk_score=0.55, t=122)
        assert sm.current_state == RiskState.CRITICAL

    def test_critical_timeout(self):
        sm = DRAS5StateMachine(require_human_approval=False)
        sm.update(risk_score=0.75, t=0)
        sm.update(risk_score=0.75, t=62)
        assert sm.current_state == RiskState.EMERGENCY

    def test_check_timeout_method(self):
        sm = DRAS5StateMachine()
        sm.update(risk_score=0.35, t=0)
        assert not sm.check_timeout(t=100)
        assert sm.check_timeout(t=302)

    def test_auto_escalate_method(self):
        sm = DRAS5StateMachine()
        sm.update(risk_score=0.35, t=0)
        sm.auto_escalate(t=302)
        assert sm.current_state == RiskState.ALERT


class TestC4HumanGate:
    """Theorem 4: S4->S5 blocked without approval."""

    def test_blocked_without_approval(self):
        sm = DRAS5StateMachine(require_human_approval=True)
        sm.update(risk_score=0.75, t=10)
        sm.update(risk_score=0.95, t=20, human_approved=False)
        assert sm.current_state == RiskState.CRITICAL

    def test_allowed_with_approval(self):
        sm = DRAS5StateMachine(require_human_approval=True)
        sm.update(risk_score=0.75, t=10)
        sm.update(risk_score=0.95, t=20, human_approved=True)
        assert sm.current_state == RiskState.EMERGENCY

    def test_c4_only_for_s4_to_s5(self):
        sm = DRAS5StateMachine(require_human_approval=True)
        # Other transitions should not require approval
        sm.update(risk_score=0.55, t=10, human_approved=False)
        assert sm.current_state == RiskState.ALERT


class TestC5Deescalation:
    """Theorem 5: controlled de-escalation."""

    def test_grant(self):
        # Use ALERT (T_max=120s) so t=50 is within timeout
        sm = DRAS5StateMachine(require_human_approval=False)
        sm.update(risk_score=0.55, t=0)
        assert sm.current_state == RiskState.ALERT

        # ALERT->MONITOR: need rho_eff < theta_2=0.30
        series = [0.25, 0.22, 0.20, 0.18, 0.15]
        sm.update(
            risk_score=0.15,
            t=50,
            deescalation_request=True,
            human_approved=True,
            dual_approval=True,
            rho_eff_series=series,
        )
        assert sm.current_state == RiskState.MONITOR

    def test_single_step_only(self):
        """De-escalation should drop exactly one level."""
        sm = DRAS5StateMachine(require_human_approval=False)
        sm.update(risk_score=0.55, t=0)

        series = [0.25, 0.22, 0.20]
        sm.update(
            risk_score=0.15,
            t=50,
            deescalation_request=True,
            human_approved=True,
            dual_approval=True,
            rho_eff_series=series,
        )
        assert sm.current_state == RiskState.MONITOR  # not SAFE

    def test_deny_without_dual_approval(self):
        sm = DRAS5StateMachine(require_human_approval=False)
        sm.update(risk_score=0.55, t=0)

        series = [0.25, 0.22, 0.20]
        sm.update(
            risk_score=0.15,
            t=50,
            deescalation_request=True,
            human_approved=True,
            dual_approval=False,
            rho_eff_series=series,
        )
        assert sm.current_state == RiskState.ALERT  # stays

    def _recovering(self, **kw):
        sm = DRAS5StateMachine(require_human_approval=False)
        sm.update(risk_score=0.55, t=0)
        return sm, sm.update(risk_score=0.15, t=50, deescalation_request=True,
                             human_approved=True, rho_eff_series=[0.25, 0.22, 0.20], **kw)

    def test_single_approval_denied_each_signal(self):
        # Each approval signal is a separate input; either one missing denies.
        assert self._recovering(approval_1=True, approval_2=False)[1] == RiskState.ALERT
        assert self._recovering(approval_1=False, approval_2=True)[1] == RiskState.ALERT

    def test_two_signals_grant(self):
        assert self._recovering(approval_1=True, approval_2=True)[1] == RiskState.MONITOR

    def test_same_approver_not_independent(self):
        _, st = self._recovering(approval_1=True, approval_2=True,
                                 approver_1="dr-a", approver_2="dr-a")
        assert st == RiskState.ALERT

    def test_approvers_recorded_in_audit_log(self):
        sm = DRAS5StateMachine(require_human_approval=False, enable_audit=True)
        sm.update(risk_score=0.55, t=0)
        sm.update(risk_score=0.15, t=50, deescalation_request=True, human_approved=True,
                  rho_eff_series=[0.25, 0.22, 0.20], approval_1=True, approval_2=True,
                  approver_1="dr-a", approver_2="dr-b")
        last = sm.audit_log.entries[-1]
        assert last.metadata["approver_1"] == "dr-a"
        assert last.metadata["approver_2"] == "dr-b"
        assert "rho_eff" in last.metadata

    def test_legacy_dual_approval_flag_still_sets_both(self):
        assert self._recovering(dual_approval=True)[1] == RiskState.MONITOR
        assert self._recovering(dual_approval=False)[1] == RiskState.ALERT

    def test_deny_decay_not_sustained(self):
        sm = DRAS5StateMachine(require_human_approval=False)
        sm.update(risk_score=0.55, t=0)

        series = [0.25, 0.35, 0.20]  # middle sample above theta_2=0.30
        sm.update(
            risk_score=0.15,
            t=50,
            deescalation_request=True,
            human_approved=True,
            dual_approval=True,
            rho_eff_series=series,
        )
        assert sm.current_state == RiskState.ALERT  # stays


class TestC3AuditCompleteness:
    """Theorem 3: every transition produces an audit entry."""

    def test_audit_count_matches_transitions(self):
        sm = DRAS5StateMachine(require_human_approval=False)
        sm.update(risk_score=0.35, t=10)
        sm.update(risk_score=0.55, t=20)
        sm.update(risk_score=0.75, t=30)
        assert len(sm.get_history()) == 3

    def test_audit_entry_fields(self):
        sm = DRAS5StateMachine(require_human_approval=False, session_id="test-1")
        sm.update(risk_score=0.55, t=10)
        entry = sm.get_history()[0]
        assert entry.from_state == RiskState.SAFE
        assert entry.to_state == RiskState.ALERT
        assert entry.risk_score == 0.55
        assert entry.trigger == "escalation"
        assert entry.session_id == "test-1"

    def test_no_audit_without_transition(self):
        sm = DRAS5StateMachine()
        sm.update(risk_score=0.15, t=10)  # stays in SAFE
        assert len(sm.get_history()) == 0

    def test_audit_export_json(self):
        sm = DRAS5StateMachine(require_human_approval=False)
        sm.update(risk_score=0.55, t=10)
        json_str = sm.audit_log.to_json()
        assert "SAFE" in json_str
        assert "ALERT" in json_str

    def test_audit_export_csv(self):
        sm = DRAS5StateMachine(require_human_approval=False)
        sm.update(risk_score=0.55, t=10)
        csv_str = sm.audit_log.to_csv()
        assert "from_state" in csv_str
        assert "ALERT" in csv_str


class TestStatistics:
    def test_statistics(self):
        sm = DRAS5StateMachine(require_human_approval=False)
        sm.update(risk_score=0.35, t=10)
        sm.update(risk_score=0.55, t=20)
        stats = sm.get_statistics()
        assert stats["current_state"] == "ALERT"
        assert stats["total_transitions"] == 2
        assert stats["last_risk_score"] == 0.55


class TestEdgeCases:
    def test_risk_score_boundary(self):
        sm = DRAS5StateMachine(require_human_approval=False)
        assert sm.update(risk_score=0.0, t=0) == RiskState.SAFE
        assert sm.update(risk_score=1.0, t=1) == RiskState.EMERGENCY

    def test_invalid_risk_score(self):
        sm = DRAS5StateMachine()
        with pytest.raises(ValueError):
            sm.update(risk_score=-0.1, t=0)
        with pytest.raises(ValueError):
            sm.update(risk_score=1.1, t=0)

    def test_force_state(self):
        sm = DRAS5StateMachine()
        sm.update(risk_score=0.75, t=10)
        sm.force_state(RiskState.MONITOR, reason="test_reset", t=20)
        assert sm.current_state == RiskState.MONITOR

    def test_multi_step_escalation(self):
        """Jumping from SAFE to CRITICAL in one step."""
        sm = DRAS5StateMachine(require_human_approval=False)
        assert sm.update(risk_score=0.75, t=10) == RiskState.CRITICAL


class TestC4AllRoutes:
    """Theorem 4 (revised): no route into EMERGENCY without approval."""

    def test_skip_from_alert_blocked(self):
        sm = DRAS5StateMachine()
        sm.update(risk_score=0.55, t=0)
        assert sm.update(risk_score=0.95, t=10) == RiskState.CRITICAL

    def test_critical_timeout_waits_for_approval(self):
        sm = DRAS5StateMachine()
        sm.update(risk_score=0.75, t=0)
        assert sm.update(risk_score=0.75, t=62) == RiskState.CRITICAL
        assert sm.update(risk_score=0.75, t=72, human_approved=True) == RiskState.EMERGENCY

    def test_timeout_audit_records_real_approval(self):
        sm = DRAS5StateMachine(require_human_approval=False)
        sm.update(risk_score=0.35, t=0)
        sm.update(risk_score=0.35, t=302)
        assert sm.transition_history[-1].approved is False


def test_monitor_returns_to_safe_after_sustained_recovery():
    """Regression: S2 -> S1 needed rho_eff < theta_1 = 0 and was unreachable (Corollary 1)."""
    sm = DRAS5StateMachine(require_human_approval=True)
    sm.update(risk_score=0.35, t=0)
    assert sm.current_state == RiskState.MONITOR
    for i in range(1, 200):
        sm.update(risk_score=0.0, t=i * 10.0, human_approved=True, deescalation_request=True,
                  approval_1=True, approval_2=True, approver_1="a", approver_2="b")
    assert sm.current_state == RiskState.SAFE
