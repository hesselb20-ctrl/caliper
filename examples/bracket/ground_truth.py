"""The known part: a hand-written CadQuery L-bracket with deliberately awkward numbers.

This file is the ground truth. It does not use caliper's code generator, so the
accuracy test is not marking its own homework.
"""

import cadquery as cq

TRUTH = {
    "length": 80.0,  # along X
    "width": 50.0,  # along Y
    "thickness": 5.0,
    "corner_radius": 6.0,  # the two corners away from the flange
    "hole_diameter": 6.5,
    "hole_spacing": 40.0,  # the reference measurement handed to caliper
    "hole_y": -8.0,
    "slot_length": 14.0,
    "slot_width": 5.0,
    "slot_y": 8.0,
    "flange_height": 40.0,  # from the underside of the base
    "flange_thickness": 5.0,
    "flange_hole_diameter": 5.2,
    "flange_hole_spacing": 44.0,
    "flange_hole_height": 26.0,
}


def make_bracket(t=TRUTH):
    L, W, T = t["length"], t["width"], t["thickness"]
    base = cq.Workplane("XY").box(L, W, T, centered=(True, True, False))
    base = base.edges("|Z and <Y").fillet(t["corner_radius"])
    flange = (
        cq.Workplane("XY")
        .box(L, t["flange_thickness"], t["flange_height"], centered=(True, True, False))
        .translate((0, W / 2 - t["flange_thickness"] / 2, 0))
    )
    part = base.union(flange)
    for sx in (-1, 1):
        drill = cq.Workplane("XY").circle(t["hole_diameter"] / 2).extrude(T + 2).translate((sx * t["hole_spacing"] / 2, t["hole_y"], -1))
        part = part.cut(drill)
    slot = cq.Workplane("XY").slot2D(t["slot_length"], t["slot_width"]).extrude(T + 2).translate((0, t["slot_y"], -1))
    part = part.cut(slot)
    for sx in (-1, 1):
        drill = cq.Solid.makeCylinder(
            t["flange_hole_diameter"] / 2,
            t["flange_thickness"] + 2,
            cq.Vector(sx * t["flange_hole_spacing"] / 2, W / 2 - t["flange_thickness"] - 1, t["flange_hole_height"]),
            cq.Vector(0, 1, 0),
        )
        part = part.cut(drill)
    return part


if __name__ == "__main__":
    cq.exporters.export(make_bracket(), "ground_truth.step")
