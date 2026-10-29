"""A layout: the track pieces on the baseboard, how they join up, and saving
it to a .strack file (JSON).

Two kinds of piece live in a layout:

- PlacedPiece — a piece from one of Simple-Track's libraries, put down at a
  position and rotation. Its shape always comes from the library.
- ImportedPiece — a piece brought in from another program (an AnyRail
  layout) whose part isn't in our libraries. It carries its own shape.
"""
from __future__ import annotations

import json
import math
import uuid
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

from simple_track.core.geometry import (Point, Pose, Segment, Transform, angle_difference,
                                         transform_segment)
from simple_track.core.library import TrackPiece, find_library, find_piece

FILE_FORMAT = "simple-track"
FILE_VERSION = 1
FILE_SUFFIX = ".strack"

# How close two connectors must be to count as joined.
JOIN_DISTANCE_MM = 1.0
JOIN_ANGLE_DEGREES = 2.0

DEFAULT_GAUGE_MM = 16.5


def _new_id() -> str:
    return uuid.uuid4().hex[:12]


@dataclass
class PlacedPiece:
    library_id: str
    code: str
    transform: Transform = field(default_factory=Transform)
    id: str = field(default_factory=_new_id)

    @property
    def definition(self) -> TrackPiece | None:
        return find_piece(self.library_id, self.code)

    @property
    def label(self) -> str:
        definition = self.definition
        return f"{self.code} — {definition.name}" if definition else self.code

    @property
    def gauge_mm(self) -> float:
        library = find_library(self.library_id)
        return library.gauge_mm if library else DEFAULT_GAUGE_MM

    @property
    def sleeper_mm(self) -> float:
        library = find_library(self.library_id)
        return library.sleeper_mm if library else DEFAULT_GAUGE_MM * 1.7

    def connectors(self) -> list[Pose]:
        definition = self.definition
        if definition is None:
            return []
        return [c.transformed(self.transform) for c in definition.connectors]

    def segments(self) -> list[Segment]:
        definition = self.definition
        if definition is None:
            return []
        return [transform_segment(s, self.transform) for s in definition.segments]

    def polylines(self) -> list[list[Point]]:
        return [s.points() for s in self.segments()]

    def moved(self, transform: Transform) -> None:
        self.transform = self.transform.then(transform)

    def to_json(self) -> dict:
        t = self.transform
        return {"type": "placed", "id": self.id, "library": self.library_id, "code": self.code,
                "x": round(t.dx, 3), "y": round(t.dy, 3), "rotation": round(t.rotation, 4)}


@dataclass
class ImportedPiece:
    code: str
    source_library: str
    lines: list[list[Point]]
    connector_poses: list[Pose]
    gauge_mm: float = DEFAULT_GAUGE_MM
    id: str = field(default_factory=_new_id)

    @property
    def label(self) -> str:
        return f"{self.code} (imported, {self.source_library})" if self.source_library else self.code

    @property
    def sleeper_mm(self) -> float:
        return self.gauge_mm * 1.7

    def connectors(self) -> list[Pose]:
        return list(self.connector_poses)

    def polylines(self) -> list[list[Point]]:
        return self.lines

    def moved(self, transform: Transform) -> None:
        self.lines = [[transform.apply(p) for p in line] for line in self.lines]
        self.connector_poses = [c.transformed(transform) for c in self.connector_poses]

    def to_json(self) -> dict:
        return {"type": "imported", "id": self.id, "code": self.code, "library": self.source_library,
                "gauge_mm": self.gauge_mm,
                "lines": [[[round(x, 2), round(y, 2)] for x, y in line] for line in self.lines],
                "connectors": [[round(c.x, 2), round(c.y, 2), round(c.heading, 3)] for c in self.connector_poses]}


Piece = PlacedPiece | ImportedPiece


def connectors_join(a: Pose, b: Pose) -> bool:
    return (math.hypot(a.x - b.x, a.y - b.y) <= JOIN_DISTANCE_MM
            and angle_difference(a.heading, b.heading + 180.0) <= JOIN_ANGLE_DEGREES)


@dataclass
class Layout:
    name: str = "Untitled layout"
    pieces: list[Piece] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)  # e.g. what an import couldn't bring across

    # --- editing

    def add(self, piece: Piece) -> Piece:
        self.pieces.append(piece)
        return piece

    def remove(self, piece_id: str) -> None:
        self.pieces = [p for p in self.pieces if p.id != piece_id]

    def get(self, piece_id: str) -> Piece | None:
        for piece in self.pieces:
            if piece.id == piece_id:
                return piece
        return None

    def place(self, library_id: str, code: str, target: Pose | None = None, local_index: int = 0) -> PlacedPiece:
        """Add a library piece. With a target connector it's joined on there,
        by its connector number `local_index`; otherwise it goes at the origin."""
        definition = find_piece(library_id, code)
        if definition is None:
            raise KeyError(f"no piece {code} in library {library_id}")
        transform = Transform()
        if target is not None:
            local = definition.connectors[local_index % len(definition.connectors)]
            transform = Transform.aligning(local, target)
        piece = PlacedPiece(library_id, code, transform)
        self.add(piece)
        return piece

    # --- connections

    def free_connectors(self) -> list[tuple[Piece, int, Pose]]:
        """Every connector with nothing joined to it: where track can be added."""
        all_connectors = [(piece, i, pose) for piece in self.pieces for i, pose in enumerate(piece.connectors())]
        free = []
        for piece, i, pose in all_connectors:
            joined = any(other is not piece and connectors_join(pose, other_pose)
                         for other, _, other_pose in all_connectors)
            if not joined:
                free.append((piece, i, pose))
        return free

    def snap_transform(self, moving: list[Piece], distance_mm: float,
                       angle_degrees: float = 25.0) -> Transform | None:
        """After pieces are dragged: the small move that joins one of their
        free connectors exactly onto a nearby free connector of the rest of
        the layout, or None if nothing is close enough."""
        moving_ids = {p.id for p in moving}
        free = self.free_connectors()
        ours = [pose for piece, _, pose in free if piece.id in moving_ids]
        theirs = [pose for piece, _, pose in free if piece.id not in moving_ids]
        best = None
        for mine in ours:
            for other in theirs:
                gap = math.hypot(mine.x - other.x, mine.y - other.y)
                if gap > distance_mm or angle_difference(mine.heading, other.heading + 180.0) > angle_degrees:
                    continue
                if best is None or gap < best[0]:
                    best = (gap, mine, other)
        if best is None:
            return None
        _, mine, other = best
        turn = Transform.rotation_about((mine.x, mine.y), other.heading + 180.0 - mine.heading)
        return turn.then(Transform(other.x - mine.x, other.y - mine.y, 0.0))

    # --- reports

    def parts_list(self) -> list[tuple[str, str, str, int]]:
        """(library name, code, description, count) for every part used."""
        counts: Counter = Counter()
        for piece in self.pieces:
            if isinstance(piece, PlacedPiece):
                library = find_library(piece.library_id)
                definition = piece.definition
                counts[(library.name if library else piece.library_id, piece.code,
                        definition.name if definition else "")] += 1
            else:
                source = piece.source_library or "drawn freehand"
                counts[(f"Imported ({source})", piece.code, "")] += 1
        return sorted((lib, code, name, n) for (lib, code, name), n in counts.items())

    def bounds(self) -> tuple[float, float, float, float] | None:
        xs, ys = [], []
        for piece in self.pieces:
            for line in piece.polylines():
                for x, y in line:
                    xs.append(x)
                    ys.append(y)
        if not xs:
            return None
        return min(xs), min(ys), max(xs), max(ys)

    # --- files

    def to_json(self) -> dict:
        return {"format": FILE_FORMAT, "version": FILE_VERSION, "name": self.name,
                "notes": self.notes, "pieces": [p.to_json() for p in self.pieces]}

    def save(self, path: Path) -> None:
        path.write_text(json.dumps(self.to_json(), indent=1), encoding="utf-8")

    @classmethod
    def from_json(cls, data: dict) -> "Layout":
        if data.get("format") != FILE_FORMAT:
            raise ValueError("not a Simple-Track layout")
        if data.get("version", 0) > FILE_VERSION:
            raise ValueError("this layout was saved by a newer Simple-Track — please update")
        layout = cls(name=data.get("name", "Untitled layout"), notes=list(data.get("notes", [])))
        for raw in data.get("pieces", []):
            if raw.get("type") == "placed":
                layout.add(PlacedPiece(raw["library"], raw["code"],
                                       Transform(raw.get("x", 0.0), raw.get("y", 0.0), raw.get("rotation", 0.0)),
                                       raw.get("id") or _new_id()))
            elif raw.get("type") == "imported":
                layout.add(ImportedPiece(
                    raw.get("code", "?"), raw.get("library", ""),
                    [[(x, y) for x, y in line] for line in raw.get("lines", [])],
                    [Pose(x, y, h) for x, y, h in raw.get("connectors", [])],
                    raw.get("gauge_mm", DEFAULT_GAUGE_MM), raw.get("id") or _new_id()))
        return layout

    @classmethod
    def load(cls, path: Path) -> "Layout":
        return cls.from_json(json.loads(path.read_text(encoding="utf-8")))
