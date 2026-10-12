"""Figure: end-of-episode miss rate and over-escalation for every system (results/recoverable_baselines.csv).

Panel (a): MER_end (%) by trajectory family. Panel (b): overall binary OER (%) and end-of-episode
excess (levels). Output: figures/fig_systems_mer_oer.pdf (+ .png at 300 dpi).
Usage: python scripts/fig_recoverable.py
"""
from __future__ import annotations

import csv
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

REPO = Path(__file__).resolve().parents[1]
SYSTEMS = [("NEWS2 (every 2nd)", "NEWS2 (stateless, every 2nd)"),
           ("Max-hold", "Max-hold"),
           ("Hysteresis", "Hysteresis"),
           ("Timed-release max-hold", "Timed-release max-hold"),
           ("Decayed max", "Decayed max"),
           ("DRAS-5 (no C5)", "DRAS-5 without C5"),
           ("DRAS-5 (full)", "DRAS-5 (full)")]
FAMS = [("monotonic", "Monotonic"), ("oscillating", "Oscillating"),
        ("spike_emergency", "Spike to\nemergency"), ("spike_critical", "Spike to\ncritical"),
        ("OVERALL", "Overall")]
COLORS = ["#999999", "#56B4E9", "#0072B2", "#CC79A7", "#F0E442", "#E69F00", "#009E73"]


def main() -> None:
    rows = list(csv.DictReader(open(REPO / "results" / "recoverable_baselines.csv", encoding="utf-8")))
    get = {(r["system"], r["trajectory_type"]): r for r in rows}
    plt.rcParams.update({"font.size": 9, "font.family": "DejaVu Sans"})
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(7.5, 7.2), gridspec_kw={"height_ratios": [1.15, 1]})
    x = np.arange(len(FAMS))
    w = 0.8 / len(SYSTEMS)
    for k, ((key, label), c) in enumerate(zip(SYSTEMS, COLORS)):
        vals = [float(get[(key, f)]["mer_end_pct"]) for f, _ in FAMS]
        ax1.bar(x - 0.4 + w * (k + 0.5), vals, w, color=c, edgecolor="black", linewidth=0.4, label=label)
    ax1.set_xticks(x, [lab for _, lab in FAMS])
    ax1.set_ylabel(r"MER$_{\mathrm{end}}$ (%)")
    ax1.set_ylim(0, 105)
    ax1.title.set_y(1.3)
    ax1.set_title("(a) End-of-episode miss rate by family", fontsize=9, loc="left")
    ax1.grid(axis="y", lw=0.3, alpha=0.5)
    ax1.legend(fontsize=7.5, ncol=3, loc="lower center", bbox_to_anchor=(0.45, 1.07), frameon=False)
    y = np.arange(len(SYSTEMS))
    oer = [float(get[(k, "OVERALL")]["oer_pct"]) for k, _ in SYSTEMS]
    exc = [float(get[(k, "OVERALL")]["end_excess_levels"]) for k, _ in SYSTEMS]
    ax2.barh(y, oer, color=COLORS, edgecolor="black", linewidth=0.4)
    for yi, (o, e) in enumerate(zip(oer, exc)):
        ax2.text(o + 1, yi, f"{o:.1f}%  | excess {e:.2f}", va="center", fontsize=7.5)
    ax2.set_yticks(y, [lab for _, lab in SYSTEMS])
    ax2.invert_yaxis()
    ax2.set_xlim(0, 125)
    ax2.set_xlabel("Binary over-escalation, OER (%)")
    ax2.set_title("(b) Overall OER and end-of-episode excess (levels)", fontsize=9, loc="left")
    ax2.grid(axis="x", lw=0.3, alpha=0.5)
    fig.tight_layout()
    out = REPO / "figures" / "fig_systems_mer_oer"
    fig.savefig(out.with_suffix(".pdf"))
    fig.savefig(out.with_suffix(".png"), dpi=300)
    print("wrote", out)


if __name__ == "__main__":
    main()
