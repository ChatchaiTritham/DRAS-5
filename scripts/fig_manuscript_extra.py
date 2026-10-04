#!/usr/bin/env python3
"""
Two manuscript figures drawn only from released outputs (no typed-in numbers):

  fig_mer_ci.pdf      Missed Escalation Rate by trajectory family with 95% bootstrap
                      intervals, read from results/mer_by_type.csv and summary.json
  fig_trajectory.pdf  One seed-42 spike-to-critical trajectory: the instantaneous
                      risk and the level reported by NEWS2-style sampling, a
                      max-hold scorer, DRAS-5 without C5 and DRAS-5 with C5

Usage
-----
    python scripts/fig_manuscript_extra.py [--outdir figures]
"""
from __future__ import annotations

import argparse
import csv
import json
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import run_all as R  # noqa: E402
from pubviz import PALETTE, apply_pub_style  # noqa: E402

logging.disable(logging.CRITICAL)
ROOT = Path(__file__).resolve().parent.parent
LABELS = {"monotonic": "Monotonic", "oscillating": "Oscillating",
          "spike_emergency": "Spike→Emerg.", "spike_critical": "Spike→Crit."}
NAMES = {1: "S1", 2: "S2", 3: "S3", 4: "S4", 5: "S5"}


def fig_mer(outdir: Path):
    rows = list(csv.DictReader(open(ROOT / "results" / "mer_by_type.csv", encoding="utf-8")))
    summ = json.load(open(ROOT / "results" / "summary.json", encoding="utf-8"))
    cats = [LABELS[r["trajectory_type"]] for r in rows] + ["Overall"]
    def series(key):
        v = [float(r[f"mer_{key}_pct"]) for r in rows] + [summ["mer_overall_pct"][key]]
        lo = [float(r[f"mer_{key}_ci_lo"]) for r in rows] + [summ["mer_overall_ci95"][key][0]]
        hi = [float(r[f"mer_{key}_ci_hi"]) for r in rows] + [summ["mer_overall_ci95"][key][1]]
        v, lo, hi = map(np.array, (v, lo, hi))
        return v, np.vstack([v - lo, hi - v])
    apply_pub_style()
    fig, ax = plt.subplots(figsize=(5.7, 3.0))
    x = np.arange(len(cats))
    w = 0.26
    spec = [("news2", "NEWS2 (stateless)", PALETTE[1]), ("mews", "MEWS (stateless)", PALETTE[4]),
            ("dras5", "DRAS-5 (C1 reach); max-hold", PALETTE[2])]
    for k, (key, lab, col) in enumerate(spec):
        v, err = series(key)
        b = ax.bar(x + (k - 1) * w, v, w, label=lab, color=col, edgecolor="black",
                   linewidth=0.5, yerr=err, error_kw=dict(lw=0.8, capsize=2))
        for xi, vi in zip(x + (k - 1) * w, v):
            ax.text(xi, vi + 3.2 if vi > 0 else 1.5, f"{vi:.1f}", ha="center", va="bottom",
                    fontsize=6.5, rotation=90 if vi > 0 else 0)
    ax.set_xticks(x, cats)
    ax.set_ylabel("Missed escalation rate (%)")
    ax.set_ylim(0, 128)
    ax.set_yticks(range(0, 101, 20))
    ax.legend(loc="upper center", ncol=3, bbox_to_anchor=(0.5, 1.13), fontsize=8)
    ax.grid(axis="x", visible=False)
    fig.savefig(outdir / "fig_mer_ci.pdf")
    plt.close(fig)


def levels(rho):
    return [int(R.risk_to_state(r)) for r in rho]


def fig_traj(outdir: Path, j: int = 0):
    rho = R.make_trajectory("spike_critical", R._traj_seed(R.BASE_SEED, "spike_critical", j))
    t = np.arange(len(rho)) * R.DT_SECONDS
    true = levels(rho)
    news2 = R.stateless_reported_levels(rho, R.NEWS2_OBS_INTERVAL)
    maxhold = list(np.maximum.accumulate(true))
    noc5, _ = R.run_dras5(rho, enable_c5=False)
    full, _ = R.run_dras5(rho, enable_c5=True)
    noc5, full = [int(x) for x in noc5], [int(x) for x in full]
    grant = next((i for i in range(1, len(full)) if full[i] < full[i - 1]), None)

    apply_pub_style()
    fig, (a, b) = plt.subplots(2, 1, figsize=(5.7, 4.6), sharex=True,
                               gridspec_kw=dict(height_ratios=[1, 1.35]))
    for th, name in ((0.3, "S2"), (0.5, "S3"), (0.7, "S4"), (0.9, "S5")):
        a.axhline(th, color="0.6", lw=0.6, ls="--")
        a.text(t[-1] + 8, th, name, va="center", fontsize=7, color="0.35")
    a.plot(t, rho, color=PALETTE[0], lw=1.3)
    a.set_ylabel(r"Risk score $\rho$")
    a.set_ylim(0, 1.0)
    pk = int(np.argmax(rho))
    a.annotate("peak", (t[pk], rho[pk]), (t[pk] + 70, rho[pk] + 0.05), fontsize=8,
               arrowprops=dict(arrowstyle="-", lw=0.6))

    b.step(t, true, where="post", color="0.45", lw=1.0, ls=":", label=r"True level $\tau(\rho)$")
    b.step(t, news2, where="post", color=PALETTE[1], lw=1.3, label="NEWS2-style (every 2nd sample)")
    b.step(t, np.array(maxhold) + 0.07, where="post", color=PALETTE[4], lw=1.3, ls="--", label="Max-hold")
    b.step(t, np.array(full) - 0.07, where="post", color=PALETTE[2], lw=1.8, label="DRAS-5 (full)")
    if grant is not None:
        b.annotate("C5 grant", (t[grant], full[grant] - 0.07), (t[grant] - 330, 2.15), fontsize=8,
                   arrowprops=dict(arrowstyle="->", lw=0.8))
    b.set_yticks(range(1, 6), [NAMES[i] for i in range(1, 6)])
    b.set_ylim(0.6, 5.0)
    b.set_ylabel("Reported level")
    b.set_xlabel("Time (s)")
    h, l = b.get_legend_handles_labels()
    fig.legend(h, l, loc="upper center", ncol=2, fontsize=7.5, bbox_to_anchor=(0.5, 1.07))
    fig.align_ylabels([a, b])
    fig.savefig(outdir / "fig_trajectory.pdf")
    plt.close(fig)
    return dict(trajectory=j, grant_step=grant, peak_step=pk)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--outdir", default=str(ROOT / "figures"))
    a = ap.parse_args()
    out = Path(a.outdir)
    out.mkdir(parents=True, exist_ok=True)
    fig_mer(out)
    print(fig_traj(out))


if __name__ == "__main__":
    main()
