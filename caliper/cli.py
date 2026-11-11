"""Command line: ``caliper scan photos/ --ref "hole spacing 40mm" --out part/``."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


def _print_result(result) -> None:
    print(f"\nFeature tree ({result.describer}):")
    for line in result.tree.describe().splitlines():
        print("  " + line)
    thinnest = result.report.thinnest
    best = result.report.best_orientation
    print("\nManufacturability:")
    if thinnest:
        state = "ok" if thinnest.ok else f"BELOW the {result.report.min_wall:g} mm minimum"
        print(f"  thinnest wall: {thinnest.thickness:.2f} mm ({thinnest.name}) - {state}")
    if best:
        print(f"  best print orientation: {best.orientation}, {best.area_mm2:.1f} mm2 of unsupported overhang")
    for warning in [*result.warnings, *result.report.warnings]:
        print(f"  warning: {warning}")
    print("\nWrote:")
    for path in sorted(set(result.files.values())):
        print(f"  {path}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="caliper", description="Photos plus one known measurement in, parametric CAD out.")
    sub = parser.add_subparsers(dest="command", required=True)

    scan = sub.add_parser("scan", help="turn 1-4 photos into a parametric model")
    scan.add_argument("photos", help="folder with 1-4 photos (name them top/side/front for best results)")
    scan.add_argument("--ref", required=True, help='one known measurement, e.g. "hole spacing 40mm" or "marker 30mm"')
    scan.add_argument("--out", default="part", help="output folder (default: part/)")
    scan.add_argument("--describer", choices=["auto", "claude", "classical"], default="auto", help="auto uses Claude when ANTHROPIC_API_KEY is set")
    scan.add_argument("--snap", type=float, default=0.5, help="snap dimensions to this grid in mm; 0 keeps raw measurements (default 0.5)")
    scan.add_argument("--min-wall", type=float, default=1.2, help="minimum printable wall in mm (default 1.2)")
    scan.add_argument("--max-overhang", type=float, default=45.0, help="overhang limit in degrees from vertical (default 45)")
    scan.add_argument("--no-preview", action="store_true", help="skip preview.png")

    rebuild = sub.add_parser("rebuild", help="regenerate STEP/STL after editing params.json")
    rebuild.add_argument("part", help="folder written by caliper scan")
    rebuild.add_argument("--min-wall", type=float, default=1.2)
    rebuild.add_argument("--max-overhang", type=float, default=45.0)
    rebuild.add_argument("--no-preview", action="store_true")

    marker = sub.add_parser("marker", help="write a printable ArUco marker PNG")
    marker.add_argument("--out", default="marker.png")
    marker.add_argument("--id", type=int, default=0)
    marker.add_argument("--px", type=int, default=800)

    args = parser.parse_args(argv)
    try:
        if args.command == "scan":
            from .pipeline import scan as run_scan

            result = run_scan(args.photos, args.ref, args.out, args.describer, args.snap, args.min_wall, args.max_overhang, not args.no_preview)
            _print_result(result)
            return 0 if result.report.ok else 2
        if args.command == "rebuild":
            from .pipeline import rebuild as run_rebuild

            result = run_rebuild(args.part, args.min_wall, args.max_overhang, not args.no_preview)
            _print_result(result)
            return 0 if result.report.ok else 2
        if args.command == "marker":
            import cv2

            from .calibration import draw_marker

            cv2.imwrite(str(Path(args.out)), draw_marker(args.id, args.px))
            print(f"wrote {args.out}: print it, measure the black square's side, and pass --ref \"marker <side>mm\"")
            return 0
    except Exception as exc:  # surface a clean one-line error to the terminal
        print(f"caliper: error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
