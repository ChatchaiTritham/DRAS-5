"""Tests for dras5.simulator — trajectory generation and evaluation."""

import pytest
from dras5.states import RiskState
from dras5.simulator import generate_trajectory, run_evaluation


class TestGenerateTrajectory:
    def test_monotonic(self):
        traj = generate_trajectory(ttype="monotonic", n_steps=50, seed=0)
        assert len(traj) == 50
        assert all(0 <= p.rho <= 1 for p in traj)

    def test_oscillating(self):
        traj = generate_trajectory(ttype="oscillating", n_steps=50, seed=0)
        assert len(traj) == 50

    def test_spike_recover(self):
        traj = generate_trajectory(ttype="spike_recover", n_steps=50, seed=0)
        assert len(traj) == 50
        # The spike should push the system to high state
        max_sys = max(p.system_state for p in traj)
        assert max_sys >= RiskState.CRITICAL

    def test_invalid_type(self):
        with pytest.raises(ValueError):
            generate_trajectory(ttype="invalid")

    def test_reproducibility(self):
        t1 = generate_trajectory(ttype="monotonic", seed=42)
        t2 = generate_trajectory(ttype="monotonic", seed=42)
        assert [p.rho for p in t1] == [p.rho for p in t2]


class TestRunEvaluation:
    def test_small_evaluation(self):
        result = run_evaluation(n_trajectories=30, n_steps=20)
        assert result.n_trajectories == 30
        assert result.n_evaluations == 30 * 20
        # MER should be 0% (structural guarantee of C1)
        assert result.mer == 0.0

    def test_mer_zero_structural_guarantee(self):
        """Table 6: MER=0% for DRAS is a structural guarantee."""
        result = run_evaluation(n_trajectories=300, n_steps=50)
        assert result.mer == 0.0
