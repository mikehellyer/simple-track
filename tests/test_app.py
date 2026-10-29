import os

import pytest

from simple_track.app import self_test

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


def test_self_test_passes():
    assert self_test() == 0


@pytest.fixture
def window(tmp_path):
    from PySide6.QtWidgets import QApplication

    from simple_track.core.settings import SettingsStore
    from simple_track.gui.main_window import MainWindow

    app = QApplication.instance() or QApplication([])
    win = MainWindow(SettingsStore(tmp_path / "settings.json"), check_updates=False)
    yield win
    win._dirty = False
    win.close()
    app.processEvents()


def test_building_track_and_undo(window):
    window.canvas.place("hornby-oo", "R600")
    window.canvas.place("hornby-oo", "R604")
    assert len(window.canvas.layout_model.pieces) == 2
    assert window.canvas.layout_model.free_connectors()[0].__class__ is tuple
    window._do_undo()
    assert len(window.canvas.layout_model.pieces) == 1
    window._do_redo()
    assert len(window.canvas.layout_model.pieces) == 2


def test_tab_turns_the_new_piece_round(window):
    first = window.canvas.place("peco-oo-streamline-100", "SL-95")
    before = [round(c.x) for c in first.connectors()]
    assert window.canvas.next_end()
    after = [round(c.x) for c in first.connectors()]
    assert before != after
    # still joined to nothing else, still three free ends
    assert len(window.canvas.layout_model.free_connectors()) == 3


def test_parts_list_follows_edits(window):
    window.canvas.place("peco-n-setrack", "ST1")
    window.canvas.place("peco-n-setrack", "ST1")
    assert "2 pieces" in window.parts_panel._total.text()


def test_piece_drag_data_round_trips():
    from simple_track.gui.library_panel import decode_piece, encode_piece

    assert decode_piece(encode_piece("peco-oo-setrack", "ST-225")) == ("peco-oo-setrack", "ST-225")


def test_dropping_a_piece_near_an_end_joins_it(window):
    from simple_track.gui.canvas import to_scene

    canvas = window.canvas
    first = canvas.place("hornby-oo", "R600")
    end = first.connectors()[1]
    near = to_scene((end.x + 40, end.y + 10))  # mouse just past the end
    canvas.resetTransform()  # 1 px = 1 mm, so the drop snap reaches 30 mm
    target = canvas.preview_piece("hornby-oo", "R600", near)
    assert target is None  # the piece's centre is under the mouse, so its end is ~120 mm away
    near = to_scene((end.x + 90, end.y + 6))
    assert canvas.preview_piece("hornby-oo", "R600", near) is not None
    dropped = canvas.drop_piece("hornby-oo", "R600", near)
    assert dropped is not None
    assert len(canvas.layout_model.pieces) == 2
    assert len(canvas.layout_model.free_connectors()) == 2
    assert canvas.selected_pieces() == [dropped]
    window._do_undo()
    assert len(canvas.layout_model.pieces) == 1


def test_dropping_on_empty_board_places_it_under_the_mouse(window):
    from simple_track.gui.canvas import from_scene, to_scene

    piece = window.canvas.drop_piece("peco-n-setrack", "ST1", to_scene((500, 300)))
    xs = [p[0] for line in piece.polylines() for p in line]
    assert (min(xs) + max(xs)) / 2 == pytest.approx(500)
    assert from_scene(to_scene((1, 2))) == (1, 2)


def test_dropping_onto_a_free_end_joins_there(window):
    from simple_track.gui.canvas import to_scene

    canvas = window.canvas
    first = canvas.place("hornby-oo", "R600")
    end = first.connectors()[1]
    canvas.resetTransform()
    canvas.drop_piece("hornby-oo", "R604", to_scene((end.x + 5, end.y - 4)))
    assert len(canvas.layout_model.free_connectors()) == 2
