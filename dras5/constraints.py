"""
DRAS-5 Constraint Enforcement (C1--C5)

Implements the five formal safety constraints as validators that return
(passed: bool, reason: str).  The unified update procedure (Algorithm 1)
calls these validators in sequence.

Constraint summary
------------------
C1  Monotonic Escalation    s(t+1) >= s(t) unless C5-approved
C2  Timeout Enforcement     duration(S_k) <= T_max(S_k) + epsilon
C3  Audit Completeness      every transition logged (handled by AuditLog)
C4  Human Approval Gate     S4 -> S5 requires alpha = 1
C5  Controlled De-escalation  sustained decay + dual approval + single step

Reference
---------
Tritham C, Snae Namahoot C (2026). DRAS-5, Definitions 4.1--4.5.
"""

from __future__ import annotations

from typing import List, Tuple

from .states import RiskState, STATE_CONFIG

__all__ = ["check_c1", "check_c2", "check_c4", "check_c5",
           "validate_all"]

ConstraintResult = Tuple[bool, str]


# ------------------------------------------------------------------
# C1: Monotonic Escalation (Definition 4.1 / Theorem 1)
# ------------------------------------------------------------------

def check_c1(current: RiskState, proposed: RiskState,
             c5_approved: bool = False) -> ConstraintResult:
    """Enforce non-decreasing state level.

    Returns (True, ...) if the transition is upward, lateral, or a
    C5-approved de-escalation.
    """
    if proposed >= current:
        return True, "C1 OK: escalation or hold"
    if c5_approved:
        return True, "C1 OK: C5-approved de-escalation"
    return False, f"C1 VIOLATION: {current.name}->{proposed.name} blocked (no C5 approval)"


# ------------------------------------------------------------------
# C2: Timeout Enforcement (Definition 4.2 / Theorem 2)
# ------------------------------------------------------------------

def check_c2(state: RiskState, elapsed: float,
             epsilon: float = 1.0) -> ConstraintResult:
    """Check whether the patient has exceeded T_max in the current state.

    Parameters
    ----------
    state : RiskState
    elapsed : float
        Time (seconds) spent in *state*.
    epsilon : float
        Polling tolerance (default 1 s).

    Returns
    -------
    (bool, str)
        True means a timeout has occurred and auto-escalation is needed.
    """
    t_max = STATE_CONFIG[state]["t_max"]
    if t_max == float("inf"):
        return False, "C2 OK: no timeout for this state"
    if elapsed >= t_max + epsilon:
        return True, f"C2 TIMEOUT: {state.name} exceeded {t_max}s (+{epsilon}s tolerance)"
    return False, f"C2 OK: {elapsed:.1f}s / {t_max}s"


# ------------------------------------------------------------------
# C4: Human Approval Gate (Definition 4.4 / Theorem 4)
# ------------------------------------------------------------------

def check_c4(current: RiskState, proposed: RiskState,
             alpha: bool) -> ConstraintResult:
    """Block S4 -> S5 unless clinician approval (alpha) is present."""
    if current == RiskState.CRITICAL and proposed == RiskState.EMERGENCY:
        if alpha:
            return True, "C4 OK: S4->S5 approved"
        return False, "C4 BLOCKED: S4->S5 requires human approval (alpha=1)"
    return True, "C4 OK: gate not applicable"


# ------------------------------------------------------------------
# C5: Controlled De-escalation (Definition 4.5 / Theorem 5)
# ------------------------------------------------------------------

def check_c5(current: RiskState,
             rho_eff_series: List[float],
             alpha1: bool,
             alpha2: bool) -> ConstraintResult:
    """Evaluate Algorithm 2 — C5 de-escalation decision.

    Parameters
    ----------
    current : RiskState
        Patient's current state S_k.
    rho_eff_series : list of float
        Effective risk values sampled over the full cooling period
        [t_r, t_r + T_cool].
    alpha1, alpha2 : bool
        Two independent clinician approvals.

    Returns
    -------
    (bool, str)
        True means de-escalation is granted.
    """
    # Lines 1-2 of Algorithm 2
    if current == RiskState.SAFE:
        return False, "C5 DENY: already at S1"
    if current == RiskState.EMERGENCY:
        return False, "C5 DENY: S5 requires full clinical review"

    # Line 3-5: dual approval
    if not alpha1 or not alpha2:
        missing = []
        if not alpha1:
            missing.append("alpha1")
        if not alpha2:
            missing.append("alpha2")
        return False, f"C5 DENY: missing clinician approval ({', '.join(missing)})"

    # Target threshold for one level below
    target = RiskState(int(current) - 1)
    theta_target = STATE_CONFIG[target]["theta"]

    # Cooling period check
    t_cool = STATE_CONFIG[current]["t_cool"]
    if t_cool is None:
        return False, "C5 DENY: no cooling period defined"

    if len(rho_eff_series) == 0:
        return False, "C5 DENY: no decay observations"

    # Lines 6-11: sustained decay check
    for i, rho_eff in enumerate(rho_eff_series):
        if rho_eff >= theta_target:
            return False, (
                f"C5 DENY: decay not sustained at sample {i} "
                f"(rho_eff={rho_eff:.4f} >= theta={theta_target})"
            )

    return True, "C5 GRANT: all conditions met"


# ------------------------------------------------------------------
# Combined validator
# ------------------------------------------------------------------

def validate_all(current: RiskState,
                 proposed: RiskState,
                 elapsed: float,
                 alpha: bool = False,
                 c5_approved: bool = False,
                 epsilon: float = 1.0) -> Tuple[bool, List[str]]:
    """Run C1, C2, and C4 checks in sequence.

    C3 is enforced by the AuditLog (append-only).
    C5 is evaluated separately via check_c5().

    Returns (all_passed, list_of_messages).
    """
    results: List[ConstraintResult] = []
    results.append(check_c1(current, proposed, c5_approved))
    results.append(check_c2(current, elapsed, epsilon))
    results.append(check_c4(current, proposed, alpha))

    all_ok = all(r[0] for r in results)
    messages = [r[1] for r in results]
    return all_ok, messages
