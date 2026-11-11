"""Render three synthetic 'phone photos' of the ground-truth bracket.

The camera is a real pinhole at arm's length, deliberately not quite square to
the part (about a degree of tilt, a couple of degrees of roll), and the frames
get lens blur, sensor noise, vignetting and JPEG compression. No dimension is
written anywhere in the images.
"""

import math
import sys
from pathlib import Path

import numpy as np
from PIL import Image

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from caliper.export import tessellate  # noqa: E402
from caliper.render import Camera, render_mesh  # noqa: E402
from ground_truth import TRUTH, make_bracket  # noqa: E402

SIZE = (2000, 1500)
FOV = 20.0
PART_COLOR = (0.91, 0.47, 0.18)
DESK = (0.80, 0.82, 0.84)


def roll(up, forward, degrees):
    """Rotate the up vector about the viewing direction."""
    up, forward = np.array(up, float), np.array(forward, float)
    forward /= np.linalg.norm(forward)
    a = math.radians(degrees)
    return tuple(up * math.cos(a) + np.cross(forward, up) * math.sin(a))


CAMERAS = {
    # straight down, from 385 mm
    "top": Camera(eye=(6, -7, 385), target=(1, -2, 5), up=roll((0, 1, 0), (0, 0, -1), 2.5), fov_deg=FOV),
    # end-on, looking along -X at the L-shaped end face
    "side": Camera(eye=(420, 4, 23), target=(40, 1, 20), up=roll((0, 0, 1), (-1, 0, 0), -1.8), fov_deg=FOV),
    # looking along +Y at the inner face of the flange
    "front": Camera(eye=(3, -405, 27), target=(0, 20, 22), up=roll((0, 0, 1), (0, 1, 0), 1.2), fov_deg=FOV),
}


def photograph(rgba: np.ndarray, rng: np.random.Generator) -> Image.Image:
    import cv2

    img = rgba[..., :3].astype(np.float32)
    h, w = img.shape[:2]
    yy, xx = np.mgrid[0:h, 0:w]
    r2 = ((xx - w / 2) / (w / 2)) ** 2 + ((yy - h / 2) / (h / 2)) ** 2
    img *= (1 - 0.06 * r2)[..., None]  # vignette
    img = cv2.GaussianBlur(img, (0, 0), 0.8)  # lens softness
    img += rng.normal(0, 1.6, img.shape)  # sensor noise
    return Image.fromarray(np.clip(img, 0, 255).astype(np.uint8))


def main(out_dir=HERE / "photos"):
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    vertices, triangles = tessellate(make_bracket(), tolerance=0.005, angular_tolerance=0.05)
    rng = np.random.default_rng(7)
    focal_35 = round(43.2666 / (2 * math.tan(math.radians(FOV) / 2)) * SIZE[1] / math.hypot(*SIZE))
    for name, camera in CAMERAS.items():
        rgba = render_mesh(vertices, triangles, camera, size=SIZE, color=PART_COLOR, background=DESK, style="headlight", edges=False)
        image = photograph(rgba, rng)
        exif = Image.Exif()
        exif_ifd = exif.get_ifd(0x8769)
        exif_ifd[0xA405] = int(focal_35)
        exif[0x8769] = exif_ifd
        image.save(out_dir / f"{name}.jpg", quality=92, exif=exif)
        print(f"wrote {out_dir / (name + '.jpg')}")
    return TRUTH


if __name__ == "__main__":
    main()
