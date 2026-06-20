"""Create DRAS-5 curated manuscript figure manifest and visual QA sheet."""

from __future__ import annotations

import argparse
import csv
from datetime import datetime
from pathlib import Path

from PIL import Image, ImageDraw


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_FIGURE_DIR = ROOT / "figures"
DEFAULT_MANIFEST = ROOT / "FIGURE_MANIFEST.csv"
DPI = 300

FIGURES = [
    {
        "figure_id": "DRAS5-F1",
        "stem": "fig1_state_machine",
        "role": "manuscript",
        "caption": "DRAS-5 state machine with five acuity states, thresholds, and bidirectional transitions.",
        "article_section": "State-machine architecture",
    },
    {
        "figure_id": "DRAS5-F2",
        "stem": "fig2_pipeline",
        "role": "manuscript",
        "caption": "DRAS-5 processing pipeline from risk estimation to constrained state update and audit logging.",
        "article_section": "System pipeline",
    },
    {
        "figure_id": "DRAS5-F3",
        "stem": "fig4_mer",
        "role": "manuscript",
        "caption": "Missed-escalation rate by trajectory type: DRAS-5 flat at 0% (structural C1 guarantee) beside the stateless NEWS2/MEWS baselines. Driven by results/mer_by_type.csv.",
        "article_section": "Missed-escalation results",
    },
    {
        "figure_id": "DRAS5-F4",
        "stem": "fig5_oer",
        "role": "manuscript",
        "caption": "Over-escalation rate with and without C5; the two series coincide because C5 grants nothing on this regime. Driven by results/oer_by_type.csv.",
        "article_section": "Over-escalation results",
    },
    {
        "figure_id": "DRAS5-F5",
        "stem": "fig3_c5_decay",
        "role": "supplementary",
        "caption": "C5 de-escalation decay behavior supporting constrained risk reduction.",
        "article_section": "Supplementary governance analysis",
    },
    {
        "figure_id": "DRAS5-F6",
        "stem": "fig7_c5_rejection",
        "role": "supplementary",
        "caption": "C5 de-escalation request outcomes, with all requests denied for an incomplete cooling window. Driven by results/c5_outcomes.csv.",
        "article_section": "Supplementary governance analysis",
    },
]


def write_manifest(figure_dir: Path, manifest_path: Path) -> None:
    fieldnames = [
        "figure_id",
        "role",
        "png",
        "pdf",
        "source_script",
        "source_data",
        "caption",
        "article_section",
        "generated_at",
        "dpi",
    ]
    generated_at = datetime.now().isoformat(timespec="seconds")
    with manifest_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for item in FIGURES:
            png_path = figure_dir / f"{item['stem']}.png"
            pdf_path = figure_dir / f"{item['stem']}.pdf"
            if not png_path.exists() or not pdf_path.exists():
                raise FileNotFoundError(f"Missing figure pair for {item['stem']}")
            writer.writerow(
                {
                    "figure_id": item["figure_id"],
                    "role": item["role"],
                    "png": str(png_path.relative_to(ROOT)),
                    "pdf": str(pdf_path.relative_to(ROOT)),
                    "source_script": "scripts/generate_figures.py",
                    "source_data": "scripts/generate_figures.py",
                    "caption": item["caption"],
                    "article_section": item["article_section"],
                    "generated_at": generated_at,
                    "dpi": str(DPI),
                }
            )


def make_contact_sheet(figure_dir: Path) -> Path:
    pngs = [figure_dir / f"{item['stem']}.png" for item in FIGURES]
    thumbs = []
    for path in pngs:
        with Image.open(path) as image:
            thumb = image.convert("RGB")
            original = thumb.size
            thumb.thumbnail((500, 320), Image.Resampling.LANCZOS)
            canvas = Image.new("RGB", (540, 395), "white")
            canvas.paste(thumb, ((540 - thumb.width) // 2, 42))
            draw = ImageDraw.Draw(canvas)
            draw.text((8, 8), path.name, fill="black")
            draw.text((8, 370), f"{original[0]}x{original[1]}", fill="black")
            thumbs.append(canvas)

    cols = 2
    rows = (len(thumbs) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * 540, rows * 395), "white")
    for index, thumb in enumerate(thumbs):
        sheet.paste(thumb, ((index % cols) * 540, (index // cols) * 395))

    sheet_path = figure_dir / "visual_qa_contact_sheet.png"
    sheet.save(sheet_path)
    return sheet_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Create DRAS-5 manuscript figure manifest")
    parser.add_argument("--figure-dir", type=Path, default=DEFAULT_FIGURE_DIR)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    args = parser.parse_args()

    write_manifest(args.figure_dir, args.manifest)
    sheet_path = make_contact_sheet(args.figure_dir)

    print(f"Wrote manifest: {args.manifest}")
    print(f"Wrote visual QA contact sheet: {sheet_path}")


if __name__ == "__main__":
    main()
