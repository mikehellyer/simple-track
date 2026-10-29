"""Builds Simple-Track's track libraries from XTrackCAD parameter files.

XTrackCAD (https://sourceforge.net/projects/xtrkcad-fork/) publishes the
geometry of most manufacturers' track as .xtp parameter files. This reads the
ones listed in LIBRARIES and writes src/simple_track/core/libraries/*.json in
Simple-Track's own format (millimetres, maths angles, first connector at the
origin facing -x). Not part of the app; re-run it when a library needs
regenerating or a new one is added.

Usage: venv/bin/python tools/xtp_to_library.py <folder holding the .xtp files>

The .xtp files themselves are fetched from the XTrackCAD source tree,
app/lib/params/.
"""
from __future__ import annotations

import json
import math
import re
import shlex
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "src" / "simple_track" / "core" / "libraries"
INCH = 25.4

OO = {"scale": "OO", "gauge_mm": 16.5, "sleeper_mm": 28}
N = {"scale": "N", "gauge_mm": 9.0, "sleeper_mm": 15}

LIBRARIES = [
    {"file": "OO-HornbyOO.xtp", "id": "hornby-oo", "name": "Hornby OO", "manufacturer": "Hornby", **OO},
    {"file": "HO-Peco-Code100Setrack.xtp", "id": "peco-oo-setrack", "name": "Peco Setrack (OO/HO, code 100)",
     "manufacturer": "Peco", **OO},
    {"file": "HO-Peco-Code100Streamline.xtp", "id": "peco-oo-streamline-100",
     "name": "Peco Streamline (OO/HO, code 100)", "manufacturer": "Peco", **OO},
    {"file": "OO-Peco-Code75Bullhead.xtp", "id": "peco-oo-bullhead-75", "name": "Peco Bullhead (OO, code 75)",
     "manufacturer": "Peco", **OO},
    {"file": "N-PecoCode80Setrack.xtp", "id": "peco-n-setrack", "name": "Peco Setrack (N, code 80)",
     "manufacturer": "Peco", **N},
    {"file": "N-PecoCode80Streamline.xtp", "id": "peco-n-streamline-80", "name": "Peco Streamline (N, code 80)",
     "manufacturer": "Peco", **N},
    {"file": "N-PecoCode55Finescale.xtp", "id": "peco-n-finescale-55", "name": "Peco Finescale (N, code 55)",
     "manufacturer": "Peco", **N},
]

# Words dropped from XTrackCAD's section headings: the library name already says them.
_SECTION_NOISE = re.compile(
    r"\b(peco|hornby|n[- ]scale|ho[- ]scale|oo[- ]scale|ho|oo|n|code\s*\d+|streamline|setrack|finescale|"
    r"bullhead|scale|track)\b|[-–]", re.I)


_DECORATION = {"L", "L3", "A", "A3", "F", "F3", "F4", "Y", "Y3", "Y4", "G", "G3", "B", "B3",
               "Z", "Z3", "Q", "Q3", "J", "J3", "H", "M"}


def _section_name(text: str) -> str:
    cleaned = " ".join(_SECTION_NOISE.sub(" ", text).split()).lstrip("/0123456789 ")
    return cleaned[:1].upper() + cleaned[1:] if cleaned else "Straight"


def _code(part: str) -> str:
    return part.strip().replace("R.", "R")


def _r(value: float) -> float:
    return round(value, 3)


def parse_xtp(text: str) -> list[dict]:
    pieces: list[dict] = []
    section = "Straight"
    current: dict | None = None
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        word = line.split()[0]
        if word == "SUBCONTENTS":
            section = _section_name(line[len("SUBCONTENTS"):])
        elif word == "TURNOUT":
            match = re.match(r'TURNOUT\s+\S+\s+"([^"]*)"', line)
            fields = [f.strip() for f in match.group(1).split("\t")] if match else []
            fields = [f for f in fields if f]
            if len(fields) < 2:
                current = None
                continue
            current = {"code": _code(fields[-1]), "name": fields[-2] if len(fields) >= 3 else fields[0],
                       "section": section, "connectors": [], "segments": [], "routes": [], "index": {}, "count": 0}
        elif current is None:
            continue
        elif word in ("END$SEGS", "END"):
            # Routes number every segment, decoration included; map them
            # onto the track segments kept here.
            index = current.pop("index")
            current.pop("count")
            current["routes"] = [[index[i] for i in r if i in index] for r in current["routes"]]
            current["routes"] = [r for r in current["routes"] if r]
            if current["connectors"] and current["segments"]:
                pieces.append(current)
            current = None
        elif word == "P":
            tokens = shlex.split(line)
            current["routes"].append([int(t) - 1 for t in tokens[2:] if t.lstrip("-").isdigit() and int(t) > 0])
        elif word == "E" or word == "T":
            x, y, compass = (float(v) for v in line.split()[1:4])
            current["connectors"].append([x * INCH, y * INCH, (90.0 - compass) % 360.0])
        elif word == "S":
            x1, y1, x2, y2 = (float(v) for v in line.split()[3:7])
            current["index"][current["count"]] = len(current["segments"])
            current["count"] += 1
            current["segments"].append(["S", x1 * INCH, y1 * INCH, x2 * INCH, y2 * INCH])
        elif word == "C":
            radius, cx, cy, a0, sweep = (float(v) for v in line.split()[3:8])
            # XTrackCAD runs compass angles (clockwise from north) from a0
            # to a0+sweep; in maths angles that's the same arc run backwards.
            current["index"][current["count"]] = len(current["segments"])
            current["count"] += 1
            current["segments"].append(["A", cx * INCH, cy * INCH, abs(radius) * INCH, 90.0 - a0 - sweep, sweep])
        elif word in _DECORATION:
            current["count"] += 1  # ties, outlines, labels: drawn by XTrackCAD, not needed here
    return pieces


def _normalise(piece: dict) -> dict:
    """Move the piece so its first connector sits at the origin facing -x."""
    x0, y0, h0 = piece["connectors"][0]
    rotation = math.radians(180.0 - h0)
    c, s = math.cos(rotation), math.sin(rotation)

    def move(x: float, y: float) -> tuple[float, float]:
        x, y = x - x0, y - y0
        return x * c - y * s, x * s + y * c

    turn = math.degrees(rotation)
    connectors = []
    for x, y, h in piece["connectors"]:
        nx, ny = move(x, y)
        connectors.append([_r(nx), _r(ny), _r((h + turn) % 360.0)])
    segments = []
    for seg in piece["segments"]:
        if seg[0] == "S":
            (ax, ay), (bx, by) = move(seg[1], seg[2]), move(seg[3], seg[4])
            segments.append(["S", _r(ax), _r(ay), _r(bx), _r(by)])
        else:
            cx, cy = move(seg[1], seg[2])
            segments.append(["A", _r(cx), _r(cy), _r(seg[3]), _r((seg[4] + turn) % 360.0), _r(seg[5])])
    return {**piece, "connectors": connectors, "segments": segments}


def build(xtp_dir: Path) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for spec in LIBRARIES:
        source = xtp_dir / spec["file"]
        raw = source.read_bytes()
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            text = raw.decode("latin-1")
        pieces = [_normalise(p) for p in parse_xtp(text)]
        seen: set[str] = set()
        unique = []
        for piece in pieces:
            if piece["code"] in seen:
                continue
            seen.add(piece["code"])
            unique.append(piece)
        library = {k: v for k, v in spec.items() if k != "file"}
        library["source"] = f"Geometry from XTrackCAD parameter file {spec['file']}"
        library["pieces"] = unique
        out = OUT_DIR / f"{spec['id']}.json"
        out.write_text(json.dumps(library, indent=1) + "\n", encoding="utf-8")
        print(f"{out.name}: {len(unique)} pieces")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    build(Path(sys.argv[1]))
