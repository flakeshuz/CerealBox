from __future__ import annotations

import os
import subprocess
import sys
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from CerealBox.app import _load_frontend


class CoreFrontendBoundaryTests(unittest.TestCase):
    def test_frontend_loader_uses_registered_frontend_entry_points(self) -> None:
        frontend = Mock(return_value=0)
        entry = Mock(name="sample", load=Mock(return_value=frontend))
        entry.name = "sample"
        with patch("CerealBox.app.metadata.entry_points", return_value=[entry]):
            self.assertIs(_load_frontend("sample"), frontend)
        entry.load.assert_called_once_with()

    def test_workspace_modules_load_without_qt_or_view_factories(self) -> None:
        repository_parent = Path(__file__).resolve().parents[2]
        script = """
import sys
import tempfile
from pathlib import Path
from CerealBox.application import create_workspace
from CerealBox.core import Vault

with tempfile.TemporaryDirectory() as directory:
    vault = Vault.create(Path(directory) / "headless.cerealbox", "test-password")
    workspace = create_workspace(vault)
    assert workspace.modules
    assert all(not hasattr(module, "create_view") for module in workspace.modules.values())
    assert not any(name == "PyQt6" or name.startswith("PyQt6.") for name in sys.modules)
"""
        environment = os.environ.copy()
        environment["PYTHONPATH"] = str(repository_parent)
        result = subprocess.run(
            [sys.executable, "-c", script],
            cwd=repository_parent,
            env=environment,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
