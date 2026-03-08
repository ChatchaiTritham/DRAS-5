"""
Transition Rules
================

Formal rules governing state transitions.
"""

from typing import Callable, Dict, Any, Optional
from dataclasses import dataclass
import logging

from .states import RiskState

logger = logging.getLogger(__name__)


@dataclass
class TransitionRule:
    """
    Formal transition rule.

    Specifies conditions under which a state transition is allowed.
    """
    from_state: RiskState
    to_state: RiskState
    condition: Callable[[Dict[str, Any]], bool]
    description: str

    def is_allowed(self, context: Dict[str, Any]) -> bool:
        """Check if transition is allowed given context"""
        try:
            return self.condition(context)
        except Exception as e:
            logger.error(f"Transition rule evaluation failed: {e}")
            return False


class TransitionValidator:
    """
    Validates state transitions against formal rules.
    """

    def __init__(self):
        self.rules: Dict[tuple, TransitionRule] = {}
        self._initialize_default_rules()

    def _initialize_default_rules(self):
        """Initialize default transition rules"""

        # S1 (SAFE) → S2 (MONITOR)
        self.add_rule(TransitionRule(
            from_state=RiskState.SAFE,
            to_state=RiskState.MONITOR,
            condition=lambda ctx: ctx.get("risk_score", 0) >= 0.3,
            description="Risk score ≥ 0.3"
        ))

        # S2 (MONITOR) → S3 (ALERT)
        self.add_rule(TransitionRule(
            from_state=RiskState.MONITOR,
            to_state=RiskState.ALERT,
            condition=lambda ctx: ctx.get("risk_score", 0) >= 0.5,
            description="Risk score ≥ 0.5"
        ))

        # S3 (ALERT) → S4 (CRITICAL)
        self.add_rule(TransitionRule(
            from_state=RiskState.ALERT,
            to_state=RiskState.CRITICAL,
            condition=lambda ctx: ctx.get("risk_score", 0) >= 0.7,
            description="Risk score ≥ 0.7"
        ))

        # S4 (CRITICAL) → S5 (EMERGENCY)
        self.add_rule(TransitionRule(
            from_state=RiskState.CRITICAL,
            to_state=RiskState.EMERGENCY,
            condition=lambda ctx: (
                ctx.get("risk_score", 0) >= 0.9 and
                ctx.get("approved", False)
            ),
            description="Risk score ≥ 0.9 AND human approval"
        ))

        # Allow staying in same state
        for state in RiskState:
            self.add_rule(TransitionRule(
                from_state=state,
                to_state=state,
                condition=lambda ctx: True,
                description="Self-transition always allowed"
            ))

    def add_rule(self, rule: TransitionRule):
        """Add transition rule"""
        key = (rule.from_state, rule.to_state)
        self.rules[key] = rule
        logger.debug(
            f"Rule added: {rule.from_state.name} → {rule.to_state.name}: "
            f"{rule.description}"
        )

    def validate(
        self,
        from_state: RiskState,
        to_state: RiskState,
        context: Dict[str, Any]
    ) -> bool:
        """
        Validate if transition is allowed.

        Args:
            from_state: Current state
            to_state: Target state
            context: Context for evaluation

        Returns:
            True if transition is valid
        """
        key = (from_state, to_state)

        if key not in self.rules:
            logger.warning(
                f"No rule defined for {from_state.name} → {to_state.name}"
            )
            return False

        rule = self.rules[key]
        allowed = rule.is_allowed(context)

        if not allowed:
            logger.warning(
                f"Transition rejected: {from_state.name} → {to_state.name} "
                f"(rule: {rule.description})"
            )

        return allowed

    def get_allowed_transitions(
        self,
        from_state: RiskState,
        context: Dict[str, Any]
    ) -> list[RiskState]:
        """Get list of states that can be transitioned to"""
        allowed = []

        for to_state in RiskState:
            if self.validate(from_state, to_state, context):
                allowed.append(to_state)

        return allowed

    def explain_transition(
        self,
        from_state: RiskState,
        to_state: RiskState
    ) -> Optional[str]:
        """Get explanation of transition rule"""
        key = (from_state, to_state)

        if key in self.rules:
            return self.rules[key].description

        return None
