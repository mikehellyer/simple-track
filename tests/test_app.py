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
