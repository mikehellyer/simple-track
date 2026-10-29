import math

import pytest

from simple_track.core.geometry import (Arc, Bezier, Pose, Straight, Transform, angle_difference,
                                         distance_to_polyline, normalise_angle, offset_polyline,
                                         transform_segment)


def test_normalise_angle():
    assert normalise_angle(-90) == 270
    assert normalise_angle(720) == 0
    assert angle_difference(10, 350) == pytest.approx(20)


def test_aligning_puts_connectors_face_to_face():
    local = Pose(0, 0, 180)  # a piece's first end, facing -x
    target = Pose(100, 50, 90)  # a free end facing up
    t = Transform.aligning(local, target)
    joined = local.transformed(t)
    assert (joined.x, joined.y) == pytest.approx((100, 50))
    assert angle_difference(joined.heading, target.heading + 180) == pytest.approx(0, abs=1e-9)


def test_then_and_rotation_about():
    quarter = Transform.rotation_about((10, 0), 90)
    assert quarter.apply((20, 0)) == pytest.approx((10, 10))
    combined = Transform(5, 0, 0).then(quarter)
    assert combined.apply((15, 0)) == pytest.approx(quarter.apply((20, 0)))


def test_arc_points_and_length():
    arc = Arc((0, 0), 100, 0, 90)
    points = arc.points()
    assert points[0] == pytest.approx((100, 0))
    assert points[-1] == pytest.approx((0, 100), abs=1e-9)
    assert arc.length() == pytest.approx(math.pi * 50)


def test_transform_segment_keeps_shape():
    arc = Arc((0, 0), 100, 0, 45)
    moved = transform_segment(arc, Transform(10, 20, 90))
    assert moved.points()[0] == pytest.approx((10, 120))
    assert moved.length() == pytest.approx(arc.length())


def test_bezier_ends():
    curve = Bezier((0, 0), (10, 0), (20, 10), (30, 10))
    assert curve.points()[0] == (0, 0)
    assert curve.points()[-1] == pytest.approx((30, 10))
    assert curve.length() > math.dist((0, 0), (30, 10))


def test_offset_and_distance():
    line = Straight((0, 0), (100, 0)).points()
    assert offset_polyline(line, 5) == [(0, 5), (100, 5)]
    assert distance_to_polyline((50, 7), line) == pytest.approx(7)
