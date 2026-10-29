"""Track libraries: the catalogue of sectional pieces Simple-Track can place.

Each library is a JSON file in core/libraries/. A piece is drawn in its own
frame, with its first connector at the origin facing out along -x (heading
180°), so placing one is just a rotate-and-move (see geometry.Transform).

    {"id": "peco-oo-setrack", "name": "Peco Setrack (OO/HO)",
     "manufacturer": "Peco", "scale": "OO", "gauge_mm": 16.5, "sleeper_mm": 26,
     "pieces": [
       {"code": "ST-200", "name": "Straight", "section": "Straight track",
        "connectors": [[0, 0, 180], [168, 0, 0]],
        "segments": [["S", 0, 0, 168, 0]],
        "routes": [[0]]}]}

Segments are ["S", x1, y1, x2, y2] for straights and
["A", cx, cy, radius, start_angle, sweep] for arcs. Routes list the segment
indices a train runs along for each setting of a point.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

from simple_track.core.geometry import Arc, Pose, Segment, Straight

LIBRARY_DIR = Path(__file__).parent / "libraries"


@dataclass(frozen=True)
class TrackPiece:
    library_id: str
    code: str
    name: str
    section: str
    connectors: tuple[Pose, ...]
    segments: tuple[Segment, ...]
    routes: tuple[tuple[int, ...], ...] = ()

    @property
    def is_point(self) -> bool:
        return len(self.connectors) > 2

    def centre(self) -> tuple[float, float]:
        """Middle of the piece's bounding box, in its own frame — where the
        mouse holds it while it's dragged in."""
        points = [p for s in self.segments for p in s.points()]
        xs, ys = [p[0] for p in points], [p[1] for p in points]
        return ((min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2)

    def length(self) -> float:
        """Length of the first route (the straight road through a point)."""
        route = self.routes[0] if self.routes else range(len(self.segments))
        return sum(self.segments[i].length() for i in route)


@dataclass
class Library:
    id: str
    name: str
    manufacturer: str
    scale: str
    gauge_mm: float
    sleeper_mm: float
    source: str = ""
    pieces: list[TrackPiece] = field(default_factory=list)

    def piece(self, code: str) -> TrackPiece | None:
        for piece in self.pieces:
            if piece.code == code:
                return piece
        return None

    def sections(self) -> list[str]:
        seen: list[str] = []
        for piece in self.pieces:
            if piece.section not in seen:
                seen.append(piece.section)
        return seen


def _segment(raw: list) -> Segment:
    kind, *values = raw
    if kind == "S":
        x1, y1, x2, y2 = values
        return Straight((x1, y1), (x2, y2))
    if kind == "A":
        cx, cy, radius, start, sweep = values
        return Arc((cx, cy), radius, start, sweep)
    raise ValueError(f"unknown segment type {kind!r}")


def parse_library(data: dict) -> Library:
    library = Library(
        id=data["id"],
        name=data["name"],
        manufacturer=data.get("manufacturer", ""),
        scale=data.get("scale", ""),
        gauge_mm=float(data["gauge_mm"]),
        sleeper_mm=float(data.get("sleeper_mm", data["gauge_mm"] * 1.6)),
        source=data.get("source", ""),
    )
    for raw in data["pieces"]:
        library.pieces.append(TrackPiece(
            library_id=library.id,
            code=raw["code"],
            name=raw["name"],
            section=raw.get("section", ""),
            connectors=tuple(Pose(x, y, h) for x, y, h in raw["connectors"]),
            segments=tuple(_segment(s) for s in raw["segments"]),
            routes=tuple(tuple(r) for r in raw.get("routes", [])),
        ))
    return library


def load_library(path: Path) -> Library:
    return parse_library(json.loads(path.read_text(encoding="utf-8")))


@lru_cache(maxsize=1)
def builtin_libraries() -> tuple[Library, ...]:
    """Every library shipped with the app, in the order shown to the user."""
    libraries = [load_library(path) for path in sorted(LIBRARY_DIR.glob("*.json"))]
    return tuple(sorted(libraries, key=lambda lib: (lib.scale != "OO", lib.scale, lib.name)))


def find_library(library_id: str) -> Library | None:
    for library in builtin_libraries():
        if library.id == library_id:
            return library
    return None


def find_piece(library_id: str, code: str) -> TrackPiece | None:
    library = find_library(library_id)
    return library.piece(code) if library else None
