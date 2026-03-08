"""
Constraint System
=================

Formal constraints for state machine safety.
"""

from enum import Enum
from typing import Any, Callable, Optional, List
from dataclasses import dataclass
import logging

logger = logging.getLogger(__name__)

__all__ = [
    "ConstraintType",
    "ConstraintViolation",
    "Constraint",
    "check_c1",
    "check_c2",
    "check_c4",
    "check_c5",
]


class ConstraintType(Enum):
    """Types of constraints"""
    MONOTONIC = "monotonic"          # No downgrades
    TIMEOUT = "timeout"              # Time limits
    APPROVAL = "approval"            # Human approval required
    THRESHOLD = "threshold"          # Value thresholds
    AUDIT = "audit"                  # Audit requirements
    CUSTOM = "custom"                # Custom constraint


@dataclass
class ConstraintViolation(Exception):
    """Exception raised when constraint is violated"""
    constraint_type: ConstraintType
    message: str
    metadata: dict


@dataclass
class Constraint:
    """
    Formal constraint definition.
    """
    name: str
    constraint_type: ConstraintType
    validator: Callable[[Any], bool]
    error_message: str
    metadata: dict

    def __init__(
        self,
        name: str,
        constraint_type: ConstraintType,
        validator: Optional[Callable[[Any], bool]] = None,
        error_message: str = "",
        **kwargs
    ):
        self.name = name
        self.constraint_type = constraint_type
        self.validator = validator or (lambda x: True)
        self.error_message = error_message or f"{constraint_type.value} constraint violated"
        self.metadata = kwargs

    def check(self, context: dict) -> bool:
        """Check if constraint is satisfied"""
        try:
            return self.validator(context)
        except Exception as e:
            logger.error(f"Constraint check failed: {e}")
            return False

    def enforce(self, context: dict):
        """Enforce constraint, raise exception if violated"""
        if not self.check(context):
            raise ConstraintViolation(
                constraint_type=self.constraint_type,
                message=self.error_message,
                metadata={**self.metadata, **context}
            )


class ConstraintSystem:
    """
    System for managing and enforcing multiple constraints.
    """

    def __init__(self):
        self.constraints: List[Constraint] = []
        self.violations: List[ConstraintViolation] = []

    def add_constraint(self, constraint: Constraint):
        """Add constraint to system"""
        self.constraints.append(constraint)
        logger.info(f"Constraint added: {constraint.name} ({constraint.constraint_type.value})")

    def remove_constraint(self, name: str):
        """Remove constraint by name"""
        self.constraints = [c for c in self.constraints if c.name != name]
        logger.info(f"Constraint removed: {name}")

    def check_all(self, context: dict) -> bool:
        """Check all constraints"""
        all_satisfied = True

        for constraint in self.constraints:
            if not constraint.check(context):
                all_satisfied = False
                logger.warning(f"Constraint violated: {constraint.name}")

        return all_satisfied

    def enforce_all(self, context: dict):
        """Enforce all constraints"""
        for constraint in self.constraints:
            try:
                constraint.enforce(context)
            except ConstraintViolation as e:
                self.violations.append(e)
                logger.error(f"Constraint violation: {e.message}")
                raise

    def get_violations(self) -> List[ConstraintViolation]:
        """Get list of violations"""
        return self.violations.copy()

    def clear_violations(self):
        """Clear violation history"""
        self.violations = []


# Predefined constraint factories

def monotonic_constraint() -> Constraint:
    """Create monotonic escalation constraint"""
    def validator(ctx: dict) -> bool:
        from_state = ctx.get("from_state")
        to_state = ctx.get("to_state")

        if from_state is None or to_state is None:
            return True

        return to_state >= from_state

    return Constraint(
        name="monotonic_escalation",
        constraint_type=ConstraintType.MONOTONIC,
        validator=validator,
        error_message="State downgrade not allowed (monotonic constraint)"
    )


def timeout_constraint(max_duration: float) -> Constraint:
    """Create timeout constraint"""
    def validator(ctx: dict) -> bool:
        duration = ctx.get("duration", 0)
        return duration <= max_duration

    return Constraint(
        name="timeout",
        constraint_type=ConstraintType.TIMEOUT,
        validator=validator,
        error_message=f"State timeout exceeded (max: {max_duration}s)",
        max_duration=max_duration
    )


def approval_constraint(required_for: List[str]) -> Constraint:
    """Create human approval constraint"""
    def validator(ctx: dict) -> bool:
        transition = ctx.get("transition", "")
        approved = ctx.get("approved", False)

        if transition in required_for:
            return approved
        return True

    return Constraint(
        name="human_approval",
        constraint_type=ConstraintType.APPROVAL,
        validator=validator,
        error_message="Human approval required for this transition",
        required_for=required_for
    )


def threshold_constraint(
    parameter: str,
    min_value: Optional[float] = None,
    max_value: Optional[float] = None
) -> Constraint:
    """Create threshold constraint"""
    def validator(ctx: dict) -> bool:
        value = ctx.get(parameter)

        if value is None:
            return True

        if min_value is not None and value < min_value:
            return False
        if max_value is not None and value > max_value:
            return False

        return True

    bounds = []
    if min_value is not None:
        bounds.append(f"min={min_value}")
    if max_value is not None:
        bounds.append(f"max={max_value}")

    return Constraint(
        name=f"threshold_{parameter}",
        constraint_type=ConstraintType.THRESHOLD,
        validator=validator,
        error_message=f"Threshold constraint violated for {parameter} ({', '.join(bounds)})",
        parameter=parameter,
        min_value=min_value,
        max_value=max_value
    )


from dras5.states import RiskState


def check_c1(
    from_state: RiskState,
    to_state: RiskState,
    c5_approved: bool = False
) -> tuple[bool, str]:
    """Theorem 1: state level is non-decreasing unless C5-approved."""
    if from_state <= to_state:
        return True, "GRANT: monotonic escalation allowed"
    if c5_approved:
        return True, "GRANT: C5-approved de-escalation"
    return False, f"DENY: cannot downgrade from {from_state.name} to {to_state.name} without C5 approval"


def check_c2(
    state: RiskState,
    duration: float,
    epsilon: float = 0
) -> tuple[bool, str]:
    """Theorem 2: duration(S_k) <= T_max + epsilon."""
    from dras5.states import STATE_CONFIG
    t_max = STATE_CONFIG[state].get("t_max", float("inf"))
    if t_max == float("inf"):
        return False, "GRANT: no timeout for this state"
    if duration <= t_max + epsilon:
        return False, "GRANT: within timeout"
    return True, f"DENY: timeout exceeded ({duration}s > {t_max}s)"


def check_c4(
    from_state: RiskState,
    to_state: RiskState,
    alpha: bool = False
) -> tuple[bool, str]:
    """Theorem 4: S4 -> S5 requires alpha=1."""
    if from_state == RiskState.CRITICAL and to_state == RiskState.EMERGENCY:
        if alpha:
            return True, "GRANT: emergency escalation approved"
        return False, "DENY: human approval required for emergency escalation"
    return True, "GRANT: C4 not applicable to this transition"


def check_c5(
    from_state: RiskState,
    series: list,
    alpha1: bool = True,
    alpha2: bool = True
) -> tuple[bool, str]:
    """Theorem 5: bounded, approved, single-step de-escalation."""
    if from_state == RiskState.SAFE:
        return False, "DENY: already at S1 (SAFE)"
    if from_state == RiskState.EMERGENCY:
        return False, "DENY: S5 requires full clinical review"
    if not alpha1:
        return False, "DENY: alpha1 (physician) approval required"
    if not alpha2:
        return False, "DENY: alpha2 (supervisor) approval required"
    if not series:
        return False, "DENY: empty risk series"
    from dras5.states import STATE_CONFIG
    # Use the TARGET state's theta (S_{k-1}), not the current state's theta
    target_state = RiskState(from_state - 1)
    theta = STATE_CONFIG[target_state].get("theta", 0.5)
    if not all(r < theta for r in series):
        return False, "DENY: some values above threshold"
    for i in range(1, len(series)):
        if series[i] >= series[i-1]:
            return False, "DENY: decay not sustained below threshold"
    return True, f"GRANT: sustained decay below {theta}"
