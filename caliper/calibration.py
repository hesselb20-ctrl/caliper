"""Scale calibration: turning pixels into millimetres.

Three sources of scale are supported:

1. A reference measurement typed by the user (``"hole spacing 40mm"``): once the
   same quantity is found in a photo, ``mm_per_px = reference_mm / pixels``.
2. A printed ArUco marker of known size lying next to the part.
3. Chaining: a dimension measured in an already calibrated view (say the plate
   length) calibrates a second view that also shows it.

A scale only holds on one plane. :func:`scale_at_height` moves it to a parallel
plane when the camera distance is known (from EXIF focal length or a marker).
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass

import numpy as np

_UNIT_TO_MM = {
    "mm": 1.0,
    "millimeter": 1.0,
    "millimeters": 1.0,
    "millimetre": 1.0,
    "millimetres": 1.0,
    "cm": 10.0,
    "m": 1000.0,
    "in": 25.4,
    "inch": 25.4,
    "inches": 25.4,
    '"': 25.4,
}

# Order matters: more specific phrases first.
_KINDS: list[tuple[str, tuple[str, ...]]] = [
    ("marker", ("aruco", "marker")),
    ("hole_spacing", ("hole spacing", "hole distance", "hole pitch", "center to center", "centre to centre", "c-c", "between holes")),
    ("hole_diameter", ("hole diameter", "hole dia", "bore")),
    ("flange_height", ("flange height", "wall height", "overall height", "height", "tall")),
    ("thickness", ("thickness", "thick")),
    ("length", ("length", "long")),
    ("width", ("width", "wide")),
]

_NUMBER = re.compile(r"(-?\d+(?:[.,]\d+)?)\s*(millimet(?:er|re)s?|mm|cm|inch(?:es)?|in|m|\")?", re.IGNORECASE)


@dataclass(frozen=True)
class Reference:
    """A known real-world measurement, e.g. ``hole spacing 40mm``."""

    kind: str
    value_mm: float
    raw: str


def parse_reference(text: str) -> Reference:
    """Parse ``"hole spacing 40mm"``, ``"width 2 in"``, ``"aruco marker 30 mm"``..."""
    if not text or not text.strip():
        raise ValueError("empty reference measurement")
    lowered = text.lower()
    kind = None
    for name, phrases in _KINDS:
        if any(p in lowered for p in phrases):
            kind = name
            break
    if kind is None:
        raise ValueError(
            f"could not tell what {text!r} measures; use e.g. 'hole spacing 40mm', "
            "'length 80mm', 'width 50mm', 'thickness 5mm', 'hole diameter 6mm' or 'marker 30mm'"
        )
    matches = [m for m in _NUMBER.finditer(lowered) if m.group(1)]
    if not matches:
        raise ValueError(f"no number found in reference {text!r}")
    # Prefer a number that carries a unit; otherwise take the last number and assume mm.
    with_unit = [m for m in matches if m.group(2)]
    m = (with_unit or matches)[-1]
    value = float(m.group(1).replace(",", "."))
    unit = (m.group(2) or "mm").lower()
    value_mm = value * _UNIT_TO_MM[unit]
    if value_mm <= 0:
        raise ValueError("a reference measurement must be positive")
    return Reference(kind=kind, value_mm=value_mm, raw=text.strip())


# ---- plain scale math ---------------------------------------------------------------


def mm_per_px(reference_mm: float, reference_px: float) -> float:
    """Scale of a plane on which ``reference_mm`` spans ``reference_px`` pixels."""
    if reference_px <= 0:
        raise ValueError("reference length in pixels must be positive")
    if reference_mm <= 0:
        raise ValueError("reference length in mm must be positive")
    return reference_mm / reference_px


def focal_px_from_35mm(focal_35mm: float, image_width_px: int, image_height_px: int) -> float:
    """Focal length in pixels from the EXIF '35 mm equivalent' focal length.

    The 35 mm equivalent is defined on the frame diagonal (43.27 mm).
    """
    diagonal_px = math.hypot(image_width_px, image_height_px)
    return focal_35mm / 43.2666 * diagonal_px


def camera_distance(focal_px: float, scale_mm_per_px: float) -> float:
    """Distance from the pinhole to a fronto-parallel plane with the given scale."""
    return focal_px * scale_mm_per_px


def scale_at_height(scale_mm_per_px: float, distance_mm: float, height_mm: float) -> float:
    """Move a scale to a parallel plane ``height_mm`` closer to the camera.

    Under a pinhole camera the scale is proportional to the distance, so a plane
    that is ``height_mm`` nearer has scale ``s * (Z - h) / Z``. Ignoring this is
    the classic way to get a tall feature a few percent too big.
    """
    if distance_mm <= 0:
        raise ValueError("camera distance must be positive")
    if height_mm >= distance_mm:
        raise ValueError("the plane cannot be behind the camera")
    return scale_mm_per_px * (distance_mm - height_mm) / distance_mm


def chained_width(visible_depth_mm: float, hidden_px: float, total_px: float) -> float:
    """Total width when one view sees only part of it.

    The top view measures the visible depth of the base (the part of the plate
    not covered by the flange) in millimetres; the side view sees the whole
    width in pixels, of which ``hidden_px`` belong to the flange. Solving
    ``W = visible + hidden_px * W / total_px`` for ``W`` gives the total width
    without needing the side view's scale first.
    """
    if not 0 <= hidden_px < total_px:
        raise ValueError("hidden pixels must be smaller than the total")
    return visible_depth_mm / (1.0 - hidden_px / total_px)


def relative_error(estimate: float, truth: float) -> float:
    return (estimate - truth) / truth


# ---- ArUco marker ---------------------------------------------------------------------


@dataclass
class MarkerCalibration:
    mm_per_px: float
    corners_px: np.ndarray  # (4, 2) image coordinates, clockwise from top-left
    homography: np.ndarray  # image px -> marker-plane mm (origin at the marker's top-left corner)
    marker_id: int


def marker_scale(corners_px: np.ndarray, marker_mm: float) -> float:
    """Mean scale over the four sides of a detected square marker."""
    c = np.asarray(corners_px, dtype=float).reshape(4, 2)
    sides = np.linalg.norm(c - np.roll(c, -1, axis=0), axis=1)
    return mm_per_px(marker_mm, float(sides.mean()))


def marker_homography(corners_px: np.ndarray, marker_mm: float) -> np.ndarray:
    """Homography that maps image pixels onto the marker plane in millimetres."""
    import cv2

    src = np.asarray(corners_px, dtype=np.float32).reshape(4, 2)
    dst = np.array([[0, 0], [marker_mm, 0], [marker_mm, marker_mm], [0, marker_mm]], dtype=np.float32)
    return cv2.getPerspectiveTransform(src, dst)


def apply_homography(h: np.ndarray, points_px: np.ndarray) -> np.ndarray:
    pts = np.asarray(points_px, dtype=float).reshape(-1, 2)
    homog = np.hstack([pts, np.ones((len(pts), 1))]) @ np.asarray(h, dtype=float).T
    return homog[:, :2] / homog[:, 2:3]


def detect_marker(image_bgr: np.ndarray, marker_mm: float, dictionary: str = "DICT_4X4_50") -> MarkerCalibration | None:
    """Find one ArUco marker and return the scale and homography of its plane."""
    import cv2

    aruco = cv2.aruco
    detector = aruco.ArucoDetector(aruco.getPredefinedDictionary(getattr(aruco, dictionary)), aruco.DetectorParameters())
    gray = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2GRAY) if image_bgr.ndim == 3 else image_bgr
    corners, ids, _ = detector.detectMarkers(gray)
    if ids is None or len(ids) == 0:
        return None
    c = np.asarray(corners[0]).reshape(4, 2)
    return MarkerCalibration(
        mm_per_px=marker_scale(c, marker_mm),
        corners_px=c,
        homography=marker_homography(c, marker_mm),
        marker_id=int(np.asarray(ids).ravel()[0]),  # ids is (N, 1) in OpenCV 4 and (N,) in 5
    )


def draw_marker(marker_id: int = 0, size_px: int = 400, dictionary: str = "DICT_4X4_50") -> np.ndarray:
    """Render a printable ArUco marker (``caliper marker`` writes this to a PNG)."""
    import cv2

    aruco = cv2.aruco
    return aruco.generateImageMarker(aruco.getPredefinedDictionary(getattr(aruco, dictionary)), marker_id, size_px)
