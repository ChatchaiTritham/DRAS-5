# Dynamic Risk Assessment State Machine (DRAS-5)

> Reference implementation plus a fixed-seed evaluation script that let a reader re-derive the paper's central safety property: under the monotonic-escalation rule, a deteriorating patient is never silently down-classified.

![License](https://img.shields.io/badge/license-MIT-blue) ![Python](https://img.shields.io/badge/python-3.10%2B-blue) ![Reproducible](https://img.shields.io/badge/reproducible-seed--42-success)

## Overview

Bedside risk monitoring still leans on stateless early-warning scores. Each new measurement is judged on its own, so a brief dip after a critical reading can quietly reset the patient to a lower acuity. When the next deterioration falls between observations, the earlier crisis has already been forgotten. Probabilistic models raise sensitivity but inherit the same blind spot: they emit a fresh estimate per step without any memory of how the patient's state has moved.

DRAS-5 sits between an upstream risk source and the clinical workflow as a five-state supervisor. It does not try to be a better classifier; it constrains the *output sequence* of whatever score feeds it. Five invariants are checked on every transition — monotonic escalation (C1), timeout-driven auto-escalation (C2), an append-only audit trail (C3), a human approval gate for the highest tier (C4), and a decay-gated, dual-approval de-escalation protocol (C5). Each runs in constant time per update.

This repository is the artifact behind those claims. It holds the package source, a deterministic driver pinned to seed 42, the committed metric tables it writes, and the figure generators. The point is verifiability: a reader can install the package, run one script, and confirm the headline number for themselves rather than take it on trust.

## Key results

All figures below come from `python scripts/run_all.py` at seed 42 on the synthetic cohort (5,000 trajectories, 100 steps each, 500,000 evaluations). They are properties of this generated cohort and its observation model, not clinical validation.

- **Missed-escalation rate is 0% for DRAS-5 on every trajectory family.** This is a structural consequence of C1, not a statistical estimate — once a sample crosses an escalation threshold the state cannot fall except through an approved de-escalation.
- **Stateless baselines miss a large share of escalations under intermittent sampling.** In this run the modelled NEWS2 scorer records 74.2% overall and MEWS 75.6%; graded under-recognition is 64.8% and 67.0% respectively. (These magnitudes are far higher than the values in the manuscript tables — see the caveat below.)
- **C5 grants no de-escalation on the released parameter regime.** Of 26,673 de-escalation requests, every one is denied for an incomplete cooling window: each state's cooling period is at least twice its timeout, so C2 auto-escalates before the window can close. The "no premature de-escalation" guarantee therefore holds vacuously here, and we make no empirical de-escalation-benefit claim on this cohort.
- **Over-escalation is identical with and without C5 (69.7% overall).** Because C5 fires zero grants, the two configurations produce the same state sequence. The high binary rate is the deliberate cost of holding an elevated state through a conservative recovery window — the same conservatism that yields 0% missed escalation.
- **Per-update cost stays well under the 1 ms target.** Mean transition latency is about 0.03 ms (roughly 33,000 updates/s) over 50,000 operations. Timing is wall-clock and machine-dependent, so it is the only output that shifts run to run.

## Repository structure

```text
src/dras5/        package: state machine, constraints, decay, simulator, audit, CLI
scripts/          run_all.py (seed-42 driver) and generate_figures.py
results/          committed metric tables and summary.json written by run_all.py
figures/          publication figures (.png/.pdf) and FIGURE_MANIFEST.csv inventory
tests/            unit and behaviour checks for each constraint
notebooks/        worked examples of the state machine and governance workflow
data/, models/    placeholders (no external dataset is required)
```

## Installation

```bash
git clone https://github.com/ChatchaiTritham/DRAS-5.git
cd DRAS-5
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e .
```

## Reproducing the results

```bash
python scripts/run_all.py          # fixed seed 42; a few minutes on a standard workstation
python scripts/generate_figures.py # redraws the data figures from results/*.csv
```

`run_all.py` writes the metric tables in `results/` (`mer_by_type.csv`, `oer_by_type.csv`, `c5_outcomes.csv`, `ml_wrapper.csv`, `latency.csv`) and `summary.json`. Per-trajectory seeds derive from a stable type index, independent of `PYTHONHASHSEED`, so the scientific outputs are byte-identical on rerun. The single exception is `latency.csv`: wall-clock timing drifts by a few hundredths of a millisecond across machines, which leaves the reported throughput and confidence interval slightly variable while every other number stays fixed.

One honesty note for reviewers: the metric magnitudes regenerated here differ from the corresponding tables in the current manuscript draft (for example, baseline missed-escalation overall 74.2% / 75.6% here versus 6.5% / 22.2% in the paper, and 26,673 de-escalation requests here versus 52,958 in the paper). The *qualitative* findings agree across both — DRAS-5 at 0% missed escalation, C5 granting nothing on this regime, and over-escalation unchanged by C5 — but the exact figures do not. `REPRODUCIBILITY.md` records this discrepancy and which claims reproduce. The over-escalation magnitudes are illustrative and depend on the cohort and parameter regime; we treat them as such and make no portable numeric claim from them.

## Results and figures

The curated set is tracked in `FIGURE_MANIFEST.csv`. Two of the data figures (`fig4_mer`, `fig5_oer`) are redrawn directly from the committed CSVs; several others are schematic diagrams or analytical illustrations that do not read from `results/` — those are flagged below.

- `figures/fig1_state_machine.png` — the five acuity states with their thresholds, timeouts, and the escalation (solid) versus C5 de-escalation (dashed) transitions. Schematic; layout and labels are drawn from fixed parameters, not run output.
- `figures/fig2_pipeline.png` — the order in which an update is checked (C2 → C1 → C4 → C5, then audit). Schematic of Algorithm 1.
- `figures/fig3_c5_decay.png` and `figures/fig3b_decay_comparison.png` — the exponential-decay envelope that gates C5, and how the per-state decay rates compare. Analytical curves from the published λ values; they do not depend on `run_all.py`.
- `figures/fig4_mer.png` — missed-escalation rate by trajectory type, with DRAS-5 flat at 0% beside the stateless baselines. Driven by `results/mer_by_type.csv`.
- `figures/fig5_oer.png` — over-escalation rate with and without C5; the two series coincide, the visual counterpart of C5 granting nothing here. Driven by `results/oer_by_type.csv`.
- `figures/fig7_c5_rejection.png` — the C5 outcome breakdown, showing all requests denied for an incomplete cooling window. Driven by `results/c5_outcomes.csv`.
- `figures/fig9_3d_trajectory.png` — three example trajectories regenerated from the simulator at seed 42 (computed, not hardcoded).

**Removed figures.** Five figures whose values were typed into the script rather than produced by any analysis have been removed, along with both their generator functions and their committed `.png`/`.pdf` outputs:

- `fig6_sensitivity` / `fig8_3d_sensitivity` — threshold and 3D sensitivity panels. The OER/MTCS curves and the 3D OER surface were typed in; no perturbation sweep exists in this repository, and the values contradicted the seed-42 results. The only reproducible part of the sensitivity claim (MER stays 0% under perturbation) is structural.
- `fig10_performance` / `fig11_regulatory` / `fig12_compliance` — the per-operation latency bars, throughput gauge, IEC/EU-AI-Act regulatory mapping, and per-constraint event counts were all written into the script. `run_all.py` emits only one aggregate transition latency (`results/latency.csv`); the rest had no computational source, and `fig10`'s gauge (8,333 updates/s) even contradicted the measured ~33,000 updates/s.

`run_all.py` is the authoritative source for any quoted metric; only figures that read from `results/` (or are clearly labelled schematic/analytical diagrams) are retained.

## Data

No human-subject data is used. All trajectories are generated synthetically inside `src/dras5/simulator.py` from parametric profiles (monotonic, oscillating, spike-and-recover) seeded at 42. Because there are no patient records, no ethics approval or IRB review applies.

## Citation

```bibtex
@article{tritham_dras5,
  title   = {{DRAS-5}: A Formally Verified Runtime Safety Layer for Clinical
             Decision-Support Systems},
  author  = {Tritham, Chatchai and Namahoot, Chakkrit Snae},
  journal = {PeerJ Computer Science},
  year    = {2026},
  note    = {Under review}
}
```

A permanent, citable archival snapshot of the released code will be provided upon acceptance.

## License

Released under the MIT License (see `LICENSE`).

## Contact

**Chatchai Tritham** — Department of Computer Science and Information Technology, Faculty of Science, Naresuan University, Phitsanulok 65000, Thailand. Email: chatchait66@nu.ac.th · ORCID: 0000-0001-7899-228X
**Chakkrit Snae Namahoot** — same affiliation. Email: chakkrits@nu.ac.th · ORCID: 0000-0003-4660-4590

## Portfolio relationship

| Repository | Role |
|---|---|
| BASICS-CDSS | Beyond-accuracy evaluation methodology |
| TRI-X | Framework-level package |
| ORASR | Routing and safety-action component |
| DRAS-5 | Dynamic risk-state component |
| SAFE-Gate | Safety-gated ensemble framework |
| SynDX | Synthetic validation and explainability evidence |
| SURgul | SRGL/governance reproducibility component |
| TRI-X-CDSS | Integration and implementation package |
| Selective-CDSS | Risk-controlled selective-prediction (abstention) component |
| Causal-CDSS | Causal-inference evaluation component |
| Beyond-Accuracy | Simulation-based safety/calibration evaluation framework |
