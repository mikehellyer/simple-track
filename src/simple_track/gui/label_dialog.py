"""Adding or editing a text label or heading."""
from __future__ import annotations

from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QDialogButtonBox, QDoubleSpinBox, QFormLayout,
                               QLineEdit, QVBoxLayout)

from simple_track.core.layout import HEADING_SIZE_MM, LABEL_SIZE_MM, TextLabel

HEADING = "Heading"
LABEL = "Label"
CUSTOM = "Custom"
STYLES = {HEADING: (HEADING_SIZE_MM, True), LABEL: (LABEL_SIZE_MM, False)}


class LabelDialog(QDialog):
    def __init__(self, label: TextLabel | None = None, heading: bool = False, parent=None):
        super().__init__(parent)
        self._editing = label is not None
        self.setWindowTitle("Edit text" if self._editing else ("Add heading" if heading else "Add label"))
        layout = QVBoxLayout(self)
        form = QFormLayout()

        self._text = QLineEdit(label.text if label else "")
        self._text.setPlaceholderText("e.g. Dunnaemare station")
        form.addRow("Text", self._text)

        self._style = QComboBox()
        self._style.addItems([HEADING, LABEL, CUSTOM])
        form.addRow("Style", self._style)

        self._size = QDoubleSpinBox()
        self._size.setRange(3, 2000)
        self._size.setDecimals(0)
        self._size.setSuffix(" mm")
        form.addRow("Size", self._size)

        self._bold = QCheckBox("Bold")
        form.addRow("", self._bold)
        layout.addLayout(form)

        self._buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self._buttons.accepted.connect(self.accept)
        self._buttons.rejected.connect(self.reject)
        layout.addWidget(self._buttons)

        size, bold = (label.size_mm, label.bold) if label else STYLES[HEADING if heading else LABEL]
        self._size.setValue(size)
        self._bold.setChecked(bold)
        self._match_style()
        self._style.currentTextChanged.connect(self._on_style)
        self._size.valueChanged.connect(self._match_style)
        self._bold.toggled.connect(self._match_style)
        self._text.textChanged.connect(self._update_ok)
        self._update_ok()

    def _on_style(self, style: str) -> None:
        if style in STYLES:
            size, bold = STYLES[style]
            for widget, value in ((self._size, size), (self._bold, bold)):
                widget.blockSignals(True)
                widget.setValue(value) if widget is self._size else widget.setChecked(value)
                widget.blockSignals(False)

    def _match_style(self) -> None:
        current = (self._size.value(), self._bold.isChecked())
        style = next((name for name, preset in STYLES.items() if preset == current), CUSTOM)
        self._style.blockSignals(True)
        self._style.setCurrentText(style)
        self._style.blockSignals(False)

    def _update_ok(self) -> None:
        self._buttons.button(QDialogButtonBox.Ok).setEnabled(bool(self._text.text().strip()))

    def apply_to(self, label: TextLabel) -> None:
        label.text = self._text.text().strip()
        label.size_mm = self._size.value()
        label.bold = self._bold.isChecked()

    def new_label(self) -> TextLabel:
        label = TextLabel("", 0.0, 0.0)
        self.apply_to(label)
        return label
