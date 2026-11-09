import math

import pytest

from simple_track.core.geometry import Arc, angle_difference
from simple_track.core.library import builtin_libraries, find_piece

EXPECTED = {
    "hornby-oo", "peco-oo-setrack", "peco-oo-streamline-100", "peco-oo-bullhead-75",
    "peco-n-setrack", "peco-n-streamline-80", "peco-n-finescale-55",
    "kato-n-unitrack", "kato-oo9-unitrack",
}
GAUGES = {"OO": 16.5, "N": 9.0, "OO9": 9.0}


def test_all_libraries_load():
    libraries = {lib.id: lib for lib in builtin_libraries()}
    assert set(libraries) == EXPECTED
    for lib in libraries.values():
        assert lib.pieces, lib.id
        assert lib.gauge_mm == GAUGES[lib.scale]


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
    ("kato-n-unitrack", "20-000", 248.0),
    ("kato-oo9-unitrack", "52-120", 124.0),
])
def test_known_straights(library, code, length):
    assert find_piece(library, code).length() == pytest.approx(length, abs=0.5)


@pytest.mark.parametrize("library, code, radius, sweep", [
    ("hornby-oo", "R604", 371, 22.5),  # 1st radius
    ("hornby-oo", "R606", 438, 22.5),  # 2nd radius
    ("hornby-oo", "R608", 505, 22.5),  # 3rd radius
    ("peco-n-setrack", "ST3", 228, 22.5),
    ("kato-n-unitrack", "20-100", 249, 45),  # R249
    ("kato-n-unitrack", "20-170", 216, 45),  # R216
    ("kato-n-unitrack", "20-110", 282, 45),  # the standard curves above R249,
    ("kato-n-unitrack", "20-120", 315, 45),  # added because XTrackCAD's file
    ("kato-n-unitrack", "20-121", 315, 15),  # no longer lists them
    ("kato-n-unitrack", "20-132", 348, 45),
    ("kato-n-unitrack", "20-140", 381, 30),
    ("kato-n-unitrack", "20-150", 718, 15),
    ("kato-oo9-unitrack", "52-220", 183, 45),
    ("kato-oo9-unitrack", "52-250", 481, 15),
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


def test_a_turntable_has_only_its_rim_ends():
    from simple_track.core.library import find_piece

    turntable = find_piece("kato-n-unitrack", "20-283")
    assert len(turntable.connectors) == 36  # its pivot point isn't an end


def test_kato_part_numbers_listed_twice_are_both_kept():
    from simple_track.core.library import find_library

    codes = {p.code for p in find_library("kato-n-unitrack").pieces}
    assert {"20-320", "20-320 (Crossing 90d w/o S45.5)", "S45.5"} <= codes


def test_added_kato_curve_matches_the_concrete_sleeper_one():
    plain = find_piece("kato-n-unitrack", "20-120")  # R315 45°, drawn from the catalogue
    concrete = find_piece("kato-n-unitrack", "20-124")  # R315 45°, from XTrackCAD
    for a, b in zip(plain.connectors, concrete.connectors):
        assert (a.x, a.y, a.heading) == pytest.approx((b.x, b.y, b.heading), abs=0.01)
