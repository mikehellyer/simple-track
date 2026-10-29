"""Importing AnyRail layouts (.any).

An .any file is a Boost.Serialization binary archive (see
docs/anyrail-format.md). Its class layouts aren't published, so this reader
doesn't walk the archive field by field. It looks for the records whose
shape we've worked out and trusts only those that pass sanity checks:

- a part: its part number string straight after which comes a library id
  string ("SL-E595", "PC0100");
- a connector: four doubles — x, y, z (cm, y down) and a heading in radians —
  followed by the library id string. A connector shared by two joined parts
  is written once; afterwards the archive refers to it by object id;
- flexible track: a cubic Bézier, four (x, y) point objects with
  consecutive object ids;
- a curve: an arc record x, y, angle, radius, sweep, length — the last
  always equals radius × |sweep|, which is what makes it findable.

Straight track has no recognisable record of its own yet; it's drawn by
joining connectors that line up. Each AnyRail part becomes an ImportedPiece
carrying its own shape.
"""
from __future__ import annotations

import math
import re
import struct
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

from simple_track.core.geometry import Bezier, Point, Pose, Straight
from simple_track.core.layout import DEFAULT_GAUGE_MM, ImportedPiece, Layout

CM = 10.0  # AnyRail stores centimetres
PART_SPAN_LIMIT = 0x1000  # a part's record is ~1.5 KB; never search further than this
GAP_BRIDGE_LIMIT_MM = 120.0

_STRING = re.compile(rb"([\x01-\x40])\x00{7}([\x20-\x7e]+)")
_LIBRARY_ID = re.compile(r"^[A-Za-z0-9_]{2,24}$")
# A lookahead, so a near-miss can't swallow the bytes of the real match after it.
_BEZIER = re.compile(
    rb"(?s)(?=(..)(?:\x01\x00{4})?(....)(.{8})(.{8})" + rb"\1(....)(.{8})(.{8})" * 3 + rb")")


class AnyRailError(ValueError):
    pass


@dataclass
class _Connector:
    position: int
    object_id: int
    class_id: bytes
    x: float
    y: float
    angle: float  # radians, AnyRail's convention


@dataclass
class _Part:
    position: int
    code: str
    library: str
    gauge_mm: float = DEFAULT_GAUGE_MM
    lines: list[list[Point]] = field(default_factory=list)
    connectors: list[_Connector] = field(default_factory=list)


def _strings(data: bytes) -> list[tuple[int, int, str]]:
    """Every length-prefixed ASCII string: (start, end, text)."""
    found = []
    for match in _STRING.finditer(data):
        length = match.group(1)[0]
        text = match.group(2)[:length]
        if len(text) == length:
            found.append((match.start(), match.start() + 8 + length, text.decode("ascii")))
    return found


def _plausible(value: float, limit: float) -> bool:
    return math.isfinite(value) and abs(value) < limit


def _find_connectors(data: bytes, strings) -> tuple[list[_Connector], set[str]]:
    candidates = []
    for start, _end, text in strings:
        if start < 42 or not _LIBRARY_ID.match(text):
            continue
        x, y, z, angle = struct.unpack_from("<4d", data, start - 32)
        if not (_plausible(x, 1e5) and _plausible(y, 1e5) and _plausible(z, 1e4) and -7.0 <= angle <= 7.0):
            continue
        if (z != 0.0 and abs(z) < 1e-9) or (x == 0.0 and y == 0.0):
            continue  # denormals and zeros: the part header, not a connector
        object_id = struct.unpack_from("<I", data, start - 40)[0]
        candidates.append(_Connector(start, object_id, data[start - 42:start - 40], x, y, angle))
    if not candidates:
        return [], set()

    def library_of(c: _Connector) -> str:
        return data[c.position + 8:c.position + 8 + data[c.position]].decode("ascii")

    # A part's header can look like a connector too (its part number after
    # four stray doubles). Real connectors share one class id, so library
    # ids are taken only from those.
    class_id = Counter(c.class_id for c in candidates).most_common(1)[0][0]
    libraries = {library_of(c) for c in candidates if c.class_id == class_id}
    return [c for c in candidates if library_of(c) in libraries], libraries


def _find_parts(strings, libraries: set[str]) -> list[_Part]:
    parts = []
    for (start, end, code), (next_start, next_end, library) in zip(strings, strings[1:]):
        if next_start == end and library in libraries and code not in libraries:
            parts.append(_Part(start, code, library))
            parts[-1].gauge_mm = _gauge_after(strings, next_end)
    return parts


def _gauge_after(strings, position: int) -> float:
    """Parts carry a gauge string ("0-16.5", "00") a little after the
    library id."""
    for start, _end, text in strings:
        if position <= start < position + 200:
            match = re.search(r"(\d+(?:\.\d+)?)$", text)
            if match and ("-" in text or "." in text):
                value = float(match.group(1))
                if 4.0 <= value <= 100.0:
                    return value
            if text in ("00", "OO", "H0", "HO"):
                return 16.5
            if text == "N":
                return 9.0
    return DEFAULT_GAUGE_MM


def _to_mm(x: float, y: float) -> Point:
    return (x * CM, -y * CM)


def _connector_pose(c: _Connector) -> Pose:
    # AnyRail's heading points into the piece, as (sin a, cos a) in y-down
    # coordinates. Outwards in y-up maths angles that's atan2(cos a, -sin a).
    heading = math.degrees(math.atan2(math.cos(c.angle), -math.sin(c.angle))) % 360.0
    x, y = _to_mm(c.x, c.y)
    return Pose(x, y, heading)


def _beziers(data: bytes, lo: int, hi: int) -> list[list[Point]]:
    lines = []
    for match in _BEZIER.finditer(data, lo, hi):
        groups = match.groups()[1:]
        ids = [struct.unpack("<I", groups[i])[0] for i in range(0, 12, 3)]
        if ids != list(range(ids[0], ids[0] + 4)):
            continue
        points = [struct.unpack("<2d", groups[i + 1] + groups[i + 2]) for i in range(0, 12, 3)]
        if not all(_plausible(v, 1e5) for p in points for v in p):
            continue
        line = Bezier(*(_to_mm(*p) for p in points)).points()
        if line not in lines:
            lines.append(line)
    return lines


def _arcs(data: bytes, lo: int, hi: int) -> list[tuple[float, float, float, float, float]]:
    """Arc records as (x, y, angle, radius, sweep), AnyRail units."""
    arcs = []
    i = lo
    while i <= hi - 48:
        x, y, angle, radius, sweep, length = struct.unpack_from("<6d", data, i)
        if (1.0 < radius < 5000.0 and 0.001 < abs(sweep) <= 2 * math.pi + 1e-9 and length > 0.1
                and abs(abs(radius * sweep) - length) < 1e-6 * max(1.0, length)
                and _plausible(x, 1e5) and _plausible(y, 1e5) and -7.0 <= angle <= 7.0):
            arcs.append((x, y, angle, radius, sweep))
            i += 48
            continue
        i += 1
    return arcs


def _arc_points(x: float, y: float, angle: float, radius: float, sweep: float) -> list[Point]:
    """An arc record drawn out. (x, y) is where the curve starts; `angle`
    is that point's direction from the centre in y-up maths terms — turned
    half a circle when the sweep is negative — and the curve runs on from
    there by `sweep` radians."""
    sx, sy = _to_mm(x, y)
    r = radius * CM
    start = angle + (math.pi if sweep < 0 else 0.0)
    cx, cy = sx - r * math.cos(start), sy - r * math.sin(start)
    steps = max(4, int(abs(math.degrees(sweep)) / 2))
    return [(cx + r * math.cos(start + sweep * k / steps), cy + r * math.sin(start + sweep * k / steps))
            for k in range(steps + 1)]


def _part_connectors(data: bytes, lo: int, hi: int, by_id: dict[int, _Connector], class_id: bytes,
                     full: list[_Connector]) -> list[_Connector]:
    found: dict[int, tuple[int, _Connector]] = {}
    for c in full:
        if lo <= c.position < hi:
            found.setdefault(c.object_id, (c.position, c))
    for match in re.finditer(re.escape(class_id) + rb"(....)", data[lo:hi]):
        object_id = struct.unpack("<I", match.group(1))[0]
        if object_id in by_id:
            found.setdefault(object_id, (lo + match.start(), by_id[object_id]))
    return [c for _, c in sorted(found.values(), key=lambda item: item[0])]


def _near(a: Point, b: Point, tolerance: float = 0.5) -> bool:
    return math.dist(a, b) <= tolerance


def _lines_up(a: Pose, b: Pose) -> bool:
    """True if a straight piece of track would join connectors a and b."""
    if math.dist((a.x, a.y), (b.x, b.y)) < 0.1:
        return False
    along = math.degrees(math.atan2(b.y - a.y, b.x - a.x))
    return (abs(((a.heading + 180.0 - along) + 180.0) % 360.0 - 180.0) < 1.0
            and abs(((b.heading - along) + 180.0) % 360.0 - 180.0) < 1.0)


def _join_by_connectors(poses: list[Pose]) -> list[list[Point]]:
    """Shape for a part with no recognised segments: straight where its
    connectors line up, otherwise a smooth curve from the first connector."""
    lines = []
    first = poses[0]
    for other in poses[1:]:
        if _lines_up(first, other):
            lines.append(Straight((first.x, first.y), (other.x, other.y)).points())
            continue
        handle = math.dist((first.x, first.y), (other.x, other.y)) / 3.0

        def inward(p: Pose) -> Point:
            r = math.radians(p.heading + 180.0)
            return (p.x + handle * math.cos(r), p.y + handle * math.sin(r))

        lines.append(Bezier((first.x, first.y), inward(first), inward(other), (other.x, other.y)).points())
    return lines


def _bridge_gaps(lines: list[list[Point]], poses: list[Pose]) -> list[list[Point]]:
    """Straight track between a connector and the nearest end of the
    drawn shape, for the straight lead-ins we can't read yet."""
    ends = [line[0] for line in lines] + [line[-1] for line in lines]
    extra = []
    for pose in poses:
        here = (pose.x, pose.y)
        if any(_near(here, e) for e in ends):
            continue
        nearest = min(ends, key=lambda e: math.dist(here, e))
        if math.dist(here, nearest) <= GAP_BRIDGE_LIMIT_MM:
            extra.append([here, nearest])
    # Straight roads through a point: connector to connector, if nothing covers them.
    for i, a in enumerate(poses):
        for b in poses[i + 1:]:
            if _lines_up(a, b) and not any(_near((a.x, a.y), l[0], 1) and _near((b.x, b.y), l[-1], 1)
                                           or _near((b.x, b.y), l[0], 1) and _near((a.x, a.y), l[-1], 1)
                                           for l in lines + extra):
                extra.append([(a.x, a.y), (b.x, b.y)])
    return lines + extra


def _far_from(line: list[Point], poses: list[Pose]) -> bool:
    return all(min(math.dist(end, (p.x, p.y)) for p in poses) > GAP_BRIDGE_LIMIT_MM for end in (line[0], line[-1]))


def _end_poses(line: list[Point]) -> list[Pose]:
    """Connectors at both ends of a line, facing outwards along it."""
    (ax, ay), (bx, by) = line[0], line[1]
    (cx, cy), (dx, dy) = line[-2], line[-1]
    return [Pose(ax, ay, math.degrees(math.atan2(ay - by, ax - bx)) % 360.0),
            Pose(dx, dy, math.degrees(math.atan2(dy - cy, dx - cx)) % 360.0)]


def read_any(data: bytes, name: str = "Imported layout") -> Layout:
    if b"serialization::archive" not in data[:40] or b"AnyRail" not in data[:80]:
        raise AnyRailError("not a layout file Simple-Track can import")
    strings = _strings(data)
    connectors, libraries = _find_connectors(data, strings)
    if not connectors:
        raise AnyRailError("couldn't find any track in this file")

    class_id = Counter(c.class_id for c in connectors).most_common(1)[0][0]
    by_id = {c.object_id: c for c in connectors if c.class_id == class_id}
    parts = _find_parts(strings, libraries)

    # The last part is followed by other records (connection tables that
    # mention every connector), so it gets a typical part's span, not
    # everything up to the end of the file.
    spans = sorted(b.position - a.position for a, b in zip(parts, parts[1:]))
    last_span = min(PART_SPAN_LIMIT, int(spans[len(spans) // 2] * 1.2)) if spans else PART_SPAN_LIMIT

    layout = Layout(name=name)
    for index, part in enumerate(parts):
        lo = part.position
        hi = min(parts[index + 1].position if index + 1 < len(parts) else len(data),
                 lo + (PART_SPAN_LIMIT if index + 1 < len(parts) else last_span))
        part.connectors = _part_connectors(data, lo, hi, by_id, class_id, connectors)
        poses = [_connector_pose(c) for c in part.connectors]
        part.lines = _beziers(data, lo, hi) + [_arc_points(*arc) for arc in _arcs(data, lo, hi)]
        if not poses and not part.lines:
            continue
        if poses:
            # A curve nowhere near this part's ends isn't its own: it's
            # track drawn freehand (no part record of its own) that happens
            # to sit in this part's stretch of the file. It stands alone.
            strays = [line for line in part.lines if _far_from(line, poses)]
            part.lines = [line for line in part.lines if line not in strays]
            for line in strays:
                layout.add(ImportedPiece("Curve", "", [line], _end_poses(line), part.gauge_mm))
        if part.lines:
            lines = _bridge_gaps(part.lines, poses) if poses else part.lines
        else:
            lines = _join_by_connectors(poses) if len(poses) >= 2 else []
        if not lines:
            continue
        layout.add(ImportedPiece(part.code, part.library, lines, poses, part.gauge_mm))

    if b"CSurface" in data:
        layout.notes.append("The background picture wasn't imported.")
    if b"CText" in data:
        layout.notes.append("Text labels weren't imported.")
    if b"CWorkArea" in data:
        layout.notes.append("The baseboard outline wasn't imported.")
    return layout


def import_any(path: Path) -> Layout:
    return read_any(path.read_bytes(), name=path.stem)
