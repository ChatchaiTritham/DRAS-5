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
`PYTHONHASHSEED`). Cohort counts and safety metrics are deterministic; wall-clock
latency is machine-dependent, and the GBT RMSE can vary in the fourth decimal
place across numerical-library versions, so the manuscript reports it to three
decimal places.

## What reproduces

| Result | `run_all.py` (seed 42, 5000 trajectories) | Artifact | Status |
|--------|-------------------------------------------|----------|--------|
| Missed Escalation Rate, DRAS-5 (Eq. 10) | **0.0%** (every trajectory type) | `mer_by_type.csv` | reproduced (structural consequence of C1) |
| Missed Escalation Rate, NEWS2 / MEWS | **74.2% / 75.6%** | `mer_by_type.csv` | reproduced |
| Graded under-recognition, NEWS2 / MEWS | **65% / 67%** (DRAS-5 0%) | `mer_by_type.csv` (`urr_*`), `summary.json` | reproduced |
| Over-Escalation Rate, DRAS-5 with / without C5 (binary, Eq. 11) | **69.7% / 69.7%** (0.0% reduction) | `oer_by_type.csv`, `summary.json` (`oer_reduction_pct`) | reproduced |
| C5 de-escalation outcomes | **1,250 granted, 0 premature** (47,407 decay / 67,100 cooling / 0 approval denials; 115,757 requests) | `c5_outcomes.csv` | reproduced |
| ML-wrapper guarantee (GBT input) | governed MER **0.0%** vs ungoverned **100%**, GBT RMSE **0.056** (three decimals) | `summary.json` (`ml_wrapper`) | reproduced |
| Transition latency / throughput | **<1 ms/update** (O(1)) | `latency.csv` | reproduced (wall-clock; machine-dependent) |

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
instantaneous true level), the rounded rate is 69.7% with and without C5. C5 grants
1,250 safe single-step de-escalations, but each post-grant state remains above the
instantaneous recovered true level, so the binary indicator is unchanged. This
cohort therefore exercises the controlled-de-escalation guarantee directly, with
zero premature grants, but does not establish an over-escalation benefit.

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
sustained sub-threshold recovery) intended to exercise controlled de-escalation.
Across the complete cohort C5 grants 1,250 requests after all guards clear; 47,407
requests are denied for unsustained decay and 67,100 for an incomplete cooling
window. No request is denied for approval because the simulation supplies dual
approval to isolate the temporal guards, and no premature grant occurs.

## Not reproduced from this repository

| Manuscript result | Reason |
|-------------------|--------|
| Threshold sensitivity sweep (Table 9 / Figure 6 OER & MTCS columns; old `fig8_3d_sensitivity`) | no perturbation-sweep code in this repository; the MER = 0% invariance across perturbations is structural. The hardcoded `fig6_sensitivity` / `fig8_3d_sensitivity` figures and their generators have been removed. |
| Per-operation latency breakdown / throughput gauge (old `fig10_performance`) | `run_all.py` emits only one host-specific aggregate transition latency (`latency.csv`, below 1 ms in the committed run); the four-bar breakdown and gauge value were typed in and have been removed. |
| Regulatory coverage matrix / per-constraint event counts (old `fig11_regulatory`, `fig12_compliance`) | editorial/typed-in values with no computational source in this repository; figures and generators removed. |

## Status

Every quantitative claim the manuscript now presents as an empirical result is
regenerated by `scripts/run_all.py` at seed 42 and committed under `results/`. The
central structural guarantee (MER = 0%) is both proved and reproduced. On this
parameter regime C5 grants 1,250 of 115,757 requests after all formal guards clear,
with zero premature de-escalations. Binary over-escalation remains 69.7% because
the granted single-step transitions remain above the instantaneous recovered true
level. The baseline magnitudes are properties of this synthetic cohort and its
memory model, not clinical-validation figures.
