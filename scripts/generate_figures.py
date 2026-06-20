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
import matplotlib.gridspec as gridspec
import matplotlib.patches as mpatches
import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d import Axes3D  # noqa: F401 (side-effect import)

# Attempt serif font; fall back to DejaVu Serif on Linux/CI
try:
    matplotlib.font_manager.findfont("Times New Roman", fallback_to_default=False)
    FONT_FAMILY = "Times New Roman"
except Exception:
    FONT_FAMILY = "DejaVu Serif"

PUBLICATION_DPI = 300
DEFAULT_SAVE_PADDING_INCHES = 0.05
DEFAULT_TIGHT_BBOX = "tight"
FIGURE_1_HEIGHT = 3.2
FIGURE_2_HEIGHT = 4.5
STATE_CIRCLE_RADIUS = 0.65
DEFAULT_AXIS_LINE_WIDTH = 0.6

plt.rcParams.update(
    {
        "font.family": "serif",
        "font.serif": [FONT_FAMILY],
        "font.size": 9,
        "axes.labelsize": 10,
        "axes.titlesize": 11,
        "xtick.labelsize": 8,
        "ytick.labelsize": 8,
        "legend.fontsize": 8,
        "figure.dpi": PUBLICATION_DPI,
        "savefig.dpi": 300,
        "savefig.bbox": "tight",
        "savefig.pad_inches": 0.05,
        "axes.linewidth": 0.6,
        "lines.linewidth": 1.2,
        "patch.linewidth": 0.5,
        "axes.grid": False,
    }
)

# ── Colour palette (Springer-friendly, colour-blind safe) ────────
STATE_COLORS = {
    "S1": "#2ecc71",  # green
    "S2": "#f1c40f",  # yellow
    "S3": "#e67e22",  # orange
    "S4": "#e74c3c",  # red
    "S5": "#1a1a2e",  # near-black
}
DRAS_BLUE = "#2980b9"
DRAS_RED = "#c0392b"
DRAS_GREEN = "#27ae60"
DRAS_GRAY = "#7f8c8d"
DRAS_ORANGE = "#d35400"
LIGHT_BG = "#f8f9fa"
PUBLICATION_DPI = 300
DEFAULT_SAVE_PADDING_INCHES = 0.05
DEFAULT_TIGHT_BBOX = "tight"
FIGURE_1_HEIGHT = 3.2
FIGURE_2_HEIGHT = 4.5
STATE_CIRCLE_RADIUS = 0.65
DEFAULT_AXIS_LINE_WIDTH = 0.6

COL_SPRINGER = DRAS_BLUE  # primary accent

# Springer column widths
SINGLE_COL = 3.5  # inches
DOUBLE_COL = 7.0


def save(fig, name: str, outdir: Path):
    for ext in ("pdf", "png"):
        fig.savefig(outdir / f"{name}.{ext}")
    plt.close(fig)
    print(f"  [OK] {name}.pdf / .png")


# ── Results loader ────────────────────────────────────────────────
# Data-bearing figures (MER, OER, C5 outcomes) are drawn from the committed
# CSVs produced by scripts/run_all.py, never from numbers typed into this file.
# Run `python scripts/run_all.py` first if results/ is empty.
import csv

RESULTS_DIR = Path(__file__).resolve().parent.parent / "results"


def _read_csv(name: str) -> list[dict]:
    path = RESULTS_DIR / name
    if not path.exists():
        raise FileNotFoundError(
            f"{path} not found. Run `python scripts/run_all.py` to generate results first."
        )
    with path.open(encoding="utf-8") as f:
        return list(csv.DictReader(f))


# =====================================================================
# FIGURE 1: State Machine Diagram (high-quality matplotlib)
# =====================================================================
def fig1_state_machine(outdir: Path):
    fig, ax = plt.subplots(figsize=(DOUBLE_COL, FIGURE_1_HEIGHT))
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

    # Escalation arrows (solid)
    arrow_kw = dict(
        arrowstyle="-|>", color="#333", lw=1.3, connectionstyle="arc3,rad=0", zorder=2
    )
    for a, b in [("S1", "S2"), ("S2", "S3"), ("S3", "S4"), ("S4", "S5")]:
        xa, ya = positions[a]
        xb, yb = positions[b]
        ax.annotate("", xy=(xb - 0.68, yb), xytext=(xa + 0.68, ya), arrowprops=arrow_kw)

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
    fig, ax = plt.subplots(figsize=(SINGLE_COL, FIGURE_2_HEIGHT))
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
        rect = mpatches.FancyBboxPatch(
            (0.5, y),
            5.0,
            box_h,
            boxstyle="round,pad=0.15",
            facecolor=fc,
            edgecolor=ec,
            linewidth=1.3,
            zorder=3,
        )
        ax.add_patch(rect)
        ax.text(
            3.0,
            y + box_h * 0.65,
            label,
            ha="center",
            va="center",
            fontsize=8,
            fontweight="bold",
            color=ec,
            zorder=4,
        )
        ax.text(
            3.0,
            y + box_h * 0.28,
            desc,
            ha="center",
            va="center",
            fontsize=7,
            color="#333",
            zorder=4,
        )

        if i < len(phases) - 1:
            ax.annotate(
                "",
                xy=(3.0, y - gap * 0.15),
                xytext=(3.0, y + 0.02),
                arrowprops=dict(arrowstyle="-|>", color="#555", lw=1.0),
            )

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
    # Driven by results/mer_by_type.csv (scripts/run_all.py, seed 42).
    rows = _read_csv("mer_by_type.csv")
    label_map = {"monotonic": "Monotonic", "oscillating": "Oscillating",
                 "spike_emergency": "Spike-emerg.", "spike_critical": "Spike-crit."}
    types = [label_map.get(r["trajectory_type"], r["trajectory_type"]) for r in rows]
    news2 = [float(r["mer_news2_pct"]) for r in rows]
    mews = [float(r["mer_mews_pct"]) for r in rows]
    dras = [float(r["mer_dras5_pct"]) for r in rows]
    # Overall = simple mean across the equal-sized trajectory families.
    types.append("Overall")
    for series in (news2, mews, dras):
        series.append(round(sum(series) / len(series), 2))

    fig, ax = plt.subplots(figsize=(DOUBLE_COL, 2.8))
    x = np.arange(len(types))
    w = 0.27
    ax.bar(x - w, news2, w, label="NEWS2 (stateless)", color="#e74c3c", edgecolor="#922b21", linewidth=0.4)
    ax.bar(x, mews, w, label="MEWS (stateless)", color="#e67e22", edgecolor="#a04000", linewidth=0.4)
    bars = ax.bar(x + w, dras, w, label="DRAS-5", color=DRAS_BLUE, edgecolor="#2471a3", linewidth=0.5)
    for bar, h in zip(bars, dras):
        ax.text(bar.get_x() + bar.get_width() / 2, max(h, 0) + 0.5,
                f"{h:.1f}", ha="center", va="bottom", fontsize=6,
                color=DRAS_BLUE, fontweight="bold")

    ax.set_xticks(x)
    ax.set_xticklabels(types)
    ax.set_ylabel("Missed Escalation Rate (%)")
    ax.set_ylim(0, max(news2 + mews) * 1.2)
    ax.legend(loc="upper left", framealpha=0.95, fontsize=7)
    ax.set_title(
        "MER by Trajectory Type: DRAS-5 = 0% (structural C1 guarantee, seed 42)",
        fontsize=9,
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
    label_map = {"monotonic": "Monotonic", "oscillating": "Oscillating",
                 "spike_emergency": "Spike-emerg.", "spike_critical": "Spike-crit."}
    types = [label_map.get(r["trajectory_type"], r["trajectory_type"]) for r in rows]
    dras_no_c5 = [float(r["oer_no_c5_pct"]) for r in rows]
    dras_full = [float(r["oer_with_c5_pct"]) for r in rows]
    types.append("Overall")
    dras_no_c5.append(round(sum(dras_no_c5) / len(dras_no_c5), 2))
    dras_full.append(round(sum(dras_full) / len(dras_full), 2))

    fig, ax = plt.subplots(figsize=(DOUBLE_COL, 2.8))
    x = np.arange(len(types))
    w = 0.30
    ax.bar(
        x - w / 2, dras_no_c5, w, label="DRAS (no C5)",
        color="#e8d5b7", edgecolor="#b7950b", linewidth=0.5,
    )
    ax.bar(
        x + w / 2, dras_full, w, label="DRAS (with C5)",
        color=DRAS_BLUE, edgecolor="#2471a3", linewidth=0.5,
    )
    for i in range(len(types)):
        ax.text(
            x[i], max(dras_no_c5[i], dras_full[i]) + 1.5,
            f"{dras_full[i]:.1f}%",
            ha="center", fontsize=7, color="#333",
        )

    ax.set_xticks(x)
    ax.set_xticklabels(types)
    ax.set_ylabel("Over-Escalation Rate (%)")
    ax.set_ylim(0, max(dras_no_c5 + dras_full) * 1.25)
    ax.legend(loc="upper left", framealpha=0.95, fontsize=7)
    ax.set_title(
        "Over-Escalation Rate by Trajectory Type (seed 42); "
        "binary OER is near-identical with/without C5",
        fontsize=8.5,
        pad=6,
    )

    save(fig, "fig5_oer", outdir)


# NOTE: A "fig6_sensitivity" generator was removed for research integrity. Its OER
# and MTCS curves were typed into the script, not produced by any perturbation
# sweep (no sweep code exists in this repository) and they contradicted the
# seed-42 results in results/. The only reproducible part of the sensitivity claim
# (MER = 0% under perturbation) is structural; see REPRODUCIBILITY.md.


# =====================================================================
# FIGURE 7: C5 Rejection Breakdown (Table 8)
# =====================================================================
def fig7_c5_rejection(outdir: Path):
    # Driven by results/c5_outcomes.csv (scripts/run_all.py, seed 42).
    rows = {r["reason"]: int(r["count"]) for r in _read_csv("c5_outcomes.csv")}
    order = [
        ("granted", "Granted", DRAS_GREEN),
        ("denied_decay", "Decay\nnot sust.", DRAS_RED),
        ("denied_cooling", "Cooling\nincompl.", DRAS_ORANGE),
        ("denied_approval", "Single\napproval", DRAS_GRAY),
    ]
    cats = [lbl for _, lbl, _ in order]
    sizes = [rows.get(k, 0) for k, _, _ in order]
    colors = [c for _, _, c in order]
    total = sum(sizes)

    fig, ax = plt.subplots(figsize=(DOUBLE_COL, 3.0))
    bars = ax.barh(cats, sizes, color=colors, edgecolor="#555", linewidth=0.4)
    for i, v in enumerate(sizes):
        pct = (100.0 * v / total) if total else 0.0
        ax.text(v + max(sizes) * 0.01 + 1, i, f"{v:,} ({pct:.1f}%)", va="center", fontsize=7)
    ax.set_xlabel("Count")
    ax.set_xlim(0, max(sizes) * 1.2 if max(sizes) else 1)
    ax.set_title(
        f"C5 De-escalation Request Outcomes (n = {total:,}, seed 42): "
        "0 granted under the committed model",
        fontsize=8.5,
    )
    ax.invert_yaxis()

    plt.tight_layout()
    save(fig, "fig7_c5_rejection", outdir)


# NOTE: A "fig8_3d_sensitivity" generator was removed for research integrity. The
# 3D surface was produced from a typed-in analytical OER model (constant 3.6 plus
# linear terms), not from measured data; no perturbation/decay sweep exists in
# this repository. See REPRODUCIBILITY.md.


# =====================================================================
# FIGURE 9: 3D State Trajectory Visualization
# =====================================================================
def fig9_3d_trajectory(outdir: Path):
    fig = plt.figure(figsize=(DOUBLE_COL, 4.0))
    ax = fig.add_subplot(111, projection="3d")

    # Add parent to path for simulator import
    sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
    from dras5.simulator import generate_trajectory

    # Generate three trajectory types
    traj_types = [
        ("monotonic", "Monotonic", DRAS_BLUE, "-"),
        ("oscillating", "Oscillating", DRAS_ORANGE, "--"),
        ("spike_recover", "Spike-recover", DRAS_RED, "-."),
    ]

    for i, (tt, label, color, ls) in enumerate(traj_types):
        traj = generate_trajectory(ttype=tt, n_steps=80, dt=10, seed=42)
        t_vals = [p.t for p in traj]
        rho_vals = [p.rho for p in traj]
        state_vals = [int(p.system_state) for p in traj]

        ax.plot(
            t_vals,
            rho_vals,
            state_vals,
            color=color,
            lw=1.2,
            ls=ls,
            label=label,
            alpha=0.85,
        )

    # State level planes
    for level, name, color in [
        (1, "S1", "#2ecc71"),
        (3, "S3", "#e67e22"),
        (5, "S5", "#1a1a2e"),
    ]:
        ax.plot(
            [0, 800], [0, 0], [level, level], color=color, lw=0.4, ls=":", alpha=0.4
        )

    ax.set_xlabel("Time (s)", fontsize=8, labelpad=8)
    ax.set_ylabel("Risk score", fontsize=8, labelpad=8)
    ax.set_zlabel("State level", fontsize=8, labelpad=6)
    ax.set_zticks([1, 2, 3, 4, 5])
    ax.set_zticklabels(["S1", "S2", "S3", "S4", "S5"])
    ax.set_title(
        "3D Trajectory Visualization: Risk, Time, and State", fontsize=9, pad=10
    )
    ax.view_init(elev=20, azim=-60)
    ax.tick_params(labelsize=7)
    ax.legend(loc="upper left", fontsize=7, framealpha=0.9)

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
    print(f"Output: {outdir.resolve()}\n")

    generators = [
        ("Fig 1", "State machine diagram", fig1_state_machine),
        ("Fig 2", "Constraint pipeline", fig2_pipeline),
        ("Fig 3", "C5 exponential decay (S4 params)", fig3_c5_decay),
        ("Fig 3b", "Multi-state decay comparison", fig3b_decay_comparison),
        ("Fig 4", "MER bar chart (from results/mer_by_type.csv)", fig4_mer),
        ("Fig 5", "OER comparison (from results/oer_by_type.csv)", fig5_oer),
        # Removed for research integrity (their generators are gone and the stale
        # PNG/PDF outputs deleted): Fig 6 / Fig 8 (threshold + 3D sensitivity:
        # hardcoded, no sweep code) and Fig 10 / Fig 11 / Fig 12 (performance,
        # regulatory, compliance dashboards: values typed in, not sourced from
        # results/; Fig 10's throughput even contradicted latency.csv). See
        # REPRODUCIBILITY.md and README.md.
        ("Fig 7", "C5 outcomes breakdown (from results/c5_outcomes.csv)", fig7_c5_rejection),
        ("Fig 9", "3D trajectory visualization", fig9_3d_trajectory),
    ]

    for label, desc, fn in generators:
        print(f"{label}: {desc}")
        fn(outdir)

    print(f"\nDone. {len(generators)} figures generated in {outdir.resolve()}")


if __name__ == "__main__":
    main()
