"""Filterable, keyboard-friendly navigation for the workspace."""
from __future__ import annotations

from collections.abc import Callable

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QFrame,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from . import theme as T

GROUPS = (
    ("DAILY", ("Dashboard", "Calendar", "Tasks", "Notes", "Habits", "Goals")),
    ("PERSONAL", ("Money", "Taxes", "Health", "Home", "Contacts")),
)


class Sidebar(QFrame):
    def __init__(self, parent: QWidget, titles: list[str], on_select: Callable[[int], None]):
        super().__init__(parent)
        self.setObjectName("sidebar")
        self.setMinimumWidth(210)
        self.setMaximumWidth(280)
        self._titles = titles
        self._rows: list[tuple[int, QPushButton]] = []
        self._sections: list[tuple[QLabel, list[tuple[int, QPushButton]]]] = []
        outer = QVBoxLayout(self)
        outer.setContentsMargins(16, 20, 14, 14)
        outer.setSpacing(6)

        brand = QLabel("CerealBox")
        brand.setObjectName("brand")
        outer.addWidget(brand)
        tagline = QLabel("Start your day, sorted.")
        tagline.setObjectName("muted")
        outer.addWidget(tagline)

        self.query = QLineEdit()
        self.query.setPlaceholderText("Find a space…")
        self.query.setClearButtonEnabled(True)
        self.query.setAccessibleName("Filter workspace navigation")
        outer.addWidget(self.query)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        body = QWidget()
        self._body_layout = QVBoxLayout(body)
        self._body_layout.setContentsMargins(0, 6, 0, 6)
        self._body_layout.setSpacing(2)
        scroll.setWidget(body)
        outer.addWidget(scroll, 1)

        used: set[int] = set()
        group_defs = (*GROUPS, ("LIBRARY", tuple(t for t in titles if not any(t in names for _, names in GROUPS))))
        for heading, names in group_defs:
            indices = [i for i, title in enumerate(titles) if title in names and i not in used]
            if not indices:
                continue
            label = QLabel(heading)
            label.setObjectName("muted")
            label.setStyleSheet("font-size: 8pt; font-weight: 700; padding: 8px 8px 2px;")
            self._body_layout.addWidget(label)
            rows: list[tuple[int, QPushButton]] = []
            for index in indices:
                used.add(index)
                name = titles[index]
                button = QPushButton("Today" if name == "Dashboard" else name)
                button.setObjectName("navItem")
                button.setCursor(Qt.CursorShape.PointingHandCursor)
                button.setCheckable(True)
                button.setAccessibleName(f"Open {name}")
                button.clicked.connect(lambda _checked=False, n=index: on_select(n))
                self._body_layout.addWidget(button)
                rows.append((index, button))
                self._rows.append((index, button))
            self._sections.append((label, rows))
        self._body_layout.addStretch(1)

        footer = QLabel("LOCAL & ENCRYPTED\nYour life stays yours.")
        footer.setObjectName("muted")
        outer.addWidget(footer)
        self.query.textChanged.connect(self._filter)
        self._active = -1

    def _filter(self, value: str) -> None:
        query = value.strip().casefold()
        for heading, rows in self._sections:
            visible = []
            for index, button in rows:
                matches = query in f"{self._titles[index]} {button.text()}".casefold()
                button.setVisible(matches)
                if matches:
                    visible.append(index)
            heading.setVisible(bool(visible))

    def set_active(self, index: int) -> None:
        self._active = index
        for i, row in self._rows:
            row.setChecked(i == index)
            row.setProperty("active", i == index)
            row.style().unpolish(row)
            row.style().polish(row)
