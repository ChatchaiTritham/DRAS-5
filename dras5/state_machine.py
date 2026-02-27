"""
DRAS-5 Unified State Machine (Algorithm 1)

Implements the DRAS Unified State Update Procedure with all five
constraints (C1--C5) and exponential decay de-escalation.

Usage
-----
    from dras5 import DRAS5StateMachine, RiskState

    sm = DRAS5StateMachine()
    sm.update(risk_score=0.45, t=10.0)       # -> MONITOR
    sm.update(risk_score=0.72, t=20.0)       # -> CRITICAL
    sm.update(risk_score=0.95, t=30.0,
              human_approved=True)            # -> EMERGENCY

Reference
---------
Tritham C, Snae Namahoot C (2026). DRAS-5, Algorithm 1.
"""

from __future__ import annotations

import time as _time
from typing import Dict, List, Optional, Tuple

from .states import RiskState, STATE_CONFIG, risk_to_state
from .decay import DecayTracker
from .audit import AuditLog, AuditEntry
from .constraints import check_c1, check_c2, check_c4, check_c5

__all__ = ["DRAS5StateMachine"]


class DRAS5StateMachine:
    """Five-state risk assessment machine with formal constraint enforcement.

    Parameters
    ----------
    initial_state : RiskState
        Starting state (default: SAFE).
    enable_constraints : bool
        If False, constraints are logged but not enforced.
    enable_audit : bool
        If False, no audit entries are written.
    require_human_approval : bool
        If False, the C4 gate is bypassed (for simulation only).
    session_id : str
        Identifier for the patient session.
    use_wall_clock : bool
        If True, timestamps come from ``time.time()`` instead of the
        caller-supplied *t* parameter.
    """

    def __init__(
        self,
        initial_state: RiskState = RiskState.SAFE,
        enable_constraints: bool = True,
        enable_audit: bool = True,
        require_human_approval: bool = True,
        session_id: str = "",
        use_wall_clock: bool = False,
    ) -> None:
        self._state = initial_state
        self._enable_constraints = enable_constraints
        self._enable_audit = enable_audit
        self._require_human_approval = require_human_approval
        self._session_id = session_id
        self._use_wall_clock = use_wall_clock

        # Timing
        self._state_entry_time: float = _time.time() if use_wall_clock else 0.0
        self._last_update_time: float = self._state_entry_time

        # Decay tracker (C5)
        self._decay = DecayTracker()
        self._decay.reset(initial_state)

        # Audit log (C3)
        self._audit = AuditLog()

        # Statistics
        self._state_counts: Dict[RiskState, int] = {s: 0 for s in RiskState}
        self._state_counts[initial_state] = 1
        self._total_transitions: int = 0
        self._last_risk: float = 0.0

    # ==================================================================
    # Core update — Algorithm 1
    # ==================================================================

    def update(
        self,
        risk_score: float,
        t: Optional[float] = None,
        human_approved: bool = False,
        deescalation_request: bool = False,
        dual_approval: bool = False,
        rho_eff_series: Optional[List[float]] = None,
    ) -> RiskState:
        """Execute one DRAS update cycle (Algorithm 1).

        Parameters
        ----------
        risk_score : float
            Instantaneous risk rho in [0, 1].
        t : float or None
            Current time.  Ignored when *use_wall_clock* is True.
        human_approved : bool
            Clinician approval flag (alpha).
        deescalation_request : bool
            If True, evaluate C5 de-escalation.
        dual_approval : bool
            Second clinician approval (alpha_2) for C5.
        rho_eff_series : list of float or None
            Effective risk samples over the cooling period, required when
            *deescalation_request* is True.

        Returns
        -------
        RiskState
            The state after this update.
        """
        if risk_score < 0.0 or risk_score > 1.0:
            raise ValueError(f"risk_score must be in [0, 1], got {risk_score}")

        now = _time.time() if self._use_wall_clock else (t if t is not None else 0.0)
        s_prev = self._state
        elapsed = now - self._state_entry_time

        # Update peak tracker
        self._decay.update_peak(risk_score, now)

        # ---- Phase 1: Timeout enforcement (C2) ----
        timeout_fired, c2_msg = check_c2(self._state, elapsed)
        if timeout_fired and self._state not in (RiskState.SAFE, RiskState.EMERGENCY):
            self._do_transition(
                new_state=RiskState(int(self._state) + 1),
                rho=risk_score,
                rho_eff=risk_score,
                trigger="timeout",
                alpha=False,
                alpha2=False,
                t=now,
            )

        # ---- Phase 2: Risk-based escalation (C1) ----
        mapped = risk_to_state(risk_score)
        if mapped > self._state:
            # Special case: C4 gate for S4 -> S5
            if self._state == RiskState.CRITICAL and mapped == RiskState.EMERGENCY:
                if self._require_human_approval and not human_approved:
                    # C4 blocks the transition
                    self._last_risk = risk_score
                    self._last_update_time = now
                    return self._state
            self._do_transition(
                new_state=mapped,
                rho=risk_score,
                rho_eff=risk_score,
                trigger="escalation",
                alpha=human_approved,
                alpha2=dual_approval,
                t=now,
            )

        # ---- Phase 3: C5 controlled de-escalation ----
        if deescalation_request and self._state not in (RiskState.SAFE, RiskState.EMERGENCY):
            series = rho_eff_series if rho_eff_series is not None else []
            c5_ok, c5_msg = check_c5(
                current=self._state,
                rho_eff_series=series,
                alpha1=human_approved,
                alpha2=dual_approval,
            )
            if c5_ok:
                new_s = RiskState(int(self._state) - 1)
                self._do_transition(
                    new_state=new_s,
                    rho=risk_score,
                    rho_eff=series[-1] if series else risk_score,
                    trigger="c5_deescalation",
                    alpha=human_approved,
                    alpha2=dual_approval,
                    t=now,
                    note=c5_msg,
                )

        self._last_risk = risk_score
        self._last_update_time = now
        return self._state

    # ==================================================================
    # Timeout helpers
    # ==================================================================

    def check_timeout(self, t: Optional[float] = None) -> bool:
        """Return True if the current state has exceeded T_max."""
        now = _time.time() if self._use_wall_clock else (t if t is not None else 0.0)
        elapsed = now - self._state_entry_time
        fired, _ = check_c2(self._state, elapsed)
        return fired

    def auto_escalate(self, t: Optional[float] = None) -> RiskState:
        """Escalate by one level due to timeout.  Returns the new state."""
        if self._state in (RiskState.SAFE, RiskState.EMERGENCY):
            return self._state
        now = _time.time() if self._use_wall_clock else (t if t is not None else 0.0)
        new_s = RiskState(int(self._state) + 1)
        self._do_transition(
            new_state=new_s,
            rho=self._last_risk,
            rho_eff=self._last_risk,
            trigger="timeout",
            alpha=False,
            alpha2=False,
            t=now,
        )
        return self._state

    # ==================================================================
    # Query interface
    # ==================================================================

    @property
    def current_state(self) -> RiskState:
        return self._state

    @property
    def audit_log(self) -> AuditLog:
        return self._audit

    def get_current_duration(self, t: Optional[float] = None) -> float:
        now = _time.time() if self._use_wall_clock else (t if t is not None else self._last_update_time)
        return now - self._state_entry_time

    def get_time_remaining(self, t: Optional[float] = None) -> Optional[float]:
        t_max = STATE_CONFIG[self._state]["t_max"]
        if t_max == float("inf"):
            return None
        duration = self.get_current_duration(t)
        return max(0.0, t_max - duration)

    def get_history(self) -> List[AuditEntry]:
        return self._audit.entries

    def get_statistics(self) -> dict:
        return {
            "current_state": self._state.name,
            "current_duration": self.get_current_duration(),
            "total_transitions": self._total_transitions,
            "last_risk_score": self._last_risk,
            "state_counts": {s.name: c for s, c in self._state_counts.items()},
        }

    def get_effective_risk(self, rho: float, t: float) -> float:
        """Compute rho_eff(t) without advancing the state machine."""
        return self._decay.effective_risk(rho, t, self._state)

    # ==================================================================
    # Administrative
    # ==================================================================

    def force_state(self, state: RiskState, reason: str = "",
                    t: Optional[float] = None) -> None:
        """Force the machine into *state* (for demos / clinical resets)."""
        now = _time.time() if self._use_wall_clock else (t if t is not None else 0.0)
        self._do_transition(
            new_state=state,
            rho=self._last_risk,
            rho_eff=self._last_risk,
            trigger=f"force_reset:{reason}",
            alpha=True,
            alpha2=True,
            t=now,
            note=f"Administrative reset: {reason}",
        )

    # ==================================================================
    # Internal
    # ==================================================================

    def _do_transition(self, *, new_state: RiskState, rho: float,
                       rho_eff: float, trigger: str, alpha: bool,
                       alpha2: bool, t: float, note: str = "") -> None:
        old_state = self._state
        if new_state == old_state:
            return

        if self._enable_audit:
            self._audit.append(
                timestamp=t,
                from_state=old_state,
                to_state=new_state,
                risk_score=rho,
                rho_eff=rho_eff,
                trigger=trigger,
                approval_1=alpha,
                approval_2=alpha2,
                session_id=self._session_id,
                note=note,
            )

        self._state = new_state
        self._state_entry_time = t
        self._state_counts[new_state] = self._state_counts.get(new_state, 0) + 1
        self._total_transitions += 1

        # Reset decay tracker for the new state
        self._decay.reset(new_state)
