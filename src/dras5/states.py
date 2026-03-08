"""
DRAS-5 State Definitions

Implements the five risk assessment states (S1--S5) with their associated
parameters as specified in Table 2 of the manuscript.

Reference
---------
Tritham C, Snae Namahoot C (2026). DRAS-5: A Dynamic Risk Assessment
State Machine with Exponential Decay De-escalation and Provable Safety
Guarantees for Clinical Decision Support.
"""

import math
from enum import IntEnum
from typing import Dict, Optional

__all__ = ["RiskState", "STATE_CONFIG"]


class RiskState(IntEnum):
    """Five-level risk state enumeration (Eq. 1).

    The ordering satisfies S1 < S2 < S3 < S4 < S5.
    """

    SAFE = 1
    MONITOR = 2
    ALERT = 3
    CRITICAL = 4
    EMERGENCY = 5


# Table 2 — complete parameter set for every state.
STATE_CONFIG: Dict[RiskState, dict] = {
    RiskState.SAFE: {
        "label": "SAFE",
        "theta": 0.00,  # entry threshold
        "theta_upper": 0.30,  # upper boundary
        "t_max": float("inf"),  # no timeout
        "lam": None,  # no decay
        "t_cool": None,  # no cooling period
    },
    RiskState.MONITOR: {
        "label": "MONITOR",
        "theta": 0.30,
        "theta_upper": 0.50,
        "t_max": 300.0,  # 5 min
        "lam": 0.005,  # decay rate (s^-1)
        "t_cool": 600.0,  # cooling period (s)
    },
    RiskState.ALERT: {
        "label": "ALERT",
        "theta": 0.50,
        "theta_upper": 0.70,
        "t_max": 120.0,  # 2 min
        "lam": 0.003,
        "t_cool": 300.0,
    },
    RiskState.CRITICAL: {
        "label": "CRITICAL",
        "theta": 0.70,
        "theta_upper": 0.90,
        "t_max": 60.0,  # 1 min
        "lam": 0.001,
        "t_cool": 180.0,
    },
    RiskState.EMERGENCY: {
        "label": "EMERGENCY",
        "theta": 0.90,
        "theta_upper": 1.00,
        "t_max": float("inf"),  # absorbing state
        "lam": None,
        "t_cool": None,
    },
}


def risk_to_state(rho: float) -> RiskState:
    """Risk-to-state mapping function tau(rho) (Eq. 2).

    Parameters
    ----------
    rho : float
        Risk score in [0, 1].

    Returns
    -------
    RiskState
        The state corresponding to *rho*.
    """
    if rho < 0.0 or rho > 1.0:
        raise ValueError(f"Risk score must be in [0, 1], got {rho}")
    if rho >= 0.9:
        return RiskState.EMERGENCY
    if rho >= 0.7:
        return RiskState.CRITICAL
    if rho >= 0.5:
        return RiskState.ALERT
    if rho >= 0.3:
        return RiskState.MONITOR
    return RiskState.SAFE


def half_life(state: RiskState) -> Optional[float]:
    """Proposition 1: t_{1/2} = ln(2) / lambda_k."""
    lam = STATE_CONFIG[state]["lam"]
    if lam is None:
        return None
    return math.log(2) / lam


def min_deescalation_latency(from_state: RiskState) -> float:
    """Proposition 2: T_min(S_k -> S1) = sum of T_cool(S_j) for j=2..k."""
    total = 0.0
    for level in range(2, int(from_state) + 1):
        s = RiskState(level)
        t_cool = STATE_CONFIG[s]["t_cool"]
        if t_cool is not None:
            total += t_cool
    return total
