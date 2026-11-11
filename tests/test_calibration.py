import math

import numpy as np
import pytest

from caliper import calibration as cal


@pytest.mark.parametrize(
    "text, kind, mm",
    [
        ("hole spacing 40mm", "hole_spacing", 40.0),
        ("Hole spacing: 40 mm", "hole_spacing", 40.0),
        ("centre to centre 1.5 in", "hole_spacing", 38.1),
        ("width 5cm", "width", 50.0),
        ("length 80", "length", 80.0),
        ("thickness 3,2 mm", "thickness", 3.2),
        ("hole diameter 6.5mm", "hole_diameter", 6.5),
        ("aruco marker 30 mm", "marker", 30.0),
        ("overall height 40mm", "flange_height", 40.0),
    ],
)
def test_parse_reference(text, kind, mm):
    ref = cal.parse_reference(text)
    assert ref.kind == kind
    assert ref.value_mm == pytest.approx(mm)


@pytest.mark.parametrize("text", ["", "40mm", "hole spacing", "width 0 mm"])
def test_parse_reference_rejects(text):
    with pytest.raises(ValueError):
        cal.parse_reference(text)


def test_mm_per_px():
    assert cal.mm_per_px(40.0, 400.0) == pytest.approx(0.1)
    with pytest.raises(ValueError):
        cal.mm_per_px(40.0, 0.0)
    with pytest.raises(ValueError):
        cal.mm_per_px(-1.0, 10.0)


def test_focal_and_distance_round_trip():
    # A 4000x3000 photo at 26 mm equivalent; a plane at 400 mm.
    f = cal.focal_px_from_35mm(26.0, 4000, 3000)
    assert f == pytest.approx(26.0 / 43.2666 * 5000)
    scale = 400.0 / f  # mm per px on a plane 400 mm away
    assert cal.camera_distance(f, scale) == pytest.approx(400.0)


def test_scale_at_height_matches_pinhole_projection():
    # Project a 40 mm segment at three heights with a pinhole and recover it.
    f, z = 3000.0, 400.0
    ground_scale = z / f
    for height in (0.0, 5.0, 40.0):
        pixels = f * 40.0 / (z - height)
        assert pixels * cal.scale_at_height(ground_scale, z, height) == pytest.approx(40.0)
    # Ignoring the height of a 40 mm tall feature costs about 11 % at 400 mm.
    naive = f * 40.0 / (z - 40.0) * ground_scale
    assert naive / 40.0 - 1 == pytest.approx(40.0 / 360.0)
    with pytest.raises(ValueError):
        cal.scale_at_height(ground_scale, z, z)


def test_chained_width():
    # 50 mm plate, 5 mm of it under the flange, seen end-on at 12.3 px/mm.
    assert cal.chained_width(45.0, 5 * 12.3, 50 * 12.3) == pytest.approx(50.0)
    assert cal.chained_width(45.0, 0, 100) == pytest.approx(45.0)
    with pytest.raises(ValueError):
        cal.chained_width(45.0, 100, 100)


def test_relative_error():
    assert cal.relative_error(40.4, 40.0) == pytest.approx(0.01)


def test_marker_scale_and_homography():
    # A 30 mm marker seen as a 300 px square, rotated 20 degrees.
    a = math.radians(20)
    rot = np.array([[math.cos(a), -math.sin(a)], [math.sin(a), math.cos(a)]])
    square = np.array([[0, 0], [300, 0], [300, 300], [0, 300]], dtype=float)
    corners = square @ rot.T + [500, 400]
    assert cal.marker_scale(corners, 30.0) == pytest.approx(0.1)
    h = cal.marker_homography(corners, 30.0)
    mapped = cal.apply_homography(h, corners)
    assert mapped == pytest.approx(np.array([[0, 0], [30, 0], [30, 30], [0, 30]]), abs=1e-3)
    centre = cal.apply_homography(h, corners.mean(axis=0))
    assert centre == pytest.approx(np.array([[15, 15]]), abs=1e-3)


def test_homography_removes_perspective():
    # Keystoned marker: the far edge is shorter. Distances on the plane still come out right.
    corners = np.array([[100, 100], [400, 120], [380, 380], [120, 400]], dtype=float)
    h = cal.marker_homography(corners, 50.0)
    pts = cal.apply_homography(h, corners)
    sides = np.linalg.norm(pts - np.roll(pts, -1, axis=0), axis=1)
    assert sides == pytest.approx([50, 50, 50, 50], abs=1e-3)


def test_detect_marker_in_synthetic_photo():
    cv2 = pytest.importorskip("cv2")
    marker = cal.draw_marker(marker_id=3, size_px=240)
    photo = np.full((800, 1000), 235, dtype=np.uint8)
    photo[300:540, 380:620] = marker
    found = cal.detect_marker(cv2.cvtColor(photo, cv2.COLOR_GRAY2BGR), marker_mm=24.0)
    assert found is not None and found.marker_id == 3
    assert found.mm_per_px == pytest.approx(0.1, rel=0.01)
    assert cal.detect_marker(np.full((200, 200, 3), 200, dtype=np.uint8), 24.0) is None
