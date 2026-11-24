"""Background Git operations used by the update menu."""
from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import QThread, pyqtSignal

from ...core.updater import UpdateError, UpdateStatus, apply_update, check_for_updates


class UpdateCheckWorker(QThread):
    checked = pyqtSignal(object)
    failed = pyqtSignal(str)

    def __init__(self, root: Path, parent=None):
        super().__init__(parent)
        self.root = root

    def run(self) -> None:
        try:
            self.checked.emit(check_for_updates(self.root))
        except UpdateError as exc:
            self.failed.emit(str(exc))


class UpdateApplyWorker(QThread):
    applied = pyqtSignal(str)
    failed = pyqtSignal(str)

    def __init__(self, root: Path, expected_sha: str, parent=None):
        super().__init__(parent)
        self.root = root
        self.expected_sha = expected_sha

    def run(self) -> None:
        try:
            self.applied.emit(apply_update(self.root, self.expected_sha))
        except UpdateError as exc:
            self.failed.emit(str(exc))
