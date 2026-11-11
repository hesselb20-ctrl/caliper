"""Generate every README image, in code, from the bracket example's real output.

    python scripts/make_media.py            # hero.png, how-it-works.svg, feature-tree.svg, accuracy.png
    python scripts/make_media.py --frames   # also the pre-rendered frames the tutorial video uses

Colours and type sizes come from media/theme.json, which the Remotion tutorial reads too.
Run examples/bracket/run_example.py first: the numbers drawn here are read from its output.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

ROOT = Path(__file__).resolve().parents[1]
MEDIA = ROOT / "media"
EXAMPLE = ROOT / "examples" / "bracket"
FRAMES = ROOT / "tutorial" / "public" / "frames"
sys.path.insert(0, str(EXAMPLE))

THEME = json.loads((MEDIA / "theme.json").read_text(encoding="utf-8"))
C = THEME["color"]
SCALE = THEME["type"]["scale"]
SANS, MONO = THEME["type"]["sans"], THEME["type"]["mono"]


def rgb(hex_color: str) -> tuple[int, int, int]:
    h = hex_color.lstrip("#")
    return tuple(int(h[i : i + 2], 16) for i in (0, 2, 4))


def unit(hex_color: str) -> tuple[float, float, float]:
    return tuple(v / 255 for v in rgb(hex_color))


def font(kind: str, px: int) -> ImageFont.FreeTypeFont:
    """Segoe UI / Consolas when present (Windows), DejaVu otherwise."""
    candidates = {
        "regular": ["segoeui.ttf", "DejaVuSans.ttf"],
        "semibold": ["seguisb.ttf", "DejaVuSans-Bold.ttf"],
        "bold": ["segoeuib.ttf", "DejaVuSans-Bold.ttf"],
        "mono": ["consola.ttf", "DejaVuSansMono.ttf"],
    }[kind]
    for name in candidates:
        try:
            return ImageFont.truetype(name, px)
        except OSError:
            continue
    return ImageFont.load_default(px)


def load_example():
    from caliper.features import FeatureTree

    tree = FeatureTree.load(EXAMPLE / "out" / "feature_tree.json")
    accuracy = json.loads((EXAMPLE / "accuracy.json").read_text(encoding="utf-8"))
    return tree, accuracy


def example_mesh():
    from caliper.export import read_stl

    return read_stl(EXAMPLE / "out" / "part.stl")


def framed_camera(vertices, azimuth, elevation, fov=22.0, margin=1.12):
    from caliper.render import orbit_camera

    lo, hi = vertices.min(axis=0), vertices.max(axis=0)
    center = (lo + hi) / 2
    radius = float(np.linalg.norm(hi - lo)) / 2
    return orbit_camera(center, radius / math.sin(math.radians(fov) / 2) * margin, azimuth, elevation, fov)


# ---- hero.png -----------------------------------------------------------------------------------


def dimension(draw, a, b, label, f, color, offset=(0, 0), line=None):
    """A dimension line between two pixel points with end ticks and a pill label."""
    ax, ay = a
    bx, by = b
    if line:  # a line that crosses the part gets a dark casing so it stays visible
        draw.line([a, b], fill=rgb(C["bg"]), width=9)
    draw.line([a, b], fill=line or color, width=3)
    length = math.hypot(bx - ax, by - ay)
    nx, ny = -(by - ay) / length, (bx - ax) / length
    for px, py in (a, b):
        draw.line([(px - nx * 9, py - ny * 9), (px + nx * 9, py + ny * 9)], fill=color, width=3)
    mx, my = (ax + bx) / 2 + offset[0], (ay + by) / 2 + offset[1]
    box = draw.textbbox((0, 0), label, font=f)
    tw, th = box[2] - box[0], box[3] - box[1]
    pad = 10
    draw.rounded_rectangle([mx - tw / 2 - pad, my - th / 2 - pad, mx + tw / 2 + pad, my + th / 2 + pad], 10, fill=rgb(C["bg"]), outline=color, width=2)
    draw.text((mx - tw / 2, my - th / 2 - box[1]), label, font=f, fill=rgb(C["text"]))


def make_hero(tree) -> Path:
    from caliper.render import render_mesh

    W, H = 1660, 760
    img = Image.new("RGB", (W, H), rgb(C["bg"]))
    # Soft glow behind the model so it sits on the dark ground.
    glow = Image.new("RGB", (W, H), rgb(C["bg"]))
    ImageDraw.Draw(glow).ellipse([930, 150, 1610, 700], fill=rgb(C["panelRaised"]))
    img = Image.blend(img, glow.filter(ImageFilter.GaussianBlur(120)), 0.9)
    draw = ImageDraw.Draw(img)

    # A faint millimetre grid: the visual idea of the project.
    for x in range(0, W, 40):
        draw.line([(x, 0), (x, H)], fill=(20, 26, 33), width=1)
    for y in range(0, H, 40):
        draw.line([(0, y), (W, y)], fill=(20, 26, 33), width=1)

    # Model render with real dimension callouts.
    vertices, triangles = example_mesh()
    size = (820, 680)
    camera = framed_camera(vertices, -58, 27, margin=1.2)
    model = Image.fromarray(render_mesh(vertices, triangles, camera, size=size, color=unit(C["part"]), background=None, style="studio"))
    ox, oy = 850, 60
    img.paste(model, (ox, oy), model)
    draw = ImageDraw.Draw(img)
    p = tree.params()
    L, Wd, fh = p["base.length"], p["base.width"], p["flange.height"]

    def px(point):
        x, y = camera.project(point, size)[0]
        return (ox + x, oy + y)

    f_dim = font("mono", SCALE["label"] * 2 - 8)
    blue = rgb(C["measure"])
    dimension(draw, px((-L / 2, -Wd / 2 - 9, 0)), px((L / 2, -Wd / 2 - 9, 0)), f"{L:g}", f_dim, blue)
    dimension(draw, px((L / 2 + 9, -Wd / 2, 0)), px((L / 2 + 9, Wd / 2, 0)), f"{Wd:g}", f_dim, blue)
    dimension(draw, px((-L / 2 - 7, Wd / 2, 0)), px((-L / 2 - 7, Wd / 2, fh)), f"{fh:g}", f_dim, blue)
    T = p["base.thickness"]
    h1, h2 = px((p["h1.x"], p["h1.y"], T)), px((p["h2.x"], p["h2.y"], T))
    dimension(draw, h1, h2, f"{abs(p['h2.x'] - p['h1.x']):g} ref", f_dim, rgb(C["accent"]), offset=(0, 46), line=rgb(C["text"]))

    # Left column: wordmark, tagline, command.
    x0 = 84
    draw.text((x0, 86), "caliper", font=font("bold", 132), fill=rgb(C["text"]))
    # the wordmark's caliper jaws: two ticks and a rule under the word
    draw.line([(x0 + 4, 262), (x0 + 430, 262)], fill=rgb(C["accent"]), width=6)
    for tx in (x0 + 4, x0 + 430):
        draw.line([(tx, 246), (tx, 278)], fill=rgb(C["accent"]), width=6)
    f_tag = font("semibold", SCALE["title"] * 2 - 8)
    draw.text((x0, 312), "Photos and one known", font=f_tag, fill=rgb(C["text"]))
    draw.text((x0, 372), "measurement in.", font=f_tag, fill=rgb(C["text"]))
    draw.text((x0, 432), "Parametric CAD out.", font=f_tag, fill=rgb(C["accent"]))

    f_cmd = font("mono", SCALE["body"] * 2 - 2)
    command = 'caliper scan photos/ --ref "hole spacing 40mm" --out part/'
    cw = draw.textlength("$ " + command, font=f_cmd)
    draw.rounded_rectangle([x0, 536, x0 + cw + 56, 606], 14, fill=rgb(C["panel"]), outline=rgb(C["line"]), width=2)
    draw.text((x0 + 28, 555), "$", font=f_cmd, fill=rgb(C["muted"]))
    draw.text((x0 + 28 + draw.textlength("$ ", font=f_cmd), 555), command, font=f_cmd, fill=rgb(C["text"]))

    f_cap = font("regular", SCALE["caption"] * 2)
    draw.text((x0, 640), "STEP  ·  STL  ·  params.json  ·  editable CadQuery", font=f_cap, fill=rgb(C["muted"]))

    out = MEDIA / "hero.png"
    img.save(out, optimize=True)
    return out


# ---- how-it-works.svg ---------------------------------------------------------------------------


def svg_header(width: int, height: int, label: str) -> list[str]:
    return [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" width="{width}" height="{height}" role="img" aria-label="{label}">',
        "<style>",
        f"  text {{ font-family: {SANS}; fill: {C['text']}; }}",
        f"  .mono {{ font-family: {MONO}; }}",
        f"  .muted {{ fill: {C['muted']}; }}",
        f"  .accent {{ fill: {C['accent']}; }}",
        f"  .measure {{ fill: {C['measure']}; }}",
        f"  .caption {{ font-size: {SCALE['caption']}px; }}",
        f"  .body {{ font-size: {SCALE['body']}px; }}",
        f"  .label {{ font-size: {SCALE['label']}px; font-weight: 600; }}",
        "</style>",
        f'<rect width="{width}" height="{height}" rx="14" fill="{C["bg"]}"/>',
    ]


def make_how_it_works() -> Path:
    W, H = 830, 236
    card_w, card_h, gap, top = 138, 176, 22, 30
    left = (W - 5 * card_w - 4 * gap) / 2
    s = svg_header(W, H, "How caliper works: photos and a reference measurement, scale calibration, feature tree, CadQuery code, STEP and STL files")
    stroke = f'fill="none" stroke="{C["text"]}" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"'
    acc = f'fill="none" stroke="{C["accent"]}" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"'
    blue = f'fill="none" stroke="{C["measure"]}" stroke-width="1.6" stroke-linecap="round"'
    icons = [
        # photos + reference
        f'<rect x="18" y="10" width="46" height="34" rx="4" {stroke} opacity="0.45"/>'
        f'<rect x="8" y="18" width="46" height="34" rx="4" fill="{C["panel"]}" stroke="{C["text"]}" stroke-width="1.6"/>'
        f'<circle cx="22" cy="35" r="4" {acc}/><circle cx="40" cy="35" r="4" {acc}/>'
        f'<path d="M22 46 H40 M22 43 V49 M40 43 V49" {blue}/>',
        # scale: a rule with ticks
        f'<path d="M6 40 H66" {stroke}/>'
        + "".join(f'<path d="M{6 + i * 6} 40 V{28 if i % 5 == 0 else 34}" {stroke}/>' for i in range(11))
        + f'<path d="M6 18 H36 M6 14 V22 M36 14 V22" {acc}/>',
        # feature tree
        f'<rect x="24" y="8" width="24" height="14" rx="3" {acc}/>'
        f'<path d="M36 22 V32 M12 32 H60 M12 32 V40 M36 32 V40 M60 32 V40" {stroke}/>'
        f'<rect x="3" y="40" width="18" height="12" rx="3" {stroke}/><rect x="27" y="40" width="18" height="12" rx="3" {stroke}/>'
        f'<rect x="51" y="40" width="18" height="12" rx="3" {stroke}/>',
        # code
        f'<path d="M20 16 L8 30 L20 44 M52 16 L64 30 L52 44" {stroke}/><path d="M42 12 L30 48" {acc}/>',
        # solid
        f'<path d="M36 8 L62 20 V42 L36 54 L10 42 V20 Z M10 20 L36 32 L62 20 M36 32 V54" {stroke}/>'
        f'<circle cx="36" cy="20" r="5" {acc}/>',
    ]
    steps = [
        ("Photos + reference", ["1 to 4 photos and one", "measurement you know"]),
        ("Scale", ["mm per pixel for each view,", "chained between views"]),
        ("Feature tree", ["plate, holes, fillets, flange,", "each with dimensions"]),
        ("CadQuery", ["readable model.py driven", "by params.json"]),
        ("STEP + STL", ["an editable solid and a", "mesh ready to print"]),
    ]
    for i, ((title, lines), icon) in enumerate(zip(steps, icons)):
        x = left + i * (card_w + gap)
        s.append(f'<g transform="translate({x:.1f} {top})">')
        s.append(f'<rect width="{card_w}" height="{card_h}" rx="10" fill="{C["panel"]}" stroke="{C["line"]}"/>')
        s.append(f'<text x="14" y="24" class="mono caption accent">0{i + 1}</text>')
        s.append(f'<g transform="translate({(card_w - 72) / 2:.1f} 34)">{icon}</g>')
        s.append(f'<text x="{card_w / 2}" y="118" text-anchor="middle" class="body" font-weight="600">{title}</text>')
        for j, line in enumerate(lines):
            s.append(f'<text x="{card_w / 2}" y="{138 + j * 16}" text-anchor="middle" class="muted" font-size="10.5">{line}</text>')
        s.append("</g>")
        if i < 4:
            ax = x + card_w + 4
            ay = top + card_h / 2
            s.append(f'<path d="M{ax:.1f} {ay} H{ax + gap - 9:.1f} M{ax + gap - 14:.1f} {ay - 4} L{ax + gap - 9:.1f} {ay} L{ax + gap - 14:.1f} {ay + 4}" fill="none" stroke="{C["muted"]}" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/>')
    s.append("</svg>")
    out = MEDIA / "how-it-works.svg"
    out.write_text("\n".join(s) + "\n", encoding="utf-8")
    return out


# ---- feature-tree.svg ---------------------------------------------------------------------------


def make_feature_tree(tree) -> Path:
    W, H = 830, 500
    p = tree.params()
    L, Wd, T = p["base.length"], p["base.width"], p["base.thickness"]
    r, fh, ft = p["fillet.radius"], p["flange.height"], p["flange.thickness"]
    k = 3.3  # px per mm
    s = svg_header(W, H, "Annotated example: the bracket's feature tree next to a dimensioned drawing of the part")
    part = f'fill="{C["panelRaised"]}" stroke="{C["text"]}" stroke-width="1.6" stroke-linejoin="round"'
    hole = f'fill="{C["bg"]}" stroke="{C["text"]}" stroke-width="1.4"'
    dim = f'fill="none" stroke="{C["measure"]}" stroke-width="1.1"'
    ref = f'fill="none" stroke="{C["accent"]}" stroke-width="1.4"'

    def badge(x, y, n):
        return (
            f'<circle cx="{x:.1f}" cy="{y:.1f}" r="9" fill="{C["accent"]}"/>'
            f'<text x="{x:.1f}" y="{y + 4:.1f}" text-anchor="middle" font-size="11" font-weight="700" style="fill:{C["bg"]}">{n}</text>'
        )

    def hdim(x1, x2, y, label, style=dim, cls="measure", above=True):
        ty = y - 6 if above else y + 15
        return (
            f'<path d="M{x1:.1f} {y} H{x2:.1f} M{x1:.1f} {y - 5} V{y + 5} M{x2:.1f} {y - 5} V{y + 5}" {style}/>'
            f'<text x="{(x1 + x2) / 2:.1f}" y="{ty}" text-anchor="middle" class="mono caption {cls}">{label}</text>'
        )

    def vdim(x, y1, y2, label):
        return (
            f'<path d="M{x} {y1:.1f} V{y2:.1f} M{x - 5} {y1:.1f} H{x + 5} M{x - 5} {y2:.1f} H{x + 5}" {dim}/>'
            f'<text x="{x - 8}" y="{(y1 + y2) / 2 + 4:.1f}" text-anchor="end" class="mono caption measure">{label}</text>'
        )

    # --- top view: origin at the plate centre, +y up ---
    cx, cy = 232, 150
    X = lambda x: cx + x * k  # noqa: E731
    Y = lambda y: cy - y * k  # noqa: E731
    s.append(f'<text x="64" y="38" class="caption muted" letter-spacing="1.2">TOP VIEW</text>')
    x0, x1, y0, y1 = X(-L / 2), X(L / 2), Y(Wd / 2), Y(-Wd / 2)
    rr = r * k
    s.append(f'<path d="M{x0:.1f} {y0:.1f} H{x1:.1f} V{y1 - rr:.1f} A{rr:.1f} {rr:.1f} 0 0 1 {x1 - rr:.1f} {y1:.1f} H{x0 + rr:.1f} A{rr:.1f} {rr:.1f} 0 0 1 {x0:.1f} {y1 - rr:.1f} Z" {part}/>')
    s.append(f'<rect x="{x0:.1f}" y="{y0:.1f}" width="{L * k:.1f}" height="{ft * k:.1f}" fill="{C["line"]}" stroke="{C["text"]}" stroke-width="1.6"/>')
    for name in ("h1", "h2"):
        s.append(f'<circle cx="{X(p[name + ".x"]):.1f}" cy="{Y(p[name + ".y"]):.1f}" r="{p[name + ".diameter"] / 2 * k:.1f}" {hole}/>')
    sl, sw = p["slot1.length"] * k, p["slot1.width"] * k
    s.append(f'<rect x="{X(p["slot1.x"]) - sl / 2:.1f}" y="{Y(p["slot1.y"]) - sw / 2:.1f}" width="{sl:.1f}" height="{sw:.1f}" rx="{sw / 2:.1f}" {hole}/>')
    s.append(hdim(x0, x1, y1 + 26, f"{L:g}", above=False))
    s.append(vdim(x0 - 22, y0, y1, f"{Wd:g}"))
    hy = Y(p["h1.y"])
    s.append(hdim(X(p["h1.x"]), X(p["h2.x"]), hy + 24, f"{abs(p['h2.x'] - p['h1.x']):g} reference", ref, "accent", above=False))
    s.append(f'<path d="M{X(p["h1.x"]):.1f} {hy + 14:.1f} V{hy + 29:.1f} M{X(p["h2.x"]):.1f} {hy + 14:.1f} V{hy + 29:.1f}" {ref} stroke-dasharray="2 3"/>')
    s.append(f'<text x="{X(p["h2.x"]) + 16:.1f}" y="{hy - 10:.1f}" class="mono caption measure">&#216;{p["h2.diameter"]:g}</text>')
    s.append(f'<text x="{x1 - rr - 4:.1f}" y="{y1 - rr + 2:.1f}" text-anchor="end" class="mono caption measure">R{r:g}</text>')
    s.append(badge(x0 + 18, y0 + ft * k + 20, 1))
    s.append(badge(x1 - 8, y1 - 8, 2))
    s.append(badge(x1 + 16, y0 + ft * k / 2, 3))
    s.append(badge(X(p["h1.x"]) - 22, hy - 6, 4))
    s.append(badge(X(p["h2.x"]) - 22, hy - 6, 5))
    s.append(badge(X(p["slot1.x"]) + sl / 2 + 16, Y(p["slot1.y"]), 6))

    # --- front view: looking at the inside of the flange, z up ---
    fx, fy = 232, 458  # centre x, baseline y (z = 0)
    FX = lambda u: fx + u * k  # noqa: E731
    FZ = lambda z: fy - z * k  # noqa: E731
    s.append(f'<text x="64" y="{FZ(fh) - 20:.1f}" class="caption muted" letter-spacing="1.2">FRONT VIEW</text>')
    s.append(f'<rect x="{FX(-L / 2):.1f}" y="{FZ(fh):.1f}" width="{L * k:.1f}" height="{fh * k:.1f}" {part}/>')
    s.append(f'<rect x="{FX(-L / 2):.1f}" y="{FZ(T):.1f}" width="{L * k:.1f}" height="{T * k:.1f}" fill="{C["line"]}" stroke="{C["text"]}" stroke-width="1.6"/>')
    for name in ("fh1", "fh2"):
        s.append(f'<circle cx="{FX(p[name + ".u"]):.1f}" cy="{FZ(p[name + ".v"]):.1f}" r="{p[name + ".diameter"] / 2 * k:.1f}" {hole}/>')
    s.append(vdim(FX(-L / 2) - 22, FZ(fh), FZ(0), f"{fh:g}"))
    s.append(hdim(FX(p["fh1.u"]), FX(p["fh2.u"]), FZ(p["fh1.v"]) - 22, f"{abs(p['fh2.u'] - p['fh1.u']):g}"))
    s.append(f'<text x="{FX(p["fh2.u"]) + 14:.1f}" y="{FZ(p["fh2.v"]) + 18:.1f}" class="mono caption measure">&#216;{p["fh2.diameter"]:g}</text>')
    s.append(badge(FX(p["fh1.u"]) - 20, FZ(p["fh1.v"]) + 2, 7))
    s.append(badge(FX(p["fh2.u"]) - 20, FZ(p["fh2.v"]) + 2, 8))
    s.append(f'<path d="M{FX(L / 2) + 22:.1f} {FZ(T):.1f} V{FZ(0):.1f} M{FX(L / 2) + 17:.1f} {FZ(T):.1f} H{FX(L / 2) + 27:.1f} M{FX(L / 2) + 17:.1f} {FZ(0):.1f} H{FX(L / 2) + 27:.1f}" {dim}/>')
    s.append(f'<text x="{FX(L / 2) + 32:.1f}" y="{FZ(T / 2) + 4:.1f}" class="mono caption measure">{T:g}</text>')

    # --- the tree itself ---
    px0, pw = 448, 352
    s.append(f'<rect x="{px0}" y="24" width="{pw}" height="{H - 48}" rx="10" fill="{C["panel"]}" stroke="{C["line"]}"/>')
    s.append(f'<text x="{px0 + 20}" y="52" class="mono caption muted">feature_tree.json</text>')
    rows = [
        (1, 0, "base", "base_plate", f"length {L:g}   width {Wd:g}   thickness {T:g}"),
        (2, 1, "fillet", "fillet", f"radius {r:g}   corners free"),
        (3, 1, "flange", "flange", f"height {fh:g}   thickness {ft:g}   edge +y"),
        (7, 2, "fh1", "hole", f"u {p['fh1.u']:g}   v {p['fh1.v']:g}   &#216; {p['fh1.diameter']:g}"),
        (8, 2, "fh2", "hole", f"u {p['fh2.u']:g}   v {p['fh2.v']:g}   &#216; {p['fh2.diameter']:g}"),
        (4, 1, "h1", "hole", f"x {p['h1.x']:g}   y {p['h1.y']:g}   &#216; {p['h1.diameter']:g}"),
        (5, 1, "h2", "hole", f"x {p['h2.x']:g}   y {p['h2.y']:g}   &#216; {p['h2.diameter']:g}"),
        (6, 1, "slot1", "slot", f"x {p['slot1.x']:g}   y {p['slot1.y']:g}   {p['slot1.length']:g} &#215; {p['slot1.width']:g}"),
    ]
    row_h, ry0 = 49, 92
    for i, (n, depth, fid, ftype, text) in enumerate(rows):
        y = ry0 + i * row_h
        x = px0 + 34 + depth * 26
        if depth:
            parent_x = px0 + 34 + (depth - 1) * 26
            parent_i = max(j for j in range(i) if rows[j][1] == depth - 1)
            s.append(f'<path d="M{parent_x} {ry0 + parent_i * row_h + 9} V{y - 4} H{x - 12}" fill="none" stroke="{C["line"]}" stroke-width="1.4"/>')
        s.append(badge(x, y - 4, n))
        s.append(f'<text x="{x + 18}" y="{y}" class="mono body" font-weight="700">{fid}</text>')
        s.append(f'<text x="{x + 18 + len(fid) * 8.6 + 10:.1f}" y="{y}" class="mono caption accent">{ftype}</text>')
        s.append(f'<text x="{x + 18}" y="{y + 18}" class="mono caption muted" xml:space="preserve">{text}</text>')
    s.append("</svg>")
    out = MEDIA / "feature-tree.svg"
    out.write_text("\n".join(s) + "\n", encoding="utf-8")
    return out


# ---- accuracy.png -------------------------------------------------------------------------------


def make_accuracy(accuracy) -> Path:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib import font_manager

    for name in ("Segoe UI", "DejaVu Sans"):
        if any(f.name == name for f in font_manager.fontManager.ttflist):
            plt.rcParams["font.family"] = name
            break
    mono = "Consolas" if any(f.name == "Consolas" for f in font_manager.fontManager.ttflist) else "DejaVu Sans Mono"

    rows = [r for r in accuracy["rows"] if not r["is_reference"]]
    rows.sort(key=lambda r: abs(r["error_mm"]), reverse=True)
    summary = accuracy["summary"]
    n = len(rows)
    px = 1 / 200
    fig = plt.figure(figsize=(1660 * px, 1000 * px), dpi=200, facecolor=C["bg"])
    ax = fig.add_axes([0.50, 0.105, 0.33, 0.70], facecolor=C["bg"])
    ys = np.arange(n)[::-1]
    limit = 0.6
    ax.axvspan(-0.2, 0.2, color=C["panelRaised"], zorder=0)
    ax.axvline(0, color=C["muted"], lw=0.8, zorder=1)
    for y, row in zip(ys, rows):
        ax.plot([0, row["error_mm"]], [y, y], color=C["accent"], lw=1.6, solid_capstyle="round", zorder=2)
    ax.scatter([r["error_mm"] for r in rows], ys, s=42, color=C["accent"], edgecolor=C["bg"], linewidth=1.2, zorder=3)
    ax.set_xlim(-limit, limit)
    ax.set_ylim(-0.7, n - 0.3)
    ax.set_yticks([])
    ax.set_xticks([-0.4, -0.2, 0, 0.2, 0.4])
    ax.set_xticklabels(["-0.4", "-0.2", "0", "+0.2", "+0.4"], color=C["muted"], fontsize=7, fontfamily=mono)
    ax.tick_params(axis="x", length=0, pad=5)
    ax.set_xlabel("error, mm (estimated minus true)", color=C["muted"], fontsize=7, labelpad=5)
    for spine in ax.spines.values():
        spine.set_visible(False)
    ax.grid(axis="x", color=C["line"], lw=0.5, zorder=0)
    ax.text(0, n - 0.35, "±0.2 mm", color=C["muted"], fontsize=6, ha="center", va="bottom", fontfamily=mono)

    # Table columns drawn in figure coordinates so they line up with the dot rows.
    def row_y(y):
        return ax.transData.transform((0, y))[1] / fig.bbox.height

    head_y = row_y(n - 1) + 0.052
    columns = [(0.045, "left", "Dimension"), (0.355, "right", "True"), (0.455, "right", "Estimated"), (0.955, "right", "Error")]
    for x, align, title in columns:
        fig.text(x, head_y, title, color=C["muted"], fontsize=7, ha=align, va="center")
    for y, row in zip(ys, rows):
        fy = row_y(y)
        fig.text(0.045, fy, row["label"], color=C["text"], fontsize=8, ha="left", va="center")
        fig.text(0.355, fy, f"{row['truth_mm']:.2f}", color=C["muted"], fontsize=8, ha="right", va="center", fontfamily=mono)
        fig.text(0.455, fy, f"{row['measured_mm']:.2f}", color=C["text"], fontsize=8, ha="right", va="center", fontfamily=mono)
        fig.text(0.955, fy, f"{row['error_mm']:+.2f} mm  {row['error_pct']:+.1f}%", color=C["text"], fontsize=8, ha="right", va="center", fontfamily=mono)
    fig.text(0.045, 0.935, "Estimated vs true dimensions", color=C["text"], fontsize=14, fontweight="bold", ha="left", va="center")
    fig.text(
        0.045,
        0.883,
        f"Synthetic bracket, {summary['dimensions_scored']} dimensions from 3 rendered photos and one reference (hole spacing 40 mm).  "
        f"Mean |error| {summary['mean_abs_error_mm']:.2f} mm, worst {summary['max_abs_error_mm']:.2f} mm.",
        color=C["muted"],
        fontsize=7,
        ha="left",
        va="center",
    )
    fig.text(0.045, 0.03, "Raw measurements from the offline classical describer, before snapping to round values. All values in mm.", color=C["muted"], fontsize=6, ha="left", va="center")
    out = MEDIA / "accuracy.png"
    fig.savefig(out, facecolor=C["bg"])
    plt.close(fig)
    return out


# ---- frames for the tutorial video -----------------------------------------------------------------


def make_frames(tree) -> None:
    import cadquery as cq

    from caliper.codegen import build
    from caliper.export import tessellate
    from caliper.render import render_mesh
    from ground_truth import make_bracket

    FRAMES.mkdir(parents=True, exist_ok=True)
    color = unit(C["part"])
    size = (900, 900)
    vertices, triangles = example_mesh()

    # 1. turntable of the generated STL
    turns = 120
    for i in range(turns):
        camera = framed_camera(vertices, -58 + 360 * i / turns, 27, margin=1.25)
        Image.fromarray(render_mesh(vertices, triangles, camera, size=size, color=color, background=None)).save(FRAMES / f"turn_{i:03d}.png", optimize=True)

    # 2. parameter edit: flange.height swept by really rebuilding the model each step
    start, end, steps = tree.params()["flange.height"], 60.0, 30
    tall = tessellate(build(tree.with_params({"flange.height": end})))[0]
    for i in range(steps + 1):
        height = start + (end - start) * i / steps
        v, t = tessellate(build(tree.with_params({"flange.height": height})))
        camera = framed_camera(tall, -58, 27, margin=1.25)  # fixed framing so only the part changes
        Image.fromarray(render_mesh(v, t, camera, size=size, color=color, background=None)).save(FRAMES / f"edit_{i:03d}.png", optimize=True)

    # 3. the broken original: the ground-truth bracket snapped along a jagged line
    whole = make_bracket()
    zig = [(-6, -40), (3, -18), (-4, -6), (5, 6), (-2, 16), (4, 40), (60, 40), (60, -40)]
    cutter = cq.Workplane("XY").polyline(zig).close().extrude(80).translate((8, 0, -10))
    right = whole.intersect(cutter).translate((5, -3, 0)).rotate((0, 0, 0), (0, 0, 1), -5)
    left = whole.cut(cutter)
    pieces = [tessellate(left), tessellate(right)]
    v = np.vstack([pieces[0][0], pieces[1][0]])
    t = np.vstack([pieces[0][1], pieces[1][1] + len(pieces[0][0])])
    camera = framed_camera(v, -58, 27, margin=1.25)
    Image.fromarray(render_mesh(v, t, camera, size=size, color=unit("#8F9AA8"), background=None)).save(FRAMES / "broken.png", optimize=True)

    # 4. the three photos, downscaled for the video
    for name in ("top", "side", "front"):
        photo = Image.open(EXAMPLE / "photos" / f"{name}.jpg")
        photo.resize((800, 600), Image.LANCZOS).save(FRAMES / f"photo_{name}.jpg", quality=90)

    # 5. the model growing feature by feature: each stage is a real build of a partial tree
    from caliper.features import FeatureTree
    from ground_truth import TRUTH
    from render_photos import CAMERAS, SIZE

    full_camera = framed_camera(vertices, -58, 27, margin=1.25)
    for i in range(len(tree.features)):
        partial = FeatureTree(features=tree.features[: i + 1]).validate()
        v, t = tessellate(build(partial))
        Image.fromarray(render_mesh(v, t, full_camera, size=size, color=color, background=None)).save(FRAMES / f"stage_{i:02d}.png", optimize=True)

    # 6. numbers the video quotes, straight from the example output
    accuracy = json.loads((EXAMPLE / "accuracy.json").read_text(encoding="utf-8"))
    calibration = json.loads((EXAMPLE / "out" / "calibration.json").read_text(encoding="utf-8"))
    report = json.loads((EXAMPLE / "out" / "report.json").read_text(encoding="utf-8")) if (EXAMPLE / "out" / "report.json").exists() else {}
    holes = [(-TRUTH["hole_spacing"] / 2, TRUTH["hole_y"], TRUTH["thickness"]), (TRUTH["hole_spacing"] / 2, TRUTH["hole_y"], TRUTH["thickness"])]
    ref_line = (CAMERAS["top"].project(holes, SIZE) / np.array(SIZE)).round(4).tolist()
    model_lines = (EXAMPLE / "out" / "model.py").read_text(encoding="utf-8").splitlines()
    start_line = next(i for i, line in enumerate(model_lines) if line.startswith("def build"))
    data = {
        "features": tree.to_dict()["features"],
        "params": tree.params(),
        "summary": accuracy["summary"],
        "scales": calibration["scales"],
        "dfm": report,
        "refLine": ref_line,
        "modelSource": model_lines[start_line : start_line + 22],
        "turnFrames": turns,
        "editFrames": steps + 1,
        "editTo": end,
    }
    (ROOT / "tutorial" / "src").mkdir(parents=True, exist_ok=True)
    (ROOT / "tutorial" / "src" / "example.json").write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--frames", action="store_true", help="also render the frames used by the tutorial video")
    args = parser.parse_args()
    tree, accuracy = load_example()
    for path in (make_hero(tree), make_how_it_works(), make_feature_tree(tree), make_accuracy(accuracy)):
        print(f"wrote {path.relative_to(ROOT)}")
    if args.frames:
        make_frames(tree)
        print(f"wrote frames to {FRAMES.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
