"""Setting the size of the baseboard."""
from __future__ import annotations

from PySide6.QtWidgets import (QComboBox, QDialog, QDialogButtonBox, QDoubleSpinBox, QFormLayout, QGroupBox,
                               QVBoxLayout)

from simple_track.core.layout import Baseboard
from simple_track.core.units import BASEBOARD_PRESETS, UNITS, from_mm, to_mm

CUSTOM = "Custom size"
DEFAULT_SIZE_MM = BASEBOARD_PRESETS["8 × 4 ft"]


class BaseboardDialog(QDialog):
    def __init__(self, baseboard: Baseboard | None, unit: str = "mm", parent=None):
        super().__init__(parent)
        self.setWindowTitle("Baseboard size")
        layout = QVBoxLayout(self)

        self._group = QGroupBox("Baseboard")
        self._group.setCheckable(True)
        self._group.setChecked(baseboard is not None)
        form = QFormLayout(self._group)

        self._preset = QComboBox()
        self._preset.addItem(CUSTOM)
        self._preset.addItems(list(BASEBOARD_PRESETS))
        form.addRow("Preset", self._preset)

        self._unit = QComboBox()
        self._unit.addItems(list(UNITS))
        self._unit.setCurrentText(unit if unit in UNITS else "mm")
        form.addRow("Units", self._unit)

        self._width = QDoubleSpinBox()
        self._depth = QDoubleSpinBox()
        for box in (self._width, self._depth):
            box.setMaximum(1_000_000)
        form.addRow("Width", self._width)
        form.addRow("Depth", self._depth)
        layout.addWidget(self._group)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self._unit_shown = self._unit.currentText()
        self._set_mm(*((baseboard.width_mm, baseboard.depth_mm) if baseboard else DEFAULT_SIZE_MM))
        self._match_preset()
        self._preset.currentTextChanged.connect(self._on_preset)
        self._unit.currentTextChanged.connect(self._on_unit)
        self._width.valueChanged.connect(self._match_preset)
        self._depth.valueChanged.connect(self._match_preset)

    def _set_mm(self, width_mm: float, depth_mm: float) -> None:
        unit = self._unit.currentText()
        decimals = max(1, UNITS[unit][1])  # so imperial presets stay exact in mm
        for box, mm in ((self._width, width_mm), (self._depth, depth_mm)):
            box.blockSignals(True)
            box.setDecimals(decimals)
            box.setMinimum(from_mm(50, unit))
            box.setSuffix(f" {unit}")
            box.setValue(from_mm(mm, unit))
            box.blockSignals(False)
        self._unit_shown = unit

    def _size_mm(self) -> tuple[float, float]:
        return to_mm(self._width.value(), self._unit_shown), to_mm(self._depth.value(), self._unit_shown)

    def _on_preset(self, name: str) -> None:
        if name in BASEBOARD_PRESETS:
            self._set_mm(*BASEBOARD_PRESETS[name])

    def _on_unit(self, unit: str) -> None:
        width, depth = to_mm(self._width.value(), self._unit_shown), to_mm(self._depth.value(), self._unit_shown)
        self._set_mm(width, depth)

    def _match_preset(self) -> None:
        width, depth = self._size_mm()
        match = next((name for name, (w, d) in BASEBOARD_PRESETS.items()
                      if abs(w - width) < 1 and abs(d - depth) < 1), CUSTOM)
        self._preset.blockSignals(True)
        self._preset.setCurrentText(match)
        self._preset.blockSignals(False)

    def unit(self) -> str:
        return self._unit.currentText()

    def baseboard(self) -> Baseboard | None:
        if not self._group.isChecked():
            return None
        return Baseboard(*self._size_mm())
