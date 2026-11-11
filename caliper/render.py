"""Offscreen rendering of a triangle mesh with a real pinhole camera (VTK).

Used for the preview image every scan writes, and by the examples to render
synthetic "photos" of a known model.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np


@dataclass
class Camera:
    eye: tuple[float, float, float]
    target: tuple[float, float, float]
    up: tuple[float, float, float] = (0, 0, 1)
    fov_deg: float = 20.0  # vertical field of view

    def focal_px(self, image_height: int) -> float:
        return (image_height / 2) / math.tan(math.radians(self.fov_deg) / 2)

    def project(self, points, size: tuple[int, int]) -> np.ndarray:
        """Pinhole projection of world points to pixel coordinates, matching :func:`render_mesh`."""
        w, h = size
        eye = np.array(self.eye, dtype=float)
        forward = np.array(self.target, dtype=float) - eye
        forward /= np.linalg.norm(forward)
        right = np.cross(forward, np.array(self.up, dtype=float))
        right /= np.linalg.norm(right)
        up = np.cross(right, forward)
        p = np.asarray(points, dtype=float).reshape(-1, 3) - eye
        depth = p @ forward
        f = self.focal_px(h)
        return np.stack([w / 2 + f * (p @ right) / depth, h / 2 - f * (p @ up) / depth], axis=1)


def orbit_camera(center, radius: float, azimuth_deg: float, elevation_deg: float, fov_deg: float = 22.0) -> Camera:
    az, el = math.radians(azimuth_deg), math.radians(elevation_deg)
    eye = (
        center[0] + radius * math.cos(el) * math.cos(az),
        center[1] + radius * math.cos(el) * math.sin(az),
        center[2] + radius * math.sin(el),
    )
    return Camera(eye=eye, target=tuple(center), fov_deg=fov_deg)


def _polydata(vertices: np.ndarray, triangles: np.ndarray):
    import vtk
    from vtk.util import numpy_support

    points = vtk.vtkPoints()
    points.SetData(numpy_support.numpy_to_vtk(np.ascontiguousarray(vertices, dtype=np.float64), deep=True))
    cells = vtk.vtkCellArray()
    conn = numpy_support.numpy_to_vtkIdTypeArray(np.ascontiguousarray(triangles, dtype=np.int64).ravel(), deep=True)
    offsets = numpy_support.numpy_to_vtkIdTypeArray(np.arange(0, 3 * len(triangles) + 1, 3, dtype=np.int64), deep=True)
    cells.SetData(offsets, conn)
    poly = vtk.vtkPolyData()
    poly.SetPoints(points)
    poly.SetPolys(cells)
    return poly


def render_mesh(
    vertices: np.ndarray,
    triangles: np.ndarray,
    camera: Camera,
    size: tuple[int, int] = (1200, 900),
    color: tuple[float, float, float] = (0.91, 0.47, 0.18),
    background: tuple[float, float, float] | None = (1, 1, 1),
    style: str = "studio",
    edges: bool = True,
    edge_color: tuple[float, float, float] = (0.08, 0.1, 0.13),
) -> np.ndarray:
    """Render to an ``(H, W, 4)`` uint8 RGBA array.

    ``style="headlight"`` lights the part from the camera with no specular, so the
    face you are looking at is the brightest; ``style="studio"`` is a softer
    three-light look with outlined edges for previews and figures.
    ``background=None`` gives a transparent background.
    """
    import vtk
    from vtk.util import numpy_support

    poly = _polydata(vertices, triangles)
    clean = vtk.vtkCleanPolyData()
    clean.SetInputData(poly)
    normals = vtk.vtkPolyDataNormals()
    normals.SetInputConnection(clean.GetOutputPort())
    normals.SetFeatureAngle(35.0)
    normals.SplittingOn()
    normals.ConsistencyOff()
    normals.AutoOrientNormalsOff()

    mapper = vtk.vtkPolyDataMapper()
    mapper.SetInputConnection(normals.GetOutputPort())
    actor = vtk.vtkActor()
    actor.SetMapper(mapper)
    prop = actor.GetProperty()
    prop.SetColor(*color)

    renderer = vtk.vtkRenderer()
    renderer.AddActor(actor)
    renderer.SetBackground(*(background or (0, 0, 0)))
    renderer.SetBackgroundAlpha(0.0 if background is None else 1.0)

    if style == "headlight":
        prop.SetAmbient(0.12)
        prop.SetDiffuse(0.88)
        prop.SetSpecular(0.0)
        renderer.AutomaticLightCreationOff()
        light = vtk.vtkLight()
        light.SetLightTypeToHeadlight()
        renderer.AddLight(light)
    else:
        prop.SetAmbient(0.22)
        prop.SetDiffuse(0.8)
        prop.SetSpecular(0.12)
        prop.SetSpecularPower(24)
        renderer.AutomaticLightCreationOff()
        kit = vtk.vtkLightKit()
        kit.SetKeyLightIntensity(0.95)
        kit.SetKeyToFillRatio(2.6)
        kit.SetKeyToHeadRatio(5.0)
        kit.SetKeyToBackRatio(4.0)
        kit.SetKeyLightWarmth(0.55)
        kit.SetFillLightWarmth(0.45)
        kit.AddLightsToRenderer(renderer)

    if edges:
        feature = vtk.vtkFeatureEdges()
        feature.SetInputConnection(clean.GetOutputPort())
        feature.BoundaryEdgesOn()
        feature.FeatureEdgesOn()
        feature.ManifoldEdgesOff()
        feature.NonManifoldEdgesOff()
        feature.SetFeatureAngle(35.0)
        feature.ColoringOff()
        edge_mapper = vtk.vtkPolyDataMapper()
        edge_mapper.SetInputConnection(feature.GetOutputPort())
        edge_mapper.SetResolveCoincidentTopologyToPolygonOffset()
        edge_actor = vtk.vtkActor()
        edge_actor.SetMapper(edge_mapper)
        edge_actor.GetProperty().SetColor(*edge_color)
        edge_actor.GetProperty().SetLineWidth(max(1.0, size[1] / 500))
        edge_actor.GetProperty().LightingOff()
        renderer.AddActor(edge_actor)

    window = vtk.vtkRenderWindow()
    window.SetOffScreenRendering(1)
    window.SetMultiSamples(8)
    window.SetAlphaBitPlanes(1)
    window.AddRenderer(renderer)
    window.SetSize(int(size[0]), int(size[1]))

    cam = renderer.GetActiveCamera()
    cam.SetPosition(*camera.eye)
    cam.SetFocalPoint(*camera.target)
    cam.SetViewUp(*camera.up)
    cam.SetViewAngle(camera.fov_deg)
    renderer.ResetCameraClippingRange()
    window.Render()

    grab = vtk.vtkWindowToImageFilter()
    grab.SetInput(window)
    grab.SetInputBufferTypeToRGBA()
    grab.ReadFrontBufferOff()
    grab.Update()
    image = grab.GetOutput()
    w, h, _ = image.GetDimensions()
    array = numpy_support.vtk_to_numpy(image.GetPointData().GetScalars()).reshape(h, w, -1)
    window.Finalize()
    return np.ascontiguousarray(array[::-1]).astype(np.uint8)


def preview(vertices: np.ndarray, triangles: np.ndarray, path, size=(1200, 900), azimuth=-55.0, elevation=28.0, **kwargs) -> None:
    """Write an isometric-ish preview PNG framed on the mesh."""
    from PIL import Image

    lo, hi = vertices.min(axis=0), vertices.max(axis=0)
    center = (lo + hi) / 2
    radius = float(np.linalg.norm(hi - lo)) / 2
    fov = 22.0
    distance = radius / math.sin(math.radians(fov) / 2) * 1.08
    cam = orbit_camera(center, distance, azimuth, elevation, fov)
    Image.fromarray(render_mesh(vertices, triangles, cam, size=size, **kwargs)).save(path)
