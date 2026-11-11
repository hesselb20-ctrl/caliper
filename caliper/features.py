"""The feature tree: the design-intent description that sits between photos and CAD.

Coordinate convention (millimetres):
  * The base plate is centred on the origin in X and Y and sits on Z = 0.
  * ``length`` runs along X, ``width`` along Y, ``thickness`` along Z.
  * A flange stands on one edge of the base (``+y``, ``-y``, ``+x`` or ``-x``).
    Its ``height`` is measured from Z = 0, so it includes the base thickness.
  * A hole whose parent is the base uses ``x``/``y`` from the plate centre.
    A hole whose parent is a flange uses ``u`` (along the edge, from its
    centre) and ``v`` (height above Z = 0).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

EDGES = ("+y", "-y", "+x", "-x")
CORNERS = ("all", "free")

# type -> (numeric params, string params with allowed values)
SCHEMA: dict[str, tuple[tuple[str, ...], dict[str, tuple[str, ...]]]] = {
    "base_plate": (("length", "width", "thickness"), {}),
    "fillet": (("radius",), {"corners": CORNERS}),
    "flange": (("height", "thickness"), {"edge": EDGES}),
    "hole": (("diameter",), {}),  # plus x/y or u/v depending on the parent
    "slot": (("x", "y", "length", "width", "angle"), {}),
    "boss": (("x", "y", "diameter", "height", "bore"), {}),
}

# Params that may legitimately be zero or negative (positions, angles, optional bore).
_SIGNED = {"x", "y", "u", "v", "angle", "bore"}


class FeatureTreeError(ValueError):
    """Raised when a feature tree is not buildable."""


@dataclass
class Feature:
    id: str
    type: str
    params: dict[str, Any]
    parent: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {"id": self.id, "type": self.type, "parent": self.parent, "params": dict(self.params)}


@dataclass
class FeatureTree:
    features: list[Feature]
    part_type: str = "part"
    units: str = "mm"
    notes: str = ""
    meta: dict[str, Any] = field(default_factory=dict)

    # ---- access -----------------------------------------------------------------
    def of_type(self, type_: str) -> list[Feature]:
        return [f for f in self.features if f.type == type_]

    def get(self, id_: str) -> Feature:
        for f in self.features:
            if f.id == id_:
                return f
        raise KeyError(id_)

    @property
    def base(self) -> Feature:
        bases = self.of_type("base_plate")
        if len(bases) != 1:
            raise FeatureTreeError(f"expected exactly one base_plate, found {len(bases)}")
        return bases[0]

    def children(self, id_: str) -> list[Feature]:
        return [f for f in self.features if f.parent == id_]

    # ---- parameters ---------------------------------------------------------------
    def params(self) -> dict[str, float]:
        """Flat ``{"<id>.<param>": value}`` view of every numeric parameter."""
        out: dict[str, float] = {}
        for f in self.features:
            for k, v in f.params.items():
                if isinstance(v, (int, float)) and not isinstance(v, bool):
                    out[f"{f.id}.{k}"] = float(v)
        return out

    def with_params(self, flat: dict[str, float]) -> "FeatureTree":
        """Return a copy with numeric parameters replaced from a flat mapping."""
        tree = FeatureTree.from_dict(self.to_dict())
        for key, value in flat.items():
            fid, _, pname = key.partition(".")
            tree.get(fid).params[pname] = float(value)
        tree.validate()
        return tree

    # ---- validation ---------------------------------------------------------------
    def validate(self) -> "FeatureTree":
        ids = [f.id for f in self.features]
        if len(set(ids)) != len(ids):
            raise FeatureTreeError("feature ids must be unique")
        base = self.base
        for f in self.features:
            if f.type not in SCHEMA:
                raise FeatureTreeError(f"{f.id}: unknown feature type {f.type!r}")
            numeric, strings = SCHEMA[f.type]
            required = list(numeric)
            if f.type == "hole":
                parent = self.get(f.parent) if f.parent else base
                if parent.type == "flange":
                    required += ["u", "v"]
                elif parent.type == "base_plate":
                    required += ["x", "y"]
                else:
                    raise FeatureTreeError(f"{f.id}: a hole must sit on the base or a flange")
            for name in required:
                value = f.params.get(name)
                if not isinstance(value, (int, float)) or isinstance(value, bool):
                    raise FeatureTreeError(f"{f.id}: missing numeric parameter {name!r}")
                if name not in _SIGNED and value <= 0:
                    raise FeatureTreeError(f"{f.id}: {name} must be positive, got {value}")
            for name, allowed in strings.items():
                if f.params.get(name) not in allowed:
                    raise FeatureTreeError(f"{f.id}: {name} must be one of {allowed}")
            if f.type != "base_plate":
                if f.parent is None:
                    f.parent = base.id
                if f.parent not in ids:
                    raise FeatureTreeError(f"{f.id}: unknown parent {f.parent!r}")
        if len(self.of_type("flange")) > 1:
            raise FeatureTreeError("v1 supports at most one flange")
        if len(self.of_type("fillet")) > 1:
            raise FeatureTreeError("v1 supports at most one corner fillet")
        b = base.params
        for fl in self.of_type("flange"):
            if fl.params["height"] <= b["thickness"]:
                raise FeatureTreeError(f"{fl.id}: flange height must exceed the base thickness")
        for fi in self.of_type("fillet"):
            if fi.params["radius"] * 2 >= min(b["length"], b["width"]):
                raise FeatureTreeError(f"{fi.id}: fillet radius too large for the plate")
        return self

    # ---- (de)serialisation ----------------------------------------------------------
    def to_dict(self) -> dict[str, Any]:
        return {
            "part_type": self.part_type,
            "units": self.units,
            "notes": self.notes,
            "features": [f.to_dict() for f in self.features],
            "meta": self.meta,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "FeatureTree":
        features = [
            Feature(id=f["id"], type=f["type"], params=dict(f.get("params", {})), parent=f.get("parent"))
            for f in data["features"]
        ]
        return cls(
            features=features,
            part_type=data.get("part_type", "part"),
            units=data.get("units", "mm"),
            notes=data.get("notes", ""),
            meta=dict(data.get("meta", {})),
        )

    def save(self, path: str | Path) -> None:
        Path(path).write_text(json.dumps(self.to_dict(), indent=2) + "\n", encoding="utf-8")

    @classmethod
    def load(cls, path: str | Path) -> "FeatureTree":
        return cls.from_dict(json.loads(Path(path).read_text(encoding="utf-8"))).validate()

    def describe(self) -> str:
        """Indented, human-readable outline of the tree."""
        lines: list[str] = []

        def fmt(f: Feature) -> str:
            parts = []
            for k, v in f.params.items():
                parts.append(f"{k}={v:g}" if isinstance(v, (int, float)) else f"{k}={v}")
            return f"{f.id} [{f.type}] " + ", ".join(parts)

        def walk(f: Feature, depth: int) -> None:
            lines.append("  " * depth + fmt(f))
            for child in self.children(f.id):
                walk(child, depth + 1)

        walk(self.base, 0)
        return "\n".join(lines)


def snap_value(value: float, step: float, tolerance: float = 0.35) -> float:
    """Snap ``value`` to the nearest multiple of ``step`` when it is close enough.

    Designers pick round numbers; a measured 39.87 mm is almost certainly 40.
    ``tolerance`` is the largest deviation, as a fraction of ``step``, that we
    are willing to call measurement noise.
    """
    if step <= 0:
        return value
    nearest = round(value / step) * step
    return round(nearest, 6) if abs(nearest - value) <= tolerance * step else round(value, 3)


def snap_tree(tree: FeatureTree, step: float = 0.5, tolerance: float = 0.35) -> FeatureTree:
    """Design-intent pass: snap dimensions to round values and restore symmetry."""
    out = FeatureTree.from_dict(tree.to_dict())
    for f in out.features:
        for k, v in list(f.params.items()):
            if isinstance(v, (int, float)) and not isinstance(v, bool):
                f.params[k] = snap_value(float(v), step, tolerance)
    # Hole pairs that are nearly mirrored about the centre line are made exactly so.
    for parent in {f.parent for f in out.of_type("hole")}:
        holes = [f for f in out.of_type("hole") if f.parent == parent]
        axis = "u" if holes and "u" in holes[0].params else "x"
        if len(holes) == 2:
            a, b = holes
            if abs(a.params[axis] + b.params[axis]) <= step:
                half = snap_value((abs(a.params[axis]) + abs(b.params[axis])) / 2, step / 2, 0.5)
                a.params[axis] = -half if a.params[axis] < 0 else half
                b.params[axis] = -half if b.params[axis] < 0 else half
    out.meta["snapped_to_mm"] = step
    return out.validate()
