# Changelog

All notable changes to DRAS-5 will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
- 13 publication-quality figures (2D + 3D, 300 DPI PDF/PNG)
- CLI entry points: `dras5-demo` and `dras5-validate`
- Jupyter notebook for interactive exploration
- CITATION.cff for proper academic citation

[1.0.0]: https://github.com/ChatchaiTritham/DRAS-5/releases/tag/v1.0.0
