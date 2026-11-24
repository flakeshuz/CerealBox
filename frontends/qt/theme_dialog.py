"""Theme selection and live preview dialog."""
from __future__ import annotations

from collections.abc import Callable

from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QApplication,
    QColorDialog,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from . import theme as T


class ThemeDialog(QDialog):
    def __init__(
        self,
        app: QApplication,
        original: dict[str, str],
        on_preview: Callable[[], None],
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self.app = app
        self.original = T.normalize_theme(original)
        self.config = dict(self.original)
        self.on_preview = on_preview
        self.setWindowTitle("Customize theme")
        self.setModal(True)

        root = QVBoxLayout(self)
        form = QFormLayout()
        self.preset = QComboBox()
        self._preset_ids = list(T.PRESET_LABELS)
        for key in self._preset_ids:
            self.preset.addItem(T.PRESET_LABELS[key], key)
        self.preset.setCurrentIndex(self._preset_ids.index(self.config["preset"]))
        form.addRow("Theme", self.preset)

        self._swatches: dict[str, QLabel] = {}
        self._color_buttons: dict[str, QPushButton] = {}
        for field in T.COLOR_FIELDS:
            row = QHBoxLayout()
            swatch = QLabel()
            swatch.setFixedSize(32, 24)
            self._swatches[field] = swatch
            row.addWidget(swatch)
            button = QPushButton("Choose…")
            button.setAccessibleName(f"Choose {field} color")
            button.setToolTip(f"Choose {field} color")
            button.clicked.connect(lambda _checked=False, name=field: self._choose_color(name))
            self._color_buttons[field] = button
            row.addWidget(button)
            row.addStretch(1)
            form.addRow(field.capitalize(), row)
        root.addLayout(form)

        self.status = QLabel()
        self.status.setWordWrap(True)
        root.addWidget(self.status)

        buttons = QDialogButtonBox()
        self.apply_button = buttons.addButton("Apply", QDialogButtonBox.ButtonRole.AcceptRole)
        cancel = buttons.addButton(QDialogButtonBox.StandardButton.Cancel)
        self.apply_button.setProperty("primary", True)
        self.apply_button.clicked.connect(self._apply)
        cancel.clicked.connect(self.reject)
        root.addWidget(buttons)
        self.preset.currentIndexChanged.connect(self._preset_changed)
        self._update_controls()
        self._preview()

    def _preset_changed(self, index: int) -> None:
        if not 0 <= index < len(self._preset_ids):
            return
        preset = self._preset_ids[index]
        if preset == "custom":
            self.config = {"preset": "custom", **{
                field: self.config[field] for field in T.COLOR_FIELDS
            }}
        else:
            self.config = T.theme_config(preset)
        self._update_controls()
        self._preview()

    def _choose_color(self, field: str) -> None:
        dialog = QColorDialog(QColor(self.config[field]), self)
        dialog.setOption(QColorDialog.ColorDialogOption.DontUseNativeDialog, True)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        self.config = {"preset": "custom", **{
            name: self.config[name] for name in T.COLOR_FIELDS
        }}
        self.config[field] = dialog.selectedColor().name().upper()
        self.preset.setCurrentIndex(self._preset_ids.index("custom"))
        self._update_controls()
        self._preview()

    def _update_controls(self) -> None:
        custom = self.config["preset"] == "custom"
        for field, button in self._color_buttons.items():
            button.setEnabled(custom)
            button.setText(self.config[field])
            self._swatches[field].setToolTip(self.config[field])
            self._swatches[field].setStyleSheet(
                f"background: {self.config[field]}; border: 1px solid {T.LINE}; border-radius: 3px;"
            )

    def _preview(self) -> None:
        T.apply(self.app, self.config)
        self.on_preview()
        errors = T.theme_errors(self.config)
        self.apply_button.setEnabled(not errors)
        if errors:
            self.status.setObjectName("themeError")
            self.status.setStyleSheet(f"color: {T.NOW};")
            self.status.setText("\n".join(errors))
        else:
            self.status.setObjectName("muted")
            self.status.setStyleSheet("")
            self.status.setText(f"Previewing {T.PRESET_LABELS[self.config['preset']]}. Apply to save this theme.")
        self._update_controls()

    def _apply(self) -> None:
        if not T.theme_errors(self.config):
            self.accept()

    def done(self, result: int) -> None:
        if result != QDialog.DialogCode.Accepted:
            T.apply(self.app, self.original)
            self.on_preview()
        super().done(result)
