"""A basic manufacturability check for FDM printing.

Two questions, answered conservatively:

* **Walls** - is any wall, web or ligament thinner than the printer can lay down?
  Read straight off the feature tree, so the answer names the feature at fault.
* **Overhangs** - how much surface faces down at more than the overhang angle,
  for each of the six axis-aligned print orientations? Read off the mesh.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

from .features import FeatureTree

ORIENTATIONS = {
    "+z up (as modelled)": (0, 0, 1),
    "-z up (flipped)": (0, 0, -1),
    "+y up": (0, 1, 0),
    "-y up": (0, -1, 0),
    "+x up": (1, 0, 0),
    "-x up": (-1, 0, 0),
}


@dataclass
class Wall:
    name: str
    thickness: float
    ok: bool


@dataclass
class Overhang:
    orientation: str
    area_mm2: float
    fraction: float
    bed_contact_mm2: float


@dataclass
class DfmReport:
    min_wall: float
    max_overhang_deg: float
    walls: list[Wall] = field(default_factory=list)
    overhangs: list[Overhang] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def thinnest(self) -> Wall | None:
        return min(self.walls, key=lambda w: w.thickness) if self.walls else None

    @property
    def best_orientation(self) -> Overhang | None:
        if not self.overhangs:
            return None
        return min(self.overhangs, key=lambda o: (round(o.area_mm2, 1), -o.bed_contact_mm2))

    @property
    def ok(self) -> bool:
        return all(w.ok for w in self.walls)

    def to_dict(self) -> dict:
        best = self.best_orientation
        return {
            "ok": self.ok,
            "min_wall_mm": self.min_wall,
            "max_overhang_deg": self.max_overhang_deg,
            "walls": [w.__dict__ for w in self.walls],
            "overhangs": [o.__dict__ for o in self.overhangs],
            "best_orientation": best.orientation if best else None,
            "warnings": self.warnings,
        }

    def to_markdown(self) -> str:
        lines = ["## Manufacturability (FDM)", ""]
        lines.append(f"Minimum wall: {self.min_wall:g} mm. Overhang limit: {self.max_overhang_deg:g} degrees from vertical.")
        lines += ["", "| Wall / web | Thickness (mm) | OK |", "|---|---|---|"]
        for w in sorted(self.walls, key=lambda w: w.thickness):
            lines.append(f"| {w.name} | {w.thickness:.2f} | {'yes' if w.ok else 'NO'} |")
        if self.overhangs:
            lines += ["", "| Print orientation | Unsupported overhang (mm2) | Share of surface | Bed contact (mm2) |", "|---|---|---|---|"]
            for o in sorted(self.overhangs, key=lambda o: o.area_mm2):
                lines.append(f"| {o.orientation} | {o.area_mm2:.1f} | {o.fraction * 100:.1f}% | {o.bed_contact_mm2:.0f} |")
            lines += ["", f"Suggested orientation: **{self.best_orientation.orientation}**."]
        for warning in self.warnings:
            lines.append(f"- Warning: {warning}")
        return "\n".join(lines) + "\n"


def wall_thicknesses(tree: FeatureTree) -> list[tuple[str, float]]:
    """Every wall, web and edge margin the feature tree implies."""
    base = tree.base
    L, W, T = (base.params[k] for k in ("length", "width", "thickness"))
    walls: list[tuple[str, float]] = [(f"{base.id} thickness", T)]
    flanges = tree.of_type("flange")
    for fl in flanges:
        walls.append((f"{fl.id} thickness", fl.params["thickness"]))

    def base_margin(x: float, y: float, rx: float, ry: float) -> float:
        return min(L / 2 - abs(x) - rx, W / 2 - abs(y) - ry)

    round_cuts: list[tuple[str, str, float, float, float]] = []  # id, parent, a, b, radius
    for h in tree.of_type("hole"):
        parent = tree.get(h.parent)
        r = h.params["diameter"] / 2
        if parent.type == "flange":
            run = L if parent.params["edge"] in ("+y", "-y") else W
            u, v = h.params["u"], h.params["v"]
            margin = min(run / 2 - abs(u) - r, parent.params["height"] - v - r, v - r)
            walls.append((f"{h.id} to {parent.id} edge", margin))
            round_cuts.append((h.id, parent.id, u, v, r))
        else:
            walls.append((f"{h.id} to plate edge", base_margin(h.params["x"], h.params["y"], r, r)))
            round_cuts.append((h.id, parent.id, h.params["x"], h.params["y"], r))
    for s in tree.of_type("slot"):
        a = math.radians(s.params["angle"])
        half_l, half_w = s.params["length"] / 2, s.params["width"] / 2
        rx = abs(math.cos(a)) * half_l + abs(math.sin(a)) * half_w
        ry = abs(math.sin(a)) * half_l + abs(math.cos(a)) * half_w
        walls.append((f"{s.id} to plate edge", base_margin(s.params["x"], s.params["y"], rx, ry)))
        # Conservative: treat the slot as its bounding circle when checking webs.
        round_cuts.append((s.id, base.id, s.params["x"], s.params["y"], half_l))
    for b in tree.of_type("boss"):
        if b.params.get("bore", 0) > 0:
            walls.append((f"{b.id} wall", (b.params["diameter"] - b.params["bore"]) / 2))
    for i, (id_a, par_a, xa, ya, ra) in enumerate(round_cuts):
        for id_b, par_b, xb, yb, rb in round_cuts[i + 1 :]:
            if par_a == par_b:
                walls.append((f"web {id_a} to {id_b}", math.hypot(xa - xb, ya - yb) - ra - rb))
    return walls


def overhangs(vertices: np.ndarray, triangles: np.ndarray, max_overhang_deg: float = 45.0) -> list[Overhang]:
    """Down-facing area beyond the overhang limit, per axis-aligned orientation."""
    a, b, c = (vertices[triangles[:, i]] for i in range(3))
    cross = np.cross(b - a, c - a)
    area = np.linalg.norm(cross, axis=1) / 2
    keep = area > 1e-12
    normals = cross[keep] / (2 * area[keep, None])
    area, centroids, tri_v = area[keep], (a[keep] + b[keep] + c[keep]) / 3, np.stack([a[keep], b[keep], c[keep]], axis=1)
    total = float(area.sum())
    # A face is an unsupported overhang when it faces down by more than the limit
    # measured from vertical, i.e. normal . down > cos(90 - limit) ... expressed from vertical:
    threshold = math.cos(math.radians(90.0 - max_overhang_deg))
    out = []
    for name, up in ORIENTATIONS.items():
        up_v = np.array(up, dtype=float)
        heights = tri_v @ up_v  # (M, 3)
        bed = heights.min()
        on_bed = (heights.max(axis=1) - bed) < 1e-3
        facing_down = (normals @ -up_v) > threshold + 1e-9
        bad = facing_down & ~on_bed
        out.append(
            Overhang(
                orientation=name,
                area_mm2=float(area[bad].sum()),
                fraction=float(area[bad].sum() / total) if total else 0.0,
                bed_contact_mm2=float(area[on_bed & facing_down].sum()),
            )
        )
    del centroids
    return out


def check(
    tree: FeatureTree,
    mesh: tuple[np.ndarray, np.ndarray] | None = None,
    min_wall: float = 1.2,
    max_overhang_deg: float = 45.0,
) -> DfmReport:
    report = DfmReport(min_wall=min_wall, max_overhang_deg=max_overhang_deg)
    for name, thickness in wall_thicknesses(tree):
        report.walls.append(Wall(name=name, thickness=round(thickness, 3), ok=thickness >= min_wall))
        if thickness <= 0:
            report.warnings.append(f"{name}: features overlap or break out of the part ({thickness:.2f} mm)")
    for h in tree.of_type("hole"):
        if h.params["diameter"] < 2.0:
            report.warnings.append(f"{h.id}: holes under 2 mm usually print closed; drill after printing")
    if mesh is not None:
        report.overhangs = overhangs(mesh[0], mesh[1], max_overhang_deg)
    return report
