"""Measurement on drawn images, the Claude request, and the bracket example end to end."""

import json
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from caliper.calibration import parse_reference
from caliper.ingest import Photo, assign_views
from caliper.measure import measure_face, read_profile, segment
from caliper.vision import MODEL, build_request, describe_with_claude, tree_from_response

cv2 = pytest.importorskip("cv2")

BG, FACE, WALL = (214, 209, 204), (46, 120, 232), (10, 20, 40)  # BGR
PHOTOS = Path(__file__).resolve().parents[1] / "examples" / "bracket" / "photos"


def drawn_plate(angle=0.0):
    """900x500 px plate with two 60 px holes 400 px apart and a 140x50 px slot."""
    img = np.full((1200, 1600, 3), BG, dtype=np.uint8)
    cv2.rectangle(img, (350, 350), (1249, 849), FACE, -1)
    for cx in (600, 1000):
        cv2.circle(img, (cx, 700), 30, BG, -1, cv2.LINE_AA)
    cv2.rectangle(img, (755, 475), (845, 525), BG, -1)
    cv2.circle(img, (755, 500), 25, BG, -1, cv2.LINE_AA)
    cv2.circle(img, (845, 500), 25, BG, -1, cv2.LINE_AA)
    if angle:
        m = cv2.getRotationMatrix2D((800, 600), angle, 1.0)
        img = cv2.warpAffine(img, m, (1600, 1200), flags=cv2.INTER_CUBIC, borderValue=BG)
    return cv2.GaussianBlur(img, (0, 0), 0.8)


@pytest.mark.parametrize("angle", [0.0, 3.0, -4.0])
def test_measure_face_on_a_drawn_plate(angle):
    face = measure_face(drawn_plate(angle))
    assert abs(face.rotation_deg) == pytest.approx(abs(angle), abs=0.3)
    assert face.width == pytest.approx(900, abs=3)
    assert face.height == pytest.approx(500, abs=3)
    holes = [o for o in face.openings if o.is_round]
    slots = [o for o in face.openings if not o.is_round]
    assert len(holes) == 2 and len(slots) == 1
    assert [h.diameter for h in holes] == pytest.approx([60, 60], abs=1.5)
    assert abs(holes[1].cx - holes[0].cx) == pytest.approx(400, abs=1.0)
    assert slots[0].length == pytest.approx(140, abs=3)
    assert slots[0].width == pytest.approx(50, abs=2)


def test_segment_separates_face_from_walls():
    img = np.full((600, 800, 3), BG, dtype=np.uint8)
    cv2.rectangle(img, (200, 200), (599, 399), FACE, -1)
    cv2.rectangle(img, (200, 150), (599, 199), WALL, -1)  # a shaded wall above the face
    part, face = segment(img)
    assert part.sum() == pytest.approx(400 * 250, rel=0.02)
    assert face.sum() == pytest.approx(400 * 200, rel=0.02)


def test_read_profile_finds_the_l_shape():
    img = np.full((900, 1200, 3), BG, dtype=np.uint8)
    cv2.rectangle(img, (300, 600), (799, 649), FACE, -1)  # base: 500 x 50
    cv2.rectangle(img, (750, 250), (799, 649), FACE, -1)  # flange: 50 wide, 400 tall overall
    profile = read_profile(img)
    assert profile.width_px == pytest.approx(500, abs=3)
    assert profile.height_px == pytest.approx(400, abs=3)
    assert profile.thickness_px == pytest.approx(50, abs=2)
    assert profile.flange_px == pytest.approx(50, abs=2)


def test_assign_views():
    assert assign_views(["IMG_top", "IMG_side", "front_face"]) == ["top", "side", "front"]
    assert assign_views(["a", "b", "c", "d"]) == ["top", "side", "front", "iso"]
    assert assign_views(["side_view", "x"]) == ["side", "top"]


# ---- Claude describer (no network: a stub client records the request) -----------------------


def _feature(**kwargs):
    blank = dict(parent="", edge="", corners="", length=0, width=0, thickness=0, height=0, diameter=0, radius=0, bore=0, angle=0, x=0, y=0, u=0, v=0)
    return blank | kwargs


RESPONSE = {
    "part_type": "bracket",
    "notes": "Flange holes assumed symmetric.",
    "features": [
        _feature(id="base", type="base_plate", length=80, width=50, thickness=5),
        _feature(id="flange", type="flange", parent="base", edge="+y", thickness=5, height=40),
        _feature(id="h1", type="hole", parent="base", diameter=6.5, x=-20, y=-8),
        _feature(id="fh1", type="hole", parent="flange", diameter=5.2, u=-22, v=26),
    ],
}


class StubClient:
    def __init__(self, stop_reason="end_turn"):
        self.request = None
        self.beta = SimpleNamespace(messages=SimpleNamespace(create=self._create))
        self._stop = stop_reason

    def _create(self, **kwargs):
        self.request = kwargs
        return SimpleNamespace(stop_reason=self._stop, content=[SimpleNamespace(type="text", text=json.dumps(RESPONSE))])


def photos():
    return [Photo(Path("top.jpg"), "top", drawn_plate()), Photo(Path("side.jpg"), "side", np.full((3000, 4000, 3), 200, np.uint8))]


def test_request_shape():
    req = build_request(photos(), parse_reference("hole spacing 40mm"))
    assert req["model"] == MODEL == "claude-fable-5-2"
    assert "thinking" not in req and "temperature" not in req  # not accepted by this model
    assert req["output_config"]["format"]["type"] == "json_schema"
    assert req["fallbacks"] == "default" and req["betas"] == ["server-side-fallback-2026-07-01"]
    content = req["messages"][0]["content"]
    images = [b for b in content if b["type"] == "image"]
    assert len(images) == 2 and images[0]["source"]["media_type"] == "image/jpeg"
    assert len(images[1]["source"]["data"]) < 400_000  # the 12 MP frame was downscaled
    assert "hole spacing 40mm" in content[-1]["text"]
    item = req["output_config"]["format"]["schema"]["properties"]["features"]["items"]
    assert item["additionalProperties"] is False and set(item["required"]) == set(item["properties"])


def test_describe_with_claude_parses_and_validates():
    client = StubClient()
    tree = describe_with_claude(photos(), parse_reference("hole spacing 40mm"), client=client)
    assert [f.id for f in tree.features] == ["base", "flange", "h1", "fh1"]
    assert tree.get("fh1").params == {"u": -22, "v": 26, "diameter": 5.2}
    assert tree.get("h1").params == {"x": -20, "y": -8, "diameter": 6.5}
    assert tree.notes.startswith("Flange holes")
    assert client.request["model"] == "claude-fable-5-2"
    with pytest.raises(RuntimeError):
        describe_with_claude(photos(), parse_reference("hole spacing 40mm"), client=StubClient("refusal"))


def test_tree_from_response_rejects_nonsense():
    bad = json.loads(json.dumps(RESPONSE))
    bad["features"][0]["length"] = 0
    with pytest.raises(ValueError):
        tree_from_response(bad)


# ---- the bracket example, end to end ------------------------------------------------------------


@pytest.mark.skipif(not (PHOTOS / "top.jpg").exists(), reason="example photos not rendered")
def test_bracket_example_end_to_end(tmp_path):
    from caliper.pipeline import rebuild, scan

    result = scan(PHOTOS, "hole spacing 40mm", tmp_path, describer="classical", snap=0)
    p = result.tree.params()
    truth = {
        "base.length": 80.0,
        "base.width": 50.0,
        "base.thickness": 5.0,
        "fillet.radius": 6.0,
        "flange.height": 40.0,
        "flange.thickness": 5.0,
        "h1.diameter": 6.5,
        "h1.y": -8.0,
        "slot1.length": 14.0,
        "slot1.width": 5.0,
        "fh1.diameter": 5.2,
        "fh1.v": 26.0,
    }
    for key, value in truth.items():
        assert p[key] == pytest.approx(value, rel=0.04), key
    assert p["h2.x"] - p["h1.x"] == pytest.approx(40.0, abs=1e-2)  # the reference itself
    assert p["fh2.u"] - p["fh1.u"] == pytest.approx(44.0, rel=0.02)
    assert result.tree.get("flange").params["edge"] == "+y"
    for name in ("step", "stl", "model", "params", "tree", "report", "preview"):
        assert result.files[name].exists(), name

    # Edit one parameter and rebuild: the parametric promise.
    params = json.loads((tmp_path / "params.json").read_text())
    params["flange.height"] = 60.0
    (tmp_path / "params.json").write_text(json.dumps(params))
    assert rebuild(tmp_path).tree.get("flange").params["height"] == 60.0
