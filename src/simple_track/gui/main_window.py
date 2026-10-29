"""The main window: the parts bin on the left, the layout in the middle, the
parts list on the right, and the menus."""
from __future__ import annotations

import json
import sys
from pathlib import Path

from PySide6.QtCore import Qt, QTimer, QUrl
from PySide6.QtGui import QAction, QDesktopServices, QIcon, QKeySequence
from PySide6.QtWidgets import (QDockWidget, QFileDialog, QLabel, QMainWindow, QMessageBox, QVBoxLayout,
                               QWidget)

from simple_track import __version__
from simple_track.core.anyrail import AnyRailError, import_any
from simple_track.core.diagnostics import log_dir
from simple_track.core.layout import FILE_SUFFIX, Layout
from simple_track.core.self_update import download_asset, find_asset_for_this_platform, launch_installer
from simple_track.core.settings import SettingsStore
from simple_track.core.updater import API_TIMEOUT_SECONDS, check_for_update
from simple_track.gui.canvas import LayoutCanvas
from simple_track.gui.library_panel import LibraryPanel
from simple_track.gui.parts_panel import PartsPanel
from simple_track.gui.update_banner import UpdateBanner
from simple_track.gui.workers import BackgroundRunner

UPDATE_OWNER = "mikehellyer"
UPDATE_REPO = "simple-track"
BACKGROUND_JOIN_TIMEOUT_MS = (API_TIMEOUT_SECONDS + 1) * 1000
ICON_PATH = Path(__file__).parent / "resources" / "icon.png"
UNDO_LIMIT = 200


class MainWindow(QMainWindow):
    def __init__(self, store: SettingsStore | None = None, check_updates: bool = True):
        super().__init__()
        self.setWindowIcon(QIcon(str(ICON_PATH)))
        self.resize(1320, 820)

        self._store = store or SettingsStore()
        self._runner = BackgroundRunner(self)
        self._pending_update = None
        self._path: Path | None = None
        self._dirty = False
        self._undo: list[str] = []
        self._redo: list[str] = []

        central = QWidget()
        layout = QVBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self._update_banner = UpdateBanner()
        self._update_banner.update_clicked.connect(self._start_update)
        layout.addWidget(self._update_banner)
        self.canvas = LayoutCanvas()
        layout.addWidget(self.canvas, stretch=1)
        self.setCentralWidget(central)

        self.library_panel = LibraryPanel(self._store.settings.library)
        self.library_panel.piece_chosen.connect(self._add_piece)
        self.library_panel.library_changed.connect(lambda library_id: self._store.update(library=library_id))
        library_dock = QDockWidget("Track", self)
        library_dock.setObjectName("track")
        library_dock.setWidget(self.library_panel)
        library_dock.setFeatures(QDockWidget.DockWidgetMovable)
        self.addDockWidget(Qt.LeftDockWidgetArea, library_dock)

        self.parts_panel = PartsPanel()
        parts_dock = QDockWidget("Parts list", self)
        parts_dock.setObjectName("parts")
        parts_dock.setWidget(self.parts_panel)
        parts_dock.setFeatures(QDockWidget.DockWidgetMovable | QDockWidget.DockWidgetClosable)
        self.addDockWidget(Qt.RightDockWidgetArea, parts_dock)
        self._parts_dock = parts_dock

        self._position = QLabel()
        self.statusBar().addPermanentWidget(self._position)
        self.canvas.cursor_moved.connect(lambda x, y: self._position.setText(f"x {x:.0f} mm   y {y:.0f} mm"))
        self.canvas.changed.connect(self._on_changed)
        self.canvas.selection_changed.connect(self._on_selection)

        self._build_menus()
        self._set_layout(Layout(), None)
        self.statusBar().showMessage("Pick a track library on the left, then double-click a piece to start.")
        if check_updates:
            QTimer.singleShot(1500, self._check_for_updates)

    # --- menus

    def _action(self, menu, text: str, slot, shortcut=None) -> QAction:
        action = QAction(text, self)
        if shortcut is not None:
            action.setShortcut(shortcut)
        action.triggered.connect(slot)
        menu.addAction(action)
        return action

    def _build_menus(self) -> None:
        file_menu = self.menuBar().addMenu("&File")
        self._action(file_menu, "&New layout", self._new, QKeySequence.New)
        self._action(file_menu, "&Open…", self._open, QKeySequence.Open)
        self._action(file_menu, "&Save", self._save, QKeySequence.Save)
        self._action(file_menu, "Save &as…", self._save_as, QKeySequence.SaveAs)
        file_menu.addSeparator()
        self._action(file_menu, "&Import…", self._import_layout, "Ctrl+I")
        file_menu.addSeparator()
        self._action(file_menu, "&Quit", self.close, QKeySequence.Quit)

        edit_menu = self.menuBar().addMenu("&Edit")
        self._undo_action = self._action(edit_menu, "&Undo", self._do_undo, QKeySequence.Undo)
        self._redo_action = self._action(edit_menu, "&Redo", self._do_redo, QKeySequence.Redo)
        edit_menu.addSeparator()
        self._action(edit_menu, "Turn the new piece &round (Tab)", self.canvas.next_end)
        self._action(edit_menu, "Rotate selection (R)", lambda: self.canvas.rotate_selected())
        self._action(edit_menu, "&Delete selection (Del)", self.canvas.delete_selected)
        self._action(edit_menu, "Select &all", self.canvas.select_all, QKeySequence.SelectAll)

        view_menu = self.menuBar().addMenu("&View")
        self._action(view_menu, "Zoom to &fit", self.canvas.zoom_to_fit, "F")
        self._action(view_menu, "Zoom &in", lambda: self.canvas.zoom(1.25), QKeySequence.ZoomIn)
        self._action(view_menu, "Zoom &out", lambda: self.canvas.zoom(0.8), QKeySequence.ZoomOut)
        view_menu.addSeparator()
        view_menu.addAction(self._parts_dock.toggleViewAction())

        help_menu = self.menuBar().addMenu("&Help")
        self._action(help_menu, "Check for &updates", lambda: self._check_for_updates(tell_if_none=True))
        self._action(help_menu, "Open the &log folder",
                     lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(log_dir()))))
        help_menu.addSeparator()
        self._action(help_menu, "&About Simple-Track", self._about)

    # --- layout state

    def _set_layout(self, layout: Layout, path: Path | None) -> None:
        self._path = path
        self._dirty = False
        self._undo.clear()
        self._redo.clear()
        self._snapshot = json.dumps(layout.to_json())
        self.canvas.set_layout(layout)
        self._after_edit()

    def _on_changed(self) -> None:
        self._undo.append(self._snapshot)
        del self._undo[:-UNDO_LIMIT]
        self._redo.clear()
        self._snapshot = json.dumps(self.canvas.layout_model.to_json())
        self._dirty = True
        self._after_edit()

    def _restore(self, snapshot: str) -> None:
        self._snapshot = snapshot
        self.canvas.set_layout(Layout.from_json(json.loads(snapshot)), fit=False)
        self._dirty = True
        self._after_edit()

    def _do_undo(self) -> None:
        if self._undo:
            self._redo.append(self._snapshot)
            self._restore(self._undo.pop())

    def _do_redo(self) -> None:
        if self._redo:
            self._undo.append(self._snapshot)
            self._restore(self._redo.pop())

    def _after_edit(self) -> None:
        self.parts_panel.show_layout(self.canvas.layout_model)
        self._undo_action.setEnabled(bool(self._undo))
        self._redo_action.setEnabled(bool(self._redo))
        name = self._path.stem if self._path else self.canvas.layout_model.name
        self.setWindowTitle(f"{'• ' if self._dirty else ''}{name} — Simple-Track")

    def _on_selection(self, count: int) -> None:
        if count:
            pieces = self.canvas.selected_pieces()
            label = pieces[0].label if count == 1 else f"{count} pieces"
            self.statusBar().showMessage(f"{label} selected — drag to move, R to rotate, Del to delete")
        else:
            self.statusBar().clearMessage()

    def _add_piece(self, library_id: str, code: str) -> None:
        self.canvas.place(library_id, code)
        self.canvas.setFocus()

    # --- files

    def _folder(self) -> str:
        return self._store.settings.last_folder or str(Path.home())

    def _confirm_discard(self) -> bool:
        if not self._dirty:
            return True
        answer = QMessageBox.question(self, "Simple-Track", "Save the changes to this layout first?",
                                      QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel)
        if answer == QMessageBox.Save:
            return self._save()
        return answer == QMessageBox.Discard

    def _new(self) -> None:
        if self._confirm_discard():
            self._set_layout(Layout(), None)

    def _open(self) -> None:
        if not self._confirm_discard():
            return
        name, _ = QFileDialog.getOpenFileName(self, "Open layout", self._folder(),
                                              f"Simple-Track layouts (*{FILE_SUFFIX});;Other layouts (*.any)")
        if name:
            self.open_path(Path(name))

    def open_path(self, path: Path) -> None:
        if path.suffix.lower() == ".any":
            self._import_path(path)
            return
        try:
            layout = Layout.load(path)
        except (OSError, ValueError, KeyError) as error:
            QMessageBox.warning(self, "Simple-Track", f"Couldn't open {path.name}:\n{error}")
            return
        self._store.update(last_folder=str(path.parent))
        self._set_layout(layout, path)

    def _save(self) -> bool:
        if self._path is None:
            return self._save_as()
        try:
            self.canvas.layout_model.save(self._path)
        except OSError as error:
            QMessageBox.warning(self, "Simple-Track", f"Couldn't save {self._path.name}:\n{error}")
            return False
        self._dirty = False
        self._after_edit()
        return True

    def _save_as(self) -> bool:
        suggested = str(Path(self._folder()) / f"{self.canvas.layout_model.name}{FILE_SUFFIX}")
        name, _ = QFileDialog.getSaveFileName(self, "Save layout", suggested, f"Simple-Track layouts (*{FILE_SUFFIX})")
        if not name:
            return False
        path = Path(name)
        if path.suffix.lower() != FILE_SUFFIX:
            path = path.with_suffix(FILE_SUFFIX)
        self._path = path
        self.canvas.layout_model.name = path.stem
        self._store.update(last_folder=str(path.parent))
        return self._save()

    def _import_layout(self) -> None:
        if not self._confirm_discard():
            return
        name, _ = QFileDialog.getOpenFileName(self, "Import", self._folder(), "Layouts (*.any)")
        if name:
            self._import_path(Path(name))

    def _import_path(self, path: Path) -> None:
        try:
            layout = import_any(path)
        except (OSError, AnyRailError) as error:
            QMessageBox.warning(self, "Import", f"Couldn't import {path.name}:\n{error}")
            return
        self._store.update(last_folder=str(path.parent))
        self._set_layout(layout, None)
        self._dirty = True
        self._after_edit()
        notes = "\n".join(f"• {note}" for note in layout.notes)
        QMessageBox.information(
            self, "Import",
            f"Imported {len(layout.pieces)} pieces from {path.name}.\n\n"
            "Imported track keeps its original shapes (shown in grey); it can be moved, rotated "
            "and deleted, and new track can be joined onto it." + (f"\n\n{notes}" if notes else ""))

    # --- about & updates

    def _about(self) -> None:
        QMessageBox.about(
            self,
            "About Simple-Track",
            f"<b>Simple-Track</b> v{__version__}<br><br>"
            "A model railway layout designer: Peco and Hornby track in OO and N.<br><br>"
            "Track geometry from the parameter files of "
            "<a href='https://sourceforge.net/projects/xtrkcad-fork/'>XTrackCAD</a>.<br><br>"
            "By Mike Hellyer, built with Claude Code.",
        )

    def _check_for_updates(self, tell_if_none: bool = False) -> None:
        def checked(info):
            self._on_update_checked(info)
            if info is None and tell_if_none:
                QMessageBox.information(self, "Simple-Track", f"You have the latest version ({__version__}).")

        self._runner.run(lambda: check_for_update(__version__, UPDATE_OWNER, UPDATE_REPO), checked,
                         lambda error: None)

    def _on_update_checked(self, info) -> None:
        if info:
            self._pending_update = info
            self._update_banner.announce(info.version)

    def _start_update(self) -> None:
        if self._pending_update is None:
            return
        asset_url = find_asset_for_this_platform(self._pending_update.assets)
        if asset_url is None:
            self._update_banner.set_status(f"No installer for this platform — see {self._pending_update.url}")
            return
        self._update_banner.set_busy(True, "Downloading…")
        self._runner.run(lambda: download_asset(asset_url), self._on_update_downloaded,
                         lambda error: self._on_update_downloaded(None))

    def _on_update_downloaded(self, path) -> None:
        if path is None:
            self._update_banner.set_status("Couldn't download the update — try again")
            self._update_banner.set_busy(False)
            return
        try:
            process = launch_installer(path)
        except OSError:
            self._update_banner.set_status(f"Downloaded to {path} — open it manually")
            self._update_banner.set_busy(False)
            return

        self._update_banner.set_status("Installer launched — closing to finish…")
        if sys.platform not in ("win32", "darwin") and process is not None:
            # Linux: wait for pkexec/apt to finish before quitting — quitting
            # immediately can kill its password prompt before it's answered.
            self._runner.run(lambda: (path, self._wait_for_installer(process)), self._on_installer_finished)
        else:
            QTimer.singleShot(1500, self.close)

    @staticmethod
    def _wait_for_installer(process) -> tuple[int, str]:
        returncode = process.wait()
        stderr_text = process.stderr.read().strip() if process.stderr is not None else ""
        return returncode, stderr_text

    def _on_installer_finished(self, result) -> None:
        path, (returncode, stderr_text) = result
        if returncode == 0:
            self._dirty = False  # the installer is replacing us; nothing to ask
            self.close()
            return
        detail = f": {stderr_text}" if stderr_text else f" (exit code {returncode})"
        self._update_banner.set_status(f"Update didn't install{detail} — installer is at {path}")
        self._update_banner.set_busy(False)

    def closeEvent(self, event) -> None:
        if not self._confirm_discard():
            event.ignore()
            return
        self._store.save()
        self._runner.shutdown(BACKGROUND_JOIN_TIMEOUT_MS)
        super().closeEvent(event)
