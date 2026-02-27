"""
DRAS-5 Exponential Risk Decay (C5 core)

Implements the effective-risk function (Eq. 5):

    rho_eff(t) = max(rho(t), rho_peak * exp(-lambda_k * (t - t_peak)))

The decay enforces *risk memory*: after a high-risk episode the effective
risk decays exponentially rather than dropping immediately, preventing
premature de-escalation.

Reference
---------
Tritham C, Snae Namahoot C (2026). DRAS-5, Section 3.3.
"""

import math
from typing import Optional

from .states import RiskState, STATE_CONFIG

__all__ = ["DecayTracker"]


class DecayTracker:
    """Tracks peak risk and computes effective risk via exponential decay.

    One tracker instance is created per patient session and is updated
    whenever the patient's state changes.
    """

    def __init__(self) -> None:
        self._rho_peak: float = 0.0
        self._t_peak: float = 0.0
        self._current_state: Optional[RiskState] = None

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def update_peak(self, rho: float, t: float) -> None:
        """Record a new observed risk score; update peak if necessary."""
        if rho > self._rho_peak:
            self._rho_peak = rho
            self._t_peak = t

    def reset(self, state: RiskState) -> None:
        """Reset peak tracking when entering a new state."""
        self._rho_peak = 0.0
        self._t_peak = 0.0
        self._current_state = state

    def effective_risk(self, rho: float, t: float,
                       state: RiskState) -> float:
        """Compute rho_eff(t) per Eq. 5.

        Parameters
        ----------
        rho : float
            Instantaneous risk score.
        t : float
            Current wall-clock time (seconds since epoch or session start).
        state : RiskState
            The patient's current state (determines lambda_k).

        Returns
        -------
        float
            max(rho, rho_peak * exp(-lambda_k * (t - t_peak)))
        """
        lam = STATE_CONFIG[state]["lam"]
        if lam is None:
            # S1 and S5 have no decay — return raw risk
            return rho
        dt = max(0.0, t - self._t_peak)
        decayed = self._rho_peak * math.exp(-lam * dt)
        return max(rho, decayed)

    # ------------------------------------------------------------------
    # Read-only properties
    # ------------------------------------------------------------------

    @property
    def rho_peak(self) -> float:
        return self._rho_peak

    @property
    def t_peak(self) -> float:
        return self._t_peak
