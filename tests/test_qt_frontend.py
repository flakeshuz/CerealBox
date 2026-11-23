from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[1].parent))

from PyQt6.QtCore import QMimeData, QPointF, Qt
from PyQt6.QtGui import QDropEvent, QPalette
from PyQt6.QtWidgets import QApplication, QMessageBox, QWidget

from CerealBox.core import Vault
from CerealBox.core import updater
from CerealBox.core.updater import UpdateError, UpdateStatus
from CerealBox.modules.calendar.models import DEFAULT_CATEGORIES
from CerealBox.modules.calendar.ui import _on_color
from CerealBox.modules.dashboard import reorder
from CerealBox.modules.dashboard.ui import DASHBOARD_CARD_MIME, DashboardCardFrame
from CerealBox.modules.docsvault_ui import document_bytes, decoded_text
from CerealBox.ui.shell import Shell
from CerealBox.ui import theme as T
from CerealBox.ui.unlock import PasswordDialog


class QtFrontendTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication(["cerealbox-tests"])

    @staticmethod
    def _contrast_ratio(foreground: str, background: str) -> float:
        def luminance(color: str) -> float:
            channels = [int(color[i:i + 2], 16) / 255 for i in (1, 3, 5)]
            linear = [value / 12.92 if value <= 0.04045 else ((value + 0.055) / 1.055) ** 2.4
                      for value in channels]
            return sum(value * weight for value, weight in zip(linear, (0.2126, 0.7152, 0.0722)))

        high, low = sorted((luminance(foreground), luminance(background)), reverse=True)
        return (high + 0.05) / (low + 0.05)

    def test_update_check_compares_main_and_reports_local_changes(self) -> None:
        root = Path(__file__).resolve().parents[1]
        current = "a" * 40
        latest = "b" * 40
        with patch(
            "CerealBox.core.updater._git",
            side_effect=[
                str(root.resolve()),
                "https://github.com/flakeshuz/CerealBox",
                current,
                f"{latest}\trefs/heads/main",
                " M ui/shell.py",
            ],
        ):
            status = updater.check_for_updates(root)
        self.assertEqual(status, UpdateStatus(current, latest, True))
        self.assertTrue(status.available)

    def test_update_apply_requires_clean_checkout_and_fast_forwards_only(self) -> None:
        root = Path(__file__).resolve().parents[1]
        latest = "b" * 40
        with patch.object(updater, "check_for_updates", return_value=UpdateStatus("a" * 40, latest, True)):
            with self.assertRaisesRegex(UpdateError, "local changes"):
                updater.apply_update(root, latest)

        with patch.object(updater, "check_for_updates", return_value=UpdateStatus("a" * 40, latest, False)):
            with patch.object(updater, "_git", side_effect=["", latest, "", latest]) as git:
                self.assertEqual(updater.apply_update(root, latest), latest)
        self.assertEqual(git.call_args_list[0].args[1:], ("fetch", "--quiet", "origin", "main"))
        merge_args = git.call_args_list[2].args[1:]
        self.assertEqual(merge_args[-4:], ("merge", "--ff-only", "--no-edit", "FETCH_HEAD"))

    def test_dashboard_drag_reordering_updates_saved_layout(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            vault = Vault.create(Path(directory) / "test.cerealbox", "test-password")
            shell = Shell(Path(directory) / "test.cerealbox")
            try:
                with patch("CerealBox.ui.shell.unlock_vault", return_value=vault):
                    self.assertTrue(shell.start())
                view = shell._pages["Dashboard"]
                view.customize_box.setChecked(True)
                self.assertFalse(view.customize_hint.isHidden())
                self.assertTrue(any("Drag to reorder" in button.toolTip()
                                    for button in view.findChildren(QWidget)
                                    if hasattr(button, "toolTip")))

                target = next(frame for frame in view.findChildren(DashboardCardFrame)
                              if frame.key == "quick")
                mime = QMimeData()
                mime.setData(DASHBOARD_CARD_MIME, b"today")
                event = QDropEvent(
                    QPointF(0, 0),
                    Qt.DropAction.MoveAction,
                    mime,
                    Qt.MouseButton.LeftButton,
                    Qt.KeyboardModifier.NoModifier,
                )
                target.dropEvent(event)
                self.assertTrue(event.isAccepted())
                shown = [item["key"] for item in view.mod.layout() if item["shown"]]
                self.assertEqual(shown, ["today", "quick", "tasks"])
                self.assertEqual([item["key"] for item in reorder(view.mod.layout(), "missing", "quick")
                                  if item["shown"]], shown)
                moved_to_end = reorder(view.mod.layout(), "today", "tasks", after=True)
                self.assertEqual([item["key"] for item in moved_to_end if item["shown"]],
                                 ["quick", "tasks", "today"])
            finally:
                shell.close()
                self.app.processEvents()

    def test_palette_text_contrast_meets_wcag_aa(self) -> None:
        for foreground, background in (
            (T.FAINT, T.BG),
            (T.FAINT, T.SURFACE),
            (T.ACCENT, T.BG),
            (T.ACCENT, T.SURFACE),
            ("#FFFFFF", T.ACCENT),
        ):
            with self.subTest(foreground=foreground, background=background):
                self.assertGreaterEqual(self._contrast_ratio(foreground, background), 4.5)
        T.apply(self.app)
        palette = self.app.palette()
        self.assertEqual(
            palette.color(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Text).name(),
            T.FAINT.lower(),
        )
        self.assertEqual(
            palette.color(QPalette.ColorGroup.Active, QPalette.ColorRole.Window).name(),
            T.BG.lower(),
        )
        for _slug, _name, background in DEFAULT_CATEGORIES:
            foreground = _on_color(background).name()
            with self.subTest(category_background=background):
                self.assertGreaterEqual(self._contrast_ratio(foreground, background), 4.5)

    def test_dashboard_card_uses_light_surface(self) -> None:
        T.apply(self.app)
        frame = DashboardCardFrame("today", lambda *_: None)
        frame.setObjectName("dashboardCard")
        frame.resize(200, 100)
        frame.show()
        self.app.processEvents()
        try:
            self.assertEqual(frame.grab().toImage().pixelColor(100, 50).name(), T.SURFACE.lower())
        finally:
            frame.close()

    def test_registered_module_screens_are_qt_widgets(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            vault = Vault.create(Path(directory) / "test.cerealbox", "test-password")
            shell = Shell(Path(directory) / "test.cerealbox")
            try:
                with patch("CerealBox.ui.shell.unlock_vault", return_value=vault):
                    self.assertTrue(shell.start())
                self.assertEqual(shell.nb.count(), len(shell.api.modules))
                self.assertTrue(all(isinstance(shell.nb.widget(i), QWidget) for i in range(shell.nb.count())))
                self.assertEqual(set(shell._pages), {"Dashboard"})
                self.assertEqual(shell._page_title.text(), "Today")
                shell._select_index(1)
                self.assertEqual(shell._page_title.text(), "Calendar")
                self.assertIn("Calendar", shell._pages)
                self.assertEqual(shell.sidebar._active, 1)
                shell.sidebar.query.setText("tasks")
                visible_spaces = [
                    shell._titles[index]
                    for index, row in shell.sidebar._rows
                    if not row.isHidden()
                ]
                self.assertEqual(visible_spaces, ["Tasks"])
                shell.sidebar.query.clear()
                self.assertFalse(shell.sidebar.more.isChecked())
                self.assertTrue(shell.sidebar._more_body.isHidden())
                shell.sidebar.more.setChecked(True)
                self.assertFalse(shell.sidebar._more_body.isHidden())
                shell.sidebar.query.setText("notes")
                visible_spaces = [
                    shell._titles[index]
                    for index, row in shell.sidebar._rows
                    if not row.isHidden()
                ]
                self.assertEqual(visible_spaces, ["Notes"])
                self.assertTrue(shell.sidebar.more.isChecked())
                shell.sidebar.query.clear()
                self.assertTrue(shell.sidebar._more_body.isHidden())
            finally:
                shell.close()
                self.app.processEvents()

    def test_document_vault_search_preview_size_and_delete(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            vault = Vault.create(Path(directory) / "test.cerealbox", "test-password")
            shell = Shell(Path(directory) / "test.cerealbox")
            try:
                with patch("CerealBox.ui.shell.unlock_vault", return_value=vault):
                    self.assertTrue(shell.start())
                shell._select_index(shell._titles.index("Document Vault"))
                view = shell._pages["Document Vault"]
                module = view.module

                document = module.put_document("doc_alpha", "Alpha.txt", "hello".encode("utf-8"))
                module.put_document("doc_beta", "Beta.txt", "é".encode("utf-8"))
                view._refresh()
                self.assertEqual(document_bytes(document), 5)
                self.assertEqual(decoded_text(document), "hello")
                self.assertEqual(view.tree.topLevelItemCount(), 2)

                view.search.setText("alpha")
                self.assertEqual(view.tree.topLevelItemCount(), 1)
                view.tree.setCurrentItem(view.tree.topLevelItem(0))
                self.assertEqual(view.preview.toPlainText(), "hello")

                with patch.object(QMessageBox, "question", return_value=QMessageBox.StandardButton.Yes):
                    view._delete()
                self.assertIsNone(module.get_document("doc_alpha"))
                self.assertIn("Deleted", view.status.text())
            finally:
                shell.close()
                self.app.processEvents()

    def test_notes_search_edit_and_delete(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            vault = Vault.create(Path(directory) / "test.cerealbox", "test-password")
            shell = Shell(Path(directory) / "test.cerealbox")
            try:
                with patch("CerealBox.ui.shell.unlock_vault", return_value=vault):
                    self.assertTrue(shell.start())
                shell._select_index(shell._titles.index("Notes"))
                view = shell._pages["Notes"]
                note = view.mod.add_note("Shopping", "Buy milk")
                view.refresh()

                view.search.setText("milk")
                self.assertEqual(view.listbox.count(), 1)
                view.listbox.setCurrentRow(0)
                view.mod.update_note(note["id"], "Groceries", "Buy oat milk")
                view.refresh()
                view.search.clear()
                self.assertEqual(view.listbox.count(), 1)
                self.assertEqual(view.listbox.item(0).text(), "Groceries")

                view.listbox.setCurrentRow(0)
                with patch.object(QMessageBox, "question", return_value=QMessageBox.StandardButton.Yes):
                    view.delete_selected()
                self.assertIsNone(view.mod.get_note(note["id"]))
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
