# Changelog

All notable changes to DRAS-5 will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.6.0] - 2026-10-12

Second revision round (items E-02, E-03, E-04, E-09, E-16, E-21 of the round-2 simulated review).

### Added

- `scripts/tradeoff_frontier.py`: reach versus over-escalation frontier (threshold shift for stateless, max-hold, hysteresis, timed release and decayed max; T_max factor for DRAS-5) at ward hourly/irregular/4-hourly charting and behind the vital-sign predictor, with a matched-OER comparison; the recoverable comparison re-run on two-hour (720-sample) episodes; premature step-downs counted against the noise-free trajectory. Outputs `results/tradeoff_frontier.csv`, `tradeoff_matched.csv`, `long_episodes.csv`, `long_episodes_summary.json`, `premature_noisefree.csv`.

### Changed

- `scripts/ward_timing.py`: adds decayed max at ward decay rates and the column `c2_timeouts_per_patient_day`; all earlier rows are unchanged.
- `scripts/fig_recoverable.py`: panel (a) relabelled "ended below the sustained input peak"; panel (b) x-axis to 80%.
- README and REPRODUCIBILITY: install from the clone (`pip install -e .` or `PYTHONPATH=src`), script runtimes, and which script writes which CSV.

## [1.5.0] - 2026-10-12

Revision in response to a ten-reviewer simulated review (items D-04..D-18).

### Added

- `scripts/recoverable_baselines.py`: hysteresis, timed-release max-hold and decayed-max baselines; registration delay and failure to register within 5 min; paired bootstrap CIs (DRAS-5 vs NEWS2 on MER_end, CI of DRAS-5 MER_end, DRAS-5 vs every baseline on end excess and OER); per-family results; Dirichlet mixture-weight sensitivity; generator hyperparameter sensitivity; C5 grants by family and transition; attribution runs (no C5, C2 clock restarting, no C2). Outputs `results/recoverable_baselines.csv`, `recoverable_summary.json`, `mixture_sensitivity.csv`, `generator_sensitivity.csv`.
- `scripts/ward_timing.py`: 24-hour episodes observed hourly, irregularly (30-120 min) or 4-hourly with 10% missing charts; shipped and ward-scaled (x60) parameters. Output `results/ward_timing.csv`.
- `scripts/ml_wrapper_v2.py`: autoregressive and vital-sign (lag, nonlinearity, missingness, site shift) upstream predictors; stateless every sample / every 2nd sample, max-hold and DRAS-5 arms. Output `results/ml_wrapper_v2.csv`.
- `scripts/run_tlc.py`: regenerates `formal/out/` with TLC from TLA+ release v1.7.4 (TLC 2.19), SHA-256 pinned.
- Two TLA+ mutants (C5c two-level grant; unregistered band for reach): eight mutants, all rejected.
- `scripts/tla_conformance.py --oracle`: the model's effective-risk band comes from an independent recomputation of the decay, not from the code (`results/tla_conformance_oracle.json`).
- `scripts/fig_recoverable.py` -> `figures/fig_systems_mer_oer.pdf`.
- `DRAS5StateMachine(c2_clock="rewarrant")`: optional C2 clock that restarts when the patient returns to the band; default `"entry"` unchanged.
- `approval_pending` flag and `pending_events` when the S4 timeout elapses without S5 approval.

### Changed

- C5(a) is decided in O(1) from an incremental run counter (Theorem 6 now holds for the code); the v1.4.0 window rescan is kept as `_c5_window_ok_rescan` and `tests/test_c5_incremental.py` checks they agree. All `run_all.py` outputs are byte-identical.
- Result keys renamed to the paper's definitions: `summary.json` `mer_reach_overall_pct` (DRAS-5) and `mer_end_overall_pct` (NEWS2, MEWS) with matching `*_ci95`; `mer_by_type.csv` columns `mer_reach_dras5_*`, `mer_end_news2_*`, `mer_end_mews_*`; `maxhold_baseline.csv` `mer_reach_pct` (was `mer_ever_pct`). `under_recognition_overall_pct` is documented as a diagnostic.
- `run_all.py`: spike-to-critical decay is the named constant `SPIKEC_DECAY` (value unchanged).
- `pytest.ini`: removed the unknown `asyncio_default_fixture_loop_scope` option (warning).

### Removed

- Uncommitted λ×T_cool edit of `scripts/cooling_sweep.py` discarded (duplicated `scripts/decay_sweep.py`); the stale `results/cooling_sweep.csv|json`, used by no script or paper table, deleted.

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

- `formal/DRAS5.tla`: TLA+ specification drafted from the manuscript (not independent of the code; see `formal/README.md`), model-checked with TLC at dt = 10, 60 and 300 s for C1-C5 and reach (all hold) and Corollary 1 (violated before the fix, holds after). `formal/mutate_spec.py` confirms six injected faults are all rejected.
- `scripts/tla_conformance.py`: differential test of the released machine against the specification (1,795,659 steps, no level divergence; the code is stricter than the specification in one documented respect: it requires a non-increasing rho_eff window).

### Changed

- Metadata (`.zenodo.json`, `CITATION.cff`, README citation) no longer says "formally verified" or "guarantees zero missed escalations"; the guarantee is stated relative to the scores the layer receives, and the evaluation is synthetic only.
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
