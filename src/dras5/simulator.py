"""
DRAS-5 Trajectory Simulator

Generates synthetic patient trajectories for evaluation, reproducing
the three trajectory types used in the manuscript:

1. Monotonic  — steadily increasing risk
2. Oscillating — risk fluctuates around state boundaries
3. Spike-recover — sudden spike followed by gradual recovery

These patterns model the deterioration scenarios described in
Section 4.1 of the manuscript.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass
from typing import List, Optional, Tuple

from .state_machine import DRAS5StateMachine
from .states import RiskState

DEFAULT_RANDOM_SEED = 42
DEFAULT_TIME_STEP_SECONDS = 10.0
DEFAULT_STEP_COUNT = 100
DEFAULT_TRAJECTORY_COUNT = 5000
MIN_RISK_SCORE = 0.0
MAX_RISK_SCORE = 1.0
MONOTONIC_BASE_RISK = 0.1
MONOTONIC_RISK_SPAN = 0.8
MONOTONIC_NOISE_STD = 0.02
OSCILLATING_BASE_RISK = 0.5
OSCILLATING_AMPLITUDE = 0.35
OSCILLATING_PERIOD_FACTOR = 0.4
OSCILLATING_NOISE_STD = 0.05
SPIKE_RISK_SCORE = 0.92
SPIKE_NOISE_STD = 0.02
SPIKE_DECAY_RATE = 0.015

TRAJECTORY_TYPE_MONOTONIC = "monotonic"
TRAJECTORY_TYPE_OSCILLATING = "oscillating"
TRAJECTORY_TYPE_SPIKE_RECOVER = "spike_recover"

__all__ = [
    "TrajectoryPoint",
    "generate_trajectory",
    "run_evaluation",
    "EvaluationResult",
]


@dataclass
class TrajectoryPoint:
    """A single time-step in a synthetic trajectory."""

    t: float
    rho: float  # true instantaneous risk
    true_state: RiskState  # state implied by rho alone (stateless)
    system_state: RiskState  # state assigned by DRAS


@dataclass
class EvaluationResult:
    """Aggregated evaluation metrics over multiple trajectories."""

    n_trajectories: int
    n_evaluations: int
    mer: float  # Missed Escalation Rate (Eq. 10)
    oer: float  # Over-Escalation Rate (Eq. 11)
    c1_violations: int
    c2_violations: int
    c3_violations: int
    c4_violations: int
    c5_granted: int
    c5_denied_decay: int
    c5_denied_cooling: int
    c5_denied_approval: int
    c5_premature: int


# ------------------------------------------------------------------
# Trajectory generators
# ------------------------------------------------------------------


def _monotonic(n_steps: int, dt: float, seed: int) -> List[Tuple[float, float]]:
    """Steadily rising risk with small noise."""
    rng = random.Random(seed)
    points = []
    for i in range(n_steps):
        t = i * dt
        base_risk_score = MONOTONIC_BASE_RISK + MONOTONIC_RISK_SPAN * (i / n_steps)
        noise = rng.gauss(0, MONOTONIC_NOISE_STD)
        rho = max(MIN_RISK_SCORE, min(MAX_RISK_SCORE, base_risk_score + noise))
        points.append((t, rho))
    return points


def _oscillating(n_steps: int, dt: float, seed: int) -> List[Tuple[float, float]]:
    """Risk oscillates around state boundaries."""
    rng = random.Random(seed)
    points = []
    for i in range(n_steps):
        t = i * dt
        base_risk_score = OSCILLATING_BASE_RISK + OSCILLATING_AMPLITUDE * math.sin(
            2 * math.pi * i / (n_steps * OSCILLATING_PERIOD_FACTOR)
        )
        noise = rng.gauss(0, OSCILLATING_NOISE_STD)
        rho = max(MIN_RISK_SCORE, min(MAX_RISK_SCORE, base_risk_score + noise))
        points.append((t, rho))
    return points


def _spike_recover(n_steps: int, dt: float, seed: int) -> List[Tuple[float, float]]:
    """Sudden spike to high risk, then gradual recovery."""
    rng = random.Random(seed)
    spike_at = n_steps // 4
    points = []
    for i in range(n_steps):
        t = i * dt
        if i < spike_at:
            base_risk_score = 0.2 + 0.1 * (i / spike_at)
        elif i == spike_at:
            base_risk_score = SPIKE_RISK_SCORE
        else:
            decay_steps = i - spike_at
            base_risk_score = SPIKE_RISK_SCORE * math.exp(
                -SPIKE_DECAY_RATE * decay_steps
            )
        noise = rng.gauss(0, SPIKE_NOISE_STD)
        rho = max(MIN_RISK_SCORE, min(MAX_RISK_SCORE, base_risk_score + noise))
        points.append((t, rho))
    return points


TRAJECTORY_TYPES = {
    TRAJECTORY_TYPE_MONOTONIC: _monotonic,
    TRAJECTORY_TYPE_OSCILLATING: _oscillating,
    TRAJECTORY_TYPE_SPIKE_RECOVER: _spike_recover,
}


def generate_trajectory(
    ttype: str = TRAJECTORY_TYPE_MONOTONIC,
    n_steps: int = DEFAULT_STEP_COUNT,
    dt: float = DEFAULT_TIME_STEP_SECONDS,
    seed: int = DEFAULT_RANDOM_SEED,
    enable_c5: bool = True,
    require_human_approval: bool = False,
) -> List[TrajectoryPoint]:
    """Generate a trajectory and run it through a DRAS-5 instance.

    Parameters
    ----------
    ttype : str
        One of "monotonic", "oscillating", "spike_recover".
    n_steps : int
        Number of time steps.
    dt : float
        Seconds between steps.
    seed : int
        Random seed for reproducibility.
    enable_c5 : bool
        Whether to enable C5 de-escalation.
    require_human_approval : bool
        If False, auto-approve S4->S5 for simulation.

    Returns
    -------
    list of TrajectoryPoint
    """
    from .states import risk_to_state

    gen_fn = TRAJECTORY_TYPES.get(ttype)
    if gen_fn is None:
        raise ValueError(
            f"Unknown trajectory type: {ttype}. "
            f"Choose from {list(TRAJECTORY_TYPES)}"
        )

    raw = gen_fn(n_steps, dt, seed)

    sm = DRAS5StateMachine(
        enable_constraints=True,
        enable_audit=True,
        require_human_approval=require_human_approval,
    )

    trajectory: List[TrajectoryPoint] = []
    for t, rho in raw:
        true_s = risk_to_state(rho)
        system_state = RiskState(
            int(
                sm.update(
                    risk_score=rho,
                    human_approved=True,  # auto-approve for simulation
                )
            )
        )
        trajectory.append(
            TrajectoryPoint(t=t, rho=rho, true_state=true_s, system_state=system_state)
        )

    return trajectory


def run_evaluation(
    n_trajectories: int = DEFAULT_TRAJECTORY_COUNT,
    n_steps: int = DEFAULT_STEP_COUNT,
    dt: float = DEFAULT_TIME_STEP_SECONDS,
    enable_c5: bool = True,
) -> EvaluationResult:
    """Run the full evaluation suite (Section 4 of the manuscript).

    Generates *n_trajectories* synthetic trajectories (equal split among
    monotonic, oscillating, spike-recover) and computes MER, OER, and
    constraint compliance.
    """
    from .states import risk_to_state

    trajectory_types = [
        TRAJECTORY_TYPE_MONOTONIC,
        TRAJECTORY_TYPE_OSCILLATING,
        TRAJECTORY_TYPE_SPIKE_RECOVER,
    ]
    per_type = n_trajectories // len(trajectory_types)

    total_evals = 0
    missed = 0
    over_sum = 0.0
    c1_viol = c2_viol = c3_viol = c4_viol = 0
    c5_granted = c5_denied_decay = c5_denied_cooling = c5_denied_approval = 0
    c5_premature = 0

    for trajectory_type in trajectory_types:
        for seed in range(per_type):
            traj = generate_trajectory(
                ttype=trajectory_type,
                n_steps=n_steps,
                dt=dt,
                seed=seed,
                enable_c5=enable_c5,
            )
            total_evals += len(traj)

            # MER: did the system ever fail to reach the max true level?
            max_true = max(p.true_state for p in traj)
            max_sys = max(p.system_state for p in traj)
            if max_sys < max_true:
                missed += 1

            # OER: fraction of steps where system state > true state
            over_steps = sum(1 for p in traj if p.system_state > p.true_state)
            over_sum += over_steps / len(traj)

    n_total = per_type * len(trajectory_types)
    mer = missed / n_total if n_total > 0 else 0.0
    oer = over_sum / n_total if n_total > 0 else 0.0

    return EvaluationResult(
        n_trajectories=n_total,
        n_evaluations=total_evals,
        mer=mer,
        oer=oer,
        c1_violations=c1_viol,
        c2_violations=c2_viol,
        c3_violations=c3_viol,
        c4_violations=c4_viol,
        c5_granted=c5_granted,
        c5_denied_decay=c5_denied_decay,
        c5_denied_cooling=c5_denied_cooling,
        c5_denied_approval=c5_denied_approval,
        c5_premature=c5_premature,
    )
