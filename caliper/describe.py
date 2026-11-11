"""Classical describer: measurements in pixels + one reference -> a feature tree in mm.

Scale is established once, from the reference measurement, in whichever view
shows it. It then travels to the other views through dimensions two views
share (the plate length is visible from above and from the front; its width
from above and from the side). No view is ever scaled by guesswork.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from .calibration import Reference, chained_width, detect_marker, mm_per_px
from .features import Feature, FeatureTree
from .ingest import Photo
from .measure import MeasurementError, Opening, measure_face, read_profile, read_top

_NORMALS = {"+y": (0, 1), "-y": (0, -1), "+x": (1, 0), "-x": (-1, 0)}
# Sign of part "u" for image +x when looking at the inner face of a flange.
_FRONT_U_SIGN = {"+y": 1, "-y": -1, "+x": -1, "-x": 1}
_CORNER_SIGNS = {"tl": (-1, 1), "tr": (1, 1), "br": (1, -1), "bl": (-1, -1)}


@dataclass
class Description:
    tree: FeatureTree
    scales: dict[str, dict[str, Any]] = field(default_factory=dict)  # view -> {mm_per_px, source}
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {"scales": self.scales, "warnings": self.warnings}


def _pair_distance(openings: list[Opening]) -> float:
    """Spacing between holes: the pair when there are two, else the commonest neighbour gap."""
    pts = np.array([(o.cx, o.cy) for o in openings])
    d = np.linalg.norm(pts[:, None] - pts[None], axis=2)
    if len(pts) == 2:
        return float(d[0, 1])
    np.fill_diagonal(d, np.inf)
    return float(np.median(d.min(axis=1)))


def _by_view(photos: list[Photo]) -> dict[str, Photo]:
    return {p.view: p for p in photos}


def describe_classical(photos: list[Photo], reference: Reference, default_thickness: float = 5.0) -> Description:
    views = _by_view(photos)
    if "top" not in views:
        raise MeasurementError("the classical describer needs a top view (name a photo top.jpg)")
    warnings: list[str] = []
    scales: dict[str, dict[str, Any]] = {}

    top = read_top(views["top"].image)
    face = top.face
    edge = top.flange_edge
    round_holes = [o for o in face.openings if o.is_round]
    slots = [o for o in face.openings if not o.is_round]
    along_px, visible_px = (face.width, face.height) if edge in (None, "+y", "-y") else (face.height, face.width)

    profile = None
    if "side" in views:
        try:
            profile = read_profile(views["side"].image)
        except MeasurementError as exc:
            warnings.append(f"side view ignored: {exc}")
    front = None
    if "front" in views and edge:
        try:
            front = measure_face(views["front"].image)
        except MeasurementError as exc:
            warnings.append(f"front view ignored: {exc}")

    # ---- 1. scale of the top view from the reference ------------------------------------
    s_top: float | None = None
    s_side: float | None = None
    kind = reference.kind
    if kind == "hole_spacing" and len(round_holes) >= 2:
        s_top = mm_per_px(reference.value_mm, _pair_distance(round_holes))
        if len(round_holes) > 2:
            warnings.append("more than two holes: the reference was matched to the nearest-neighbour spacing")
    elif kind == "hole_spacing" and front is not None and len([o for o in front.openings if o.is_round]) >= 2:
        s_front = mm_per_px(reference.value_mm, _pair_distance([o for o in front.openings if o.is_round]))
        s_top = front.width * s_front / along_px
        warnings.append("reference hole spacing was taken from the flange holes in the front view")
    elif kind == "hole_diameter" and round_holes:
        s_top = mm_per_px(reference.value_mm, max(o.diameter for o in round_holes))
    elif kind == "length":
        s_top = mm_per_px(reference.value_mm, face.width if edge not in ("+x", "-x") else face.width + top.flange_strip_px)
    elif kind == "width":
        if edge in ("+y", "-y") and profile is not None and profile.flange_px:
            s_side = mm_per_px(reference.value_mm, profile.width_px)
            s_top = (reference.value_mm - profile.flange_px * s_side) / visible_px
        else:
            s_top = mm_per_px(reference.value_mm, face.height)
    elif kind in ("thickness", "flange_height") and profile is not None:
        px = profile.thickness_px if kind == "thickness" else profile.height_px
        s_side = mm_per_px(reference.value_mm, px)
        hidden = (profile.flange_px or 0.0) * s_side
        s_top = (profile.width_px * s_side - hidden) / visible_px
    elif kind == "marker":
        marker = detect_marker(views["top"].image, reference.value_mm)
        if marker is None:
            raise MeasurementError("no ArUco marker found in the top view")
        s_top = marker.mm_per_px
        warnings.append("marker scale is for the surface the marker lies on; the plate top is slightly closer to the camera")
    if s_top is None:
        raise MeasurementError(f"could not find the reference {reference.raw!r} in the photos")
    scales["top"] = {"mm_per_px": s_top, "source": f"reference: {reference.raw}"}

    along = along_px * s_top
    visible = visible_px * s_top

    # ---- 2. side view: chain the scale through the plate width ----------------------------
    thickness, flange_h, flange_t = None, None, None
    across = visible
    if profile is not None:
        if profile.flange_px and edge:
            across = chained_width(visible, profile.flange_px, profile.width_px)
            s_side = s_side or across / profile.width_px
            flange_t = profile.flange_px * s_side
            flange_h = profile.height_px * s_side
        else:
            s_side = s_side or visible / profile.width_px
            if edge:
                warnings.append("top view suggests a flange but the side view shows a plain plate; flange dropped")
                edge = None
        thickness = profile.thickness_px * s_side
        scales["side"] = {"mm_per_px": s_side, "source": "chained through the plate width seen in the top view"}
    else:
        thickness = reference.value_mm if kind == "thickness" else default_thickness
        if kind != "thickness":
            warnings.append(f"no side view: plate thickness assumed to be {default_thickness:g} mm (edit base.thickness)")
        if edge:
            warnings.append("no side view: the flange cannot be measured and was left out")
            edge = None

    if edge in ("+y", "-y") or edge is None:
        length, width = along, across
    else:
        length, width = across, along

    features = [Feature("base", "base_plate", {"length": length, "width": width, "thickness": thickness})]

    # ---- 3. corner fillets ---------------------------------------------------------------
    limit = max(3.0, 0.02 * min(face.width, face.height))
    normal = _NORMALS.get(edge or "", (0, 0))
    free = [n for n, (sx, sy) in _CORNER_SIGNS.items() if not (normal[0] and sx == normal[0]) and not (normal[1] and sy == normal[1])]
    rounded = [n for n in free if face.corner_radii.get(n, 0) > limit]
    if rounded and len(rounded) == len(free):
        radius = float(np.median([face.corner_radii[n] for n in rounded])) * s_top
        features.append(Feature("fillet", "fillet", {"radius": radius, "corners": "free" if edge else "all"}, "base"))
    elif rounded:
        warnings.append("only some corners look rounded; corner fillet left out")

    if edge:
        features.append(Feature("flange", "flange", {"height": flange_h, "thickness": flange_t, "edge": edge}, "base"))

    # ---- 4. openings in the base (positions relative to the full plate centre) -----------
    cx, cy = face.center
    shift = (normal[0] * (flange_t or 0) / 2, normal[1] * (flange_t or 0) / 2)

    def to_part(o: Opening) -> tuple[float, float]:
        return (o.cx - cx) * s_top - shift[0], -(o.cy - cy) * s_top - shift[1]

    for i, o in enumerate(round_holes, 1):
        x, y = to_part(o)
        features.append(Feature(f"h{i}", "hole", {"x": x, "y": y, "diameter": o.diameter * s_top}, "base"))
    for i, o in enumerate(slots, 1):
        x, y = to_part(o)
        features.append(
            Feature(f"slot{i}", "slot", {"x": x, "y": y, "length": o.length * s_top, "width": o.width * s_top, "angle": o.angle}, "base")
        )

    # ---- 5. front view: holes in the flange, scale chained through the plate length ----------
    if edge and front is not None:
        s_front = along / front.width
        scales["front"] = {"mm_per_px": s_front, "source": "chained through the plate length seen in the top view"}
        expected = flange_h - thickness
        if abs(front.height * s_front - expected) > 0.1 * expected:
            warnings.append("front view does not match the flange height from the side view; check it shows the flange's inner face")
        fcx, _ = front.center
        bottom = front.y0 + front.height
        sign = _FRONT_U_SIGN[edge]
        holes = sorted((o for o in front.openings if o.is_round), key=lambda o: sign * o.cx)
        for i, o in enumerate(holes, 1):
            u = sign * (o.cx - fcx) * s_front
            v = thickness + (bottom - o.cy) * s_front
            features.append(Feature(f"fh{i}", "hole", {"u": u, "v": v, "diameter": o.diameter * s_front}, "flange"))
    elif edge:
        warnings.append("no front view: holes in the flange, if any, were not captured")

    for f in features:
        for k, v in f.params.items():
            if isinstance(v, float):
                f.params[k] = round(v, 3) if not math.isnan(v) else v
    tree = FeatureTree(features=features, part_type="bracket" if edge else "plate", meta={"describer": "classical"})
    return Description(tree=tree.validate(), scales=scales, warnings=warnings)
