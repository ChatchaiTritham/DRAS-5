"""
DRAS-5: Dynamic Risk Assessment State Machine

A 5-state risk assessment framework with exponential decay de-escalation
and formal constraint enforcement (C1--C5) for clinical decision support.

Quickstart
----------
    from dras5 import DRAS5StateMachine, RiskState

    sm = DRAS5StateMachine()
    sm.update(risk_score=0.45, t=10.0)   # -> MONITOR
    sm.update(risk_score=0.72, t=20.0)   # -> CRITICAL

Reference
---------
Tritham C, Snae Namahoot C (2026). DRAS-5: A Dynamic Risk Assessment
State Machine with Exponential Decay De-escalation and Provable Safety
Guarantees for Clinical Decision Support.
"""

__version__ = "1.0.0"
__author__ = "Chatchai Tritham"
__email__ = "chatchait66@nu.ac.th"

from .states import RiskState, STATE_CONFIG, risk_to_state, half_life, min_deescalation_latency
from .decay import DecayTracker
from .audit import AuditLog, AuditEntry
from .constraints import check_c1, check_c2, check_c4, check_c5, validate_all
from .state_machine import DRAS5StateMachine
from .simulator import (
    TrajectoryPoint,
    generate_trajectory,
    run_evaluation,
    EvaluationResult,
)

__all__ = [
    # Core
    "DRAS5StateMachine",
    "RiskState",
    "STATE_CONFIG",
    # Functions
    "risk_to_state",
    "half_life",
    "min_deescalation_latency",
    # Decay
    "DecayTracker",
    # Audit
    "AuditLog",
    "AuditEntry",
    # Constraints
    "check_c1",
    "check_c2",
    "check_c4",
    "check_c5",
    "validate_all",
    # Simulation
    "TrajectoryPoint",
    "generate_trajectory",
    "run_evaluation",
    "EvaluationResult",
]
