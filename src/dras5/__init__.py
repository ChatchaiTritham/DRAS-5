"""
DRAS-5: Dynamic Risk Assessment State Machine
==============================================

5-state risk assessment machine with formal constraint enforcement.
"""

from .constants import FRAMEWORK_NAME, PACKAGE_VERSION

__version__ = PACKAGE_VERSION
__author__ = "Clinical AI Research Team"

from .states import RiskState
from .state_machine import DRAS5StateMachine, StateTransition
from .constraints import Constraint, ConstraintType, ConstraintViolation
from .transitions import TransitionRule, TransitionValidator
from .audit import AuditLogger, AuditEntry

__all__ = [
    "DRAS5StateMachine",
    "RiskState",
    "StateTransition",
    "Constraint",
    "ConstraintType",
    "ConstraintViolation",
    "TransitionRule",
    "TransitionValidator",
    "AuditLogger",
    "AuditEntry",
    "FRAMEWORK_NAME",
]
