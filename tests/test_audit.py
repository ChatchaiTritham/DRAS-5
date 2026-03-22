"""Tests for dras5.audit — immutable audit log (C3)."""

import json

import pytest
from dras5.audit import AuditEntry, AuditLog
from dras5.states import RiskState


class TestAuditLog:
    def test_append_and_length(self):
        log = AuditLog()
        log.append(
            timestamp=10.0,
            from_state=RiskState.SAFE,
            to_state=RiskState.MONITOR,
            risk_score=0.35,
            rho_eff=0.35,
            trigger="escalation",
        )
        assert len(log) == 1

    def test_entry_id_increments(self):
        log = AuditLog()
        e1 = log.append(
            timestamp=10,
            from_state=RiskState.SAFE,
            to_state=RiskState.MONITOR,
            risk_score=0.35,
            rho_eff=0.35,
            trigger="escalation",
        )
        e2 = log.append(
            timestamp=20,
            from_state=RiskState.MONITOR,
            to_state=RiskState.ALERT,
            risk_score=0.55,
            rho_eff=0.55,
            trigger="escalation",
        )
        assert e1.entry_id == 1
        assert e2.entry_id == 2

    def test_immutability(self):
        log = AuditLog()
        e = log.append(
            timestamp=10,
            from_state=RiskState.SAFE,
            to_state=RiskState.MONITOR,
            risk_score=0.35,
            rho_eff=0.35,
            trigger="escalation",
        )
        with pytest.raises(AttributeError):
            e.risk_score = 0.99  # frozen dataclass

    def test_entries_returns_copy(self):
        log = AuditLog()
        log.append(
            timestamp=10,
            from_state=RiskState.SAFE,
            to_state=RiskState.MONITOR,
            risk_score=0.35,
            rho_eff=0.35,
            trigger="escalation",
        )
        entries = log.entries
        entries.clear()
        assert len(log) == 1  # original unchanged

    def test_to_json(self):
        log = AuditLog()
        log.append(
            timestamp=10,
            from_state=RiskState.SAFE,
            to_state=RiskState.MONITOR,
            risk_score=0.35,
            rho_eff=0.35,
            trigger="escalation",
        )
        data = json.loads(log.to_json())
        assert len(data) == 1
        assert data[0]["from_state"] == "SAFE"
        assert data[0]["to_state"] == "MONITOR"

    def test_to_csv(self):
        log = AuditLog()
        log.append(
            timestamp=10,
            from_state=RiskState.SAFE,
            to_state=RiskState.MONITOR,
            risk_score=0.35,
            rho_eff=0.35,
            trigger="escalation",
        )
        csv = log.to_csv()
        assert "from_state" in csv
        assert "MONITOR" in csv

    def test_filter_by_trigger(self):
        log = AuditLog()
        log.append(
            timestamp=10,
            from_state=RiskState.SAFE,
            to_state=RiskState.MONITOR,
            risk_score=0.35,
            rho_eff=0.35,
            trigger="escalation",
        )
        log.append(
            timestamp=310,
            from_state=RiskState.MONITOR,
            to_state=RiskState.ALERT,
            risk_score=0.35,
            rho_eff=0.35,
            trigger="timeout",
        )
        assert len(log.filter_by_trigger("timeout")) == 1
        assert len(log.filter_by_trigger("escalation")) == 1

    def test_empty_csv(self):
        log = AuditLog()
        assert log.to_csv() == ""
