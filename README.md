# DRAS-5

## Overview

DRAS-5 is the Dynamic Risk Assessment State Machine used to model bounded,
stateful escalation for clinical decision support.

## Installation

```bash
pip install -e .
```

## Repository Structure

- `src/dras5/`: importable package
- `tests/`: automated tests
- `scripts/`: runnable demos and figure generation
- `notebooks/`: research notebooks

## Tutorials And Demos

- Scripts:
  - `scripts/demo.py`: quick state-machine walkthrough
  - `scripts/timeout_demo.py`: timeout and escalation behavior
  - `scripts/generate_figures.py`: manuscript-ready figure generation
- Notebooks:
  - `notebooks/01_state_machine_basics.ipynb`: core state machine, constraints, decay, and audit walkthrough
  - `notebooks/02_advanced_governance_workflows.ipynb`: timeout escalation, controlled de-escalation, manual overrides, and audit-driven workflow visualization

## Cross-Repository Tutorial Charts

- `../tutorial_surface_comparison.png`: scripts vs examples vs notebooks across all repositories
- `../tutorial_asset_density.png`: interactive/tutorial asset density normalized by repository size

## Package Scope

The package includes:

- risk states in `src/dras5/states.py`
- transition logic in `src/dras5/state_machine.py`
- constraints, audit logging, decay, and simulation helpers

## Quick Start

```bash
python -m dras5.cli
```

```python
from dras5 import DRAS5StateMachine

state_machine = DRAS5StateMachine()
for risk_score in [0.15, 0.35, 0.55, 0.75]:
    state = state_machine.update(risk_score=risk_score)
    print(f"risk={risk_score:.2f} -> {state.name}")
```

## Source Layout

This repository uses the recommended `src/<package_name>` layout.
Importable code lives in `src/dras5/`.

## Testing

```bash
pytest tests -v
```

---

## Usage Examples

### Basic Escalation

```python
from dras5 import DRAS5StateMachine, RiskState

sm = DRAS5StateMachine()

sm.update(risk_score=0.25, t=10)   # -> SAFE
sm.update(risk_score=0.45, t=20)   # -> MONITOR
sm.update(risk_score=0.65, t=30)   # -> ALERT
sm.update(risk_score=0.80, t=40)   # -> CRITICAL

# Monotonic constraint: dropping risk does NOT drop state
sm.update(risk_score=0.20, t=50)   # -> CRITICAL (C1 enforced)
```

### Human Approval Gate (C4)

```python
sm = DRAS5StateMachine(require_human_approval=True)
sm.update(risk_score=0.75, t=10)

# Blocked without approval
sm.update(risk_score=0.95, t=20, human_approved=False)   # -> CRITICAL
# Approved
sm.update(risk_score=0.95, t=21, human_approved=True)    # -> EMERGENCY
```

### C5 De-escalation

```python
from dras5 import DRAS5StateMachine, check_c5, RiskState

sm = DRAS5StateMachine(require_human_approval=False)
sm.update(risk_score=0.75, t=0)   # -> CRITICAL

# After cooling period, with sustained low effective risk:
rho_eff_samples = [0.45, 0.42, 0.40, 0.38, 0.35]  # all < theta_3 = 0.50

result = sm.update(
    risk_score=0.35,
    t=200,
    deescalation_request=True,
    human_approved=True,
    dual_approval=True,
    rho_eff_series=rho_eff_samples,
)
print(result)  # -> ALERT  (de-escalated one level)
```

### Effective Risk Computation

```python
import math
from dras5 import DRAS5StateMachine

sm = DRAS5StateMachine(require_human_approval=False)
sm.update(risk_score=0.85, t=0)   # peak in S4

# Effective risk decays exponentially from peak
for dt in [0, 100, 200, 500, 700]:
    rho_eff = sm.get_effective_risk(rho=0.30, t=dt)
    print(f"  t={dt:4d}s  rho_eff={rho_eff:.4f}")
```

### Audit Trail

```python
sm = DRAS5StateMachine(session_id="patient-42")
sm.update(risk_score=0.55, t=10)
sm.update(risk_score=0.80, t=20)

for entry in sm.get_history():
    print(f"  {entry.from_state.name} -> {entry.to_state.name}  "
          f"rho={entry.risk_score:.2f}  trigger={entry.trigger}")

# Export
print(sm.audit_log.to_json())
```

### Trajectory Simulation

```python
from dras5 import generate_trajectory, run_evaluation

# Single trajectory
traj = generate_trajectory(ttype="spike_recover", n_steps=100, seed=42)
for p in traj[:5]:
    print(f"  t={p.t:.0f}  rho={p.rho:.3f}  true={p.true_state.name}  "
          f"sys={p.system_state.name}")

# Full evaluation (5,000 trajectories)
result = run_evaluation(n_trajectories=5000)
print(f"  MER = {result.mer*100:.1f}%")
print(f"  OER = {result.oer*100:.1f}%")
```

---

## Repository Structure

```
DRAS-5/
  src/
    dras5/
     __init__.py          # Public API exports
     states.py            # RiskState enum, Table 2 parameters, tau(rho)
     state_machine.py     # DRAS5StateMachine (Algorithm 1)
    constraints.py       # C1--C5 validators
    decay.py             # Exponential risk decay tracker (Eq. 5)
    audit.py             # Immutable audit log (C3)
    simulator.py         # Trajectory generator & evaluation
    cli.py               # Command-line demo and validator
  tests/
    test_states.py
    test_constraints.py
    test_state_machine.py
    test_decay.py
    test_audit.py
    test_simulator.py
  scripts/
    demo.py              # Quick demonstration
    generate_figures.py  # Reproduce manuscript figures
  notebooks/
    01_state_machine_basics.ipynb
  .github/
    ISSUE_TEMPLATE/      # Bug report & feature request templates
    PULL_REQUEST_TEMPLATE.md
  CHANGELOG.md
  CITATION.cff
  CODE_OF_CONDUCT.md
  CONTRIBUTING.md
  LICENSE                # MIT (research use only)
  SECURITY.md
  requirements.txt
  setup.py
```

---

## Formal Properties

Seven theorems are stated and proved in the manuscript:

| Theorem | Property | Guarantee |
|---------|----------|-----------|
| 1 | C1 Invariant | State level is non-decreasing unless C5-approved |
| 2 | C2 Invariant | duration(S_k) <= T_max + epsilon |
| 3 | C3 Invariant | No transition without audit entry |
| 4 | C4 Invariant | S4 -> S5 impossible without alpha=1 |
| 5 | C5 Invariant | Bounded, approved, single-step de-escalation |
| 6 | Time complexity | O(1) per update |
| 7 | Space complexity | O(1) active state, O(n) audit log |

**Proposition 1**: Half-life t_{1/2} = ln(2) / lambda_k

**Proposition 2**: Minimum de-escalation latency S_k -> S1 = sum of T_cool(S_j), j=2..k

**Corollary 1** (Liveness): If risk stays at zero and dual approval is always available, the system eventually returns to S1.

---

## Regulatory Mapping

| Constraint | IEC 61508 | IEC 62304 | EU AI Act 2024 |
|-----------|-----------|-----------|----------------|
| C1 Monotonic | SIL 3 (7.4.2.2) | Class C | Art. 9 |
| C2 Timeout | SIL 2 (7.4.3) | Class B | Art. 9 |
| C3 Audit | SIL 1+ (7.4.7) | Class A | Art. 12 |
| C4 Human gate | SIL 3 (7.4.2.6) | Class C | Art. 14 |
| C5 De-escalation | SIL 2 (7.4.4) | Class B | Art. 9 |

---

## Safety Notice

This software is for **research purposes only**.

- Not FDA-cleared, CE-marked, or TFDA-approved
- Not validated on real patient data
- Not suitable for clinical decision-making without proper validation,
  regulatory approval, and clinical oversight
- Synthetic trajectories model literature-documented deterioration
  patterns but do not replace prospective clinical trials

---

## Citation

```bibtex
@article{tritham2026dras5,
  author  = {Tritham, Chatchai and Snae Namahoot, Chakkrit},
  title   = {{DRAS-5}: A Dynamic Risk Assessment State Machine with
             Exponential Decay De-escalation and Provable Safety
             Guarantees for Clinical Decision Support},
  journal = {Applied Intelligence},
  year    = {2026},
  note    = {Under review}
}
```

---

## License

MIT License.  See [LICENSE](LICENSE) for details.

---

## Contact

### Contact Author

**Chatchai Tritham** (PhD Candidate)

- Email: [chatchait66@nu.ac.th](mailto:chatchait66@nu.ac.th)
- Department of Computer Science and Information Technology
- Faculty of Science, Naresuan University
- Phitsanulok 65000, Thailand

### Supervisor

**Chakkrit Snae Namahoot**

- Email: [chakkrits@nu.ac.th](mailto:chakkrits@nu.ac.th)
- Department of Computer Science
- Faculty of Science, Naresuan University
- Phitsanulok 65000, Thailand
