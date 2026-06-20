#!/usr/bin/env python3
"""
End-to-end, single-seed evaluation driver for DRAS-5.

Regenerates every quantitative result reported in the manuscript from one fixed
seed and writes them as committed artifacts under ``results/``:

  results/mer_by_type.csv   Missed Escalation Rate (Eq. 10): DRAS-5 vs NEWS2/MEWS
  results/oer_by_type.csv   Over-Escalation Rate (Eq. 11): DRAS-5 with / without C5
  results/c5_outcomes.csv   C5 de-escalation request outcomes, by binding reason
  results/latency.csv       Per-operation transition latency (mean / CI / throughput)
  results/summary.json      Headline figures + run configuration

Determinism
-----------
Every trajectory is generated from an explicit per-trajectory seed derived from
BASE_SEED, so a rerun reproduces the byte-identical CSVs (latency.csv excepted:
wall-clock timing is reported but excluded from the byte-stability contract).

Baselines
---------
NEWS2 and MEWS are *stateless* early-warning scores: each reading is classified
in isolation, with no memory of earlier states. They are re-read on a sparse
schedule (every Nth step; NEWS2 denser than the older MEWS) and carry the last
observed level forward, retaining nothing else (Downey 2017). Two baseline
measures follow from this memoryless model:

  * binary MER -- a missed escalation is recorded when, at the end-of-episode
    decision point, the score has reverted below the patient's *sustained* peak
    level: the transient deterioration has resolved and the memoryless score no
    longer reflects it. A monotonic rise has no peak to forget (MER ~ 0); a
    resolved peak (oscillating, spike) is almost always under-recognised.
  * graded under-recognition rate -- the fraction of the post-peak window the
    score sits below the sustained peak (severity of the missed escalation).

DRAS-5, by C1, retains any attained level, so both measures are 0 by construction.
This is a faithful, well-defined model of stateless EWS, not a fitted curve; the
magnitudes reflect this synthetic cohort and are reported as such (see
REPRODUCIBILITY.md).

Usage
-----
    python scripts/run_all.py
    python scripts/run_all.py --trajectories 5000 --seed 42
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import random
import time
from pathlib import Path
from typing import Dict, List, Tuple

from dras5.state_machine import DRAS5StateMachine
from dras5.states import RiskState, risk_to_state, STATE_CONFIG

# ------------------------------------------------------------------ config
BASE_SEED = 42
N_TRAJECTORIES = 5000
N_STEPS = 100
DT_SECONDS = 10.0  # 1 sample / 10 s; cooling windows (180-600 s) are reachable
# Stateless early-warning scores are recorded intermittently (Downey 2017: the
# intermittent nature of EWS observation is a documented weakness). NEWS2 is
# recorded on a denser ward schedule than the older, coarser MEWS. We model this
# as the observation cadence: a peak that falls between observations is never
# seen by the stateless scorer and is therefore a missed escalation.
NEWS2_OBS_INTERVAL = 2
MEWS_OBS_INTERVAL = 3

# Trajectory shape parameters (documented so the synthetic cohort is reproducible).
MONO_BASE, MONO_SPAN, MONO_NOISE = 0.10, 0.80, 0.02
OSC_BASE, OSC_AMP, OSC_PERIOD_FACTOR, OSC_NOISE = 0.50, 0.35, 0.40, 0.05
# Spike to EMERGENCY then recover (absorbing-state case; C5 cannot fire here).
SPIKEE_PRE_BASE, SPIKEE_PRE_SLOPE, SPIKEE_PEAK = 0.20, 0.10, 0.92
SPIKEE_DECAY, SPIKEE_NOISE = 0.015, 0.02
# Spike to CRITICAL then recover (the canonical C5 scenario: Patient-A in the
# manuscript climbs to rho=0.72=CRITICAL then drops to 0.38). Peaks below the
# EMERGENCY threshold so controlled de-escalation is admissible, then sustains a
# low risk for longer than the CRITICAL cooling period.
SPIKEC_PRE_BASE, SPIKEC_PRE_SLOPE, SPIKEC_PEAK = 0.20, 0.10, 0.78
SPIKEC_RECOVER = 0.12  # sustained low risk after recovery
SPIKEC_NOISE = 0.02

# Trajectory types and their share of the cohort.
TYPES = ("monotonic", "oscillating", "spike_emergency", "spike_critical")
RESULTS = Path(__file__).resolve().parent.parent / "results"


# ------------------------------------------------------------------ trajectories
def _traj_seed(base_seed: int, ttype: str, j: int) -> int:
    """Deterministic per-trajectory seed (independent of PYTHONHASHSEED).

    Python's built-in ``hash`` for strings/tuples is salted per process, which
    would break byte-stable reproducibility; we derive the seed from a stable
    type index instead.
    """
    type_index = TYPES.index(ttype)
    return (base_seed * 1_000_003 + type_index * 100_003 + j) % (2**31 - 1)


def _clip(x: float) -> float:
    return max(0.0, min(1.0, x))


def make_trajectory(ttype: str, seed: int) -> List[float]:
    """Return a deterministic list of instantaneous risk scores rho_t."""
    rng = random.Random(seed)
    rho: List[float] = []
    spike_at = N_STEPS // 4
    for i in range(N_STEPS):
        if ttype == "monotonic":
            base = MONO_BASE + MONO_SPAN * (i / N_STEPS)
            noise = rng.gauss(0, MONO_NOISE)
        elif ttype == "oscillating":
            base = OSC_BASE + OSC_AMP * math.sin(2 * math.pi * i / (N_STEPS * OSC_PERIOD_FACTOR))
            noise = rng.gauss(0, OSC_NOISE)
        elif ttype == "spike_emergency":
            if i < spike_at:
                base = SPIKEE_PRE_BASE + SPIKEE_PRE_SLOPE * (i / spike_at)
            elif i == spike_at:
                base = SPIKEE_PEAK
            else:
                base = SPIKEE_PEAK * math.exp(-SPIKEE_DECAY * (i - spike_at))
            noise = rng.gauss(0, SPIKEE_NOISE)
        elif ttype == "spike_critical":
            if i < spike_at:
                base = SPIKEC_PRE_BASE + SPIKEC_PRE_SLOPE * (i / spike_at)
            elif i == spike_at:
                base = SPIKEC_PEAK
            else:
                # quick observed recovery to a sustained low floor
                decayed = SPIKEC_PEAK * math.exp(-0.08 * (i - spike_at))
                base = max(SPIKEC_RECOVER, decayed)
            noise = rng.gauss(0, SPIKEC_NOISE)
        else:
            raise ValueError(ttype)
        rho.append(_clip(base + noise))
    return rho


# ------------------------------------------------------------------ DRAS-5 run
def run_dras5(rho: List[float], enable_c5: bool) -> Tuple[List[RiskState], Dict[str, int]]:
    """Run a risk series through DRAS-5.

    When ``enable_c5`` is True a dual-approved de-escalation request is issued at
    every step where the instantaneous risk warrants a lower state and the
    patient is not in an absorbing/floor state; the C5 constraint inside the state
    machine decides whether to grant it. Returns per-step system states and a
    tally of C5 request outcomes classified by binding reason.
    """
    sm = DRAS5StateMachine(
        enable_constraints=True, enable_audit=False, require_human_approval=False
    )
    states: List[RiskState] = []
    c5 = {"granted": 0, "denied_decay": 0, "denied_cooling": 0, "denied_approval": 0}

    for i, r in enumerate(rho):
        t = i * DT_SECONDS
        before = sm.current_state
        want_deesc = (
            enable_c5
            and risk_to_state(r) < before
            and before not in (RiskState.SAFE, RiskState.EMERGENCY)
        )
        new = sm.update(
            risk_score=r,
            t=t,
            human_approved=True,
            deescalation_request=want_deesc,
            dual_approval=want_deesc,  # both clinician approvals supplied; C5 still gates on decay
        )
        if want_deesc:
            if new < before:
                c5["granted"] += 1
            else:
                # Classify the denial by the binding condition. Reconstruct the
                # cooling-window series exactly as the state machine evaluated it.
                t_cool = STATE_CONFIG[before].get("t_cool") or 0.0
                in_state = t - sm.state_entry_time
                if in_state + 1e-9 < t_cool:
                    c5["denied_cooling"] += 1
                else:
                    series = [
                        v
                        for ti, v in zip(sm._rho_eff_times, sm._rho_eff_history)
                        if t - ti <= t_cool
                    ]
                    target = RiskState(before - 1)
                    theta = STATE_CONFIG[target]["theta"]
                    if not series:
                        c5["denied_cooling"] += 1
                    elif not all(v < theta for v in series):
                        c5["denied_decay"] += 1
                    else:
                        c5["denied_cooling"] += 1
        states.append(RiskState(int(new)))
    return states, c5


# ------------------------------------------------------------------ stateless EWS baselines
def _level_series(rho: List[float]) -> List[int]:
    return [int(risk_to_state(r)) for r in rho]


def stateless_reported_levels(rho: List[float], interval: int) -> List[int]:
    """Acuity a *stateless* EWS reports over time.

    The score is re-read every ``interval`` samples and the system keeps no
    memory of earlier states: between readings it carries the last observed level
    forward and does not retain a transient peak that has since resolved. A denser
    cadence (smaller ``interval``) updates more often -- this is the only thing
    that distinguishes NEWS2 (frequent) from the coarser MEWS.
    """
    levels = _level_series(rho)
    reported, cur = [], levels[0]
    for i, lvl in enumerate(levels):
        if i % interval == 0:
            cur = lvl
        reported.append(cur)
    return reported


def sustained_peak_level(rho: List[float], min_run: int = 2) -> int:
    """Highest acuity level held for >= ``min_run`` consecutive samples.

    Filtering by a minimum run removes single-sample sensor noise so that a
    one-step blip is not counted as a genuine escalation (this is what made a
    smoothly rising monotonic trajectory spuriously look 'missed').
    """
    levels = _level_series(rho)
    best = min(levels)
    for val in set(levels):
        run = 0
        for lvl in levels:
            run = run + 1 if lvl >= val else 0
            if run >= min_run:
                best = max(best, val)
                break
    return best


def baseline_under_recognition_rate(rho: List[float], interval: int) -> float:
    """Fraction of the post-peak window during which the stateless score sits
    below the sustained peak level (graded severity of the missed escalation)."""
    levels = _level_series(rho)
    reported = stateless_reported_levels(rho, interval)
    peak = sustained_peak_level(rho)
    first = next((i for i, lvl in enumerate(levels) if lvl >= peak), 0)
    window = reported[first:]
    if not window:
        return 0.0
    return sum(1 for lvl in window if lvl < peak) / len(window)


def baseline_mer(rho: List[float], interval: int) -> bool:
    """True if a stateless EWS misses the escalation (memory-faithful definition).

    A missed escalation is recorded when, at the end-of-episode decision point,
    the stateless system's reported level is below the patient's sustained peak
    level: lacking memory, the score has reverted to the current (often recovered)
    reading and no longer reflects a transient deterioration the patient genuinely
    sustained. DRAS-5, by C1, holds the peak and therefore never misses. On a
    monotonic rise -- where there is no transient to forget -- the stateless score
    also misses nothing, matching the clinical expectation.
    """
    reported = stateless_reported_levels(rho, interval)
    return reported[-1] < sustained_peak_level(rho)


# ------------------------------------------------------------------ bootstrap CI
# Bootstrap configuration is fixed so the reported 95% confidence intervals are
# byte-stable across reruns (independent of the metric run's RNG state).
BOOTSTRAP_N = 1000
BOOTSTRAP_SEED = 42


def _bootstrap_ci(values: List[float], scale: float = 100.0,
                  n_boot: int = BOOTSTRAP_N, seed: int = BOOTSTRAP_SEED
                  ) -> Tuple[float, float]:
    """Seeded nonparametric bootstrap 95% CI for the mean of ``values``.

    ``values`` are per-trajectory observations (0/1 indicators for MER, or a
    per-trajectory over-escalation fraction for OER); the returned bounds are the
    2.5th / 97.5th percentiles of the resampled means, expressed on ``scale``
    (percent). Deterministic given ``seed`` -> reproducible CIs.
    """
    n = len(values)
    if n == 0:
        return 0.0, 0.0
    rng = random.Random(seed)
    means = []
    for _ in range(n_boot):
        s = 0.0
        for _ in range(n):
            s += values[rng.randrange(n)]
        means.append(scale * s / n)
    means.sort()
    lo = means[int(0.025 * n_boot)]
    hi = means[min(n_boot - 1, int(0.975 * n_boot))]
    return round(lo, 2), round(hi, 2)


# ------------------------------------------------------------------ metrics
def evaluate(n_traj: int, base_seed: int):
    per_type = n_traj // len(TYPES)
    systems = ("DRAS-5", "NEWS2", "MEWS")
    obs = {"NEWS2": NEWS2_OBS_INTERVAL, "MEWS": MEWS_OBS_INTERVAL}

    mer = {s: {tt: 0 for tt in TYPES} for s in systems}
    urr = {s: {tt: 0.0 for tt in TYPES} for s in ("NEWS2", "MEWS")}  # graded under-recognition
    oer_sum = {c: {tt: 0.0 for tt in TYPES} for c in ("c5_on", "c5_off")}
    c5_tot = {"granted": 0, "denied_decay": 0, "denied_cooling": 0, "denied_approval": 0}
    n_evals = 0

    # Per-trajectory observations retained for the seeded bootstrap CIs.
    mer_obs = {s: {tt: [] for tt in TYPES} for s in systems}
    oer_obs = {c: {tt: [] for tt in TYPES} for c in ("c5_on", "c5_off")}
    # Over-escalation locator: for every true acuity level, how many sample-steps
    # the system sat above the true level (numerator) out of all steps the patient
    # genuinely occupied that level (denominator). Reveals WHERE OER concentrates.
    over_by_level = {int(s): 0 for s in RiskState}
    steps_by_level = {int(s): 0 for s in RiskState}

    for tt in TYPES:
        for j in range(per_type):
            seed = _traj_seed(base_seed, tt, j)
            rho = make_trajectory(tt, seed)
            true_states = [risk_to_state(r) for r in rho]
            max_true = max(true_states)

            # DRAS-5 MER (structural 0%) and OER with / without C5.
            for cond, c5_on in (("c5_on", True), ("c5_off", False)):
                sys_states, c5 = run_dras5(rho, enable_c5=c5_on)
                if cond == "c5_on":
                    n_evals += len(sys_states)
                    for k in c5_tot:
                        c5_tot[k] += c5[k]
                    missed = 1 if max(sys_states) < max_true else 0
                    mer["DRAS-5"][tt] += missed
                    mer_obs["DRAS-5"][tt].append(missed)
                    # Over-escalation locator (computed on the committed c5-on run).
                    for s, ts in zip(sys_states, true_states):
                        steps_by_level[int(ts)] += 1
                        if s > ts:
                            over_by_level[int(ts)] += 1
                over = sum(1 for s, ts in zip(sys_states, true_states) if s > ts)
                oer_sum[cond][tt] += over / len(sys_states)
                oer_obs[cond][tt].append(over / len(sys_states))

            # Stateless baselines: binary MER (fails to retain the peak at the
            # decision point) and graded under-recognition rate.
            for s in ("NEWS2", "MEWS"):
                m = 1 if baseline_mer(rho, obs[s]) else 0
                mer[s][tt] += m
                mer_obs[s][tt].append(m)
                urr[s][tt] += baseline_under_recognition_rate(rho, obs[s])

    def pct(numer, denom):
        return round(100.0 * numer / denom, 2) if denom else 0.0

    n_total = per_type * len(TYPES)
    mer_rows, oer_rows = [], []
    mer_overall = {s: 0 for s in systems}
    urr_overall = {"NEWS2": 0.0, "MEWS": 0.0}
    oer_overall = {"c5_on": 0.0, "c5_off": 0.0}
    # Pooled per-trajectory observations (for overall-row CIs).
    mer_obs_all = {s: [] for s in systems}
    oer_obs_all = {c: [] for c in ("c5_on", "c5_off")}
    for tt in TYPES:
        for s in systems:
            mer_overall[s] += mer[s][tt]
            mer_obs_all[s].extend(mer_obs[s][tt])
        for s in ("NEWS2", "MEWS"):
            urr_overall[s] += urr[s][tt]
        for cond in ("c5_on", "c5_off"):
            oer_overall[cond] += oer_sum[cond][tt]
            oer_obs_all[cond].extend(oer_obs[cond][tt])
        d5_lo, d5_hi = _bootstrap_ci(mer_obs["DRAS-5"][tt])
        n2_lo, n2_hi = _bootstrap_ci(mer_obs["NEWS2"][tt])
        mw_lo, mw_hi = _bootstrap_ci(mer_obs["MEWS"][tt])
        mer_rows.append({
            "trajectory_type": tt, "n": per_type,
            "mer_dras5_pct": pct(mer["DRAS-5"][tt], per_type),
            "mer_dras5_ci_lo": d5_lo, "mer_dras5_ci_hi": d5_hi,
            "mer_news2_pct": pct(mer["NEWS2"][tt], per_type),
            "mer_news2_ci_lo": n2_lo, "mer_news2_ci_hi": n2_hi,
            "mer_mews_pct": pct(mer["MEWS"][tt], per_type),
            "mer_mews_ci_lo": mw_lo, "mer_mews_ci_hi": mw_hi,
            "urr_news2_pct": pct(urr["NEWS2"][tt], per_type),
            "urr_mews_pct": pct(urr["MEWS"][tt], per_type),
        })
        no_lo, no_hi = _bootstrap_ci(oer_obs["c5_off"][tt])
        wi_lo, wi_hi = _bootstrap_ci(oer_obs["c5_on"][tt])
        oer_rows.append({
            "trajectory_type": tt, "n": per_type,
            "oer_no_c5_pct": pct(oer_sum["c5_off"][tt], per_type),
            "oer_no_c5_ci_lo": no_lo, "oer_no_c5_ci_hi": no_hi,
            "oer_with_c5_pct": pct(oer_sum["c5_on"][tt], per_type),
            "oer_with_c5_ci_lo": wi_lo, "oer_with_c5_ci_hi": wi_hi,
        })

    oer_no = pct(oer_overall["c5_off"], n_total)
    oer_with = pct(oer_overall["c5_on"], n_total)
    reduction = round(100.0 * (oer_no - oer_with) / oer_no, 1) if oer_no else 0.0

    # Over-escalation locator table (one row per true acuity level, seed 42).
    oer_locator_rows = []
    for lvl in sorted(steps_by_level):
        st = RiskState(lvl)
        oer_locator_rows.append({
            "true_state": st.name,
            "true_level": lvl,
            "steps_at_level": steps_by_level[lvl],
            "over_escalated_steps": over_by_level[lvl],
            "oer_pct": pct(over_by_level[lvl], steps_by_level[lvl]),
        })

    # Overall-row bootstrap CIs.
    mer_ci_overall = {s.lower().replace("-", ""): _bootstrap_ci(mer_obs_all[s]) for s in systems}
    oer_ci_overall = {c: _bootstrap_ci(oer_obs_all[c]) for c in ("c5_on", "c5_off")}

    summary = {
        "config": {
            "seed": base_seed, "n_trajectories": n_total, "n_steps": N_STEPS,
            "dt_seconds": DT_SECONDS,
            "obs_interval_news2": NEWS2_OBS_INTERVAL, "obs_interval_mews": MEWS_OBS_INTERVAL,
            "n_evaluations": n_evals, "trajectory_types": list(TYPES),
        },
        "bootstrap": {"n_resamples": BOOTSTRAP_N, "seed": BOOTSTRAP_SEED, "ci": "95%"},
        "mer_overall_pct": {
            "dras5": pct(mer_overall["DRAS-5"], n_total),
            "news2": pct(mer_overall["NEWS2"], n_total),
            "mews": pct(mer_overall["MEWS"], n_total),
        },
        "mer_overall_ci95": {
            "dras5": list(mer_ci_overall["dras5"]),
            "news2": list(mer_ci_overall["news2"]),
            "mews": list(mer_ci_overall["mews"]),
        },
        "under_recognition_overall_pct": {
            "dras5": 0.0,  # DRAS-5 retains the peak (C1) -> never under-recognises
            "news2": pct(urr_overall["NEWS2"], n_total),
            "mews": pct(urr_overall["MEWS"], n_total),
        },
        "oer_overall_pct": {"no_c5": oer_no, "with_c5": oer_with},
        "oer_overall_ci95": {
            "no_c5": list(oer_ci_overall["c5_off"]),
            "with_c5": list(oer_ci_overall["c5_on"]),
        },
        "oer_reduction_pct": reduction,
        "oer_by_true_level": oer_locator_rows,
        "c5_outcomes": c5_tot,
        "c5_total_requests": sum(c5_tot.values()),
    }
    return mer_rows, oer_rows, c5_tot, oer_locator_rows, summary


# ------------------------------------------------------------------ ML wrapper experiment
def ml_wrapper_experiment(n_traj: int, base_seed: int, window: int = 5) -> dict | None:
    """Train a gradient-boosted-tree next-step risk predictor and govern it with DRAS-5.

    Demonstrates that the MER guarantee is independent of input quality: the GBT's
    noisy predictions are fed to DRAS-5 in place of ground-truth risk. Returns
    None if scikit-learn is unavailable (the rest of the pipeline does not depend
    on it). Deterministic given the seed.
    """
    try:
        from sklearn.ensemble import GradientBoostingRegressor
    except Exception:
        return None
    import numpy as np

    per_type = n_traj // len(TYPES)
    X, y, series = [], [], []
    for tt in TYPES:
        for j in range(per_type):
            rho = make_trajectory(tt, _traj_seed(base_seed, tt, j))
            series.append(rho)
            for i in range(window, len(rho)):
                X.append(rho[i - window:i])
                y.append(rho[i])
    X = np.asarray(X)
    y = np.asarray(y)
    n_train = int(0.8 * len(X))
    model = GradientBoostingRegressor(random_state=base_seed, n_estimators=100, max_depth=3)
    model.fit(X[:n_train], y[:n_train])
    pred = model.predict(X[n_train:])
    rmse = float(np.sqrt(np.mean((pred - y[n_train:]) ** 2)))

    # Govern the held-out trajectories' predicted risk with DRAS-5 (MER) and
    # compare with the ungoverned stateless use of the same predictions, scored
    # under the same intermittent-observation model as the NEWS2/MEWS baselines.
    split_traj = int(0.8 * len(series))
    governed_miss = ungoverned_miss = n = 0
    for rho in series[split_traj:]:
        # Build the windowed feature matrix for the whole trajectory, then predict
        # in one vectorised call (left-padded with the first reading).
        feats = []
        for i in range(len(rho)):
            if i >= window:
                feats.append(rho[i - window:i])
            else:
                feats.append([rho[0]] * (window - i) + rho[:i])
        pr = [_clip(p) for p in model.predict(np.asarray(feats)).tolist()]
        true_max = max(risk_to_state(r) for r in rho)
        sys_states, _ = run_dras5(pr, enable_c5=True)
        if max(sys_states) < true_max:
            governed_miss += 1
        # ungoverned: stateless prediction under intermittent observation (NEWS2 cadence)
        if baseline_mer(pr, NEWS2_OBS_INTERVAL):
            ungoverned_miss += 1
        n += 1
    return {
        "gbt_rmse": round(rmse, 4),
        "n_test_trajectories": n,
        "mer_governed_pct": round(100.0 * governed_miss / n, 2) if n else 0.0,
        "mer_ungoverned_pct": round(100.0 * ungoverned_miss / n, 2) if n else 0.0,
    }


# ------------------------------------------------------------------ latency benchmark
def benchmark_latency(n_ops: int = 50_000, seed: int = BASE_SEED) -> dict:
    """Time a representative stream of state-machine updates (real wall clock)."""
    rng = random.Random(seed)
    sm = DRAS5StateMachine(
        enable_constraints=True, enable_audit=False, require_human_approval=False
    )
    scores = [rng.random() for _ in range(n_ops)]
    samples: List[float] = []
    for i, r in enumerate(scores):
        t0 = time.perf_counter()
        sm.update(risk_score=r, t=i * DT_SECONDS, human_approved=True)
        samples.append((time.perf_counter() - t0) * 1e3)  # ms
        if sm.current_state == RiskState.EMERGENCY:
            sm = DRAS5StateMachine(
                enable_constraints=True, enable_audit=False, require_human_approval=False
            )
    samples.sort()
    n = len(samples)
    mean = sum(samples) / n
    lo = samples[int(0.025 * n)]
    hi = samples[int(0.975 * n)]
    return {
        "operations": n,
        "mean_ms": round(mean, 4),
        "ci95_low_ms": round(lo, 4),
        "ci95_high_ms": round(hi, 4),
        "throughput_per_s": int(1000.0 / mean) if mean > 0 else 0,
    }


# ------------------------------------------------------------------ io
def write_csv(path: Path, rows: List[dict]):
    if not rows:
        return
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--trajectories", type=int, default=N_TRAJECTORIES)
    ap.add_argument("--seed", type=int, default=BASE_SEED)
    ap.add_argument("--no-latency", action="store_true",
                    help="skip the wall-clock latency benchmark (for byte-stable CI)")
    ap.add_argument("--no-ml", action="store_true",
                    help="skip the (optional) ML-wrapper experiment")
    args = ap.parse_args()

    RESULTS.mkdir(exist_ok=True)
    mer_rows, oer_rows, c5_tot, oer_locator_rows, summary = evaluate(
        args.trajectories, args.seed)
    write_csv(RESULTS / "mer_by_type.csv", mer_rows)
    write_csv(RESULTS / "oer_by_type.csv", oer_rows)
    write_csv(RESULTS / "oer_by_truelevel.csv", oer_locator_rows)
    write_csv(RESULTS / "c5_outcomes.csv",
              [{"reason": k, "count": v} for k, v in c5_tot.items()])

    if not args.no_ml:
        ml = ml_wrapper_experiment(args.trajectories, args.seed)
        if ml is not None:
            write_csv(RESULTS / "ml_wrapper.csv", [ml])
            summary["ml_wrapper"] = ml

    if not args.no_latency:
        lat = benchmark_latency(seed=args.seed)
        write_csv(RESULTS / "latency.csv", [lat])
        summary["latency"] = lat

    (RESULTS / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
