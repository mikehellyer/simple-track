"""The canvas driven the way a user drives it: real mouse presses, moves and
releases on the view."""
import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


@pytest.fixture
def canvas(tmp_path):
    from PySide6.QtWidgets import QApplication

    from simple_track.core.settings import SettingsStore
    from simple_track.gui.main_window import MainWindow

    app = QApplication.instance() or QApplication([])
    window = MainWindow(SettingsStore(tmp_path / "settings.json"), check_updates=False)
    window.resize(1200, 800)
    window.show()
    app.processEvents()
    view = window.canvas
    view.resetTransform()
    view.scale(0.5, 0.5)  # 1 px = 2 mm
    view.centerOn(0, 0)
    yield view
    window._dirty = False
    window.close()
    app.processEvents()


def px(view, x, y):
    from simple_track.gui.canvas import to_scene

    return view.mapFromScene(to_scene((x, y)))


def drag(view, start, end, modifier=None):
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest

    mods = modifier or Qt.NoModifier
    QTest.mousePress(view.viewport(), Qt.LeftButton, mods, start)
    steps = 8
    for i in range(1, steps + 1):
        point = start + (end - start) * i / steps
        QTest.mouseMove(view.viewport(), point)
    QTest.mouseRelease(view.viewport(), Qt.LeftButton, mods, end)


def middle(piece):
    xs = [p[0] for line in piece.polylines() for p in line]
    ys = [p[1] for line in piece.polylines() for p in line]
    return (min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2


def test_clicking_a_piece_finds_the_track_not_the_end_markers(canvas):
    from simple_track.gui.canvas import TrackItem, to_scene

    piece = canvas.drop_piece("hornby-oo", "R600", to_scene((0, 0)))
    assert isinstance(canvas.track_item_at(px(canvas, *middle(piece))), TrackItem)
    assert isinstance(canvas.itemAt(px(canvas, *middle(piece))), TrackItem)


def test_a_loose_piece_can_be_dragged(canvas):
    from simple_track.gui.canvas import to_scene

    piece = canvas.drop_piece("hornby-oo", "R600", to_scene((0, 0)))
    x, y = middle(piece)
    drag(canvas, px(canvas, x, y), px(canvas, x + 300, y + 200))
    nx, ny = middle(piece)
    assert (nx - x, ny - y) == pytest.approx((300, 200), abs=4)


def test_a_loose_piece_dragged_to_an_end_joins_it(canvas):
    from simple_track.gui.canvas import to_scene

    base = canvas.drop_piece("hornby-oo", "R600", to_scene((0, 0)))
    loose = canvas.drop_piece("peco-oo-setrack", "ST-225", to_scene((0, -500)))
    assert len(canvas.layout_model.free_connectors()) == 4
    target = base.connectors()[1]
    # grab the loose piece by its first end and carry that end to the base's free end
    grip = loose.connectors()[0]
    drag(canvas, px(canvas, grip.x + 6, grip.y), px(canvas, target.x + 10, target.y + 8))
    assert len(canvas.layout_model.free_connectors()) == 2


def test_rubber_band_selects_several_pieces(canvas):
    from simple_track.gui.canvas import to_scene

    for x in (0, 300, 600):
        canvas.drop_piece("peco-n-setrack", "ST1", to_scene((x, 0)))
    canvas.scene().clearSelection()
    drag(canvas, px(canvas, -150, 150), px(canvas, 750, -150))
    assert len(canvas.selected_pieces()) == 3


def test_shift_click_adds_to_the_selection(canvas):
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest

    from simple_track.gui.canvas import to_scene

    a = canvas.drop_piece("peco-n-setrack", "ST1", to_scene((0, 0)))
    b = canvas.drop_piece("peco-n-setrack", "ST1", to_scene((400, 0)))
    QTest.mouseClick(canvas.viewport(), Qt.LeftButton, Qt.NoModifier, px(canvas, *middle(a)))
    QTest.mouseClick(canvas.viewport(), Qt.LeftButton, Qt.ShiftModifier, px(canvas, *middle(b)))
    assert {p.id for p in canvas.selected_pieces()} == {a.id, b.id}


def test_double_click_selects_the_joined_run_and_it_moves_and_joins_as_one(canvas):
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest

    from simple_track.gui.canvas import to_scene

    model = canvas.layout_model
    base = canvas.drop_piece("hornby-oo", "R600", to_scene((0, 0)))
    # a separate run of three joined pieces, away from the base
    first = model.place("hornby-oo", "R600", None)
    from simple_track.core.geometry import Transform

    first.moved(Transform(-200, -600, 0))
    second = model.place("hornby-oo", "R604", first.connectors()[1])
    model.place("hornby-oo", "R604", second.connectors()[1])
    canvas.refresh()
    assert len(model.free_connectors()) == 4

    QTest.mouseDClick(canvas.viewport(), Qt.LeftButton, Qt.NoModifier, px(canvas, *middle(second)))
    assert len(canvas.selected_pieces()) == 3

    grip = first.connectors()[0]
    target = base.connectors()[1]
    drag(canvas, px(canvas, grip.x + 8, grip.y), px(canvas, target.x + 12, target.y - 6))
    assert len(canvas.selected_pieces()) == 3
    assert len(model.free_connectors()) == 2  # the run is joined onto the base as a whole


def test_clicking_a_free_end_still_makes_it_the_orange_end(canvas):
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest

    from simple_track.gui.canvas import to_scene

    piece = canvas.drop_piece("hornby-oo", "R600", to_scene((0, 0)))
    before = [(round(c.x), round(c.y)) for c in piece.connectors()]
    for index in (0, 1):
        end = piece.connectors()[index]
        QTest.mouseClick(canvas.viewport(), Qt.LeftButton, Qt.NoModifier, px(canvas, end.x + 4, end.y))
        assert canvas.active == (piece.id, index)
    assert [(round(c.x), round(c.y)) for c in piece.connectors()] == before  # clicks don't move it
