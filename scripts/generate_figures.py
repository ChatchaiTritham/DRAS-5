"""
DRAS-5 Commercial-Grade Figure Generator

Produces publication-quality 2D and 3D figures for the manuscript.
All figures use serif fonts, Springer-compatible sizing, and 300 DPI.

Output directory: ../figures/ (relative to this script) or the path
passed via --outdir.

Usage:
    python scripts/generate_figures.py
    python scripts/generate_figures.py --outdir /path/to/figures
"""

from __future__ import annotations

import argparse
import math
import sys
from pathlib import Path

# ── Matplotlib setup ──────────────────────────────────────────────
import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt

# ── Canonical Top-Tier figure utilities (vendored, byte-identical) ──
# Style, palette, save_fig, schematic primitives (add_box/arrow) and the
# results/ loader all live in scripts/pubviz.py -- the single shared source
# across every PhD reproducibility repo. No figure-style code is duplicated here.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from pubviz import (  # noqa: E402
    apply_pub_style,
    save_fig,
    PALETTE,
    add_box,
    arrow,
    load_results,
    results_dir,
)

FIGURE_1_HEIGHT = 3.2
FIGURE_2_HEIGHT = 4.5
STATE_CIRCLE_RADIUS = 0.65


def save(fig, name: str, outdir: Path):
    """Thin wrapper around pubviz.save_fig (signature: fig, basename, out_dir)."""
    save_fig(fig, name, outdir)
    plt.close(fig)


# ── Colour palette (mapped to Okabe-Ito; colour-blind safe) ──────
# Acuity-state colours: kept ordinal (green→black) for the schematic
# state machine, but tinted toward Okabe-Ito hues so they harmonise
# with the data figures' series colours.
STATE_COLORS = {
    "S1": "#009E73",  # green  (Okabe-Ito bluish green)
    "S2": "#E69F00",  # amber  (Okabe-Ito orange)
    "S3": "#D55E00",  # orange (Okabe-Ito vermillion)
    "S4": "#CC79A7",  # rose   (Okabe-Ito reddish purple)
    "S5": "#000000",  # black
}
# Named accents drawn from the shared palette.
DRAS_BLUE = PALETTE[0]    # "#0072B2" primary accent
DRAS_RED = "#D55E00"      # vermillion (warning)
DRAS_GREEN = "#009E73"    # bluish green
DRAS_GRAY = "#7f8c8d"     # neutral (non-series reference lines)
DRAS_ORANGE = "#E69F00"   # orange
LIGHT_BG = "#f8f9fa"

# Springer column widths
SINGLE_COL = 3.5  # inches
DOUBLE_COL = 7.2


# ── Results loader ────────────────────────────────────────────────
# Data-bearing figures (MER, OER, C5 outcomes, over-escalation locator) are
# drawn from the committed CSVs produced by scripts/run_all.py via pubviz's
# load_results(), never from numbers typed into this file. Run
# `python scripts/run_all.py` first if results/ is empty.
def _read_csv(name: str) -> list[dict]:
    return load_results(name)


# =====================================================================
# FIGURE 1: State Machine Diagram (high-quality matplotlib)
# =====================================================================
def fig1_state_machine(outdir: Path):
    # axis("off") schematic: disable constrained_layout (no decorations to size).
    fig, ax = plt.subplots(figsize=(DOUBLE_COL, FIGURE_1_HEIGHT), layout=None)
    ax.set_xlim(-0.5, 10.5)
    ax.set_ylim(-1.0, 2.8)
    ax.set_aspect("equal")
    ax.axis("off")

    # State positions
    positions = {
        "S1": (1.0, 1.0),
        "S2": (3.0, 1.0),
        "S3": (5.0, 1.0),
        "S4": (7.0, 1.0),
        "S5": (9.0, 1.0),
    }
    labels = {
        "S1": "S1\nSAFE",
        "S2": "S2\nMONITOR",
        "S3": "S3\nALERT",
        "S4": "S4\nCRITICAL",
        "S5": "S5\nEMERGENCY",
    }
    thresholds = {
        "S1": "[0, 0.3)",
        "S2": "[0.3, 0.5)",
        "S3": "[0.5, 0.7)",
        "S4": "[0.7, 0.9)",
        "S5": "[0.9, 1.0]",
    }
    timeouts = {
        "S1": "T=inf",
        "S2": "T=300s",
        "S3": "T=120s",
        "S4": "T=60s",
        "S5": "T=inf",
    }

    # Draw states
    for sid, (x, y) in positions.items():
        circle = plt.Circle(
            (x, y),
            STATE_CIRCLE_RADIUS,
            facecolor=STATE_COLORS[sid],
            edgecolor="black",
            linewidth=1.2,
            alpha=0.85,
            zorder=3,
        )
        ax.add_patch(circle)
        tc = "white" if sid in ("S4", "S5") else "black"
        ax.text(
            x,
            y + 0.08,
            labels[sid],
            ha="center",
            va="center",
            fontsize=8,
            fontweight="bold",
            color=tc,
            zorder=4,
        )
        ax.text(
            x,
            y - 0.85,
            thresholds[sid],
            ha="center",
            va="top",
            fontsize=6.5,
            color="#333",
        )
        ax.text(
            x,
            y - 1.05,
            timeouts[sid],
            ha="center",
            va="top",
            fontsize=6,
            color="#666",
            style="italic",
        )

    # Escalation arrows (solid) -- straight; routed through pubviz.arrow.
    for a, b in [("S1", "S2"), ("S2", "S3"), ("S3", "S4"), ("S4", "S5")]:
        xa, ya = positions[a]
        xb, yb = positions[b]
        arrow(ax, (xa + 0.68, ya), (xb - 0.68, yb), color="#333", lw=1.3)

    # Human approval label on S4->S5
    ax.text(
        8.0,
        1.45,
        "alpha=1",
        ha="center",
        fontsize=6.5,
        color=DRAS_RED,
        fontstyle="italic",
    )

    # C5 de-escalation arrows (dashed, curved, below)
    deesc_kw = dict(
        arrowstyle="-|>",
        color=DRAS_BLUE,
        lw=1.0,
        linestyle="dashed",
        connectionstyle="arc3,rad=-0.4",
        zorder=2,
    )
    for a, b in [("S4", "S3"), ("S3", "S2"), ("S2", "S1")]:
        xa, ya = positions[a]
        xb, yb = positions[b]
        ax.annotate(
            "",
            xy=(xb + 0.55, yb - 0.35),
            xytext=(xa - 0.55, ya - 0.35),
            arrowprops=deesc_kw,
        )

    # Legend
    from matplotlib.lines import Line2D

    leg = [
        Line2D([0], [0], color="#333", lw=1.3, label="Risk escalation"),
        Line2D([0], [0], color=DRAS_BLUE, lw=1.0, ls="--", label="C5 de-escalation"),
    ]
    ax.legend(
        handles=leg, loc="upper left", framealpha=0.9, edgecolor="#ccc", fontsize=7
    )

    ax.set_title(
        "DRAS-5 State Machine: Five Acuity Levels with Bidirectional Transitions",
        fontsize=10,
        pad=8,
    )
    save(fig, "fig1_state_machine", outdir)


# =====================================================================
# FIGURE 2: Constraint Enforcement Pipeline (Algorithm 1)
# =====================================================================
def fig2_pipeline(outdir: Path):
    # axis("off") schematic: disable constrained_layout (no decorations to size).
    fig, ax = plt.subplots(figsize=(SINGLE_COL, FIGURE_2_HEIGHT), layout=None)
    ax.set_xlim(0, 6)
    ax.set_ylim(-0.5, 10.5)
    ax.axis("off")

    phases = [
        ("Input", "rho, alpha, t", LIGHT_BG, "#aaa"),
        ("Phase 1", "C2: Timeout\nEnforcement", "#e8f8f5", "#1abc9c"),
        ("Phase 2", "C1: Risk-Based\nEscalation", "#ebf5fb", "#3498db"),
        ("Phase 3", "C4: Human\nApproval Gate", "#fdedec", "#e74c3c"),
        ("Phase 4", "C5: Controlled\nDe-escalation", "#f4ecf7", "#8e44ad"),
        ("Phase 5", "C3: Audit\nLogging", "#fef9e7", "#f39c12"),
        ("Output", "s', log entry", LIGHT_BG, "#aaa"),
    ]

    box_h = 1.1
    gap = 0.35
    total = len(phases) * (box_h + gap) - gap
    y_start = total - 0.5

    for i, (label, desc, fc, ec) in enumerate(phases):
        y = y_start - i * (box_h + gap)
        # Rounded box + centred description routed through pubviz.add_box.
        add_box(ax, (0.5, y), 5.0, box_h, desc,
                facecolor=fc, edgecolor=ec, textcolor="#333", size=7)
        # Bold, colour-coded phase title overlaid in the upper third of the box.
        ax.text(3.0, y + box_h * 0.72, label, ha="center", va="center",
                fontsize=8, fontweight="bold", color=ec, zorder=4)

        if i < len(phases) - 1:
            # Vertical connector routed through pubviz.arrow.
            arrow(ax, (3.0, y + 0.02), (3.0, y - gap * 0.15), color="#555", lw=1.0)

    ax.set_title("Algorithm 1: Unified State Update Procedure", fontsize=9, pad=6)
    save(fig, "fig2_pipeline", outdir)


# =====================================================================
# FIGURE 3: C5 Exponential Risk Decay (corrected S4 parameters)
# =====================================================================
def fig3_c5_decay(outdir: Path):
    fig, ax = plt.subplots(figsize=(DOUBLE_COL, 3.0))

    rho_peak = 0.85
    lam = 0.001  # S4 lambda
    t_cool = 180  # S4 cooling period
    theta_target = 0.50  # theta_3

    t = np.linspace(0, 800, 500)
    rho_raw = np.where(t < 30, rho_peak, 0.30 + 0.05 * np.sin(t / 40))
    rho_decay = rho_peak * np.exp(-lam * t)
    rho_eff = np.maximum(rho_raw, rho_decay)

    t_cross = math.log(rho_peak / theta_target) / lam

    # Shaded regions
    ax.axhspan(0.70, 0.90, alpha=0.06, color=STATE_COLORS["S4"])
    ax.axhspan(0.50, 0.70, alpha=0.06, color=STATE_COLORS["S3"])

    # Cooling period
    ax.axvspan(
        t_cross,
        t_cross + t_cool,
        alpha=0.10,
        color=DRAS_BLUE,
        label=f"$T_{{cool}}$ = {t_cool}s",
    )

    # Lines
    ax.plot(
        t, rho_raw, color=DRAS_GRAY, lw=0.8, ls=":", alpha=0.7, label=r"$\rho(t)$ raw"
    )
    ax.plot(
        t,
        rho_decay,
        color=DRAS_ORANGE,
        lw=1.0,
        ls="--",
        label=r"$\rho_{peak} \cdot e^{-\lambda_4 t}$",
    )
    ax.plot(t, rho_eff, color=DRAS_RED, lw=1.8, label=r"$\rho_{eff}(t)$")

    # Threshold
    ax.axhline(theta_target, color=DRAS_GREEN, ls="-.", lw=0.9, alpha=0.8)
    ax.text(10, theta_target + 0.02, r"$\theta_3 = 0.50$", fontsize=7, color=DRAS_GREEN)

    # Crossing point
    ax.plot(t_cross, theta_target, "o", color=DRAS_BLUE, ms=5, zorder=5)
    ax.annotate(
        f"t = {t_cross:.0f}s",
        xy=(t_cross, theta_target),
        xytext=(t_cross + 40, 0.58),
        fontsize=7,
        arrowprops=dict(arrowstyle="->", color="#555", lw=0.6),
    )

    # Half-life annotation
    t_half = math.log(2) / lam
    rho_half = rho_peak / 2
    ax.plot(t_half, rho_half, "s", color=DRAS_ORANGE, ms=4, zorder=5)
    ax.annotate(
        f"$t_{{1/2}}$ = {t_half:.0f}s",
        xy=(t_half, rho_half),
        xytext=(t_half + 30, rho_half + 0.06),
        fontsize=7,
        arrowprops=dict(arrowstyle="->", color="#555", lw=0.6),
    )

    ax.set_xlabel("Time since peak (s)")
    ax.set_ylabel("Risk score")
    ax.set_xlim(0, 800)
    ax.set_ylim(0, 1.0)
    ax.legend(loc="upper right", framealpha=0.95, edgecolor="#ddd", fontsize=7)
    ax.set_title(
        r"C5 Exponential Decay: $\rho_{eff}(t) = \max(\rho(t),\; "
        r"\rho_{peak} \cdot e^{-\lambda_4 t})$  "
        r"[$\lambda_4 = 0.001$, S4 parameters]",
        fontsize=9,
        pad=6,
    )

    save(fig, "fig3_c5_decay", outdir)


# =====================================================================
# FIGURE 3b: Multi-state Decay Comparison
# =====================================================================
def fig3b_decay_comparison(outdir: Path):
    fig, ax = plt.subplots(figsize=(SINGLE_COL, 3.0))

    rho_peak = 0.85
    t = np.linspace(0, 1400, 600)

    params = [
        (0.005, "S2: $\\lambda_2$ = 0.005", STATE_COLORS["S2"], "-"),
        (0.003, "S3: $\\lambda_3$ = 0.003", STATE_COLORS["S3"], "--"),
        (0.001, "S4: $\\lambda_4$ = 0.001", STATE_COLORS["S4"], "-."),
    ]

    for lam, label, color, ls in params:
        decay = rho_peak * np.exp(-lam * t)
        ax.plot(t, decay, color=color, ls=ls, lw=1.5, label=label)

    ax.axhline(0.5, color="#aaa", ls=":", lw=0.7)
    ax.text(1350, 0.52, "0.5", fontsize=6, color="#999", ha="right")

    ax.set_xlabel("Time since peak (s)")
    ax.set_ylabel("Decayed risk")
    ax.set_xlim(0, 1400)
    ax.set_ylim(0, 0.9)
    ax.legend(loc="upper right", framealpha=0.95, fontsize=7)
    ax.set_title("Exponential Decay Rates by State", fontsize=9, pad=6)

    save(fig, "fig3b_decay_comparison", outdir)


# =====================================================================
# FIGURE 4: MER Bar Chart (Table 6)
# =====================================================================
def fig4_mer(outdir: Path):
    # Driven by results/mer_by_type.csv (+ summary.json overall CI), seed 42.
    # Error bars are the seeded bootstrap 95% CI (N=1000) computed in run_all.py.
    rows = _read_csv("mer_by_type.csv")
    summ = load_results("summary.json")
    label_map = {"monotonic": "Monotonic", "oscillating": "Oscillating",
                 "spike_emergency": "Spike-emerg.", "spike_critical": "Spike-crit."}
    types = [label_map.get(r["trajectory_type"], r["trajectory_type"]) for r in rows]

    def col(key):
        return [float(r[key]) for r in rows]

    series = {
        "news2": (col("mer_news2_pct"), col("mer_news2_ci_lo"), col("mer_news2_ci_hi")),
        "mews": (col("mer_mews_pct"), col("mer_mews_ci_lo"), col("mer_mews_ci_hi")),
        "dras": (col("mer_dras5_pct"), col("mer_dras5_ci_lo"), col("mer_dras5_ci_hi")),
    }
    # Append the pooled "Overall" bar with its own bootstrap CI from summary.json.
    types.append("Overall")
    ov = summ["mer_overall_pct"]
    ovci = summ["mer_overall_ci95"]
    for key, src in (("news2", "news2"), ("mews", "mews"), ("dras", "dras5")):
        vals, los, his = series[key]
        vals.append(float(ov[src]))
        los.append(float(ovci[src][0]))
        his.append(float(ovci[src][1]))

    def yerr(vals, los, his):
        return np.array([[max(0.0, v - lo) for v, lo in zip(vals, los)],
                         [max(0.0, hi - v) for v, hi in zip(vals, his)]])

    news2, n_lo, n_hi = series["news2"]
    mews, m_lo, m_hi = series["mews"]
    dras, d_lo, d_hi = series["dras"]

    fig, ax = plt.subplots(figsize=(DOUBLE_COL, 2.8))
    x = np.arange(len(types))
    w = 0.27
    ebar = dict(ecolor="#333", elinewidth=0.8, capsize=2.5, capthick=0.8)
    ax.bar(x - w, news2, w, yerr=yerr(news2, n_lo, n_hi), error_kw=ebar,
           label="NEWS2 (stateless)", color=PALETTE[1], edgecolor="#7a3500", linewidth=0.4)
    ax.bar(x, mews, w, yerr=yerr(mews, m_lo, m_hi), error_kw=ebar,
           label="MEWS (stateless)", color=PALETTE[4], edgecolor="#8a6300", linewidth=0.4)
    bars = ax.bar(x + w, dras, w, yerr=yerr(dras, d_lo, d_hi), error_kw=ebar,
                  label="DRAS-5", color=DRAS_BLUE, edgecolor="#004a73", linewidth=0.5)
    for bar, h in zip(bars, dras):
        ax.text(bar.get_x() + bar.get_width() / 2, max(h, 0) + 0.5,
                f"{h:.1f}", ha="center", va="bottom", fontsize=7,
                color=DRAS_BLUE, fontweight="bold")

    ax.set_xticks(x)
    ax.set_xticklabels(types)
    ax.set_xlabel("Trajectory type")
    ax.set_ylabel("Missed Escalation Rate (%)")
    ax.set_ylim(0, 105)
    ax.grid(axis="y", alpha=0.3)
    ax.grid(axis="x", visible=False)
    ax.legend(loc="upper left")
    ax.set_title(
        "MER by Trajectory Type (seed 42; error bars = bootstrap 95% CI, N=1000). "
        "DRAS-5 = 0% by structural C1 guarantee.",
        fontsize=8.5,
        pad=6,
    )

    save(fig, "fig4_mer", outdir)


# =====================================================================
# FIGURE 5: OER Comparison (Table 7)
# =====================================================================
def fig5_oer(outdir: Path):
    # Driven by results/oer_by_type.csv (scripts/run_all.py, seed 42).
    # C5 grants controlled de-escalations, but the binary OER metric (system level
    # strictly above true level) is largely unchanged because a de-escalated state
    # is still above the recovered true level; see REPRODUCIBILITY.md.
    rows = _read_csv("oer_by_type.csv")
    summ = load_results("summary.json")
    label_map = {"monotonic": "Monotonic", "oscillating": "Oscillating",
                 "spike_emergency": "Spike-emerg.", "spike_critical": "Spike-crit."}
    types = [label_map.get(r["trajectory_type"], r["trajectory_type"]) for r in rows]
    dras_no_c5 = [float(r["oer_no_c5_pct"]) for r in rows]
    no_lo = [float(r["oer_no_c5_ci_lo"]) for r in rows]
    no_hi = [float(r["oer_no_c5_ci_hi"]) for r in rows]
    dras_full = [float(r["oer_with_c5_pct"]) for r in rows]
    wi_lo = [float(r["oer_with_c5_ci_lo"]) for r in rows]
    wi_hi = [float(r["oer_with_c5_ci_hi"]) for r in rows]
    # Pooled "Overall" bar with its own bootstrap CI (summary.json).
    types.append("Overall")
    ov = summ["oer_overall_pct"]
    ovci = summ["oer_overall_ci95"]
    dras_no_c5.append(float(ov["no_c5"])); no_lo.append(float(ovci["no_c5"][0])); no_hi.append(float(ovci["no_c5"][1]))
    dras_full.append(float(ov["with_c5"])); wi_lo.append(float(ovci["with_c5"][0])); wi_hi.append(float(ovci["with_c5"][1]))

    def yerr(vals, los, his):
        return np.array([[max(0.0, v - lo) for v, lo in zip(vals, los)],
                         [max(0.0, hi - v) for v, hi in zip(vals, his)]])

    fig, ax = plt.subplots(figsize=(DOUBLE_COL, 2.8))
    x = np.arange(len(types))
    w = 0.30
    ebar = dict(ecolor="#333", elinewidth=0.8, capsize=2.5, capthick=0.8)
    ax.bar(
        x - w / 2, dras_no_c5, w, yerr=yerr(dras_no_c5, no_lo, no_hi), error_kw=ebar,
        label="DRAS (no C5)", color=PALETTE[4], edgecolor="#8a6300", linewidth=0.5,
    )
    ax.bar(
        x + w / 2, dras_full, w, yerr=yerr(dras_full, wi_lo, wi_hi), error_kw=ebar,
        label="DRAS (with C5)", color=DRAS_BLUE, edgecolor="#004a73", linewidth=0.5,
    )
    for i in range(len(types)):
        ax.text(
            x[i], max(no_hi[i], wi_hi[i]) + 1.5,
            f"{dras_full[i]:.1f}%",
            ha="center", fontsize=7, color="#333",
        )

    ax.set_xticks(x)
    ax.set_xticklabels(types)
    ax.set_xlabel("Trajectory type")
    ax.set_ylabel("Over-Escalation Rate (%)")
    ax.set_ylim(0, max(no_hi + wi_hi) * 1.18)
    ax.grid(axis="y", alpha=0.3)
    ax.grid(axis="x", visible=False)
    ax.legend(loc="upper left")
    ax.set_title(
        "Over-Escalation Rate by Trajectory Type (seed 42; error bars = bootstrap "
        "95% CI, N=1000); binary OER is near-identical with/without C5",
        fontsize=8,
        pad=6,
    )

    save(fig, "fig5_oer", outdir)


# NOTE: A "fig6_sensitivity" generator was removed for research integrity. Its OER
# and MTCS curves were typed into the script, not produced by any perturbation
# sweep (no sweep code exists in this repository) and they contradicted the
# seed-42 results in results/. The only reproducible part of the sensitivity claim
# (MER = 0% under perturbation) is structural; see REPRODUCIBILITY.md.


# =====================================================================
# FIGURE 7: C5 De-escalation Outcome Funnel (Table 8)
# =====================================================================
# Design choice: the committed seed-42 run denies *every* C5 request for one
# reason (incomplete cooling window) and grants none, so the prior single-bar
# "100% category" plot carried no information. A waterfall makes the funnel
# legible: it starts at the full request volume, debits each denial bucket in
# turn, and lands on the granted = 0 terminal -- showing both the magnitude of
# requests and exactly where they are eliminated. (A Sankey was rejected: with a
# single non-zero edge it degenerates to one ribbon and is no clearer.)
def fig7_c5_rejection(outdir: Path):
    # Driven by results/c5_outcomes.csv (scripts/run_all.py, seed 42).
    rows = {r["reason"]: int(r["count"]) for r in _read_csv("c5_outcomes.csv")}
    denial_order = [
        ("denied_cooling", "Denied:\ncooling\nincomplete", DRAS_ORANGE),
        ("denied_decay", "Denied:\ndecay not\nsustained", DRAS_RED),
        ("denied_approval", "Denied:\nsingle\napproval", DRAS_GRAY),
    ]
    total = sum(rows.get(k, 0) for k in
                ("granted", "denied_decay", "denied_cooling", "denied_approval"))
    granted = rows.get("granted", 0)

    # Build the waterfall: bar i spans [running_after, running_before]; each
    # denial debits the running pool, the final "Granted" bar is what remains.
    labels = ["C5 requests"] + [lbl for _, lbl, _ in denial_order] + ["Granted"]
    debits = [rows.get(k, 0) for k, _, _ in denial_order]
    fig, ax = plt.subplots(figsize=(DOUBLE_COL, 3.2))
    x = np.arange(len(labels))

    running = total
    # Opening bar (full request volume).
    ax.bar(0, total, 0.62, color=DRAS_BLUE, edgecolor="#004a73", linewidth=0.5, zorder=3)
    ax.text(0, total + total * 0.02, f"{total:,}\n(100%)", ha="center", va="bottom",
            fontsize=7, color=DRAS_BLUE, fontweight="bold")
    for i, ((_, lbl, col), d) in enumerate(zip(denial_order, debits), start=1):
        bottom = running - d
        ax.bar(i, d, 0.62, bottom=bottom, color=col, edgecolor="#555",
               linewidth=0.4, zorder=3)
        # Connector from previous running level to this bar's top.
        ax.plot([i - 1 + 0.31, i - 0.31], [running, running],
                color="#999", lw=0.7, ls="--", zorder=1)
        pct = 100.0 * d / total if total else 0.0
        ax.text(i, running + total * 0.02, f"-{d:,}\n({pct:.1f}%)", ha="center",
                va="bottom", fontsize=7, color=col)
        running = bottom
    # Terminal "Granted" bar (what survives the funnel).
    ax.plot([len(labels) - 2 + 0.31, len(labels) - 1 - 0.31], [running, running],
            color="#999", lw=0.7, ls="--", zorder=1)
    ax.bar(len(labels) - 1, max(granted, total * 0.004), 0.62, color=DRAS_GREEN,
           edgecolor="#055", linewidth=0.5, zorder=3)
    gpct = 100.0 * granted / total if total else 0.0
    ax.text(len(labels) - 1, total * 0.02, f"{granted:,}\n({gpct:.1f}%)", ha="center",
            va="bottom", fontsize=7, color="#0a6", fontweight="bold")

    ax.set_xticks(x)
    ax.set_xticklabels(labels, fontsize=7.5)
    ax.set_ylabel("De-escalation requests")
    ax.set_ylim(0, total * 1.18)
    ax.grid(axis="y", alpha=0.3)
    ax.grid(axis="x", visible=False)
    ax.set_title(
        f"C5 De-escalation Outcome Funnel (n = {total:,}, seed 42): "
        f"{granted:,} granted, each clearing the cooling/decay/dual-approval guards (0 premature)",
        fontsize=8,
        pad=6,
    )

    save(fig, "fig7_c5_rejection", outdir)


# =====================================================================
# FIGURE 8: Over-escalation locator (where OER occurs, by true acuity level)
# =====================================================================
# New chart requested by the viz audit: an over-escalation *locator*. It answers
# "where does the OER come from?" by decomposing the binary over-escalation rate
# across the patient's true acuity level (S1..S5). Computed deterministically in
# run_all.py (seed 42) and read from results/oer_by_truelevel.csv -- never typed.
def fig8_oer_locator(outdir: Path):
    rows = _read_csv("oer_by_truelevel.csv")
    color_for = {"SAFE": STATE_COLORS["S1"], "MONITOR": STATE_COLORS["S2"],
                 "ALERT": STATE_COLORS["S3"], "CRITICAL": STATE_COLORS["S4"],
                 "EMERGENCY": STATE_COLORS["S5"]}
    names = [r["true_state"] for r in rows]
    oer = [float(r["oer_pct"]) for r in rows]
    steps = [int(r["steps_at_level"]) for r in rows]
    over = [int(r["over_escalated_steps"]) for r in rows]
    colors = [color_for.get(n, DRAS_GRAY) for n in names]

    fig, ax = plt.subplots(figsize=(DOUBLE_COL, 3.0))
    x = np.arange(len(names))
    bars = ax.bar(x, oer, 0.62, color=colors, edgecolor="#444", linewidth=0.4, zorder=3)
    for xi, h, ov, st in zip(x, oer, over, steps):
        share = f"{ov:,}/{st:,}" if st else "0/0"
        ax.text(xi, h + 1.5, f"{h:.1f}%\n{share}", ha="center", va="bottom",
                fontsize=6.8, color="#333")

    ax.set_xticks(x)
    ax.set_xticklabels([f"S{i+1}\n{n.title()}" for i, n in enumerate(names)], fontsize=7.5)
    ax.set_xlabel("Patient's true acuity level  $\\tau(\\rho)$")
    ax.set_ylabel("Over-escalation rate at level (%)")
    ax.set_ylim(0, max(oer + [1]) * 1.25)
    ax.grid(axis="y", alpha=0.3)
    ax.grid(axis="x", visible=False)
    ax.set_title(
        "Over-escalation locator (seed 42): share of sample-steps where the "
        "system sits above the true level, by true acuity",
        fontsize=8,
        pad=6,
    )
    save(fig, "fig8_oer_locator", outdir)


# NOTE: A "fig8_3d_sensitivity" generator was removed for research integrity. The
# 3D surface was produced from a typed-in analytical OER model (constant 3.6 plus
# linear terms), not from measured data; no perturbation/decay sweep exists in
# this repository. See REPRODUCIBILITY.md.


# =====================================================================
# FIGURE 9: Per-family risk trajectories with state bands (small multiples)
# =====================================================================
# Replaces the former 3D scatter (3D-projected a 2D relationship -- risk vs.
# time, with state a deterministic function tau(rho), so the third axis was
# redundant and the projection occluded the curves). A 3x1 small-multiples
# panel reads risk(t) directly against horizontal acuity bands; the system
# state is just which band the curve sits in, so no separate axis is needed.
def fig9_3d_trajectory(outdir: Path):
    # Risk-to-state thresholds (Eq. 2) -> horizontal acuity bands, shared y-axis.
    bands = [
        (0.0, 0.3, STATE_COLORS["S1"], "S1"),
        (0.3, 0.5, STATE_COLORS["S2"], "S2"),
        (0.5, 0.7, STATE_COLORS["S3"], "S3"),
        (0.7, 0.9, STATE_COLORS["S4"], "S4"),
        (0.9, 1.0, STATE_COLORS["S5"], "S5"),
    ]
    families = [
        ("monotonic", "Monotonic rise", DRAS_BLUE),
        ("oscillating", "Oscillating", DRAS_ORANGE),
        ("spike_recover", "Spike then recover", DRAS_RED),
    ]

    # Trajectories come from the repo simulator (seed 42), not typed-in numbers.
    sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
    from dras5.simulator import generate_trajectory

    fig, axes = plt.subplots(3, 1, figsize=(DOUBLE_COL, 5.0), sharex=True)
    for ax, (tt, label, color) in zip(axes, families):
        traj = generate_trajectory(ttype=tt, n_steps=80, dt=10, seed=42)
        t_vals = [p.t for p in traj]
        rho_vals = [p.rho for p in traj]

        # Faint acuity bands (low data-ink): the band the curve is in == state.
        for lo, hi, c, name in bands:
            ax.axhspan(lo, hi, color=c, alpha=0.08, zorder=0)
            ax.text(t_vals[-1] * 1.005, (lo + hi) / 2, name, va="center",
                    ha="left", fontsize=6.5, color=c)
        # Threshold rules.
        for thr in (0.3, 0.5, 0.7, 0.9):
            ax.axhline(thr, color="#cfcfcf", lw=0.5, zorder=0)

        ax.plot(t_vals, rho_vals, color=color, lw=1.4, zorder=3)
        ax.set_ylim(0, 1.0)
        ax.set_xlim(0, t_vals[-1] * 1.04)
        ax.set_yticks([0, 0.3, 0.5, 0.7, 0.9])
        ax.set_ylabel("Risk", fontsize=8)
        ax.set_title(label, fontsize=8.5, loc="left", pad=3)
        ax.grid(False)

    axes[-1].set_xlabel("Time since admission (s)")
    fig.suptitle(
        "Per-family risk trajectories with acuity bands (DRAS-5 simulator, seed 42)",
        fontsize=9,
    )
    save(fig, "fig9_3d_trajectory", outdir)


# NOTE: Three generators were removed for research integrity because their values
# were typed into the script and could not be sourced from results/:
#   * fig10_performance  -- the four per-operation latency bars and the throughput
#     gauge were hardcoded; run_all.py emits only one aggregate transition latency
#     (results/latency.csv), and the gauge's 8,333 updates/s even contradicted the
#     measured ~33,000 updates/s.
#   * fig11_regulatory   -- the IEC 61508 / IEC 62304 / EU AI Act coverage matrix
#     is an editorial mapping with no computational source in this repository.
#   * fig12_compliance   -- the per-constraint "test events" counts (5000/1500/
#     50000/2500/800) were typed in and are not produced by run_all.py.
# See REPRODUCIBILITY.md and README.md.


# =====================================================================
# MAIN
# =====================================================================
def main():
    parser = argparse.ArgumentParser(description="Generate DRAS-5 figures")
    parser.add_argument(
        "--outdir",
        type=str,
        default=None,
        help="Output directory (default: figures/ next to repo root)",
    )
    args = parser.parse_args()

    if args.outdir:
        outdir = Path(args.outdir)
    else:
        outdir = Path(__file__).parent.parent / "figures"

    outdir.mkdir(parents=True, exist_ok=True)
    apply_pub_style()  # canonical Top-Tier style, once before plotting
    print(f"Output: {outdir.resolve()}\n")

    generators = [
        ("Fig 1", "State machine diagram", fig1_state_machine),
        ("Fig 2", "Constraint pipeline", fig2_pipeline),
        ("Fig 3", "C5 exponential decay (S4 params)", fig3_c5_decay),
        ("Fig 3b", "Multi-state decay comparison", fig3b_decay_comparison),
        ("Fig 4", "MER bar chart (from results/mer_by_type.csv)", fig4_mer),
        ("Fig 5", "OER comparison (from results/oer_by_type.csv)", fig5_oer),
        # Removed for research integrity (their generators are gone and the stale
        # PNG/PDF outputs deleted): Fig 6 (threshold sweep) and the former
        # "fig8_3d_sensitivity" 3D surface (both hardcoded, no sweep code) and
        # Fig 10 / Fig 11 / Fig 12 (performance, regulatory, compliance
        # dashboards: values typed in, not sourced from results/; Fig 10's
        # throughput even contradicted latency.csv). The Fig 8 below is a NEW,
        # results-driven over-escalation locator -- unrelated to the removed one.
        # See REPRODUCIBILITY.md and README.md.
        ("Fig 7", "C5 outcome funnel (from results/c5_outcomes.csv)", fig7_c5_rejection),
        ("Fig 8", "Over-escalation locator (from results/oer_by_truelevel.csv)", fig8_oer_locator),
        ("Fig 9", "Per-family risk trajectories with state bands (small multiples)", fig9_3d_trajectory),
    ]

    for label, desc, fn in generators:
        print(f"{label}: {desc}")
        fn(outdir)

    print(f"\nDone. {len(generators)} figures generated in {outdir.resolve()}")


if __name__ == "__main__":
    main()
