"""Shared UI building blocks used across CerealBox screens."""
from __future__ import annotations

from PyQt6.QtWidgets import QFrame, QHBoxLayout, QLabel, QListWidget, QVBoxLayout, QWidget

from . import theme as T


def page_header(parent: QWidget, title: str) -> tuple[QFrame, QHBoxLayout]:
    header = QFrame(parent)
    header.setObjectName("workspaceHeader")
    layout = QHBoxLayout(header)
    layout.setContentsMargins(16, 10, 16, 10)
    label = QLabel(title, header)
    label.setObjectName("pageTitle")
    layout.addWidget(label)
    layout.addStretch(1)
    return header, layout


def page_surface(parent: QWidget) -> QFrame:
    surface = QFrame(parent)
    surface.setObjectName("pageSurface")
    surface.setStyleSheet(
        f"QFrame#pageSurface {{ background: {T.SURFACE}; border: 1px solid {T.LINE_SOFT}; border-radius: 12px; }}"
    )
    return surface


def configure_listbox(widget: QListWidget) -> None:
    widget.setAlternatingRowColors(True)
    widget.setUniformItemSizes(True)
