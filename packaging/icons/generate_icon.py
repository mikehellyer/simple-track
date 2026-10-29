"""One-off script: draws the Simple-Track app icon and exports every
size/format the platform installers need. Not part of the app itself and
not run automatically — re-run manually if the icon design ever changes.

Usage: venv/bin/python packaging/icons/generate_icon.py
"""
from __future__ import annotations

import math
import shutil
import subprocess
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

OUT_DIR = Path(__file__).parent
APP_RESOURCES = OUT_DIR.parent.parent / "src" / "simple_track" / "gui" / "resources"
SIZE = 1024

# A plan view of track, as Simple-Track draws it: a sleepered curve sweeping
# across a pale baseboard grid, with a point branching off it.
TILE_TOP = (232, 240, 226, 255)
TILE_BOTTOM = (206, 220, 196, 255)
GRID = (190, 205, 178, 255)
SLEEPER = (138, 122, 104, 255)
RAIL = (46, 50, 54, 255)
END = (240, 140, 26, 255)


def _arc(cx, cy, r, a0, a1, steps=120):
    return [(cx + r * math.cos(math.radians(a0 + (a1 - a0) * i / steps)),
             cy + r * math.sin(math.radians(a0 + (a1 - a0) * i / steps))) for i in range(steps + 1)]


def _track(d, points, s):
    """Sleepers across the line, then two rails along it."""
    for i in range(0, len(points) - 1, 6):
        (x0, y0), (x1, y1) = points[i], points[i + 1]
        dx, dy = x1 - x0, y1 - y0
        n = math.hypot(dx, dy) or 1
        nx, ny = -dy / n, dx / n
        ux, uy = dx / n, dy / n
        half, w = 9 * s, 1.6 * s
        d.polygon([(x0 + nx * half - ux * w, y0 + ny * half - uy * w), (x0 + nx * half + ux * w, y0 + ny * half + uy * w),
                   (x0 - nx * half + ux * w, y0 - ny * half + uy * w), (x0 - nx * half - ux * w, y0 - ny * half - uy * w)],
                  fill=SLEEPER)
    for side in (-1, 1):
        rail = []
        for i, (x, y) in enumerate(points):
            j = min(i + 1, len(points) - 1)
            k = max(i - 1, 0)
            dx, dy = points[j][0] - points[k][0], points[j][1] - points[k][1]
            n = math.hypot(dx, dy) or 1
            rail.append((x - dy / n * 5 * s * side, y + dx / n * 5 * s * side))
        d.line(rail, fill=RAIL, width=int(2.2 * s), joint="curve")


def draw_icon() -> Image.Image:
    tile = Image.new("RGBA", (SIZE, SIZE))
    td = ImageDraw.Draw(tile)
    for y in range(SIZE):
        t = y / SIZE
        td.line([(0, y), (SIZE, y)], fill=tuple(int(TILE_TOP[i] + (TILE_BOTTOM[i] - TILE_TOP[i]) * t) for i in range(3)) + (255,))
    mask = Image.new("L", (SIZE, SIZE), 0)
    margin = SIZE * 0.06
    ImageDraw.Draw(mask).rounded_rectangle([margin, margin, SIZE - margin, SIZE - margin], radius=SIZE * 0.22, fill=255)
    img = tile
    s = SIZE / 100
    d = ImageDraw.Draw(img)
    for g in range(0, 101, 12):
        d.line([(g * s, 0), (g * s, SIZE)], fill=GRID, width=max(1, int(0.3 * s)))
        d.line([(0, g * s), (SIZE, g * s)], fill=GRID, width=max(1, int(0.3 * s)))

    # the main line: a sweeping curve from bottom left to top right
    cx, cy, r = 96 * s, 100 * s, 66 * s
    main = _arc(cx, cy, r, 186, 262)
    # a point: a straight road leaving the curve on its outside
    a = math.radians(206)
    bx, by = cx + r * math.cos(a), cy + r * math.sin(a)
    tx, ty = -math.sin(a), math.cos(a)
    if ty > 0:
        tx, ty = -tx, -ty
    spur = [(bx + tx * 52 * s * i / 60, by + ty * 52 * s * i / 60) for i in range(61)]
    shadow = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    sd = ImageDraw.Draw(shadow)
    for line in (main, spur):
        sd.line([(x + 1.2 * s, y + 1.6 * s) for x, y in line], fill=(0, 0, 0, 90), width=int(19 * s))
    img.alpha_composite(shadow.filter(ImageFilter.GaussianBlur(SIZE * 0.012)))
    d = ImageDraw.Draw(img)
    _track(d, spur, s)
    _track(d, main, s)
    # the orange "build from here" end marker
    ex, ey = main[-1]
    d.ellipse([ex - 7 * s, ey - 7 * s, ex + 7 * s, ey + 7 * s], outline=END, width=int(2.4 * s))

    out = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    out.paste(img, (0, 0), mask)
    return out


def main() -> None:
    icon = draw_icon()
    master_png = OUT_DIR / "icon.png"
    icon.save(master_png)
    print(f"wrote {master_png}")

    APP_RESOURCES.mkdir(parents=True, exist_ok=True)
    icon.resize((256, 256), Image.LANCZOS).save(APP_RESOURCES / "icon.png")
    print(f"wrote {APP_RESOURCES / 'icon.png'}")

    # Windows .ico (multi-resolution)
    ico_sizes = [16, 24, 32, 48, 64, 128, 256]
    ico_path = OUT_DIR / "icon.ico"
    icon.save(ico_path, sizes=[(s, s) for s in ico_sizes])
    print(f"wrote {ico_path}")

    # Linux: a few common hicolor sizes as plain PNGs.
    for s in (16, 32, 48, 64, 128, 256, 512):
        icon.resize((s, s), Image.LANCZOS).save(OUT_DIR / f"icon_{s}.png")
    print("wrote icon_16..512.png")

    # macOS .icns: iconutil on a Mac; elsewhere Pillow's own ICNS writer is
    # good enough to commit, so CI on macOS always has a file to use.
    if sys.platform == "darwin" and shutil.which("iconutil"):
        iconset = OUT_DIR / "icon.iconset"
        iconset.mkdir(exist_ok=True)
        for s in (16, 32, 128, 256, 512):
            icon.resize((s, s), Image.LANCZOS).save(iconset / f"icon_{s}x{s}.png")
            icon.resize((s * 2, s * 2), Image.LANCZOS).save(iconset / f"icon_{s}x{s}@2x.png")
        subprocess.run(
            ["iconutil", "-c", "icns", str(iconset), "-o", str(OUT_DIR / "icon.icns")],
            check=True,
        )
        for f in iconset.iterdir():
            f.unlink()
        iconset.rmdir()
    else:
        icon.save(OUT_DIR / "icon.icns")
    print(f"wrote {OUT_DIR / 'icon.icns'}")


if __name__ == "__main__":
    main()
