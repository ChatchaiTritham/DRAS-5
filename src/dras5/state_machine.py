"""
DRAS-5 State Machine
====================

Core 5-state risk assessment state machine.
"""

from typing import Optional, List, Dict, Any
from dataclasses import dataclass
import time
import logging

from dras5.audit import AuditLog, AuditEntry
from dras5.decay import DecayTracker
from dras5.states import RiskState, STATE_CONFIG

logger = logging.getLogger(__name__)

SAFE_STATE_THRESHOLD = 0.0
MONITOR_STATE_THRESHOLD = 0.3
ALERT_STATE_THRESHOLD = 0.5
CRITICAL_STATE_THRESHOLD = 0.7
EMERGENCY_STATE_THRESHOLD = 0.9

STATE_TIMEOUT_NONE = float("inf")
MONITOR_STATE_TIMEOUT_SECONDS = 300
ALERT_STATE_TIMEOUT_SECONDS = 120
CRITICAL_STATE_TIMEOUT_SECONDS = 60

DEFAULT_RISK_SCORE = 0.0
RISK_SCORE_UPDATE_TRIGGER = "risk_score_update"
TIMEOUT_ESCALATION_TRIGGER = "timeout_escalation"
MANUAL_RESET_TRIGGER = "manual_reset"
MANUAL_OVERRIDE_PREFIX = "force_"


@dataclass
class StateTransition:
    """Record of state transition"""

    from_state: RiskState
    to_state: RiskState
    timestamp: float
    risk_score: float
    trigger: str
    approved: bool
    metadata: Dict[str, Any]
    session_id: Optional[str] = None


class DRAS5StateMachine:
    """
    5-State Dynamic Risk Assessment State Machine.

    Implements monotonic risk escalation with formal constraints.
    """

    # Risk score thresholds for each state
    STATE_THRESHOLDS = {
        RiskState.SAFE: SAFE_STATE_THRESHOLD,
        RiskState.MONITOR: MONITOR_STATE_THRESHOLD,
        RiskState.ALERT: ALERT_STATE_THRESHOLD,
        RiskState.CRITICAL: CRITICAL_STATE_THRESHOLD,
        RiskState.EMERGENCY: EMERGENCY_STATE_THRESHOLD,
    }

    # Maximum duration in each state (seconds)
    STATE_TIMEOUTS = {
        RiskState.SAFE: STATE_TIMEOUT_NONE,
        RiskState.MONITOR: MONITOR_STATE_TIMEOUT_SECONDS,
        RiskState.ALERT: ALERT_STATE_TIMEOUT_SECONDS,
        RiskState.CRITICAL: CRITICAL_STATE_TIMEOUT_SECONDS,
        RiskState.EMERGENCY: STATE_TIMEOUT_NONE,
    }

    def __init__(
        self,
        initial_state: RiskState = RiskState.SAFE,
        enable_constraints: bool = True,
        enable_audit: bool = True,
        require_human_approval: bool = True,
        session_id: Optional[str] = None,
    ):
        """
        Initialize DRAS-5 state machine.

        Args:
            initial_state: Starting state
            enable_constraints: Enable constraint enforcement
            enable_audit: Enable audit logging
            require_human_approval: Require human approval for S4→S5
            session_id: Session identifier for tracking
        """
        self.current_state = initial_state
        self.enable_constraints = enable_constraints
        self.enable_audit = enable_audit
        self.require_human_approval = require_human_approval
        self.session_id = session_id or f"session-{time.time()}"

        self.state_entry_time = time.time()
        self.transition_history: List[StateTransition] = []
        self.last_risk_score = DEFAULT_RISK_SCORE
        self._audit_log = AuditLog()
        self._decay_tracker = DecayTracker()
        self._rho_eff_history: List[float] = []

        logger.info(
            f"DRAS-5 initialized: state={initial_state.name}, "
            f"constraints={enable_constraints}"
        )

    @property
    def audit_log(self) -> AuditLog:
        """Get audit log for exports."""
        return self._audit_log

    def update(
        self,
        risk_score: float,
        t: Optional[float] = None,
        force: bool = False,
        human_approved: bool = False,
        deescalation_request: bool = False,
        dual_approval: bool = False,
        rho_eff_series: Optional[List[float]] = None,
    ) -> RiskState:
        """
        Update state based on risk score.

        Args:
            risk_score: Current risk score (0-1)
            t: Current timestamp (optional, defaults to time.time())
            force: Force transition (override constraints)
            human_approved: Human approval for critical transitions
            deescalation_request: Request for controlled de-escalation
            dual_approval: Require dual approval for de-escalation
            rho_eff_series: Series of effective risk scores for de-escalation validation

        Returns:
            New state after update

        Raises:
            ValueError: If risk_score is outside [0, 1] range
            ConstraintViolation: If constraints are violated
        """
        if not 0 <= risk_score <= 1:
            raise ValueError(f"risk_score must be in [0, 1], got {risk_score}")

        current_time = t if t is not None else time.time()

        # Update decay tracker with current observation (Eq. 5)
        self._decay_tracker.update_peak(risk_score, current_time)
        rho_eff = self._decay_tracker.effective_risk(
            risk_score, current_time, self.current_state
        )
        self._rho_eff_history.append(rho_eff)

        old_state = self.current_state
        new_state = self._calculate_target_state(risk_score)

        # Handle de-escalation request
        if deescalation_request and new_state < old_state:
            if not dual_approval:
                logger.warning("De-escalation denied: dual approval required")
                new_state = old_state
            else:
                # Use externally-provided series, or fall back to internal history
                series = rho_eff_series if rho_eff_series else self._rho_eff_history
                from dras5.constraints import check_c5
                allowed, _ = check_c5(old_state, series, alpha1=True, alpha2=True)
                if not allowed:
                    logger.warning("De-escalation denied: C5 constraint not met")
                    new_state = old_state
                else:
                    # Only allow single-step de-escalation
                    min_allowed_state = RiskState(old_state - 1)
                    if new_state < min_allowed_state:
                        new_state = min_allowed_state

        # Check monotonic constraint (skip if de-escalation was explicitly approved)
        deescalation_approved = deescalation_request and dual_approval
        if self.enable_constraints and not force and not deescalation_approved:
            if new_state < old_state:
                logger.warning(
                    f"Monotonic constraint: Cannot downgrade from "
                    f"{old_state.name} to {new_state.name}"
                )
                new_state = old_state

        # Check human approval for S4→S5
        if (
            self.require_human_approval
            and old_state == RiskState.CRITICAL
            and new_state == RiskState.EMERGENCY
            and not human_approved
            and not force
        ):
            logger.warning("Human approval required for CRITICAL→EMERGENCY transition")
            new_state = RiskState.CRITICAL  # Stay in critical

        # Perform transition
        if new_state != old_state:
            self._transition(
                new_state,
                risk_score,
                trigger="escalation",
                approved=human_approved or force,
                timestamp=current_time,
            )

        # Update last risk score before timeout check so auto_escalate uses current value
        self.last_risk_score = risk_score

        # Check for timeout and auto-escalate
        self._check_and_auto_escalate(current_time)

        return self.current_state

    def _check_and_auto_escalate(self, current_time: float):
        """Check for timeout and auto-escalate if needed."""
        if self.check_timeout(t=current_time):
            self.auto_escalate(t=current_time)

    def _calculate_target_state(self, risk_score: float) -> RiskState:
        """Calculate target state based on risk score"""
        for state in reversed(list(RiskState)):
            if risk_score >= self.STATE_THRESHOLDS[state]:
                return state
        return RiskState.SAFE

    def _transition(
        self, new_state: RiskState, risk_score: float, trigger: str, approved: bool, timestamp: Optional[float] = None
    ):
        """Execute state transition"""
        old_state = self.current_state
        current_time = timestamp if timestamp is not None else time.time()

        # Create transition record
        transition = StateTransition(
            from_state=old_state,
            to_state=new_state,
            timestamp=current_time,
            risk_score=risk_score,
            trigger=trigger,
            approved=approved,
            metadata={
                "duration_in_state": current_time - self.state_entry_time,
            },
            session_id=self.session_id,
        )

        # Update state
        self.current_state = new_state
        self.state_entry_time = current_time
        self._decay_tracker.reset(new_state)
        self._rho_eff_history.clear()

        # Record transition
        if self.enable_audit:
            self.transition_history.append(transition)
            self._audit_log.append(
                timestamp=current_time,
                from_state=old_state,
                to_state=new_state,
                risk_score=risk_score,
                trigger=trigger,
                approved=approved,
                user_id=self.session_id,
            )

        logger.info(
            f"State transition: {old_state.name} → {new_state.name} "
            f"(risk={risk_score:.3f}, trigger={trigger})"
        )

    def check_timeout(self, t: Optional[float] = None) -> bool:
        """Check if current state has exceeded timeout"""
        current_time = t if t is not None else time.time()
        duration = current_time - self.state_entry_time
        timeout = self.STATE_TIMEOUTS[self.current_state]

        if timeout == float("inf"):
            return False
        if duration > timeout:
            logger.warning(
                f"State timeout: {self.current_state.name} exceeded "
                f"{timeout}s (current: {duration:.1f}s)"
            )
            return True
        return False

    def auto_escalate(self, t: Optional[float] = None):
        """Auto-escalate if timeout occurred.

        Note: This method checks timeout internally so it can be called
        standalone (e.g., from tests). When called via _check_and_auto_escalate,
        the timeout was already verified.
        """
        current_time = t if t is not None else time.time()
        if not self.check_timeout(t=current_time):
            return
        if self.current_state >= RiskState.EMERGENCY:
            return
        next_state = RiskState(self.current_state + 1)
        self._transition(
            next_state,
            self.last_risk_score,
            trigger=TIMEOUT_ESCALATION_TRIGGER,
            approved=True,
            timestamp=current_time,
        )

    def force_state(self, new_state: RiskState, reason: str = "manual_override", t: Optional[float] = None):
        """Force state change (requires explicit call)"""
        logger.warning(
            f"Force state change: {self.current_state.name} → "
            f"{new_state.name} (reason: {reason})"
        )

        self._transition(
            new_state,
            self.last_risk_score,
            trigger=f"{MANUAL_OVERRIDE_PREFIX}{reason}",
            approved=True,
        )
        if t is not None:
            self.state_entry_time = t

    def reset(self):
        """Reset to SAFE state (manual only)"""
        logger.info("Resetting state machine to SAFE")
        self._transition(
            RiskState.SAFE,
            DEFAULT_RISK_SCORE,
            trigger=MANUAL_RESET_TRIGGER,
            approved=True,
        )

    def get_history(self) -> List[StateTransition]:
        """Get transition history"""
        return self.transition_history.copy()

    def get_current_duration(self) -> float:
        """Get duration in current state"""
        return time.time() - self.state_entry_time

    def get_time_remaining(self) -> Optional[float]:
        """Get time remaining before timeout"""
        timeout = self.STATE_TIMEOUTS[self.current_state]
        if timeout == STATE_TIMEOUT_NONE:
            return None

        elapsed = self.get_current_duration()
        remaining = timeout - elapsed
        return max(0.0, remaining)

    def get_statistics(self) -> Dict[str, Any]:
        """Get state machine statistics"""
        state_counts = {}
        for state in RiskState:
            count = sum(1 for t in self.transition_history if t.to_state == state)
            state_counts[state.name] = count

        total_transitions = len(self.transition_history)

        return {
            "current_state": self.current_state.name,
            "current_duration": self.get_current_duration(),
            "time_remaining": self.get_time_remaining(),
            "total_transitions": total_transitions,
            "state_counts": state_counts,
            "last_risk_score": self.last_risk_score,
        }

    def export_audit_trail(self) -> List[Dict[str, Any]]:
        """Export audit trail as list of dicts"""
        return [
            {
                "from_state": t.from_state.name,
                "to_state": t.to_state.name,
                "timestamp": t.timestamp,
                "risk_score": t.risk_score,
                "trigger": t.trigger,
                "approved": t.approved,
                "metadata": t.metadata,
            }
            for t in self.transition_history
        ]
