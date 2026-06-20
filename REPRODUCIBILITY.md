# Reproducibility notes

This document records exactly which manuscript results are reproducible from the
committed code, using the deterministic driver `scripts/run_all.py` (fixed seed 42).
Run it with:

```bash
pip install -e .
python scripts/run_all.py            # writes results/*.csv and results/summary.json
python scripts/generate_figures.py   # redraws the data figures from results/*.csv
```

Every reported number below is regenerated from a single fixed seed (42). The
per-trajectory seeds are derived from a stable type index (independent of
`PYTHONHASHSEED`), so a rerun reproduces the byte-identical CSVs (`latency.csv`
excepted: wall-clock timing is reported but excluded from the byte-stability
contract).

## What reproduces

| Result | `run_all.py` (seed 42, 5000 trajectories) | Artifact | Status |
|--------|-------------------------------------------|----------|--------|
| Missed Escalation Rate, DRAS-5 (Eq. 10) | **0.0%** (every trajectory type) | `mer_by_type.csv` | reproduced (structural consequence of C1) |
| Missed Escalation Rate, NEWS2 / MEWS | **74.2% / 75.6%** | `mer_by_type.csv` | reproduced |
| Graded under-recognition, NEWS2 / MEWS | **65% / 67%** (DRAS-5 0%) | `mer_by_type.csv` (`urr_*`), `summary.json` | reproduced |
| Over-Escalation Rate, DRAS-5 with / without C5 (binary, Eq. 11) | **69.7% / 69.7%** (0.0% reduction) | `oer_by_type.csv`, `summary.json` (`oer_reduction_pct`) | reproduced |
| C5 de-escalation outcomes | **0 granted, 0 premature** (0 decay / 26,673 cooling / 0 approval denials; 26,673 requests) | `c5_outcomes.csv` | reproduced |
| ML-wrapper guarantee (GBT input) | governed MER **0.0%** vs ungoverned **100%**, GBT RMSE 0.0563 | `summary.json` (`ml_wrapper`) | reproduced |
| Transition latency / throughput | **~0.03 ms/update, ~33,000 updates/s** (O(1)) | `latency.csv` | reproduced (wall-clock; machine-dependent) |

### Missed Escalation Rate (memory model)

MER is defined memory-faithfully, matching the manuscript's motivating example (a
stateless score "erases" an earlier critical reading once the patient recovers): a
missed escalation is recorded when, at the end-of-episode decision point, the
system's retained level is below the patient's **sustained** peak. DRAS-5 retains
any attained level (C1), so it never misses. A stateless score keeps no memory, so
once a transient peak resolves it reverts to the current reading and no longer
reflects the escalation. This is why baseline MER is near zero on monotonic
trajectories (no peak to forget) but near-total on trajectories with a resolved
peak (oscillating, spike). The graded under-recognition rate reports the *severity*
(fraction of the post-peak window the score sits below the peak) so the result is
not read as an all-or-nothing claim.

### Over-Escalation Rate (binary vs magnitude)

Under the binary OER definition (Eq. 11: any sample whose system level exceeds the
instantaneous true level), C5 makes no difference (69.7% with and without). On the
released parameter regime the reason is simpler than a magnitude effect: C5 grants
**no** de-escalations at all (0 of 26,673 requests; see below), so the with-C5 and
without-C5 runs produce the identical state sequence. We therefore make no empirical
over-escalation-benefit claim on this cohort. The controlled-de-escalation guarantee
(no premature de-escalation, Theorem 5) holds vacuously here — every request is
denied for an incomplete cooling window, so there is no premature grant to make.

## Model refinements applied

So that C5 can operate as intended, the committed state machine makes two
refinements (the full test suite still passes):

1. **C2 timeout is risk-gated** (`_check_and_auto_escalate`): timeout
   auto-escalation does not fire for a patient whose risk has already resolved below
   the current state's entry threshold; a recovering patient stays eligible for
   controlled de-escalation instead of being forced into the absorbing EMERGENCY
   state.
2. **C5 is evaluated over the cooling-period window** (`_rho_eff_times`): the
   effective-risk samples accumulated immediately after state entry (still near the
   entry peak) are excluded; C5 is checked over the trailing window of length
   `t_cool`, matching Theorem 5(a). `check_c5` itself is unchanged.

The cohort includes a `spike_critical` family (a rise to CRITICAL followed by a
sustained sub-threshold recovery) intended to exercise controlled de-escalation. On
the released parameter regime, however, no grant occurs even on this family: each
state's cooling period is at least twice its timeout, so C2 auto-escalates before
the cooling window can close, and every C5 request is denied as `denied_cooling`
(0 granted / 0 `denied_decay` / 26,673 `denied_cooling` / 0 `denied_approval`).

## Not reproduced from this repository

| Manuscript result | Reason |
|-------------------|--------|
| Threshold sensitivity sweep (Table 9 / Figure 6 OER & MTCS columns; old `fig8_3d_sensitivity`) | no perturbation-sweep code in this repository; the MER = 0% invariance across perturbations is structural. The hardcoded `fig6_sensitivity` / `fig8_3d_sensitivity` figures and their generators have been removed. |
| Per-operation latency breakdown / throughput gauge (old `fig10_performance`) | `run_all.py` emits only one aggregate transition latency (`latency.csv`, ~0.03 ms, ~33,000 updates/s); the four-bar breakdown and gauge value were typed in and have been removed. |
| Regulatory coverage matrix / per-constraint event counts (old `fig11_regulatory`, `fig12_compliance`) | editorial/typed-in values with no computational source in this repository; figures and generators removed. |

## Status

Every quantitative claim the manuscript now presents as an empirical result is
regenerated by `scripts/run_all.py` at seed 42 and committed under `results/`. The
central structural guarantee (MER = 0%) is both proved and reproduced. On this
parameter regime C5 grants nothing (0 of 26,673 requests, all denied for an
incomplete cooling window), so the no-premature-de-escalation guarantee holds
vacuously and we make no empirical de-escalation-benefit claim here; over-escalation
is consequently identical with and without C5 (69.7%). The baseline magnitudes are
properties of this synthetic cohort and its memory model, not clinical-validation
figures.
