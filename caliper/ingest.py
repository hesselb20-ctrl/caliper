"""Photo ingest: find 1-4 images, read them, and work out which view each one is."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np

IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tif", ".tiff"}
VIEW_KEYWORDS = {
    "top": ("top", "plan", "above"),
    "side": ("side", "end", "profile"),
    "front": ("front", "face", "elevation"),
    "iso": ("iso", "angle", "perspective", "3q"),
}
DEFAULT_ORDER = ("top", "side", "front", "iso")
MAX_PHOTOS = 4


@dataclass
class Photo:
    path: Path
    view: str
    image: np.ndarray  # BGR, uint8
    focal_35mm: float | None = None

    @property
    def size(self) -> tuple[int, int]:
        return self.image.shape[1], self.image.shape[0]


def guess_view(name: str) -> str | None:
    stem = name.lower()
    for view, words in VIEW_KEYWORDS.items():
        if any(w in stem for w in words):
            return view
    return None


def _exif_focal_35mm(path: Path) -> float | None:
    try:
        from PIL import Image

        with Image.open(path) as im:
            exif = im.getexif()
            value = exif.get_ifd(0x8769).get(0xA405)  # FocalLengthIn35mmFilm
            return float(value) if value else None
    except Exception:
        return None


def assign_views(names: list[str]) -> list[str]:
    """Views from file names; unnamed photos take the remaining views in order."""
    views: list[str | None] = [guess_view(n) for n in names]
    taken = {v for v in views if v}
    spare = [v for v in DEFAULT_ORDER if v not in taken]
    return [v if v else (spare.pop(0) if spare else "iso") for v in views]


def load_photos(folder: str | Path) -> list[Photo]:
    """Load the photos in ``folder`` (or a single image file)."""
    import cv2

    root = Path(folder)
    if root.is_file():
        files = [root]
    elif root.is_dir():
        files = sorted(p for p in root.iterdir() if p.suffix.lower() in IMAGE_SUFFIXES)
    else:
        raise FileNotFoundError(f"no such photo folder: {root}")
    if not files:
        raise FileNotFoundError(f"no images found in {root}")
    if len(files) > MAX_PHOTOS:
        raise ValueError(f"caliper takes 1-{MAX_PHOTOS} photos, found {len(files)} in {root}")
    photos = []
    for path, view in zip(files, assign_views([f.stem for f in files])):
        image = cv2.imdecode(np.fromfile(str(path), dtype=np.uint8), cv2.IMREAD_COLOR)
        if image is None:
            raise ValueError(f"could not read image {path}")
        photos.append(Photo(path=path, view=view, image=image, focal_35mm=_exif_focal_35mm(path)))
    return photos
