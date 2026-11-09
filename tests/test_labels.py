import os

import pytest

from simple_track.core.geometry import Transform
from simple_track.core.layout import HEADING_SIZE_MM, Layout, TextLabel

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


def test_labels_are_saved_and_loaded(tmp_path):
    layout = Layout()
    layout.labels.append(TextLabel("Dunnaemare", 1200, 300, HEADING_SIZE_MM, True, 15))
    layout.labels.append(TextLabel("Goods yard", 400, 80))
    path = tmp_path / "labels.strack"
    layout.save(path)
    loaded = Layout.load(path)
    assert [label.to_json() for label in loaded.labels] == [label.to_json() for label in layout.labels]


def test_files_without_labels_and_broken_labels_still_open():
    base = {"format": "simple-track", "version": 1, "pieces": []}
    assert Layout.from_json(base).labels == []
    data = {**base, "labels": [{"text": "", "x": 0, "y": 0}, {"text": "No position"}, "junk",
                               {"text": "Fine", "x": 1, "y": 2}]}
    assert [label.text for label in Layout.from_json(data).labels] == ["Fine"]


def test_labels_move_turn_and_are_removed_by_id():
    layout = Layout()
    label = TextLabel("Shed", 100, 0)
    layout.labels.append(label)
    label.moved(Transform.rotation_about((0, 0), 90))
    assert (label.x, label.y, label.rotation) == pytest.approx((0, 100, 90))
    layout.remove(label.id)
    assert layout.labels == []


def test_labels_count_towards_zoom_to_fit_but_not_the_track():
    layout = Layout()
    layout.labels.append(TextLabel("Far away", 5000, 5000))
    assert layout.bounds()[2] >= 5000
    assert layout.free_connectors() == [] and layout.parts_list() == []


@pytest.fixture
def app():
    from PySide6.QtWidgets import QApplication

    return QApplication.instance() or QApplication([])


def test_dialog_styles(app):
    from PySide6.QtWidgets import QDialogButtonBox

    from simple_track.gui.label_dialog import LabelDialog

    dialog = LabelDialog(heading=True)
    assert dialog._style.currentText() == "Heading"
    assert not dialog._buttons.button(QDialogButtonBox.Ok).isEnabled()  # no text yet
    dialog._text.setText("  Dunnaemare  ")
    assert dialog._buttons.button(QDialogButtonBox.Ok).isEnabled()
    label = dialog.new_label()
    assert (label.text, label.size_mm, label.bold) == ("Dunnaemare", HEADING_SIZE_MM, True)
    dialog._style.setCurrentText("Label")
    assert not dialog._bold.isChecked() and dialog._size.value() < HEADING_SIZE_MM
    dialog._size.setValue(40)
    assert dialog._style.currentText() == "Custom"


@pytest.fixture
def window(app, tmp_path):
    from simple_track.core.settings import SettingsStore
    from simple_track.gui.main_window import MainWindow

    win = MainWindow(SettingsStore(tmp_path / "settings.json"), check_updates=False)
    win.resize(1200, 800)
    win.show()
    app.processEvents()
    view = win.canvas
    view.resetTransform()
    view.scale(0.5, 0.5)
    view.centerOn(0, 0)
    yield win
    win._dirty = False
    win.close()
    app.processEvents()


def px(view, x, y):
    from simple_track.gui.canvas import to_scene

    return view.mapFromScene(to_scene((x, y)))


def test_a_label_is_added_in_the_middle_of_the_view_and_can_be_undone(window):
    canvas = window.canvas
    label = canvas.add_label(TextLabel("Dunnaemare", 0, 0, HEADING_SIZE_MM, True))
    assert (label.x, label.y) == pytest.approx((0, 0), abs=3)
    assert canvas.selected_labels() == [label]
    window._do_undo()
    assert canvas.layout_model.labels == []
    window._do_redo()
    assert [lab.text for lab in canvas.layout_model.labels] == ["Dunnaemare"]


def test_a_label_can_be_clicked_dragged_rotated_and_deleted(window):
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest

    from simple_track.gui.canvas import LabelItem

    canvas = window.canvas
    label = canvas.add_label(TextLabel("Goods yard", 0, 0, 40))
    canvas.scene().clearSelection()
    assert isinstance(canvas.item_at(px(canvas, 0, 0)), LabelItem)

    start, end = px(canvas, 0, 0), px(canvas, 300, -200)
    QTest.mousePress(canvas.viewport(), Qt.LeftButton, Qt.NoModifier, start)
    for i in range(1, 9):
        QTest.mouseMove(canvas.viewport(), start + (end - start) * i / 8)
    QTest.mouseRelease(canvas.viewport(), Qt.LeftButton, Qt.NoModifier, end)
    assert (label.x, label.y) == pytest.approx((300, -200), abs=4)
    assert canvas.selected_labels() == [label]

    QTest.keyClick(canvas, Qt.Key_R)
    assert label.rotation == pytest.approx(15)
    QTest.keyClick(canvas, Qt.Key_Delete)
    assert canvas.layout_model.labels == []


def test_double_clicking_a_label_asks_to_edit_it(window):
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest

    canvas = window.canvas
    label = canvas.add_label(TextLabel("Platform 1", 0, 0, 40))
    canvas.edit_label_requested.disconnect(window._edit_label)  # it would open the real (modal) dialog
    asked = []
    canvas.edit_label_requested.connect(asked.append)
    QTest.mouseDClick(canvas.viewport(), Qt.LeftButton, Qt.NoModifier, px(canvas, 0, 0))
    assert asked == [label.id]


def test_editing_a_label_changes_it_and_can_be_undone(window, monkeypatch):
    from simple_track.gui import main_window

    canvas = window.canvas
    label = canvas.add_label(TextLabel("Platfrom 1", 0, 0))

    class FakeDialog:
        def __init__(self, *args, **kwargs):
            pass

        def exec(self):
            return True

        def apply_to(self, target):
            target.text, target.size_mm, target.bold = "Platform 1", 50, True

    monkeypatch.setattr(main_window, "LabelDialog", FakeDialog)
    window._edit_label(label.id)
    assert (label.text, label.size_mm, label.bold) == ("Platform 1", 50, True)
    window._do_undo()
    assert canvas.layout_model.labels[0].text == "Platfrom 1"


def test_a_label_selected_with_track_rides_along_when_it_snaps_on(window):
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest

    from simple_track.gui.canvas import to_scene

    canvas = window.canvas
    base = canvas.drop_piece("hornby-oo", "R600", to_scene((0, 0)))
    loose = canvas.drop_piece("hornby-oo", "R600", to_scene((0, -500)))
    label = canvas.add_label(TextLabel("Siding", 0, 0, 30))
    label.x, label.y = loose.connectors()[0].x + 80, loose.connectors()[0].y + 40
    canvas.refresh()
    canvas.scene().clearSelection()
    canvas._items[loose.id].setSelected(True)
    canvas._items[label.id].setSelected(True)
    offset = (label.x - loose.connectors()[0].x, label.y - loose.connectors()[0].y)

    grip, target = loose.connectors()[0], base.connectors()[1]
    start, end = px(canvas, grip.x + 30, grip.y), px(canvas, target.x + 32, target.y + 6)
    QTest.mousePress(canvas.viewport(), Qt.LeftButton, Qt.NoModifier, start)
    for i in range(1, 9):
        QTest.mouseMove(canvas.viewport(), start + (end - start) * i / 8)
    QTest.mouseRelease(canvas.viewport(), Qt.LeftButton, Qt.NoModifier, end)

    assert len(canvas.layout_model.free_connectors()) == 2  # the track joined
    joined = loose.connectors()[0]
    assert (label.x - joined.x, label.y - joined.y) == pytest.approx(offset, abs=0.5)  # and the label kept its place
