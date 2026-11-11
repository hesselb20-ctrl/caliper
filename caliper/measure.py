"""Classical (no model) measurement of a part from clean, roughly square-on photos.

Everything here works in pixels. The idea that keeps perspective honest:

    Only measure on a face that is square to the camera.

A face that looks straight at the lens is one plane, so one scale applies to
all of it. In each photo we segment that face (it is the best lit surface when
the light sits near the camera) and measure its outline and the holes in it.
Anything slanted or receding is ignored instead of being measured wrongly.

This is the offline baseline. It needs a plain background and even light; the
Claude describer is what copes with real-world photos.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np


@dataclass
class Opening:
    """A closed opening in a face: a round hole or an elongated slot (pixels)."""

    cx: float
    cy: float
    diameter: float  # area-equivalent diameter
    length: float  # long side of the fitted rectangle
    width: float  # short side
    angle: float  # degrees, long side from image +x, counter-clockwise
    circularity: float

    @property
    def is_round(self) -> bool:
        return self.length / max(self.width, 1e-6) < 1.25


@dataclass
class FaceMeasurement:
    """One square-on face, deskewed, in pixels. Image y grows downward."""

    x0: float
    y0: float
    width: float
    height: float
    openings: list[Opening] = field(default_factory=list)
    silhouette: tuple[float, float, float, float] = (0, 0, 0, 0)  # x0, y0, w, h of the whole part
    corner_radii: dict[str, float] = field(default_factory=dict)  # "tl", "tr", "br", "bl"
    row_widths: np.ndarray | None = None
    rotation_deg: float = 0.0

    @property
    def center(self) -> tuple[float, float]:
        return self.x0 + self.width / 2, self.y0 + self.height / 2


class MeasurementError(RuntimeError):
    pass


# ---- segmentation -----------------------------------------------------------------------


def _lab(image_bgr: np.ndarray) -> np.ndarray:
    import cv2

    return cv2.cvtColor(image_bgr, cv2.COLOR_BGR2LAB).astype(np.float32)


def _largest_component(mask: np.ndarray) -> np.ndarray:
    import cv2

    count, labels, stats, _ = cv2.connectedComponentsWithStats(mask.astype(np.uint8), connectivity=8)
    if count <= 1:
        return np.zeros_like(mask, dtype=bool)
    biggest = 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))
    return labels == biggest


def segment(image_bgr: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Return ``(part_mask, face_mask)`` as boolean arrays.

    Pixels are assigned to the nearest of three colours in Lab space: the
    background (sampled from the image border), the square-on face (the
    brightest part colour) and the shaded walls. Nearest-centroid puts each
    boundary halfway along the blur between two regions, which keeps edge
    positions unbiased.
    """
    import cv2

    lab = _lab(cv2.GaussianBlur(image_bgr, (0, 0), 0.6))
    h, w = lab.shape[:2]
    b = max(4, int(0.03 * min(h, w)))
    border = np.concatenate([lab[:b].reshape(-1, 3), lab[-b:].reshape(-1, 3), lab[:, :b].reshape(-1, 3), lab[:, -b:].reshape(-1, 3)])
    background = np.median(border, axis=0)
    spread = float(np.percentile(np.linalg.norm(border - background, axis=1), 99))
    dist_bg = np.linalg.norm(lab - background, axis=2)
    rough = _largest_component(dist_bg > max(18.0, 2.5 * spread))
    if rough.sum() < 0.002 * h * w:
        raise MeasurementError("could not separate the part from the background; use a plain, contrasting surface")

    part_px = lab[rough]
    lightness = part_px[:, 0]
    top = np.percentile(lightness, 95)
    face = np.median(part_px[lightness > top - 6], axis=0)
    dist_face_px = np.linalg.norm(part_px - face, axis=1)
    dark_px = part_px[dist_face_px > 30]
    centroids = [background, face]
    if len(dark_px) > 0.01 * len(part_px):
        centroids.append(np.median(dark_px, axis=0))
    stack = np.stack([np.linalg.norm(lab - c, axis=2) for c in centroids], axis=0)
    label = np.argmin(stack, axis=0)
    kernel = np.ones((3, 3), np.uint8)
    part = _largest_component(cv2.morphologyEx((label != 0).astype(np.uint8), cv2.MORPH_OPEN, kernel) > 0)
    face_mask = cv2.morphologyEx(((label == 1) & part).astype(np.uint8), cv2.MORPH_OPEN, kernel) > 0
    return part, face_mask


def _skew_angle(mask: np.ndarray) -> float:
    """Rotation (degrees, within +-45) that makes the mask's box axis-aligned."""
    import cv2

    contours, _ = cv2.findContours(mask.astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
    contour = max(contours, key=cv2.contourArea)
    angle = cv2.minAreaRect(contour)[2]
    while angle > 45:
        angle -= 90
    while angle <= -45:
        angle += 90
    return float(angle)


def _rotate(image: np.ndarray, angle_deg: float) -> np.ndarray:
    import cv2

    h, w = image.shape[:2]
    m = cv2.getRotationMatrix2D((w / 2, h / 2), angle_deg, 1.0)
    edge = [int(v) for v in np.median(np.concatenate([image[0], image[-1]]), axis=0)]
    return cv2.warpAffine(image, m, (w, h), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_CONSTANT, borderValue=edge)


# ---- measuring a face -------------------------------------------------------------------


def _openings(face: np.ndarray, filled: np.ndarray, min_area: float) -> list[Opening]:
    """Holes and slots: connected regions inside the face outline that are not face."""
    import cv2

    holes = (filled.astype(bool) & ~face.astype(bool)).astype(np.uint8)
    count, labels, stats, centroids = cv2.connectedComponentsWithStats(holes, connectivity=4)
    found: list[Opening] = []
    for i in range(1, count):
        area = float(stats[i, cv2.CC_STAT_AREA])  # pixel count: unbiased for a mid-level threshold
        if area < min_area:
            continue
        ys, xs = np.nonzero(labels == i)
        points = np.stack([xs, ys], axis=1).astype(np.float32)
        (_, _), (rw, rh), rect_angle = cv2.minAreaRect(points)
        long_side, short_side = max(rw, rh) + 1, min(rw, rh) + 1  # centre-to-centre extent plus one pixel
        angle = rect_angle if rw >= rh else rect_angle + 90
        angle = (-angle + 90) % 180 - 90  # image y is down; report counter-clockwise
        contours, _ = cv2.findContours((labels == i).astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
        perimeter = cv2.arcLength(contours[0], True) + 4
        found.append(
            Opening(
                cx=float(centroids[i][0]),
                cy=float(centroids[i][1]),
                diameter=2 * math.sqrt(area / math.pi),
                length=float(long_side),
                width=float(short_side),
                angle=float(angle),
                circularity=min(1.0, 4 * math.pi * area / (perimeter**2)),
            )
        )
    return sorted(found, key=lambda o: (round(o.cy / 20), o.cx))


def _corner_radii(face_filled: np.ndarray, x0: int, y0: int, w: int, h: int) -> dict[str, float]:
    """Radius of each corner of a rectangular face from the area missing there."""
    s = int(0.22 * min(w, h))
    radii = {}
    windows = {
        "tl": face_filled[y0 : y0 + s, x0 : x0 + s],
        "tr": face_filled[y0 : y0 + s, x0 + w - s : x0 + w],
        "br": face_filled[y0 + h - s : y0 + h, x0 + w - s : x0 + w],
        "bl": face_filled[y0 + h - s : y0 + h, x0 : x0 + s],
    }
    for name, window in windows.items():
        missing = window.size - int(window.sum())
        radius = math.sqrt(missing / (1 - math.pi / 4)) if missing > 0 else 0.0
        radii[name] = radius if radius < s else 0.0
    return radii


def measure_face(image_bgr: np.ndarray, which: str = "largest") -> FaceMeasurement:
    """Deskew the photo and measure its main square-on face."""
    import cv2

    _, face = segment(image_bgr)
    main = _largest_component(face)
    if main.sum() < 200:
        raise MeasurementError("no square-on face found; shoot straight at the part with the light behind you")
    angle = _skew_angle(main)
    if abs(angle) > 0.05:
        image_bgr = _rotate(image_bgr, angle)
    part, face = segment(image_bgr)
    main = _largest_component(face)

    ys, xs = np.nonzero(main)
    x0, x1, y0, y1 = int(xs.min()), int(xs.max()) + 1, int(ys.min()), int(ys.max()) + 1
    w, h = x1 - x0, y1 - y0
    filled = np.zeros_like(main, dtype=np.uint8)
    contours, _ = cv2.findContours(main.astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
    cv2.drawContours(filled, contours, -1, 1, thickness=cv2.FILLED)

    pys, pxs = np.nonzero(part)
    silhouette = (float(pxs.min()), float(pys.min()), float(pxs.max() + 1 - pxs.min()), float(pys.max() + 1 - pys.min()))
    return FaceMeasurement(
        x0=float(x0),
        y0=float(y0),
        width=float(w),
        height=float(h),
        openings=_openings(main, filled, min_area=max(30.0, 2e-4 * w * h)),
        silhouette=silhouette,
        corner_radii=_corner_radii(filled.astype(bool), x0, y0, w, h),
        row_widths=filled[y0:y1, x0:x1].sum(axis=1).astype(float),
        rotation_deg=angle,
    )


# ---- view-specific readings ----------------------------------------------------------------


@dataclass
class TopReading:
    face: FaceMeasurement
    flange_edge: str | None  # which base edge the flange stands on, in part axes
    flange_strip_px: float  # silhouette overhang on that side (flange seen from above)


def read_top(image_bgr: np.ndarray) -> TopReading:
    """Top view: the visible top of the base plate, its holes and where the flange is."""
    face = measure_face(image_bgr)
    sx, sy, sw, sh = face.silhouette
    margins = {
        "+y": face.y0 - sy,  # image up is part +y
        "-y": (sy + sh) - (face.y0 + face.height),
        "-x": face.x0 - sx,
        "+x": (sx + sw) - (face.x0 + face.width),
    }
    edge, strip = max(margins.items(), key=lambda kv: kv[1])
    if strip < 0.04 * min(face.width, face.height):
        return TopReading(face=face, flange_edge=None, flange_strip_px=0.0)
    return TopReading(face=face, flange_edge=edge, flange_strip_px=float(strip))


@dataclass
class ProfileReading:
    width_px: float  # full extent across (plate width, seen end-on)
    height_px: float  # full height
    thickness_px: float  # base plate thickness
    flange_px: float | None  # flange thickness, None when the profile is a plain rectangle


def read_profile(image_bgr: np.ndarray) -> ProfileReading:
    """Side view: the end face is an L (plate plus flange) or a plain rectangle."""
    face = measure_face(image_bgr)
    rows = face.row_widths
    full = float(np.percentile(rows, 98))
    wide = rows > 0.6 * full
    narrow = rows[(rows > 0) & ~wide]
    _, _, sw, _ = face.silhouette
    if len(narrow) < 0.08 * len(rows):
        return ProfileReading(width_px=sw, height_px=face.height, thickness_px=face.height, flange_px=None)
    flange = float(np.median(narrow))
    split = (full + flange) / 2
    return ProfileReading(width_px=sw, height_px=face.height, thickness_px=float((rows > split).sum()), flange_px=flange)
