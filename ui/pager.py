"""A tabless Qt page stack used with the workspace sidebar."""
from __future__ import annotations

from PyQt6.QtWidgets import QStackedWidget, QWidget


class Pager(QStackedWidget):
    """Keep the former small notebook-style API while using Qt widgets."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._titles: list[str] = []

    def add(self, widget: QWidget, text: str = "") -> None:
        self._titles.append(text)
        self.addWidget(widget)

    def tabs(self) -> list[QWidget]:
        return [self.widget(i) for i in range(self.count())]

    def tab(self, key: QWidget | int, option: str | None = None):
        index = key if isinstance(key, int) else self.index(key)
        return self._titles[index] if option == "text" else None

    def index(self, key: QWidget) -> int:
        return self.indexOf(key)

    def select(self, key: QWidget | int | None = None):
        if key is None:
            return self.currentWidget()
        self.setCurrentIndex(key if isinstance(key, int) else self.index(key))
        return None
