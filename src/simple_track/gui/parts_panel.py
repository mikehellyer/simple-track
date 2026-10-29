"""The parts list: how many of each piece the layout uses — the shopping list."""
from __future__ import annotations

from PySide6.QtWidgets import QHeaderView, QLabel, QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget

from simple_track.core.layout import Layout
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

    def show_layout(self, model: Layout, unit: str = "mm") -> None:
        self._tree.clear()
        groups: dict[str, QTreeWidgetItem] = {}
        total = 0
        for library, code, name, count in model.parts_list():
            group = groups.get(library)
            if group is None:
                group = QTreeWidgetItem([library, "", ""])
                self._tree.addTopLevelItem(group)
                group.setFirstColumnSpanned(True)
                groups[library] = group
            group.addChild(QTreeWidgetItem([code, name, str(count)]))
            total += count
        self._tree.expandAll()
        text = f"{total} piece{'s' if total != 1 else ''}"
        if model.baseboard is not None:
            board = model.baseboard
            text += f" · baseboard {describe(board.width_mm, unit)} × {describe(board.depth_mm, unit)}"
        self._total.setText(text)
