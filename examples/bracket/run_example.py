"""Synthetic benchmark: render photos of a known bracket, run caliper, compare with the truth.

    python examples/bracket/run_example.py            # offline classical describer
    python examples/bracket/run_example.py --claude   # Claude describer (needs ANTHROPIC_API_KEY)

Writes ``out/`` (what ``caliper scan`` produces) plus ``accuracy.json`` and ``accuracy.md``.
"""

import argparse
import json
import statistics
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from caliper.features import FeatureTree  # noqa: E402
from caliper.pipeline import scan  # noqa: E402
from ground_truth import TRUTH  # noqa: E402
from render_photos import main as render_photos  # noqa: E402

REFERENCE = "hole spacing 40mm"

LABELS = {
    "length": "Plate length",
    "width": "Plate width",
    "thickness": "Plate thickness",
    "corner_radius": "Corner radius",
    "hole_diameter": "Base hole diameter",
    "hole_spacing": "Base hole spacing (reference)",
    "hole_y": "Base hole offset",
    "slot_length": "Slot length",
    "slot_width": "Slot width",
    "slot_y": "Slot offset",
    "flange_height": "Flange height",
    "flange_thickness": "Flange thickness",
    "flange_hole_diameter": "Flange hole diameter",
    "flange_hole_spacing": "Flange hole spacing",
    "flange_hole_height": "Flange hole height",
}


def extract(tree: FeatureTree) -> dict[str, float]:
    """Read the same fifteen dimensions off a feature tree that TRUTH lists."""
    p = tree.params()
    mean = statistics.mean
    return {
        "length": p["base.length"],
        "width": p["base.width"],
        "thickness": p["base.thickness"],
        "corner_radius": p["fillet.radius"],
        "hole_diameter": mean([p["h1.diameter"], p["h2.diameter"]]),
        "hole_spacing": abs(p["h2.x"] - p["h1.x"]),
        "hole_y": mean([p["h1.y"], p["h2.y"]]),
        "slot_length": p["slot1.length"],
        "slot_width": p["slot1.width"],
        "slot_y": p["slot1.y"],
        "flange_height": p["flange.height"],
        "flange_thickness": p["flange.thickness"],
        "flange_hole_diameter": mean([p["fh1.diameter"], p["fh2.diameter"]]),
        "flange_hole_spacing": abs(p["fh2.u"] - p["fh1.u"]),
        "flange_hole_height": mean([p["fh1.v"], p["fh2.v"]]),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--claude", action="store_true", help="use the Claude describer instead of the offline one")
    parser.add_argument("--keep-photos", action="store_true", help="do not re-render the photos")
    args = parser.parse_args()

    if not args.keep_photos or not (HERE / "photos" / "top.jpg").exists():
        render_photos(HERE / "photos")
    result = scan(HERE / "photos", REFERENCE, HERE / "out", describer="claude" if args.claude else "classical", snap=0.5)

    measured = extract(result.measured)
    snapped = extract(result.tree)
    rows = []
    for key, truth in TRUTH.items():
        rows.append(
            {
                "key": key,
                "label": LABELS[key],
                "truth_mm": truth,
                "measured_mm": round(measured[key], 3),
                "error_mm": round(measured[key] - truth, 3),
                "error_pct": round((measured[key] - truth) / abs(truth) * 100, 2),
                "snapped_mm": round(snapped[key], 3),
                "snapped_error_mm": round(snapped[key] - truth, 3),
                "is_reference": key == "hole_spacing",
            }
        )
    scored = [r for r in rows if not r["is_reference"]]
    summary = {
        "describer": result.describer,
        "reference": REFERENCE,
        "dimensions_scored": len(scored),
        "mean_abs_error_mm": round(statistics.mean(abs(r["error_mm"]) for r in scored), 3),
        "max_abs_error_mm": round(max(abs(r["error_mm"]) for r in scored), 3),
        "mean_abs_error_pct": round(statistics.mean(abs(r["error_pct"]) for r in scored), 2),
        "max_abs_error_pct": round(max(abs(r["error_pct"]) for r in scored), 2),
        "snapped_exact": sum(1 for r in scored if abs(r["snapped_error_mm"]) < 1e-6),
        "snapped_mean_abs_error_mm": round(statistics.mean(abs(r["snapped_error_mm"]) for r in scored), 3),
    }
    (HERE / "accuracy.json").write_text(json.dumps({"summary": summary, "rows": rows}, indent=2) + "\n", encoding="utf-8")

    lines = ["| Dimension | True (mm) | Measured (mm) | Error (mm) | Error | After snap (mm) |", "|---|---:|---:|---:|---:|---:|"]
    for r in rows:
        note = " *" if r["is_reference"] else ""
        lines.append(
            f"| {r['label'].replace(' (reference)', '')}{note} | {r['truth_mm']:g} | {r['measured_mm']:.2f} | "
            f"{r['error_mm']:+.2f} | {r['error_pct']:+.1f}% | {r['snapped_mm']:g} |"
        )
    table = "\n".join(lines)
    (HERE / "accuracy.md").write_text(table + "\n", encoding="utf-8")
    print(table)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
