"""Plane geometry for track: poses, track segments and the polylines they're
drawn with.

Conventions used everywhere in Simple-Track:

- Units are millimetres.
- x runs right and y runs *up* (ordinary maths axes). The canvas flips y
  when it draws.
- Angles are degrees, anticlockwise from +x.
- A connector's heading points *out* of its piece, the way a train would
  leave it. Two pieces join when their connectors meet with opposite headings.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

Point = tuple[float, float]

# How finely curves are cut into straight lines for drawing and hit-testing.
ARC_STEP_DEGREES = 2.0
BEZIER_STEPS = 32


def normalise_angle(degrees: float) -> float:
    """The same angle in [0, 360)."""
    result = math.fmod(degrees, 360.0)
    if result < 0:
        result += 360.0
    return 0.0 if math.isclose(result, 360.0) else result


def angle_difference(a: float, b: float) -> float:
    """Smallest absolute difference between two angles, 0–180."""
    diff = abs(normalise_angle(a) - normalise_angle(b))
    return min(diff, 360.0 - diff)


@dataclass(frozen=True)
class Pose:
    """A point plus a heading: where a connector is and which way it faces."""
    x: float
    y: float
    heading: float

    def transformed(self, transform: "Transform") -> "Pose":
        x, y = transform.apply((self.x, self.y))
        return Pose(x, y, normalise_angle(self.heading + transform.rotation))


@dataclass(frozen=True)
class Transform:
    """Rotate about the origin, then translate."""
    dx: float = 0.0
    dy: float = 0.0
    rotation: float = 0.0

    def apply(self, point: Point) -> Point:
        r = math.radians(self.rotation)
        c, s = math.cos(r), math.sin(r)
        x, y = point
        return (x * c - y * s + self.dx, x * s + y * c + self.dy)

    def then(self, other: "Transform") -> "Transform":
        """This transform followed by `other`."""
        dx, dy = other.apply((self.dx, self.dy))
        return Transform(dx, dy, normalise_angle(self.rotation + other.rotation))

    @staticmethod
    def rotation_about(point: Point, degrees: float) -> "Transform":
        r = math.radians(degrees)
        c, s = math.cos(r), math.sin(r)
        px, py = point
        return Transform(px - (px * c - py * s), py - (px * s + py * c), degrees)

    @staticmethod
    def aligning(local: Pose, target: Pose) -> "Transform":
        """The transform that puts the local connector `local` onto the world
        connector `target`, facing it, so the two pieces join."""
        rotation = normalise_angle(target.heading + 180.0 - local.heading)
        r = math.radians(rotation)
        c, s = math.cos(r), math.sin(r)
        rx, ry = local.x * c - local.y * s, local.x * s + local.y * c
        return Transform(target.x - rx, target.y - ry, rotation)


@dataclass(frozen=True)
class Straight:
    start: Point
    end: Point

    def points(self) -> list[Point]:
        return [self.start, self.end]

    def length(self) -> float:
        return math.dist(self.start, self.end)


@dataclass(frozen=True)
class Arc:
    """Part of a circle: centre, radius, and the angles (anticlockwise from
    +x) it runs from and how far. A negative sweep runs clockwise."""
    centre: Point
    radius: float
    start_angle: float
    sweep: float

    def points(self) -> list[Point]:
        steps = max(2, math.ceil(abs(self.sweep) / ARC_STEP_DEGREES))
        cx, cy = self.centre
        out = []
        for i in range(steps + 1):
            a = math.radians(self.start_angle + self.sweep * i / steps)
            out.append((cx + self.radius * math.cos(a), cy + self.radius * math.sin(a)))
        return out

    def length(self) -> float:
        return self.radius * math.radians(abs(self.sweep))


@dataclass(frozen=True)
class Bezier:
    """A cubic Bézier: how AnyRail stores flexible track."""
    p0: Point
    p1: Point
    p2: Point
    p3: Point

    def points(self) -> list[Point]:
        out = []
        for i in range(BEZIER_STEPS + 1):
            t = i / BEZIER_STEPS
            u = 1 - t
            a, b, c, d = u * u * u, 3 * t * u * u, 3 * t * t * u, t * t * t
            out.append((
                a * self.p0[0] + b * self.p1[0] + c * self.p2[0] + d * self.p3[0],
                a * self.p0[1] + b * self.p1[1] + c * self.p2[1] + d * self.p3[1],
            ))
        return out

    def length(self) -> float:
        pts = self.points()
        return sum(math.dist(a, b) for a, b in zip(pts, pts[1:]))


Segment = Straight | Arc | Bezier


def transform_segment(segment: Segment, transform: Transform) -> Segment:
    if isinstance(segment, Straight):
        return Straight(transform.apply(segment.start), transform.apply(segment.end))
    if isinstance(segment, Arc):
        return Arc(transform.apply(segment.centre), segment.radius,
                   segment.start_angle + transform.rotation, segment.sweep)
    return Bezier(*(transform.apply(p) for p in (segment.p0, segment.p1, segment.p2, segment.p3)))


def offset_polyline(points: list[Point], distance: float) -> list[Point]:
    """The polyline shifted sideways by `distance` (positive = left of the
    direction of travel): how the two rails are drawn either side of the
    centre line."""
    if len(points) < 2:
        return list(points)
    out = []
    for i, (x, y) in enumerate(points):
        if i == 0:
            dx, dy = points[1][0] - x, points[1][1] - y
        elif i == len(points) - 1:
            dx, dy = x - points[i - 1][0], y - points[i - 1][1]
        else:
            dx, dy = points[i + 1][0] - points[i - 1][0], points[i + 1][1] - points[i - 1][1]
        norm = math.hypot(dx, dy) or 1.0
        out.append((x - dy / norm * distance, y + dx / norm * distance))
    return out


def distance_to_polyline(point: Point, points: list[Point]) -> float:
    px, py = point
    best = math.inf
    for (ax, ay), (bx, by) in zip(points, points[1:]):
        dx, dy = bx - ax, by - ay
        seg_len_sq = dx * dx + dy * dy
        t = 0.0 if seg_len_sq == 0 else max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / seg_len_sq))
        best = min(best, math.hypot(px - (ax + t * dx), py - (ay + t * dy)))
    return best
