"""The scan pipeline: photos + reference -> feature tree -> CadQuery -> STEP / STL + report."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from . import dfm
from .calibration import parse_reference
from .codegen import build, write_model
from .describe import describe_classical
from .export import tessellate
from .features import FeatureTree, snap_tree
from .ingest import load_photos
from .measure import MeasurementError


@dataclass
class ScanResult:
    out_dir: Path
    tree: FeatureTree
    measured: FeatureTree | None
    report: dfm.DfmReport
    files: dict[str, Path]
    scales: dict[str, Any] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    describer: str = "classical"


def _has_claude_credentials() -> bool:
    return bool(os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN"))


def materialise(tree: FeatureTree, out_dir: Path, min_wall: float = 1.2, max_overhang: float = 45.0, preview: bool = True):
    """Write model files, build the solid, export it, check it and draw a preview."""
    import cadquery as cq

    files = write_model(tree, out_dir)
    part = build(tree)
    files["step"], files["stl"] = out_dir / "part.step", out_dir / "part.stl"
    cq.exporters.export(part, str(files["step"]))
    cq.exporters.export(part, str(files["stl"]), tolerance=0.01, angularTolerance=0.1)
    mesh = tessellate(part)
    report = dfm.check(tree, mesh, min_wall=min_wall, max_overhang_deg=max_overhang)
    if preview:
        try:
            from .render import preview as draw_preview

            files["preview"] = out_dir / "preview.png"
            draw_preview(mesh[0], mesh[1], files["preview"])
        except Exception as exc:  # a preview is a nicety; never fail a scan over it
            files.pop("preview", None)
            report.warnings.append(f"preview skipped: {exc}")
    return files, report


def _write_report(result: ScanResult, reference_raw: str) -> Path:
    lines = ["# Caliper scan report", "", f"Reference: `{reference_raw}`. Describer: `{result.describer}`.", ""]
    lines += ["## Feature tree", "", "```", result.tree.describe(), "```", ""]
    if result.scales:
        lines += ["## Scale calibration", "", "| View | mm per pixel | Source |", "|---|---|---|"]
        for view, s in result.scales.items():
            lines.append(f"| {view} | {s['mm_per_px']:.5f} | {s['source']} |")
        lines.append("")
    if result.measured is not None and result.tree.meta.get("snapped_to_mm"):
        lines += ["## Measured vs design-intent values", "", "| Parameter | Measured (mm) | Snapped (mm) |", "|---|---|---|"]
        snapped = result.tree.params()
        for key, value in result.measured.params().items():
            if key in snapped:
                lines.append(f"| {key} | {value:.3f} | {snapped[key]:g} |")
        lines.append("")
    lines.append(result.report.to_markdown())
    if result.warnings:
        lines += ["## Warnings", ""] + [f"- {w}" for w in result.warnings] + [""]
    if result.tree.notes:
        lines += ["## Notes from the describer", "", result.tree.notes, ""]
    path = result.out_dir / "report.md"
    path.write_text("\n".join(lines), encoding="utf-8")
    (result.out_dir / "report.json").write_text(json.dumps(result.report.to_dict(), indent=2) + "\n", encoding="utf-8")
    return path


def scan(
    photos_dir: str | Path,
    ref: str,
    out_dir: str | Path,
    describer: str = "auto",
    snap: float = 0.5,
    min_wall: float = 1.2,
    max_overhang: float = 45.0,
    preview: bool = True,
) -> ScanResult:
    """Run the whole pipeline. ``describer`` is ``auto``, ``claude`` or ``classical``."""
    if describer not in ("auto", "claude", "classical"):
        raise ValueError("describer must be auto, claude or classical")
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    reference = parse_reference(ref)
    photos = load_photos(photos_dir)
    warnings: list[str] = []
    scales: dict[str, Any] = {}

    measured: FeatureTree | None = None
    classical_error: Exception | None = None
    try:
        description = describe_classical(photos, reference)
        measured, scales = description.tree, description.scales
        warnings += description.warnings
    except (MeasurementError, ValueError) as exc:
        classical_error = exc

    use_claude = describer == "claude" or (describer == "auto" and _has_claude_credentials())
    if use_claude:
        from .vision import MODEL, describe_with_claude

        if classical_error is not None:
            warnings.append(f"classical measurement failed ({classical_error}); dimensions are Claude's estimates alone")
        raw_tree = describe_with_claude(photos, reference, measured)
        used = MODEL
    else:
        if measured is None:
            raise MeasurementError(
                f"{classical_error} - the offline describer needs clean, square-on photos; "
                "set ANTHROPIC_API_KEY to use the Claude describer instead"
            )
        if describer == "auto":
            warnings.append("ANTHROPIC_API_KEY not set: used the offline classical describer")
        raw_tree = measured
        used = "classical"

    tree = snap_tree(raw_tree, snap) if snap > 0 else raw_tree
    (out / "measured.json").write_text(json.dumps(raw_tree.to_dict(), indent=2) + "\n", encoding="utf-8")
    files, report = materialise(tree, out, min_wall, max_overhang, preview)
    files["measured"] = out / "measured.json"
    files["calibration"] = out / "calibration.json"
    files["calibration"].write_text(
        json.dumps({"reference": {"raw": reference.raw, "kind": reference.kind, "value_mm": reference.value_mm}, "scales": scales, "describer": used}, indent=2) + "\n",
        encoding="utf-8",
    )
    result = ScanResult(out_dir=out, tree=tree, measured=raw_tree, report=report, files=files, scales=scales, warnings=warnings, describer=used)
    files["report"] = _write_report(result, reference.raw)
    return result


def rebuild(part_dir: str | Path, min_wall: float = 1.2, max_overhang: float = 45.0, preview: bool = True) -> ScanResult:
    """Re-read ``params.json`` after a manual edit and regenerate everything."""
    out = Path(part_dir)
    tree = FeatureTree.load(out / "feature_tree.json")
    params = json.loads((out / "params.json").read_text(encoding="utf-8"))
    tree = tree.with_params(params)
    tree.meta["edited"] = True
    files, report = materialise(tree, out, min_wall, max_overhang, preview)
    result = ScanResult(out_dir=out, tree=tree, measured=None, report=report, files=files, describer=str(tree.meta.get("describer", "edited")))
    files["report"] = _write_report(result, "params.json (rebuild)")
    return result
