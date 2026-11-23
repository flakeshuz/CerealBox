"""Shared visual tokens and application styling for the Qt frontend."""
from __future__ import annotations

from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import QApplication, QDialog, QWidget

BG = "#FFF7E6"
SURFACE = "#FFFCF5"
DIM = "#F7EFD9"
TODAY_BG = "#FFF0B8"
INK = "#33261C"
MUTED = "#716151"
FAINT = "#76624C"
LINE = "#E8DDBF"
LINE_SOFT = "#F1E7C9"
CONTROL = "#F7EFD9"
CONTROL_HOVER = "#ECDEB7"
ACCENT = "#B63D24"
ACCENT_SOFT = "#FFE3CF"
ACCENT_INK = "#A52F18"
NOW = "#B42318"
SUCCESS = "#5C7D3A"
FAMILY = "sans-serif"
SIZE = 10
CURRENT_DENSITY = "comfortable"
DENSITY_OPTIONS = ("comfortable", "dense")


def apply(app: QApplication) -> None:
    app.setStyle("Fusion")
    app.setFont(QFont(FAMILY, SIZE))
    app.setStyleSheet(f"""
        QWidget {{ color: {INK}; font-family: "{FAMILY}"; font-size: {SIZE}pt; }}
        QMainWindow, QDialog {{ background: {BG}; }}
        QFrame#sidebar {{ background: {SURFACE}; border-right: 1px solid {LINE}; }}
        QLabel#brand {{ font-size: 19pt; font-weight: 700; }}
        QLabel#pageTitle {{ font-size: 18pt; font-weight: 700; }}
        QLabel#muted {{ color: {MUTED}; }}
        QLineEdit, QTextEdit, QPlainTextEdit, QSpinBox, QDoubleSpinBox, QDateEdit, QTimeEdit,
        QDateTimeEdit, QComboBox, QListWidget, QTreeWidget, QTableWidget {{
            background: {SURFACE}; border: 1px solid {LINE}; border-radius: 6px; padding: 6px;
            selection-background-color: {ACCENT_SOFT}; selection-color: {INK};
        }}
        QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus, QSpinBox:focus, QComboBox:focus {{
            border: 2px solid {ACCENT};
        }}
        QPushButton {{
            background: {CONTROL}; border: 1px solid {CONTROL}; border-radius: 6px;
            padding: 7px 13px; min-height: 18px;
        }}
        QPushButton:hover {{ background: {CONTROL_HOVER}; }}
        QPushButton:pressed {{ background: {LINE}; }}
        QPushButton:disabled {{ color: {FAINT}; }}
        QPushButton[primary="true"] {{ color: white; background: {ACCENT}; border-color: {ACCENT}; font-weight: 600; }}
        QPushButton[primary="true"]:hover {{ background: #A9321C; }}
        QPushButton[danger="true"] {{ color: {NOW}; }}
        QPushButton#navItem {{
            text-align: left; background: transparent; border: 0; padding: 8px 12px;
        }}
        QPushButton#navItem:hover, QPushButton#navItem[active="true"] {{
            color: {ACCENT_INK}; background: {ACCENT_SOFT};
        }}
        QTreeWidget::item {{ padding: 6px; }}
        QHeaderView::section {{ background: {SURFACE}; color: {MUTED}; border: 0; padding: 8px; }}
        QStatusBar {{ color: {MUTED}; }}
        QFrame[card="true"] {{
            background: {SURFACE}; border: 1px solid {LINE_SOFT}; border-radius: 10px;
        }}
        QFrame[dropTarget="true"] {{ border: 2px solid {ACCENT}; }}
        QScrollBar:vertical {{ width: 10px; background: {BG}; margin: 0; }}
        QScrollBar::handle:vertical {{ background: {LINE}; border-radius: 4px; min-height: 24px; }}
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
        QToolTip {{ background: {INK}; color: white; border: 0; padding: 5px; }}
    """)


def font(size: int = SIZE, bold: bool = False) -> QFont:
    result = QFont(FAMILY, size)
    result.setBold(bold)
    return result


def set_density(root: QWidget, density: str) -> None:
    global CURRENT_DENSITY
    CURRENT_DENSITY = density if density in DENSITY_OPTIONS else "comfortable"
    root.setProperty("density", CURRENT_DENSITY)
    if CURRENT_DENSITY == "dense":
        root.setStyleSheet("""
            QPushButton { padding: 4px 10px; min-height: 15px; }
            QTreeWidget::item, QListWidget::item { padding: 3px; }
            QFrame#sidebar QPushButton { padding: 5px 10px; }
        """)
    else:
        root.setStyleSheet("")
    root.style().unpolish(root)
    root.style().polish(root)


def center(win: QDialog, parent: QWidget | None = None) -> None:
    win.adjustSize()
    if parent is not None and parent.isVisible():
        target = parent.window().frameGeometry()
        win.move(target.center() - win.rect().center())
    else:
        screen = QApplication.primaryScreen()
        if screen is not None:
            win.move(screen.availableGeometry().center() - win.rect().center())
