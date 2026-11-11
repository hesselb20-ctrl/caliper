import json
import math
import subprocess
import sys

import pytest

from caliper import dfm
from caliper.codegen import build, free_corners, generate_cadquery, write_model
from caliper.export import mesh_volume, tessellate
from caliper.features import Feature, FeatureTree, FeatureTreeError, snap_tree, snap_value


def plate(**base):
    params = {"length": 80.0, "width": 50.0, "thickness": 5.0} | base
    return [Feature("base", "base_plate", params)]


def bracket(edge="+y"):
    return FeatureTree(
        plate()
        + [
            Feature("fillet", "fillet", {"radius": 6.0, "corners": "free"}, "base"),
            Feature("flange", "flange", {"height": 40.0, "thickness": 5.0, "edge": edge}, "base"),
            Feature("h1", "hole", {"x": -20.0, "y": -8.0, "diameter": 6.5}, "base"),
            Feature("h2", "hole", {"x": 20.0, "y": -8.0, "diameter": 6.5}, "base"),
            Feature("fh1", "hole", {"u": -10.0, "v": 26.0, "diameter": 5.2}, "flange"),
            Feature("slot1", "slot", {"x": 0.0, "y": 8.0, "length": 14.0, "width": 5.0, "angle": 0.0}, "base"),
        ],
        part_type="bracket",
    ).validate()


def bbox(part):
    b = part.val().BoundingBox()
    return (b.xmin, b.xmax, b.ymin, b.ymax, b.zmin, b.zmax)


def volume(part):
    return part.val().Volume()


# ---- source generation ---------------------------------------------------------------------


def test_source_is_parametric_and_readable():
    src = generate_cadquery(bracket())
    compile(src, "model.py", "exec")
    for key in bracket().params():
        assert f'P["{key}"]' in src, key
    for comment in ("# base:", "# fillet:", "# flange:", "# h1:", "# fh1:", "# slot1:"):
        assert comment in src
    assert "def build(P):" in src and 'cq.exporters.export(part, str(HERE / "part.step"))' in src
    # No literal dimensions leak into the body: every number comes from params.
    assert "80.0" not in src and "6.5" not in src


def test_plain_plate_volume_and_bbox():
    part = build(FeatureTree(plate()))
    assert bbox(part) == pytest.approx((-40, 40, -25, 25, 0, 5))
    assert volume(part) == pytest.approx(80 * 50 * 5)


def test_holes_and_slot_remove_the_right_volume():
    tree = FeatureTree(
        plate()
        + [
            Feature("h1", "hole", {"x": -20.0, "y": 0.0, "diameter": 6.0}, "base"),
            Feature("h2", "hole", {"x": 20.0, "y": 0.0, "diameter": 6.0}, "base"),
            Feature("s", "slot", {"x": 0.0, "y": 12.0, "length": 14.0, "width": 5.0, "angle": 0.0}, "base"),
        ]
    )
    hole = math.pi * 3.0**2 * 5
    slot = (math.pi * 2.5**2 + (14 - 5) * 5) * 5
    assert volume(build(tree)) == pytest.approx(80 * 50 * 5 - 2 * hole - slot, rel=1e-6)


def test_fillet_all_corners():
    tree = FeatureTree(plate() + [Feature("f", "fillet", {"radius": 6.0, "corners": "all"}, "base")])
    assert volume(build(tree)) == pytest.approx((80 * 50 - (4 - math.pi) * 36) * 5, rel=1e-6)


@pytest.mark.parametrize("edge", ["+y", "-y", "+x", "-x"])
def test_flange_on_every_edge(edge):
    tree = FeatureTree(
        plate()
        + [
            Feature("flange", "flange", {"height": 40.0, "thickness": 5.0, "edge": edge}, "base"),
            Feature("fh", "hole", {"u": 0.0, "v": 25.0, "diameter": 6.0}, "flange"),
        ]
    )
    part = build(tree)
    assert bbox(part) == pytest.approx((-40, 40, -25, 25, 0, 40))
    run = 80 if edge in ("+y", "-y") else 50
    solid = 80 * 50 * 5 + run * 5 * 35 - math.pi * 9 * 5
    assert volume(part) == pytest.approx(solid, rel=1e-6)
    # The flange really is on the named side: the centre of mass moves that way.
    com = part.val().Center()
    coordinate = com.y if edge[1] == "y" else com.x
    assert (coordinate > 0) == (edge[0] == "+")


def test_free_corners_follow_the_flange():
    assert free_corners(bracket("+y")) == [(-1, -1), (1, -1)]
    assert free_corners(bracket("-x")) == [(1, -1), (1, 1)]


def test_full_bracket_builds_and_exports(tmp_path):
    tree = bracket()
    paths = write_model(tree, tmp_path)
    assert json.loads(paths["params"].read_text())["flange.height"] == 40.0
    part = build(tree)
    v, t = tessellate(part)
    assert mesh_volume(v, t) == pytest.approx(volume(part), rel=5e-3)
    # The generated file runs on its own, the way a user would run it.
    subprocess.run([sys.executable, str(paths["model"])], check=True, cwd=tmp_path)
    assert (tmp_path / "part.step").stat().st_size > 1000
    assert (tmp_path / "part.stl").stat().st_size > 1000


def test_editing_a_parameter_changes_the_part():
    tree = bracket()
    taller = tree.with_params({"flange.height": 60.0})
    assert bbox(build(taller))[5] == pytest.approx(60.0)
    assert volume(build(taller)) - volume(build(tree)) == pytest.approx(80 * 5 * 20, rel=1e-6)
    # build() also accepts an explicit parameter dict, as model.py does.
    assert bbox(build(tree, tree.params() | {"base.length": 100.0}))[1] == pytest.approx(50.0)


def test_boss_with_bore():
    tree = FeatureTree(plate() + [Feature("b", "boss", {"x": 0.0, "y": 0.0, "diameter": 12.0, "height": 8.0, "bore": 4.0}, "base")])
    expected = 80 * 50 * 5 + math.pi * 36 * 8 - math.pi * 4 * 13
    assert volume(build(tree)) == pytest.approx(expected, rel=1e-6)
    assert bbox(build(tree))[5] == pytest.approx(13.0)


# ---- validation and design intent -----------------------------------------------------------


@pytest.mark.parametrize(
    "features",
    [
        [],
        plate() + plate(),
        plate(length=-1.0),
        plate() + [Feature("h", "hole", {"x": 0.0, "diameter": 5.0}, "base")],
        plate() + [Feature("f", "flange", {"height": 4.0, "thickness": 5.0, "edge": "+y"}, "base")],
        plate() + [Feature("f", "flange", {"height": 40.0, "thickness": 5.0, "edge": "north"}, "base")],
        plate() + [Feature("f", "fillet", {"radius": 30.0, "corners": "all"}, "base")],
        plate() + [Feature("x", "thread", {}, "base")],
    ],
)
def test_invalid_trees_are_rejected(features):
    with pytest.raises(FeatureTreeError):
        FeatureTree(features).validate()


def test_round_trip_json(tmp_path):
    tree = bracket()
    tree.save(tmp_path / "t.json")
    assert FeatureTree.load(tmp_path / "t.json").to_dict() == tree.to_dict()


def test_snap_value():
    assert snap_value(39.87, 0.5) == 40.0
    assert snap_value(6.48, 0.5) == 6.5
    assert snap_value(5.2, 0.5) == 5.2  # too far from a round number to call it noise
    assert snap_value(5.2, 0) == 5.2


def test_snap_tree_restores_symmetry():
    tree = bracket().with_params({"h1.x": -20.10, "h2.x": 19.90, "base.length": 80.06, "h1.diameter": 6.48})
    p = snap_tree(tree, 0.5).params()
    assert (p["h1.x"], p["h2.x"]) == (-20.0, 20.0)
    assert p["base.length"] == 80.0 and p["h1.diameter"] == 6.5


# ---- manufacturability ------------------------------------------------------------------------


def test_wall_check_names_the_thin_feature():
    tree = FeatureTree(plate() + [Feature("h1", "hole", {"x": 37.0, "y": 0.0, "diameter": 5.0}, "base")]).validate()
    report = dfm.check(tree, min_wall=1.2)
    assert not report.ok
    assert report.thinnest.name == "h1 to plate edge"
    assert report.thinnest.thickness == pytest.approx(0.5)
    assert dfm.check(bracket()).ok


def test_web_between_holes():
    tree = FeatureTree(
        plate()
        + [
            Feature("a", "hole", {"x": 0.0, "y": 0.0, "diameter": 6.0}, "base"),
            Feature("b", "hole", {"x": 7.0, "y": 0.0, "diameter": 6.0}, "base"),
        ]
    ).validate()
    assert dict(dfm.wall_thicknesses(tree))["web a to b"] == pytest.approx(1.0)


def test_overhangs_of_a_plate_and_a_bracket():
    v, t = tessellate(build(FeatureTree(plate())))
    for o in dfm.overhangs(v, t):
        assert o.area_mm2 == pytest.approx(0.0, abs=1e-6)  # a box prints flat in every orientation
    v, t = tessellate(build(bracket()))
    by_name = {o.orientation: o for o in dfm.overhangs(v, t)}
    # Flipped, the plate hangs in the air above the flange tip: a large unsupported roof.
    assert by_name["-z up (flipped)"].area_mm2 > 2500
    assert by_name["+z up (as modelled)"].area_mm2 < 60  # only the crown of the horizontal flange hole
    report = dfm.check(bracket(), (v, t))
    assert report.best_orientation.area_mm2 <= by_name["+z up (as modelled)"].area_mm2
    assert "Suggested orientation" in report.to_markdown()
