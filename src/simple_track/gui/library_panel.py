"""The parts bin: pick a track library, then a piece to add."""
from __future__ import annotations

from PySide6.QtCore import QMimeData, Qt, Signal
from PySide6.QtWidgets import (QComboBox, QLabel, QLineEdit, QPushButton, QTreeWidget, QTreeWidgetItem,
                               QVBoxLayout, QWidget)

from simple_track.core.library import Library, builtin_libraries

PIECE_ROLE = Qt.UserRole
# What a piece dragged out of the list carries: "<library id>\t<code>".
PIECE_MIME = "application/x-simple-track-piece"


def encode_piece(library_id: str, code: str) -> QMimeData:
    data = QMimeData()
    data.setData(PIECE_MIME, f"{library_id}\t{code}".encode("utf-8"))
    return data


def decode_piece(data: QMimeData) -> tuple[str, str] | None:
    if not data.hasFormat(PIECE_MIME):
        return None
    library_id, _, code = bytes(data.data(PIECE_MIME)).decode("utf-8").partition("\t")
    return (library_id, code) if code else None


class _PieceTree(QTreeWidget):
    """The list of pieces; any piece can be dragged out onto the layout."""

    library_id = ""

    def mimeTypes(self) -> list[str]:
        return [PIECE_MIME]

    def mimeData(self, items) -> QMimeData:
        code = items[0].data(0, PIECE_ROLE) if items else None
        return encode_piece(self.library_id, code) if code else QMimeData()


class LibraryPanel(QWidget):
    piece_chosen = Signal(str, str)  # library id, piece code
    library_changed = Signal(str)

    def __init__(self, library_id: str = "", parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)

        self._libraries = builtin_libraries()
        self._combo = QComboBox()
        for library in self._libraries:
            self._combo.addItem(f"{library.scale} · {library.name}", library.id)
        layout.addWidget(self._combo)

        self._filter = QLineEdit()
        self._filter.setPlaceholderText("Filter pieces…")
        self._filter.setClearButtonEnabled(True)
        layout.addWidget(self._filter)

        self._tree = _PieceTree()
        self._tree.setDragEnabled(True)
        self._tree.setDragDropMode(QTreeWidget.DragOnly)
        self._tree.setHeaderLabels(["Part", "Description"])
        self._tree.setRootIsDecorated(True)
        self._tree.setColumnWidth(0, 110)
        layout.addWidget(self._tree, stretch=1)

        self._add = QPushButton("Add to layout")
        self._add.setEnabled(False)
        layout.addWidget(self._add)

        hint = QLabel("Drag a piece onto the layout — near a free end it snaps on. Or "
                      "double-click to add it at the orange end; Tab turns it round.")
        hint.setWordWrap(True)
        hint.setStyleSheet("color: palette(placeholder-text); font-size: 11px;")
        layout.addWidget(hint)

        self._combo.currentIndexChanged.connect(self._on_library_changed)
        self._filter.textChanged.connect(self._populate)
        self._tree.itemActivated.connect(self._on_activated)
        self._tree.currentItemChanged.connect(lambda item, _: self._add.setEnabled(bool(item and item.data(0, PIECE_ROLE))))
        self._add.clicked.connect(lambda: self._on_activated(self._tree.currentItem(), 0))

        index = self._combo.findData(library_id)
        self._combo.setCurrentIndex(index if index >= 0 else 0)
        self._populate()

    def library(self) -> Library:
        return self._libraries[max(0, self._combo.currentIndex())]

    def _on_library_changed(self) -> None:
        self._populate()
        self.library_changed.emit(self.library().id)

    def _populate(self) -> None:
        self._tree.clear()
        library = self.library()
        self._tree.library_id = library.id
        words = self._filter.text().lower().split()
        sections: dict[str, QTreeWidgetItem] = {}
        for piece in library.pieces:
            text = f"{piece.code} {piece.name} {piece.section}".lower()
            if not all(word in text for word in words):
                continue
            section = sections.get(piece.section)
            if section is None:
                section = QTreeWidgetItem([piece.section, ""])
                section.setFlags(section.flags() & ~Qt.ItemIsSelectable & ~Qt.ItemIsDragEnabled)
                self._tree.addTopLevelItem(section)
                section.setFirstColumnSpanned(True)
                sections[piece.section] = section
            item = QTreeWidgetItem([piece.code, piece.name])
            item.setData(0, PIECE_ROLE, piece.code)
            item.setToolTip(1, f"{piece.name}\n{piece.length():.0f} mm")
            section.addChild(item)
        self._tree.expandAll()

    def _on_activated(self, item, _column) -> None:
        if item is None:
            return
        code = item.data(0, PIECE_ROLE)
        if code:
            self.piece_chosen.emit(self.library().id, code)
