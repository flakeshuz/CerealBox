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

CORE_NAMES = ("Dashboard", "Calendar", "Tasks", "Money")
MORE_GROUPS = (
    ("DAILY", ("Notes", "Habits", "Goals")),
    ("PERSONAL", ("Taxes", "Health", "Home", "Contacts")),
    ("LIBRARY", ("Document Vault", "Passwords", "Search", "Email")),
)


class Sidebar(QFrame):
    def __init__(self, parent: QWidget, titles: list[str], on_select: Callable[[int], None]):
        super().__init__(parent)
        self.setObjectName("sidebar")
        self.setMinimumWidth(232)
        self.setMaximumWidth(264)
        self._titles = titles
        self._rows: list[tuple[int, QPushButton]] = []
        self._sections: list[tuple[QLabel, list[tuple[int, QPushButton]]]] = []
        outer = QVBoxLayout(self)
        outer.setContentsMargins(18, 22, 18, 16)
        outer.setSpacing(8)

        brand = QLabel("CerealBox")
        brand.setObjectName("brand")
        outer.addWidget(brand)
        tagline = QLabel("Start your day, sorted.")
        tagline.setObjectName("muted")
        outer.addWidget(tagline)

        self.query = QLineEdit()
        self.query.setPlaceholderText("Find a space…")
        self.query.setClearButtonEnabled(True)
        self.query.setMinimumHeight(38)
        self.query.setAccessibleName("Filter workspace navigation")
        outer.addWidget(self.query)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        body = QWidget()
        body.setObjectName("sidebarBody")
        self._body_layout = QVBoxLayout(body)
        self._body_layout.setContentsMargins(0, 6, 0, 6)
        self._body_layout.setSpacing(2)
        scroll.setWidget(body)
        outer.addWidget(scroll, 1)

        used: set[int] = set()
        core_heading = QLabel("CORE")
        core_heading.setObjectName("muted")
        core_heading.setStyleSheet("font-size: 8pt; font-weight: 700; letter-spacing: 1px; padding: 10px 12px 4px;")
        self._body_layout.addWidget(core_heading)
        core_rows: list[tuple[int, QPushButton]] = []
        for name in CORE_NAMES:
            index = next((i for i, title in enumerate(titles) if title == name), None)
            if index is None:
                continue
            used.add(index)
            button = QPushButton("Today" if name == "Dashboard" else name)
            button.setObjectName("navItem")
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.setCheckable(True)
            button.setAccessibleName(f"Open {name}")
            button.clicked.connect(lambda _checked=False, n=index: on_select(n))
            self._body_layout.addWidget(button)
            core_rows.append((index, button))
            self._rows.append((index, button))
        self._sections.append((core_heading, core_rows))

        self.more = QPushButton("More")
        self.more.setProperty("navGroup", True)
        self.more.setObjectName("navItem")
        self.more.setCursor(Qt.CursorShape.PointingHandCursor)
        self.more.setCheckable(True)
        self.more.setAccessibleName("Show more workspaces")
        self._body_layout.addWidget(self.more)
        self._more_expanded = False
        self.more.toggled.connect(self._toggle_more)

        more_body = QWidget(body)
        more_layout = QVBoxLayout(more_body)
        more_layout.setContentsMargins(0, 0, 0, 0)
        more_layout.setSpacing(2)
        self._body_layout.addWidget(more_body)
        self._more_body = more_body

        for heading, names in MORE_GROUPS:
            indices = [i for i, title in enumerate(titles) if title in names and i not in used]
            if not indices:
                continue
            label = QLabel(heading)
            label.setObjectName("muted")
            label.setStyleSheet("font-size: 8pt; font-weight: 700; letter-spacing: 1px; padding: 10px 12px 4px;")
            more_layout.addWidget(label)
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
                more_layout.addWidget(button)
                rows.append((index, button))
                self._rows.append((index, button))
            self._sections.append((label, rows))

        more_layout.addStretch(1)
        more_body.setVisible(False)
        self._body_layout.addStretch(1)

        footer = QLabel("LOCAL & ENCRYPTED")
        footer.setObjectName("muted")
        footer.setStyleSheet("font-size: 8pt; font-weight: 700; letter-spacing: 1px; padding: 10px 12px 2px;")
        outer.addWidget(footer)
        self.query.textChanged.connect(self._filter)
        self._active = -1

    def _filter(self, value: str) -> None:
        query = value.strip().casefold()
        if not query:
            self.more.setChecked(False)
            self._more_expanded = False
            self._more_body.setVisible(False)
            self.more.setText("More")
            for heading, rows in self._sections:
                heading.setVisible(heading.text() == "CORE")
                for _index, button in rows:
                    button.setVisible(heading.text() == "CORE")
            return

        secondary_visible = False
        for heading, rows in self._sections:
            visible = []
            for index, button in rows:
                matches = query in f"{self._titles[index]} {button.text()}".casefold()
                button.setVisible(matches)
                if matches:
                    visible.append(index)
                    if heading.text() != "CORE":
                        secondary_visible = True
            heading.setVisible(bool(visible))
        if secondary_visible:
            self.more.setChecked(True)
            self._more_body.setVisible(True)
            self.more.setText("Less")
        else:
            self.more.setChecked(False)
            self._more_body.setVisible(False)
            self.more.setText("More")

    def _toggle_more(self, expanded: bool) -> None:
        if self.query.text().strip():
            return
        self._more_expanded = expanded
        self._more_body.setVisible(expanded)
        self.more.setText("Less" if expanded else "More")

    def set_active(self, index: int) -> None:
        self._active = index
        for i, row in self._rows:
            row.setChecked(i == index)
            row.setProperty("active", i == index)
            row.style().unpolish(row)
            row.style().polish(row)
        if index >= 0 and index < len(self._titles) and self._titles[index] not in CORE_NAMES:
            if not self.query.text().strip():
                self.more.setChecked(True)
        elif not self.query.text().strip():
            self.more.setChecked(False)
