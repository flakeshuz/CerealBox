from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[1].parent))

from PyQt6.QtWidgets import QApplication, QWidget

from CerealBox.core import LifeAPI, Vault
from CerealBox.modules import default_modules
from CerealBox.ui.shell import Shell
from CerealBox.ui.unlock import PasswordDialog


class QtFrontendTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication(["cerealbox-tests"])

    def test_registered_module_screens_are_qt_widgets(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            vault = Vault.create(Path(directory) / "test.cerealbox", "test-password")
            api = LifeAPI(vault)
            modules = default_modules()
            for module in modules:
                api.register(module)

            shell = Shell(Path(directory) / "test.cerealbox")
            try:
                shell.attach(api)
                self.assertEqual(shell.nb.count(), len(modules))
                self.assertTrue(all(isinstance(shell.nb.widget(i), QWidget) for i in range(shell.nb.count())))
                self.assertEqual(shell._page_title.text(), "Today")
                shell._select_index(1)
                self.assertEqual(shell._page_title.text(), "Calendar")
                self.assertEqual(shell.sidebar._active, 1)
            finally:
                shell.close()
                self.app.processEvents()

    def test_password_dialog_validates_and_accepts_passwords(self) -> None:
        dialog = PasswordDialog(None, "create")
        dialog.e1.setText("short")
        dialog.e2.setText("short")
        dialog._ok()
        self.assertIsNone(dialog.password)
        self.assertIn("8 characters", dialog.msg.text())

        dialog.e1.setText("long-enough-password")
        dialog.e2.setText("not-the-same")
        dialog._ok()
        self.assertIn("don't match", dialog.msg.text())

        dialog.e2.setText("long-enough-password")
        dialog._ok()
        self.assertEqual(dialog.password, "long-enough-password")


if __name__ == "__main__":
    unittest.main()
