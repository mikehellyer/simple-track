import os

import pytest

from simple_track.core.layout import Baseboard, Layout
from simple_track.core.units import describe, from_mm, to_mm

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


def test_units():
    assert to_mm(8, "ft") == pytest.approx(2438.4)
    assert from_mm(1220, "cm") == pytest.approx(122)
    assert describe(2440, "mm") == "2440 mm"
    assert describe(1219.2, "ft") == "4 ft"
    assert describe(1220, "ft") == "4 ft"  # within a tenth of an inch
    assert describe(1371.6, "ft") == "4 ft 6 in"
    assert describe(1500, "m") == "1.5 m"


def test_baseboard_is_saved_and_loaded(tmp_path):
    layout = Layout(baseboard=Baseboard(2440, 1220))
    path = tmp_path / "board.strack"
    layout.save(path)
    assert Layout.load(path).baseboard == Baseboard(2440, 1220)


def test_older_files_and_bad_sizes_have_no_baseboard():
    assert Layout.from_json({"format": "simple-track", "version": 1, "pieces": []}).baseboard is None
    data = {"format": "simple-track", "version": 1, "pieces": [], "baseboard": {"width_mm": -5, "depth_mm": 10}}
    assert Layout.from_json(data).baseboard is None


def test_bounds_take_in_the_baseboard():
    layout = Layout(baseboard=Baseboard(1800, 1200))
    assert layout.bounds() == (0, 0, 1800, 1200)
    layout.place("hornby-oo", "R600")  # sits from x 0 to 167.5 at y 0
    assert layout.bounds() == (0, 0, 1800, 1200)


@pytest.fixture
def app():
    from PySide6.QtWidgets import QApplication

    return QApplication.instance() or QApplication([])


def test_dialog_presets_units_and_switching_off(app):
    from simple_track.gui.baseboard_dialog import BaseboardDialog

    dialog = BaseboardDialog(None, "mm")
    assert dialog.baseboard() is None  # no board yet, so the box starts unticked
    dialog._group.setChecked(True)
    dialog._preset.setCurrentText("6 × 4 ft")
    board = dialog.baseboard()
    assert (board.width_mm, board.depth_mm) == pytest.approx((1828.8, 1219.2))
    dialog._unit.setCurrentText("ft")  # same board, shown in feet
    assert dialog._width.value() == pytest.approx(6)
    assert dialog.baseboard().width_mm == pytest.approx(1828.8, abs=0.5)
    dialog._width.setValue(7)
    assert dialog._preset.currentText() == "Custom size"
    dialog._group.setChecked(False)
    assert dialog.baseboard() is None


def test_setting_a_baseboard_can_be_undone(app, tmp_path, monkeypatch):
    from simple_track.core.settings import SettingsStore
    from simple_track.gui import main_window
    from simple_track.gui.main_window import MainWindow

    class FakeDialog:
        def __init__(self, *args):
            pass

        def exec(self):
            return True

        def unit(self):
            return "ft"

        def baseboard(self):
            return Baseboard(2440, 1220)

    monkeypatch.setattr(main_window, "BaseboardDialog", FakeDialog)
    window = MainWindow(SettingsStore(tmp_path / "s.json"), check_updates=False)
    window._edit_baseboard()
    assert window.canvas.layout_model.baseboard == Baseboard(2440, 1220)
    assert "baseboard 8 ft 0.1 in × 4 ft" in window.parts_panel._total.text()
    window._do_undo()
    assert window.canvas.layout_model.baseboard is None
    window._dirty = False
    window.close()
