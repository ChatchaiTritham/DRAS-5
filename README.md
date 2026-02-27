# DRAS-5: Dynamic Risk Assessment State Machine

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.8+](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/downloads/)
[![Tests: 103 passed](https://img.shields.io/badge/tests-103%20passed-brightgreen.svg)](tests/)
[![Status: Research](https://img.shields.io/badge/status-research-orange.svg)](https://github.com/ChatchaiTritham/DRAS-5)

> A five-state risk assessment machine with exponential decay de-escalation
> and provable safety guarantees for clinical decision support.

**DRAS-5** implements a formal state machine that governs patient risk
transitions through five acuity levels (S1 SAFE through S5 EMERGENCY).
Five safety constraints (C1--C5) are enforced on every update cycle,
including a novel **controlled de-escalation protocol (C5)** that permits
state regression only when an exponential risk decay has been sustained
for a full cooling period and two independent clinicians approve.

Part of the emergency triage trilogy:
[TRI-X](https://github.com/ChatchaiTritham/TRI-X) |
**DRAS-5** |
[ORASR](https://github.com/ChatchaiTritham/ORASR)

---

## Key Results

| Metric | DRAS-5 | NEWS2 (stateless) | MEWS (stateless) |
|--------|--------|-------------------|-------------------|
| Missed Escalation Rate | **0.0%** | 11.2% | 12.8% |
| Over-Escalation Rate (with C5) | **3.6%** | 0.0% | 0.0% |
| Over-Escalation Rate (no C5) | 7.4% | 0.0% | 0.0% |

- 0% MER is a **structural guarantee** of C1, not a statistical finding
- C5 reduces over-escalation by **51%** (7.4% to 3.6%) without sacrificing safety
- O(1) transition complexity; >8,300 updates/second

---

## Quick Start

```bash
git clone https://github.com/ChatchaiTritham/DRAS-5.git && cd DRAS-5
pip install -e .

# Run interactive demo
python -m dras5.cli

# Or from Python
python -c "
from dras5 import DRAS5StateMachine, RiskState

sm = DRAS5StateMachine()
for rho in [0.15, 0.35, 0.55, 0.75]:
    s = sm.update(risk_score=rho, t=rho*100)
    print(f'rho={rho:.2f} -> {s.name}')
"
```

---

## State Model (Table 2)

| State | Entry Threshold | T_max | Decay Rate | Cooling Period | Half-Life |
|-------|:-:|:-:|:-:|:-:|:-:|
| S1 SAFE | 0.00 | -- | -- | -- | -- |
| S2 MONITOR | 0.30 | 300 s (5 min) | 0.005 s^-1 | 600 s | 139 s |
| S3 ALERT | 0.50 | 120 s (2 min) | 0.003 s^-1 | 300 s | 231 s |
| S4 CRITICAL | 0.70 | 60 s (1 min) | 0.001 s^-1 | 180 s | 693 s |
| S5 EMERGENCY | 0.90 | -- | -- | -- | -- |

Higher-acuity states have smaller decay rates, so risk memory persists
longer: S4 decays roughly 5x slower than S2.

---

## Five Safety Constraints

### C1 -- Monotonic Escalation

```
s(t+1) >= s(t)   unless C5-approved
```

Once the patient's risk state escalates, it cannot automatically revert.
This eliminates the 12--15% missed escalation rate observed in stateless
scoring systems.

### C2 -- Timeout Enforcement

```
duration(S_k) <= T_max(S_k) + epsilon
```

If a patient remains in S2, S3, or S4 beyond the maximum allowed
duration, the machine auto-escalates by one level.  This prevents
clinical situations from stalling in intermediate states.

### C3 -- Audit Completeness

Every state transition produces an immutable, append-only log entry
containing timestamp, from/to states, risk scores, trigger type,
approval signals, and constraint validation results.

### C4 -- Human Approval Gate

```
S4 -> S5  requires  alpha = 1
```

The transition from CRITICAL to EMERGENCY is blocked unless a clinician
explicitly approves.  This prevents automated over-escalation to the
highest acuity level.

### C5 -- Controlled De-escalation (Novel)

```
rho_eff(t) = max(rho(t),  rho_peak * exp(-lambda_k * (t - t_peak)))
```

De-escalation from S_k to S_{k-1} requires **all three** conditions:

1. **Sustained decay** -- the effective risk rho_eff stays below the
   target threshold for the entire cooling period T_cool.
2. **Dual clinician approval** -- two independent clinicians approve.
3. **Single-step regression** -- at most one level per de-escalation event.

De-escalation from S5 is not permitted through C5; it requires a full
clinical review.

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

## Authors

| # | Name | Role | Email |
| --- | ------ | ------ | ------- |
| 1 | **Chatchai Tritham** | PhD Candidate | `chatchait66@nu.ac.th` |
| 2 | **Chakkrit Snae Namahoot** | Supervisor (Corresponding Author) | `chakkrits@nu.ac.th` |

**Affiliation**: Department of Computer Science and Information Technology,
Faculty of Science, Naresuan University, Phitsanulok 65000, Thailand
