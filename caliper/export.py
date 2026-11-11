"""Build the solid and write STEP / STL; hand out a triangle mesh for checks and previews."""

from __future__ import annotations

from pathlib import Path

import numpy as np

from .codegen import build
from .features import FeatureTree


def tessellate(part, tolerance: float = 0.02, angular_tolerance: float = 0.1) -> tuple[np.ndarray, np.ndarray]:
    """Return ``(vertices (N, 3), triangles (M, 3))`` for a CadQuery workplane or shape."""
    shape = part.val() if hasattr(part, "val") else part
    vertices, triangles = shape.tessellate(tolerance, angular_tolerance)
    v = np.array([(p.x, p.y, p.z) for p in vertices], dtype=float)
    t = np.array(triangles, dtype=np.int64)
    return v, t


def export(tree: FeatureTree, out_dir: str | Path, stl_tolerance: float = 0.01) -> dict[str, Path]:
    """Build ``tree`` and write ``part.step`` and ``part.stl`` into ``out_dir``."""
    import cadquery as cq

    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    part = build(tree)
    paths = {"step": out / "part.step", "stl": out / "part.stl"}
    cq.exporters.export(part, str(paths["step"]))
    cq.exporters.export(part, str(paths["stl"]), tolerance=stl_tolerance, angularTolerance=0.1)
    return paths


def read_stl(path: str | Path) -> tuple[np.ndarray, np.ndarray]:
    """Minimal STL reader (binary or ASCII) returning an unindexed triangle soup."""
    data = Path(path).read_bytes()
    if len(data) >= 84:
        count = int.from_bytes(data[80:84], "little")
        if len(data) == 84 + count * 50:
            raw = np.frombuffer(data, dtype=np.dtype([("n", "<f4", 3), ("v", "<f4", (3, 3)), ("a", "<u2")]), offset=84, count=count)
            v = raw["v"].reshape(-1, 3).astype(float)
            return v, np.arange(len(v)).reshape(-1, 3)
    verts = [tuple(map(float, line.split()[1:4])) for line in data.decode("ascii", "ignore").splitlines() if line.strip().startswith("vertex")]
    v = np.array(verts, dtype=float)
    return v, np.arange(len(v)).reshape(-1, 3)


def mesh_volume(vertices: np.ndarray, triangles: np.ndarray) -> float:
    a, b, c = (vertices[triangles[:, i]] for i in range(3))
    return float(np.einsum("ij,ij->i", a, np.cross(b, c)).sum() / 6.0)
