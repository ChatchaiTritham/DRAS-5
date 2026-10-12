"""ML wrapper experiment, revised (D-08): structured upstream error and no cadence confound.

Two upstream predictors, both gradient-boosted trees trained on the same 4,000 trajectories and
tested on the 1,000 held-out trajectories of run_all.ml_wrapper_experiment (split by trajectory,
stratified by family):

  autoregressive   predicts rho(t) from the five previous rho values (the v1.4.0 model)
  vital-sign       predicts rho(t) from four simulated vital signs at time t only. The vitals
                   are generated from the TRUE risk with a per-trajectory physiological lag of
                   0-4 samples, nonlinear links (SpO2 falls quadratically), Gaussian noise and
                   10% missing values carried forward. Error therefore has structure: lag,
                   regression to the mean at the extremes (under-reporting of peaks), and
                   imputation artefacts.
  vital-sign, shifted   the same model applied to test vitals from a shifted site (heart rate
                   +10/min, systolic pressure -10 mmHg, noise x1.5): a calibration shift.

Each predictor's output is used by four arms that see EVERY sample unless stated, so memory and
cadence are separated: stateless every sample, stateless every 2nd sample (NEWS2 cadence),
max-hold every sample, and DRAS-5 (full). Metrics are scored against the sustained peak of the
input the arm received (input-relative) and of the true risk (true-relative).

Output: results/ml_wrapper_v2.csv      Usage: python scripts/ml_wrapper_v2.py [--n 5000] [--seed 42]
"""
from __future__ import annotations

import argparse
import csv
import logging
import math
import random
import sys
from pathlib import Path

import numpy as np
from sklearn.ensemble import GradientBoostingRegressor

logging.disable(logging.CRITICAL)
REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))
sys.path.insert(0, str(REPO / "scripts"))

import run_all  # noqa: E402
from run_all import (TYPES, _clip, _level_series, _traj_seed, make_trajectory,  # noqa: E402
                     run_dras5, stateless_reported_levels, sustained_peak_level)


def vitals(rho, rng, shift=False):
    lag = rng.randint(0, 4)
    k = 1.5 if shift else 1.0
    hr0, sbp0 = (80.0, 115.0) if shift else (70.0, 125.0)
    rows, last = [], None
    for i in range(len(rho)):
        r = rho[max(0, i - lag)]
        v = [hr0 + 60 * r + rng.gauss(0, 6 * k), 14 + 16 * r + rng.gauss(0, 2 * k),
             min(100.0, 98 - 12 * r * r + rng.gauss(0, 1 * k)), sbp0 - 50 * r + rng.gauss(0, 8 * k)]
        if last is not None:
            v = [lv if rng.random() < 0.10 else x for x, lv in zip(v, last)]
        rows.append(v)
        last = v
    return rows


def maxhold(levels):
    out, h = [], levels[0]
    for lv in levels:
        h = max(h, lv)
        out.append(h)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=5000)
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()
    per = args.n // len(TYPES)
    n_test = int(round(run_all.ML_TEST_FRACTION * per))
    train, test = [], []
    for tt in TYPES:
        for j in range(per):
            s = _traj_seed(args.seed, tt, j)
            (test if j >= per - n_test else train).append((tt, s, make_trajectory(tt, s)))

    W = 5
    Xa, ya, Xv, yv = [], [], [], []
    for _, s, rho in train:
        for i in range(W, len(rho)):
            Xa.append(rho[i - W:i])
            ya.append(rho[i])
        for v, r in zip(vitals(rho, random.Random(s + 17)), rho):
            Xv.append(v)
            yv.append(r)
    ar = GradientBoostingRegressor(random_state=args.seed, n_estimators=100, max_depth=3).fit(np.asarray(Xa), ya)
    vm = GradientBoostingRegressor(random_state=args.seed, n_estimators=100, max_depth=3).fit(np.asarray(Xv), yv)

    def predict(kind, s, rho):
        if kind == "autoregressive":
            f = [rho[i - W:i] if i >= W else [rho[0]] * (W - i) + rho[:i] for i in range(len(rho))]
            return ar.predict(np.asarray(f))
        return vm.predict(np.asarray(vitals(rho, random.Random(s + 17), shift=(kind == "vital-sign, shifted"))))

    arms = ("Stateless, every sample", "Stateless, every 2nd sample", "Max-hold, every sample", "DRAS-5 (full)")
    rows = []
    for kind in ("autoregressive", "vital-sign", "vital-sign, shifted"):
        acc = {a: dict(end_in=0, reach_in=0, end_tr=0, reach_tr=0, oer=0.0) for a in arms}
        se, ne, bias_hi, n_hi = 0.0, 0, 0.0, 0
        for tt, s, rho in test:
            pr = [_clip(float(p)) for p in predict(kind, s, rho)]
            for i, (p, r) in enumerate(zip(pr, rho)):
                if kind != "autoregressive" or i >= W:
                    se += (p - r) ** 2
                    ne += 1
                if r >= 0.7:
                    bias_hi += p - r
                    n_hi += 1
            truth = _level_series(rho)
            pk_in, pk_tr = sustained_peak_level(pr), sustained_peak_level(rho)
            lv = _level_series(pr)
            reps = {arms[0]: stateless_reported_levels(pr, 1), arms[1]: stateless_reported_levels(pr, 2),
                    arms[2]: maxhold(lv), arms[3]: [int(x) for x in run_dras5(pr, enable_c5=True)[0]]}
            for a, rep in reps.items():
                d = acc[a]
                d["end_in"] += rep[-1] < pk_in
                d["reach_in"] += max(rep) < pk_in
                d["end_tr"] += rep[-1] < pk_tr
                d["reach_tr"] += max(rep) < pk_tr
                d["oer"] += sum(x > y for x, y in zip(rep, truth)) / len(truth)
        n = len(test)
        for a in arms:
            d = acc[a]
            rows.append({"upstream": kind, "arm": a, "n_test": n,
                         "rmse": round(math.sqrt(se / ne), 3),
                         "mean_bias_when_true_ge_0.7": round(bias_hi / n_hi, 3),
                         "mer_end_input_pct": round(100 * d["end_in"] / n, 2),
                         "mer_reach_input_pct": round(100 * d["reach_in"] / n, 2),
                         "mer_end_true_pct": round(100 * d["end_tr"] / n, 2),
                         "mer_reach_true_pct": round(100 * d["reach_tr"] / n, 2),
                         "oer_vs_true_pct": round(100 * d["oer"] / n, 2)})
    with open(REPO / "results" / "ml_wrapper_v2.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    for r in rows:
        print(r)


if __name__ == "__main__":
    main()
