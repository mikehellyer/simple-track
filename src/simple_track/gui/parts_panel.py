"""The parts list: how many of each piece the layout uses — the shopping list."""
from __future__ import annotations

from collections import Counter

from PySide6.QtGui import QBrush, QFont, QPalette
from PySide6.QtWidgets import QHeaderView, QLabel, QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget

from simple_track.core.layout import Layout, Piece, part_row
from simple_track.core.units import describe


class PartsPanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        self._tree = QTreeWidget()
        self._tree.setHeaderLabels(["Part", "Description", "Qty"])
        header = self._tree.header()
        header.setStretchLastSection(False)
        header.setSectionResizeMode(0, QHeaderView.Interactive)
        header.setSectionResizeMode(1, QHeaderView.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self._tree.setColumnWidth(0, 120)
        layout.addWidget(self._tree, stretch=1)
        self._total = QLabel()
        layout.addWidget(self._total)
        self._rows: dict[tuple[str, str], QTreeWidgetItem] = {}  # (library, code) -> its line
        self._counts: dict[tuple[str, str], int] = {}
        self._lit: list[tuple[str, str]] = []  # the (library, code) lines lit up

    def show_layout(self, model: Layout, unit: str = "mm") -> None:
        self._tree.clear()
        self._rows, self._counts, self._lit = {}, {}, []
        groups: dict[str, QTreeWidgetItem] = {}
        total = 0
        for library, code, name, count in model.parts_list():
            group = groups.get(library)
            if group is None:
                group = QTreeWidgetItem([library, "", ""])
                self._tree.addTopLevelItem(group)
                group.setFirstColumnSpanned(True)
                groups[library] = group
            row = QTreeWidgetItem([code, name, str(count)])
            group.addChild(row)
            self._rows[(library, code)] = row
            self._counts[(library, code)] = count
            total += count
        self._tree.expandAll()
        text = f"{total} piece{'s' if total != 1 else ''}"
        if model.baseboard is not None:
            board = model.baseboard
            text += f" · baseboard {describe(board.width_mm, unit)} × {describe(board.depth_mm, unit)}"
        self._total.setText(text)

    def highlight(self, pieces: list[Piece]) -> None:
        """Mark the lines of the pieces selected on the layout; where only
        some of a part are selected, Qty shows how many of how many."""
        for key in self._lit:
            row = self._rows[key]
            for column in range(3):
                row.setBackground(column, QBrush())
            row.setFont(0, QFont())
            row.setText(2, str(self._counts[key]))
        self._lit = []
        selected = Counter(part_row(piece)[:2] for piece in pieces)
        colour = self.palette().color(QPalette.Highlight)
        colour.setAlpha(70)
        bold = QFont()
        bold.setBold(True)
        for key, chosen in selected.items():
            row = self._rows.get(key)
            if row is None:
                continue
            for column in range(3):
                row.setBackground(column, QBrush(colour))
            row.setFont(0, bold)
            if chosen != self._counts[key]:
                row.setText(2, f"{chosen} of {self._counts[key]}")
            self._lit.append(key)
        if self._lit:
            self._tree.scrollToItem(self._rows[self._lit[0]])

    def highlighted(self) -> list[tuple[str, str]]:
        """(code, Qty text) of the lines lit up — for tests."""
        return [(self._rows[key].text(0), self._rows[key].text(2)) for key in self._lit]
