# Changelog

All notable changes to DRAS-5 will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.3.0] - 2026-10-05

### Added

- Two separate C5 approval signals (`approval_1`, `approval_2`) with optional approver identifiers; a missing signal or a repeated identifier denies the request. `dual_approval=True` remains as shorthand for both.
- Audit entries for a C5 grant now record `rho_eff` and both approver identifiers.
- `scripts/revision_metrics.py`: like-for-like MER, upstream-bias and C4-cap measurements, magnitude over-escalation, band-alphabet exhaustive check.
- `scripts/recovery_metrics.py`: silent down-classification, premature step-downs and end-of-episode excess against max-hold.
- `scripts/exhaustive_boundary.py`: boundary-alphabet exhaustive and deep randomised check of C1, C2, C4, C5 and input-relative reach.
- `scripts/cooling_sweep.py` and `scripts/maxhold_baseline.py` results committed under `results/`.
- Tests for single-approval denial, same-approver denial, approver recording and the legacy flag (131 tests).

### Fixed

- **C5 de-escalation S2 -> S1 was unreachable.** `check_c5` required rho_eff < theta_1 = 0.0, which no effective risk satisfies, so a patient who reached MONITOR could never return to SAFE (a patient held at rho = 0 for 4,000 s with two approvals stayed in MONITOR). Found by model checking the TLA+ specification (Corollary 1 violated). The S2 -> S1 step now uses theta_2 (`states.deescalation_threshold`); S3 -> S2 and S4 -> S3 are unchanged. Behaviour change: S2 -> S1 grants are now possible. The 5,000-trajectory results are unchanged (no cohort trajectory requests that step).
- Specification and code now agree on two conventions found by differential testing: the C2 timeout fires when the dwell exceeds T_max (strict), and the C5 cooling window is the T_cool/dt samples after entry.

### Formal verification

- `formal/DRAS5.tla`: TLA+ specification written from the manuscript, model-checked with TLC at dt = 10, 60 and 300 s for C1-C5 and reach (all hold) and Corollary 1 (violated before the fix, holds after). `formal/mutate_spec.py` confirms six injected faults are all rejected.
- `scripts/tla_conformance.py`: differential test of the released machine against the specification (1,795,659 steps, no level divergence; the code is stricter than the specification in one documented respect: it requires a non-increasing rho_eff window).

### Changed

- `scripts/compliance_audit.py` withholds alpha_2, alpha_1 and approver independence in three separate passes.

[1.3.0]: https://github.com/ChatchaiTritham/DRAS-5/releases/tag/v1.3.0

## [1.0.0] - 2026-02-27

### Added

- Five-state risk assessment state machine (S1 SAFE through S5 EMERGENCY)
- Algorithm 1: unified update procedure with phased constraint enforcement
- C1: Monotonic escalation invariant
- C2: Timeout enforcement with auto-escalation
- C3: Immutable append-only audit log with JSON/CSV export
- C4: Human approval gate for S4 -> S5 transition
- C5: Controlled de-escalation with exponential risk decay, dual clinician approval, and single-step regression
- Exponential risk decay tracker (Eq. 5): `rho_eff(t) = max(rho(t), rho_peak * exp(-lambda_k * (t - t_peak)))`
- Table 2 state parameters with state-specific decay rates and cooling periods
- Trajectory simulator with monotonic, oscillating, and spike-recover patterns
- 103 unit tests covering all constraints and parameters
- 13 manuscript-support figures (2D + 3D, 300 DPI PDF/PNG)
- CLI entry points: `dras5-demo` and `dras5-validate`
- Jupyter notebook for interactive exploration

[1.0.0]: https://github.com/ChatchaiTritham/DRAS-5/releases/tag/v1.0.0
