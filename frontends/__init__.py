"""Optional presentation layers for CerealBox."""
from __future__ import annotations

from pathlib import Path
from typing import Protocol


class Frontend(Protocol):
    def __call__(self, vault_path: Path) -> int:
        """Run this frontend for the selected vault and return its exit code."""
