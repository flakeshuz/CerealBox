"""Qt application window, workspace navigation, and vault-wide actions."""
from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta
from pathlib import Path

from PyQt6.QtCore import QTimer, Qt
from PyQt6.QtGui import QAction, QKeySequence
from PyQt6.QtWidgets import (
    QApplication,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ..core import LifeAPI, Reminder
from ..core import dates as D
from ..modules import default_modules
from . import theme as T
from .pager import Pager
from .sidebar import Sidebar
from .unlock import ask_new_password, unlock_vault

log = logging.getLogger("cerealbox")
POLL_MS = 15_000
SYNC_CHECK_MS = 5_000
CHECKPOINT_EVERY = timedelta(minutes=10)
MAX_CATCH_UP = timedelta(hours=12)


class Shell(QMainWindow):
    def __init__(self, vault_path: Path):
        super().__init__()
        self.setWindowTitle("CerealBox")
        self.setMinimumSize(820, 540)
        self.vault_path = Path(vault_path)
        self.api: LifeAPI | None = None
        self._rem_win: QDialog | None = None
        self._rem_list: QVBoxLayout | None = None
        self._jobs: dict[str, QTimer] = {}
        self._pages: dict[str, QWidget] = {}
        self._titles: list[str] = []
        self._modules = []
        self._loaded_pages: set[int] = set()

    def closeEvent(self, event) -> None:
        for timer in self._jobs.values():
            timer.stop()
        if self.api is not None:
            try:
                rect = self.geometry()
                self.api.set_setting("core.geometry", f"{rect.width()}x{rect.height()}{rect.x():+d}{rect.y():+d}")
            except Exception:
                log.exception("Could not save window geometry")
            try:
                self._checkpoint()
            except Exception:
                log.exception("Could not save reminder checkpoint")
        event.accept()

    def start(self) -> bool:
        vault = unlock_vault(self, self.vault_path)
        if vault is None:
            return False
        api = LifeAPI(vault)
        for module in default_modules():
            api.register(module)
        self.attach(api)
        return True

    def attach(self, api: LifeAPI) -> None:
        """Build the workspace around an already-open API."""
        self.api = api
        modules = list(api.modules.values())
        self._modules = modules
        self._titles = [module.title for module in modules]
        self._pages = {}
        self._loaded_pages = set()

        central = QWidget(self)
        root = QHBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        self.sidebar = Sidebar(self, self._titles, self._select_index)
        root.addWidget(self.sidebar)

        workspace = QWidget(central)
        work_layout = QVBoxLayout(workspace)
        work_layout.setContentsMargins(22, 14, 22, 0)
        work_layout.setSpacing(0)

        header = QFrame(workspace)
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(2, 0, 2, 12)
        self._page_title = QLabel("Today")
        self._page_title.setObjectName("pageTitle")
        header_layout.addWidget(self._page_title)
        header_layout.addStretch(1)
        self._date_label = QLabel(datetime.now().strftime("%A, %B %d"))
        self._date_label.setObjectName("muted")
        header_layout.addWidget(self._date_label)
        self._new_event_button = self._button("+ Event", lambda: self._on_request(action="new_event"))
        self._new_task_button = self._button("+ Task", lambda: self._on_request(action="new_task"), primary=True)
        header_layout.addWidget(self._new_event_button)
        header_layout.addWidget(self._new_task_button)
        work_layout.addWidget(header)

        self.nb = Pager(workspace)
        for module in modules:
            page = QWidget(self.nb)
            page.setLayout(QVBoxLayout())
            page.layout().setContentsMargins(0, 0, 0, 0)
            self.nb.add(page, text=module.title)
        if self.nb.count() == 0:
            raise RuntimeError("No workspace screens are available.")
        work_layout.addWidget(self.nb, 1)
        root.addWidget(workspace, 1)
        self.setCentralWidget(central)

        self._build_menu()
        self.statusBar().showMessage("Local and encrypted")
        self.nb.currentChanged.connect(self._page_changed)
        self._ensure_page(0)
        self.sidebar.set_active(0)
        self._sync_sidebar()

        saved = api.setting("core.geometry")
        screen = QApplication.primaryScreen()
        available = screen.availableGeometry() if screen else self.geometry()
        max_width, max_height = max(1, available.width()), max(1, available.height())
        min_width, min_height = min(900, max_width), min(560, max_height)
        self.setMinimumSize(min_width, min_height)
        match = re.fullmatch(r"(\d+)x(\d+)([+-]\d+)([+-]\d+)", saved or "")
        if match:
            width = max(min_width, min(int(match.group(1)), max_width))
            height = max(min_height, min(int(match.group(2)), max_height))
            x = max(available.left(), min(int(match.group(3)), available.right() - width + 1))
            y = max(available.top(), min(int(match.group(4)), available.bottom() - height + 1))
            self.setGeometry(x, y, width, height)
        else:
            width, height = min(1180, max_width), min(780, max_height)
            self.resize(width, height)
            self.move(available.center() - self.rect().center())

        saved_check = api.setting("core.last_reminder_check")
        now = D.now()
        self._last_check = max(D.from_iso(saved_check), now - MAX_CATCH_UP) if saved_check else now
        self._checkpoint_at = now
        self._schedule("poll", 1500, self._poll_reminders)
        self._schedule("sync", 4000, self._sync_tick)
        api.on("ui.request", self._on_request)
        api.on("calendar.synced", self._on_synced)
        density = api.setting("ui.density", "comfortable")
        T.set_density(self, density)

    @staticmethod
    def _button(text: str, callback, *, primary: bool = False) -> QPushButton:
        button = QPushButton(text)
        if primary:
            button.setProperty("primary", True)
            button.style().unpolish(button)
            button.style().polish(button)
        button.clicked.connect(callback)
        return button

    def _build_menu(self) -> None:
        file_menu = self.menuBar().addMenu("&File")
        self._action(file_menu, "Save encrypted backup copy…", self._backup)
        self._action(file_menu, "Export all data as JSON…", self._export_json)
        self._action(file_menu, "Import data from JSON…", self._import_json)
        file_menu.addSeparator()
        self._action(file_menu, "Change password…", self._change_password)
        file_menu.addSeparator()
        self._action(file_menu, "Quit", self.close, "Ctrl+Q")

        view_menu = self.menuBar().addMenu("&View")
        for index, name in enumerate(self._titles):
            label = "Today" if name == "Dashboard" else name
            shortcut = f"Ctrl+{index + 1}" if index < 4 else None
            self._action(view_menu, label, lambda n=index: self._select_index(n), shortcut)
        view_menu.addSeparator()
        self._action(view_menu, "New item here", self._new_here, "Ctrl+N")
        self._action(view_menu, "Find a workspace", self._focus_navigation, "Ctrl+K")

        appearance = self.menuBar().addMenu("&Appearance")
        self._action(appearance, "Comfortable spacing", lambda: self._set_density("comfortable"))
        self._action(appearance, "Compact spacing", lambda: self._set_density("dense"))

        help_menu = self.menuBar().addMenu("&Help")
        self._action(help_menu, "Keyboard shortcuts", self.show_shortcuts, "F1")

    @staticmethod
    def _action(menu, text: str, callback, shortcut: str | None = None) -> QAction:
        action = QAction(text, menu)
        if shortcut:
            action.setShortcut(QKeySequence(shortcut))
        action.triggered.connect(lambda _checked=False: callback())
        menu.addAction(action)
        return action

    def _set_density(self, density: str) -> None:
        T.set_density(self, density)
        if self.api is not None:
            self.api.set_setting("ui.density", density)
        self.toast(f"Spacing: {density}")

    def _backup(self) -> None:
        dest, _ = QFileDialog.getSaveFileName(
            self, "Save encrypted backup", "vault-backup.cerealbox", "CerealBox vault (*.cerealbox);;All files (*)"
        )
        if not dest:
            return
        try:
            self.api.vault.backup_to(dest)
        except Exception as exc:
            log.exception("Encrypted backup failed")
            QMessageBox.critical(self, "Backup failed", str(exc))
        else:
            QMessageBox.information(self, "Backup saved", "Saved an encrypted copy. It needs your password to open.")

    def _export_json(self) -> None:
        choice = QMessageBox.warning(
            self,
            "Export unencrypted data",
            "This file will NOT be encrypted. Anyone who can open it can read your data.\n\nKeep it somewhere safe.",
            QMessageBox.StandardButton.Ok | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
        )
        if choice != QMessageBox.StandardButton.Ok:
            return
        dest, _ = QFileDialog.getSaveFileName(self, "Export all data", "cerealbox-export.json", "JSON files (*.json)")
        if not dest:
            return
        try:
            self.api.export_json(dest)
        except Exception as exc:
            log.exception("JSON export failed")
            QMessageBox.critical(self, "Export failed", str(exc))
        else:
            QMessageBox.information(self, "Export finished", f"Saved to {dest}")

    def _import_json(self) -> None:
        src, _ = QFileDialog.getOpenFileName(self, "Import CerealBox data", "", "JSON files (*.json)")
        if not src:
            return
        choice = QMessageBox(self)
        choice.setWindowTitle("Import data")
        choice.setText("How do you want to import this data?")
        choice.setInformativeText("Merge keeps existing records and replaces matching IDs. Replace removes current data.")
        merge = choice.addButton("Merge", QMessageBox.ButtonRole.AcceptRole)
        replace = choice.addButton("Replace everything", QMessageBox.ButtonRole.DestructiveRole)
        choice.addButton(QMessageBox.StandardButton.Cancel)
        choice.exec()
        if choice.clickedButton() not in (merge, replace):
            return
        try:
            self.api.import_json(Path(src), replace=choice.clickedButton() is replace)
        except Exception as exc:
            log.exception("JSON import failed")
            QMessageBox.critical(self, "Import failed", str(exc))
        else:
            QMessageBox.information(self, "Import finished", "Your data was imported.")

    def _change_password(self) -> None:
        new = ask_new_password(self)
        if not new:
            return
        try:
            self.api.vault.change_password(new)
        except Exception as exc:
            log.exception("Changing the vault password failed")
            QMessageBox.critical(self, "Password not changed", str(exc))
        else:
            QMessageBox.information(self, "Password changed", "Your vault now uses the new password.")

    def _schedule(self, name: str, ms: int, fn) -> None:
        timer = self._jobs.get(name)
        if timer is None:
            timer = QTimer(self)
            timer.setSingleShot(True)
            timer.timeout.connect(fn)
            self._jobs[name] = timer
        timer.start(ms)

    def toast(self, message: str, ms: int = 3500) -> None:
        self.statusBar().showMessage(message, ms)

    def _select_index(self, index: int) -> None:
        if 0 <= index < self.nb.count():
            self._ensure_page(index)
            self.nb.setCurrentIndex(index)

    def _ensure_page(self, index: int) -> None:
        if index in self._loaded_pages or not 0 <= index < len(self._modules):
            return
        module = self._modules[index]
        host = self.nb.widget(index)
        view = module.create_view(host)
        if view is None:
            self._loaded_pages.add(index)
            return
        if not isinstance(view, QWidget):
            raise TypeError(f"{module.name}.create_view() must return a PyQt6 QWidget.")
        host.layout().addWidget(view)
        self._pages[module.title] = view
        self._loaded_pages.add(index)

    def _page_changed(self, index: int) -> None:
        self._ensure_page(index)
        self._sync_sidebar()

    def _sync_sidebar(self, *_args) -> None:
        index = self.nb.currentIndex()
        self.sidebar.set_active(index)
        title = self._titles[index] if 0 <= index < len(self._titles) else "CerealBox"
        self._page_title.setText("Today" if title == "Dashboard" else title)
        self._new_event_button.setVisible(title == "Calendar")
        self._new_task_button.setVisible(title in ("Dashboard", "Tasks"))

    def _focus_navigation(self) -> None:
        self.sidebar.query.setFocus()
        self.sidebar.query.selectAll()

    def _on_request(self, topic: str = "", action: str = "", **_kw) -> None:
        target = ACTION_TARGETS.get(action)
        if not target:
            return
        title, method = target
        if title not in self._titles:
            return
        index = self._titles.index(title)
        self._select_index(index)
        view = self._pages.get(title)
        if view is None:
            return
        if method:
            callback = getattr(view, method, None)
            if callable(callback):
                callback()

    def _new_here(self) -> None:
        title = self._titles[self.nb.currentIndex()] if self.nb.currentIndex() >= 0 else ""
        action = {"Dashboard": "new_task", "Calendar": "new_event", "Tasks": "new_task",
                  "Money": "new_txn"}.get(title)
        if action:
            self._on_request(action=action)

    def show_shortcuts(self) -> None:
        ShortcutsDialog(self).exec()

    def _on_synced(self, topic: str = "", source=None, result=None, **_kw) -> None:
        if source and result is not None:
            self.toast(f"Calendar link updated: {result.summary().splitlines()[0]}")

    def _sync_tick(self) -> None:
        try:
            self.api.call("calendar.start_due_syncs")
            self.api.call("calendar.drain_syncs")
        except Exception:
            log.exception("Calendar link sync failed")
            self.toast("Calendar sync failed. See the application log.")
        self._schedule("sync", SYNC_CHECK_MS, self._sync_tick)

    def _checkpoint(self) -> None:
        self.api.set_setting("core.last_reminder_check", D.to_iso(self._last_check))
        self._checkpoint_at = self._last_check

    def _poll_reminders(self) -> None:
        until = D.now()
        try:
            due: list[Reminder] = self.api.call_all("reminders_due", self._last_check, until)
            self._last_check = until
            if until - self._checkpoint_at >= CHECKPOINT_EVERY:
                self._checkpoint()
            if due:
                self._show_reminders(sorted(due, key=lambda reminder: reminder.at), until)
        except Exception:
            log.exception("Reminder check failed")
            self.toast("Reminder check failed. See the application log.")
        self._schedule("poll", POLL_MS, self._poll_reminders)

    @staticmethod
    def _relative(due: datetime, now: datetime) -> str:
        mins = round((due - now).total_seconds() / 60)
        if abs(mins) < 1:
            return "now"
        text = D.fmt_span(mins)
        return f"in {text}" if mins > 0 else f"{text} ago"

    def _show_reminders(self, items: list[Reminder], now: datetime) -> None:
        if self._rem_win is None or not self._rem_win.isVisible():
            self._rem_win = QDialog(self)
            self._rem_win.setWindowTitle("Reminders")
            self._rem_win.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)
            self._rem_win.setMinimumWidth(360)
            layout = QVBoxLayout(self._rem_win)
            title = QLabel("Reminders")
            title.setObjectName("pageTitle")
            layout.addWidget(title)
            self._rem_list = layout
            dismiss = self._button("Dismiss all", self._rem_win.accept, primary=True)
            layout.addWidget(dismiss, alignment=Qt.AlignmentFlag.AlignRight)
            T.center(self._rem_win, self)
        for reminder in items:
            row = QFrame(self._rem_win)
            row_layout = QVBoxLayout(row)
            row_layout.setContentsMargins(0, 6, 0, 6)
            label = QLabel(f"{reminder.title}  ·  {self._relative(reminder.due, now)}")
            label.setFont(T.font(11, bold=True))
            row_layout.addWidget(label)
            if reminder.detail:
                detail = QLabel(reminder.detail)
                detail.setObjectName("muted")
                row_layout.addWidget(detail)
            if reminder.actions:
                actions = QHBoxLayout()
                for text, service, args in reminder.actions:
                    button = QPushButton(text)
                    button.clicked.connect(
                        lambda _checked=False, s=service, a=args, b=button: self._run_action(s, a, b)
                    )
                    actions.addWidget(button)
                row_layout.addLayout(actions)
            self._rem_list.insertWidget(self._rem_list.count() - 1, row)
        self._rem_win.show()
        self._rem_win.raise_()

    def _run_action(self, service: str, args: tuple, button: QPushButton) -> None:
        try:
            self.api.call(service, *args)
        except Exception as exc:
            log.exception("Reminder action failed: %s", service)
            QMessageBox.critical(self._rem_win or self, "Couldn't do that", str(exc))
            return
        button.setEnabled(False)
        button.setText("Done")


ACTION_TARGETS = {
    "new_event": ("Calendar", "new_event"),
    "open_calendar": ("Calendar", None),
    "open_links": ("Calendar", "open_subscriptions"),
    "new_task": ("Tasks", "new"),
    "open_tasks": ("Tasks", None),
    "new_txn": ("Money", "new_txn"),
    "new_transfer": ("Money", "new_transfer"),
    "import_csv": ("Money", "import_csv"),
    "open_bills": ("Money", "open_bills"),
    "open_money": ("Money", None),
}

SHORTCUTS = [
    ("Ctrl+1 … Ctrl+4", "Go to Today, Calendar, Tasks or Money"),
    ("Ctrl+N", "Create an item in the current screen"),
    ("Ctrl+K", "Find a workspace"),
    ("F1", "Show keyboard shortcuts"),
    ("Enter or double-click", "Open the selected item"),
    ("Delete", "Delete the selected item"),
    ("Space (Tasks)", "Complete or reopen the selected task"),
    ("← → and T (Calendar)", "Change period or jump to today"),
    ("Esc", "Close a dialog"),
]


class ShortcutsDialog(QDialog):
    def __init__(self, parent: QWidget):
        super().__init__(parent)
        self.setWindowTitle("Keyboard shortcuts")
        layout = QVBoxLayout(self)
        title = QLabel("Keyboard shortcuts")
        title.setObjectName("pageTitle")
        layout.addWidget(title)
        for keys, description in SHORTCUTS:
            row = QHBoxLayout()
            key_label = QLabel(keys)
            key_label.setObjectName("muted")
            key_label.setMinimumWidth(170)
            row.addWidget(key_label)
            row.addWidget(QLabel(description), 1)
            layout.addLayout(row)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        buttons.accepted.connect(self.accept)
        layout.addWidget(buttons)
        self.setModal(True)
        T.center(self, parent)
