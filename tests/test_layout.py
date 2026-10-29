import pytest

from simple_track.core.geometry import Pose, Transform
from simple_track.core.layout import ImportedPiece, Layout, PlacedPiece


def chain(layout: Layout, library: str, code: str, count: int) -> list[PlacedPiece]:
    pieces = [layout.place(library, code)]
    for _ in range(count - 1):
        pieces.append(layout.place(library, code, pieces[-1].connectors()[1]))
    return pieces


def test_sixteen_first_radius_curves_make_a_circle():
    layout = Layout()
    chain(layout, "hornby-oo", "R604", 16)
    assert layout.free_connectors() == []


def test_oval_of_setrack_closes():
    layout = Layout()
    pieces = chain(layout, "peco-oo-setrack", "ST-225", 8)
    for _ in range(2):
        pieces.append(layout.place("peco-oo-setrack", "ST-200", pieces[-1].connectors()[1]))
    pieces += [layout.place("peco-oo-setrack", "ST-225", pieces[-1].connectors()[1])]
    for _ in range(7):
        pieces.append(layout.place("peco-oo-setrack", "ST-225", pieces[-1].connectors()[1]))
    for _ in range(2):
        pieces.append(layout.place("peco-oo-setrack", "ST-200", pieces[-1].connectors()[1]))
    assert layout.free_connectors() == []


def test_a_point_leaves_two_free_ends():
    layout = Layout()
    start = layout.place("peco-n-setrack", "ST1")
    layout.place("peco-n-setrack", "ST5", start.connectors()[1])
    assert len(layout.free_connectors()) == 3  # the straight's far end + the point's two exits


def test_snap_joins_a_nearby_end():
    layout = Layout()
    first = layout.place("hornby-oo", "R600")
    second = layout.place("hornby-oo", "R600", first.connectors()[1])
    second.moved(Transform(6, 4, 3))  # dragged a little off
    assert len(layout.free_connectors()) == 4
    snap = layout.snap_transform([second], distance_mm=20)
    assert snap is not None
    second.moved(snap)
    assert len(layout.free_connectors()) == 2


def test_snap_ignores_far_away_track():
    layout = Layout()
    first = layout.place("hornby-oo", "R600")
    second = layout.place("hornby-oo", "R600", Pose(1000, 1000, 0))
    assert layout.snap_transform([second], distance_mm=20) is None
    assert first is not second


def test_parts_list_counts():
    layout = Layout()
    chain(layout, "hornby-oo", "R604", 3)
    layout.place("peco-oo-setrack", "ST-200")
    parts = layout.parts_list()
    assert ("Hornby OO", "R604", "Curve 1st Radius 371mm", 3) in parts
    assert sum(p[3] for p in parts) == 4


def test_save_and_load_round_trip(tmp_path):
    layout = Layout(name="Test")
    chain(layout, "peco-oo-streamline-100", "SL-95", 2)
    layout.add(ImportedPiece("SL-500", "PC0100", [[(0, 0), (100, 0)]], [Pose(0, 0, 180), Pose(100, 0, 0)]))
    path = tmp_path / "test.strack"
    layout.save(path)
    loaded = Layout.load(path)
    assert loaded.name == "Test"
    assert [p.to_json() for p in loaded.pieces] == [p.to_json() for p in layout.pieces]


def test_load_rejects_other_files(tmp_path):
    path = tmp_path / "x.strack"
    path.write_text('{"format": "something-else"}')
    with pytest.raises(ValueError):
        Layout.load(path)


def test_a_dropped_piece_snaps_on_and_turns_to_fit():
    layout = Layout()
    first = layout.place("hornby-oo", "R600")
    end = first.connectors()[1]
    # dropped near the free end, at a silly angle
    dropped_at = Transform(end.x + 8, end.y - 5, 130)
    snap = layout.snap_placement("hornby-oo", "R604", dropped_at, distance_mm=30)
    assert snap is not None
    transform, target = snap
    assert (target.x, target.y) == pytest.approx((end.x, end.y))
    layout.add(PlacedPiece("hornby-oo", "R604", transform))
    assert len(layout.free_connectors()) == 2  # joined: only the two outer ends are free


def test_a_dropped_piece_far_away_stays_where_it_is():
    layout = Layout()
    layout.place("hornby-oo", "R600")
    assert layout.snap_placement("hornby-oo", "R604", Transform(2000, 2000, 0), distance_mm=30) is None


def test_snap_candidate_names_the_end_it_joins():
    layout = Layout()
    first = layout.place("peco-n-setrack", "ST1")
    second = layout.place("peco-n-setrack", "ST1", first.connectors()[1])
    end = first.connectors()[1]
    second.moved(Transform.rotation_about((end.x, end.y), 30).then(Transform(3, 3, 0)))  # 30° out, a bit off
    transform, target = layout.snap_candidate([second], distance_mm=20)
    assert (target.x, target.y) == pytest.approx((first.connectors()[1].x, first.connectors()[1].y))
    second.moved(transform)
    assert len(layout.free_connectors()) == 2
