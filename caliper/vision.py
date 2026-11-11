"""Claude describer: photos + reference -> feature tree, via vision and structured output.

Claude is asked for *design intent*: which features exist, how they relate and
what each dimension most plausibly is. When the classical measurer managed to
read the photos, its numbers are passed along as evidence so Claude can anchor
on measured values and spend its judgement on structure.
"""

from __future__ import annotations

import base64
import json
from typing import Any

import numpy as np

from .calibration import Reference
from .features import EDGES, Feature, FeatureTree
from .ingest import Photo

MODEL = "claude-fable-5-2"
MAX_EDGE_PX = 1568

_NUM = {"type": "number"}
FEATURE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "part_type": {"type": "string", "description": "bracket, plate, mount, clip, knob..."},
        "notes": {"type": "string", "description": "Assumptions, and anything the photos did not show."},
        "features": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "string"},
                    "type": {"type": "string", "enum": ["base_plate", "fillet", "flange", "hole", "slot", "boss"]},
                    "parent": {"type": "string", "description": "id of the feature this one sits on; empty for the base plate"},
                    "edge": {"type": "string", "enum": ["", *EDGES], "description": "flange only"},
                    "corners": {"type": "string", "enum": ["", "all", "free"], "description": "fillet only"},
                    "length": _NUM,
                    "width": _NUM,
                    "thickness": _NUM,
                    "height": _NUM,
                    "diameter": _NUM,
                    "radius": _NUM,
                    "bore": _NUM,
                    "angle": _NUM,
                    "x": _NUM,
                    "y": _NUM,
                    "u": _NUM,
                    "v": _NUM,
                },
                "required": ["id", "type", "parent", "edge", "corners", "length", "width", "thickness", "height", "diameter", "radius", "bore", "angle", "x", "y", "u", "v"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["part_type", "notes", "features"],
    "additionalProperties": False,
}

SYSTEM = """You reverse-engineer simple prismatic parts from photos into a parametric feature tree.

Conventions (millimetres):
- Exactly one base_plate, centred on the origin in X and Y, sitting on Z = 0. length is along X, width along Y, thickness along Z. In the top view, image right is +X and image up is +Y.
- fillet: rounded vertical corners of the base plate. corners is "all", or "free" for only the corners not under a flange.
- flange: a wall standing on one base edge (edge is +y, -y, +x or -x). height is measured from Z = 0 and so includes the base thickness.
- hole: a through hole. On the base plate give x and y from the plate centre. On a flange give u (along the edge, from its centre) and v (height above Z = 0).
- slot: a through slot in the base: x, y, overall length, width, angle in degrees from +X.
- boss: a round boss on the base: x, y, diameter, height above the plate, bore (0 if solid).
Set every field a feature type does not use to 0 (numbers) or "" (strings).

How to work:
- The reference measurement is the only ground truth for scale. Derive every dimension from it by proportion; do not guess absolute sizes from how the part looks.
- If measured values are supplied, trust them over your own reading of the pixels unless they are plainly inconsistent with the photos, and say so in notes when you depart from them.
- Capture design intent: symmetric hole patterns stay symmetric, and equal features get equal dimensions.
- Only describe features you can actually see. Put assumptions and anything hidden in notes.
- v1 handles simple prismatic parts. If the part has curved surfaces, threads or snap fits, model the prismatic envelope and say what was left out."""

_USED = {
    "base_plate": ("length", "width", "thickness"),
    "fillet": ("radius", "corners"),
    "flange": ("height", "thickness", "edge"),
    "slot": ("x", "y", "length", "width", "angle"),
    "boss": ("x", "y", "diameter", "height", "bore"),
}


def encode_photo(photo: Photo) -> dict[str, Any]:
    """Downscale to the vision size limit and return an image content block."""
    import cv2

    image = photo.image
    h, w = image.shape[:2]
    scale = MAX_EDGE_PX / max(h, w)
    if scale < 1:
        image = cv2.resize(image, (round(w * scale), round(h * scale)), interpolation=cv2.INTER_AREA)
    ok, buffer = cv2.imencode(".jpg", image, [cv2.IMWRITE_JPEG_QUALITY, 90])
    if not ok:
        raise RuntimeError(f"could not encode {photo.path}")
    data = base64.standard_b64encode(np.asarray(buffer).tobytes()).decode("ascii")
    return {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": data}}


def build_request(photos: list[Photo], reference: Reference, measured: FeatureTree | None = None) -> dict[str, Any]:
    """The full Messages API request, kept separate from the call so it can be tested."""
    content: list[dict[str, Any]] = []
    for photo in photos:
        content.append({"type": "text", "text": f"Photo: {photo.path.name} ({photo.view} view)"})
        content.append(encode_photo(photo))
    text = f"Reference measurement: {reference.raw} ({reference.kind.replace('_', ' ')} = {reference.value_mm:g} mm).\n"
    if measured is not None:
        text += (
            "\nA classical edge-based measurer read these values from the photos (mm). Treat them as evidence:\n"
            + json.dumps(measured.to_dict()["features"], indent=1)
            + "\n"
        )
    text += "\nReturn the feature tree for this part."
    content.append({"type": "text", "text": text})
    return {
        "model": MODEL,
        "max_tokens": 16000,
        "system": SYSTEM,
        "messages": [{"role": "user", "content": content}],
        "output_config": {"effort": "high", "format": {"type": "json_schema", "schema": FEATURE_SCHEMA}},
        # If a safety classifier declines the request, let the API re-run it on its default fallback model.
        "betas": ["server-side-fallback-2026-07-01"],
        "fallbacks": "default",
    }


def tree_from_response(data: dict[str, Any]) -> FeatureTree:
    """Turn the flat structured output into a validated feature tree."""
    raw = data["features"]
    types = {f["id"]: f["type"] for f in raw}
    features = []
    for f in raw:
        kind = f["type"]
        if kind == "hole":
            names = ("u", "v", "diameter") if types.get(f["parent"]) == "flange" else ("x", "y", "diameter")
        else:
            names = _USED[kind]
        params = {n: f[n] for n in names}
        features.append(Feature(id=f["id"], type=kind, params=params, parent=f["parent"] or None))
    tree = FeatureTree(features=features, part_type=data.get("part_type", "part"), notes=data.get("notes", ""), meta={"describer": MODEL})
    return tree.validate()


def describe_with_claude(photos: list[Photo], reference: Reference, measured: FeatureTree | None = None, client: Any = None) -> FeatureTree:
    """Ask Claude for the feature tree. Needs ANTHROPIC_API_KEY (or an `ant auth login` profile)."""
    if client is None:
        import anthropic

        client = anthropic.Anthropic()
    response = client.beta.messages.create(**build_request(photos, reference, measured))
    if response.stop_reason == "refusal":
        raise RuntimeError("Claude declined to describe these photos")
    if response.stop_reason == "max_tokens":
        raise RuntimeError("Claude's answer was cut off; try fewer or smaller photos")
    text = next(block.text for block in response.content if block.type == "text")
    return tree_from_response(json.loads(text))
