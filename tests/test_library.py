import math

import pytest

from simple_track.core.geometry import Arc, angle_difference
from simple_track.core.library import builtin_libraries, find_piece

EXPECTED = {
    "hornby-oo", "peco-oo-setrack", "peco-oo-streamline-100", "peco-oo-bullhead-75",
    "peco-n-setrack", "peco-n-streamline-80", "peco-n-finescale-55",
}


def test_all_libraries_load():
    libraries = {lib.id: lib for lib in builtin_libraries()}
    assert set(libraries) == EXPECTED
    for lib in libraries.values():
        assert lib.pieces, lib.id
        assert lib.gauge_mm == (9.0 if lib.scale == "N" else 16.5)


def test_every_piece_starts_at_the_origin_facing_left():
    for lib in builtin_libraries():
        for piece in lib.pieces:
            first = piece.connectors[0]
            assert (first.x, first.y) == pytest.approx((0, 0), abs=0.01), piece.code
            assert angle_difference(first.heading, 180) < 0.01, piece.code


def test_every_connector_is_on_the_end_of_a_segment():
    for lib in builtin_libraries():
        for piece in lib.pieces:
            ends = [p for s in piece.segments for p in (s.points()[0], s.points()[-1])]
            for c in piece.connectors:
                assert min(math.dist((c.x, c.y), e) for e in ends) < 0.5, (lib.id, piece.code)


@pytest.mark.parametrize("library, code, length", [
    ("hornby-oo", "R600", 167.5),
    ("hornby-oo", "R601", 335.0),
    ("peco-oo-setrack", "ST-200", 168.0),
    ("peco-n-setrack", "ST1", 87.0),
])
def test_known_straights(library, code, length):
    assert find_piece(library, code).length() == pytest.approx(length, abs=0.5)


@pytest.mark.parametrize("library, code, radius, sweep", [
    ("hornby-oo", "R604", 371, 22.5),  # 1st radius
    ("hornby-oo", "R606", 438, 22.5),  # 2nd radius
    ("hornby-oo", "R608", 505, 22.5),  # 3rd radius
    ("peco-n-setrack", "ST3", 228, 22.5),
])
def test_known_curves(library, code, radius, sweep):
    arc = find_piece(library, code).segments[0]
    assert isinstance(arc, Arc)
    assert arc.radius == pytest.approx(radius, abs=1)
    assert abs(arc.sweep) == pytest.approx(sweep, abs=0.01)


def test_points_have_three_ends_and_two_routes():
    point = find_piece("peco-oo-streamline-100", "SL-95")
    assert point.is_point
    assert len(point.connectors) == 3
    assert len(point.routes) == 2
