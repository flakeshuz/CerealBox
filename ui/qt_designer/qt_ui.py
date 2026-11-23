"""Helpers for loading interfaces created by Qt Designer."""
from __future__ import annotations

from os import PathLike
from pathlib import Path


def load_ui(ui_file: str | PathLike[str], parent=None):
    """Load a Qt Designer .ui file, or raise ValueError when it is unavailable."""
    path = Path(ui_file)
    if not path.is_file():
        raise FileNotFoundError(f"Qt Designer file not found: {path}")

    try:
        from PyQt6 import uic
    except ImportError as exc:
        raise RuntimeError("Qt frontend not available: PyQt6 is not installed.") from exc

    return uic.loadUi(str(path), parent)
