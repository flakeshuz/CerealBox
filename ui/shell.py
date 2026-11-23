"""The main window: one tab per module, a File menu for vault-wide actions, and reminder popups."""
from __future__ import annotations

import contextlib
import logging
import os
import tkinter as tk
from datetime import datetime, timedelta
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

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
MAX_CATCH_UP = timedelta(hours=12)  # reminders missed while the app was closed, at most this far back


class Shell(tk.Tk):
    def __init__(self, vault_path: Path):
        super().__init__()
        self.withdraw()
        T.apply(self)
        self.title("CerealBox")
        self.vault_path = Path(vault_path)
        self.api: LifeAPI | None = None
        self._rem_win: tk.Toplevel | None = None
        self._rem_list: ttk.Frame | None = None
        self._jobs: dict[str, str] = {}  # the shell's pending timers, by name

    def destroy(self) -> None:
        for job in self._jobs.values():  # the shell's own timers; views clean up their own
            with contextlib.suppress(tk.TclError):
                self.after_cancel(job)
        if self.api is not None:
            try:
                self.api.set_setting("core.geometry", self.geometry())  # remember the window size and place
            except Exception:
                log.exception("Could not save window geometry")
            try:
                self._checkpoint()
            except Exception:
                log.exception("Could not save reminder checkpoint")
        super().destroy()

    # ---- startup -----------------------------------------------------------------------
    def start(self) -> bool:
        vault = unlock_vault(self, self.vault_path)
        if vault is None:
            self.destroy()
            return False
        api = LifeAPI(vault)
        for module in default_modules():
            api.register(module)
        self.attach(api)
        return True

    def attach(self, api: LifeAPI) -> None:
        """Build the UI around an already-open API (also used by tests)."""
        self.api = api
        geom = api.setting("core.geometry")
        self.geometry(geom or "1180x780")
        self.minsize(900, 560)
        self._build_menu()
        self._bind_keys()
        self._status = ttk.Label(self, text="", style="Status.TLabel", anchor="w")
        workspace = ttk.Frame(self)
        header = ttk.Frame(workspace, style="Page.TFrame", padding=(24, 16))
        header.pack(fill="x")
        self._page_title = ttk.Label(header, text="Today", style="Title.TLabel")
        self._page_title.pack(side="left")
        ttk.Button(header, text="+ Task", command=lambda: self._on_request(action="new_task")).pack(side="right", padx=4)
        ttk.Button(header, text="+ Event", command=lambda: self._on_request(action="new_event")).pack(side="right", padx=4)
        ttk.Label(header, text=datetime.now().strftime("%A, %B %d"), style="Muted.TLabel").pack(side="right", padx=18)
        ttk.Separator(workspace).pack(fill="x")
        self.nb = Pager(workspace)
        for module in api.modules.values():
            view = module.create_view(self.nb)
            if view is not None:
                self.nb.add(view, text=module.title)
        titles = [self.nb.tab(t, "text") for t in self.nb.tabs()]
        self.sidebar = Sidebar(self, titles, self._select_index)
        self._status.pack(side="bottom", fill="x")
        self.sidebar.pack(side="left", fill="y")
        workspace.pack(side="left", fill="both", expand=True)
        self.nb.pack(fill="both", expand=True)
        self.nb.bind("<<NotebookTabChanged>>", lambda _e: self._sync_sidebar())
        self._sync_sidebar()
        saved = api.setting("core.last_reminder_check")
        now = D.now()
        self._last_check = max(D.from_iso(saved), now - MAX_CATCH_UP) if saved else now
        self._checkpoint_at = now
        self._after("poll", 1500, self._poll_reminders)
        self._after("sync", 4000, self._sync_tick)
        api.on("ui.request", self._on_request)
        api.on("calendar.synced", self._on_synced)
        self.protocol("WM_DELETE_WINDOW", self.destroy)
        if not geom:
            T.center(self)
        self.deiconify()
        # Apply density from settings if available
        try:
            density = api.setting("ui.density", "comfortable")
            from .theme import set_density
            set_density(self, density)
        except Exception:
            log.debug("Could not apply density from settings")


    # ---- menu --------------------------------------------------------------------------
    def _build_menu(self) -> None:
        bar = tk.Menu(self)
        file = tk.Menu(bar, tearoff=False)
        file.add_command(label="Save encrypted backup copy…", command=self._backup)
        file.add_command(label="Export all data as JSON…", command=self._export_json)
        file.add_command(label="Import data from JSON…", command=self._import_json)
        file.add_separator()
        file.add_command(label="Change password…", command=self._change_password)
        file.add_separator()
        file.add_command(label="Quit", command=self.destroy)
        bar.add_cascade(label="File", menu=file)
        view = tk.Menu(bar, tearoff=False)
        for i, name in enumerate(("Dashboard", "Calendar", "Tasks", "Money")):
            view.add_command(label=name, accelerator=f"Ctrl+{i + 1}", command=lambda n=i: self._select_index(n))
        view.add_separator()
        view.add_command(label="New item here", accelerator="Ctrl+N", command=self._new_here)
        bar.add_cascade(label="View", menu=view)
        helpm = tk.Menu(bar, tearoff=False)
        helpm.add_command(label="Keyboard shortcuts", accelerator="F1", command=self.show_shortcuts)
        bar.add_cascade(label="Help", menu=helpm)
        # CerealBox appearance options
        appearance = tk.Menu(bar, tearoff=False)
        appearance.add_command(label="Comfortable spacing", command=lambda: self._set_density("comfortable"))
        appearance.add_command(label="Compact spacing", command=lambda: self._set_density("dense"))
        bar.add_cascade(label="Appearance", menu=appearance)
        self.config(menu=bar)

    def _set_density(self, density: str) -> None:
        try:
            from .theme import set_density
            set_density(self, density)
            if hasattr(self, "api") and self.api is not None:
                self.api.set_setting("ui.density", density)
            self.toast(f"Density: {density}")
        except Exception:
            log.exception("Failed to apply density")


    def _backup(self) -> None:
        dest = filedialog.asksaveasfilename(parent=self, title="Save encrypted backup", initialfile="vault-backup.cerealbox")
        if dest:
            self.api.vault.backup_to(dest)
            messagebox.showinfo("Backup saved", "Saved an encrypted copy. It needs your password to open.", parent=self)

    def _export_json(self) -> None:
        if not messagebox.askokcancel(
                "Export unencrypted data",
                "This file will NOT be encrypted. Anyone who can open it can read your data.\n\nKeep it somewhere safe.",
                parent=self):
            return
        dest = filedialog.asksaveasfilename(parent=self, title="Export all data", defaultextension=".json",
                                            initialfile="cerealbox-export.json", filetypes=[("JSON", "*.json")])
        if dest:
            self.api.export_json(dest)
            messagebox.showinfo("Export finished", f"Saved to {dest}", parent=self)

    def _import_json(self) -> None:
        src = filedialog.askopenfilename(parent=self, title="Import CerealBox data", filetypes=[("JSON", "*.json")])
        if not src:
            return
        choice = messagebox.askyesnocancel(
            "Import data",
            "Merge with your current data?\n\nYes: merge (records with the same ID are overwritten)\n"
            "No: replace everything\nCancel: stop", parent=self)
        if choice is None:
            return
        try:
            self.api.import_json(Path(src), replace=not choice)
        except Exception as exc:  # bad file, wrong format, ...
            log.exception("JSON import failed")
            messagebox.showerror("Import failed", str(exc), parent=self)
        else:
            messagebox.showinfo("Import finished", "Your data was imported.", parent=self)

    def _change_password(self) -> None:
        new = ask_new_password(self)
        if new:
            self.api.vault.change_password(new)
            messagebox.showinfo("Password changed", "Your vault now uses the new password.", parent=self)

    def _after(self, name: str, ms: int, fn) -> None:
        old = self._jobs.get(name)
        if old:
            with contextlib.suppress(tk.TclError):
                self.after_cancel(old)
        self._jobs[name] = self.after(ms, fn)

    # ---- status bar, routing between tabs, keyboard ----------------------------------------------
    def toast(self, message: str, ms: int = 3500) -> None:
        self._status.config(text=message)
        self._after("toast", ms, lambda: self._status.config(text=""))

    def _select_index(self, index: int) -> None:
        tabs = self.nb.tabs()
        if index < len(tabs):
            self.nb.select(tabs[index])

    def _sync_sidebar(self) -> None:
        selected = self.nb.select()
        if selected:
            self.sidebar.set_active(self.nb.index(selected))
            title = self.nb.tab(selected, "text")
            self._page_title.configure(text="Today" if title == "Dashboard" else title)

    def _select_tab(self, title: str):
        for tab in self.nb.tabs():
            if self.nb.tab(tab, "text") == title:
                self.nb.select(tab)
                return self.nb.nametowidget(tab)
        return None

    def _on_request(self, topic: str = "", action: str = "", **_kw) -> None:
        """Cards and other parts of the UI ask for things by name; this sends them to the right tab."""
        target = ACTION_TARGETS.get(action)
        if not target:
            return
        title, method = target
        if os.environ.get("CEREALBOX_UI_VERBOSE"):
            print(f"[UI] request action={action} -> tab='{title}', method='{method}'")
        view = self._select_tab(title)
        if method and view is not None and hasattr(view, method):
            getattr(view, method)()

    def _new_here(self) -> None:
        try:
            current = self.nb.tab(self.nb.select(), "text")
        except tk.TclError:
            return
        action = {"Calendar": "new_event", "Tasks": "new_task", "Money": "new_txn"}.get(current)
        if action:
            self._on_request(action=action)

    def _bind_keys(self) -> None:
        for n in range(1, 5):
            self.bind(f"<Control-Key-{n}>", lambda _e, i=n - 1: self._select_index(i))
        self.bind("<Control-n>", lambda _e: self._new_here())
        self.bind("<Control-N>", lambda _e: self._new_here())
        self.bind("<Control-slash>", lambda _e: self.show_shortcuts())
        self.bind("<F1>", lambda _e: self.show_shortcuts())

    def show_shortcuts(self) -> None:
        ShortcutsDialog(self)

    def _on_synced(self, topic: str = "", source=None, result=None, **_kw) -> None:
        if source and result is not None:
            self.toast(f"Calendar link updated: {result.summary().splitlines()[0]}")

    # ---- calendar links ----------------------------------------------------------------
    def _sync_tick(self) -> None:
        """Start any calendar links that are due, and apply the ones that finished downloading."""
        try:
            self.api.call("calendar.start_due_syncs")
            self.api.call("calendar.drain_syncs")
        except Exception:
            log.exception("Calendar link sync failed")
        self._after("sync", SYNC_CHECK_MS, self._sync_tick)

    # ---- reminders ---------------------------------------------------------------------
    def _checkpoint(self) -> None:
        """Persist how far reminders have been checked. Done rarely: each vault save rewrites the file."""
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
                self._show_reminders(sorted(due, key=lambda r: r.at), until)
        except Exception:
            log.exception("Reminder check failed")
        self._after("poll", POLL_MS, self._poll_reminders)

    @staticmethod
    def _relative(due: datetime, now: datetime) -> str:
        mins = round((due - now).total_seconds() / 60)
        if abs(mins) < 1:
            return "now"
        text = D.fmt_span(mins)
        return f"in {text}" if mins > 0 else f"{text} ago"

    def _show_reminders(self, items: list[Reminder], now: datetime) -> None:
        if self._rem_win is None or not self._rem_win.winfo_exists():
            win = self._rem_win = tk.Toplevel(self)
            win.title("Reminders")
            win.configure(bg=T.BG)
            win.attributes("-topmost", True)
            outer = ttk.Frame(win, padding=16)
            outer.pack(fill="both", expand=True)
            ttk.Label(outer, text="Reminders", style="Title.TLabel").pack(anchor="w", pady=(0, 8))
            self._rem_list = ttk.Frame(outer)
            self._rem_list.pack(fill="x")
            ttk.Button(outer, text="Dismiss all", style="Accent.TButton", command=win.destroy).pack(anchor="e", pady=(12, 0))
            T.center(win, self)
        for r in items:
            row = ttk.Frame(self._rem_list)
            row.pack(fill="x", pady=4)
            ttk.Label(row, text=f"{r.title}  ·  {self._relative(r.due, now)}", font=(T.FAMILY, 11, "bold")).pack(anchor="w")
            if r.detail:
                ttk.Label(row, text=r.detail, style="Muted.TLabel").pack(anchor="w")
            if r.actions:
                bar = ttk.Frame(row)
                bar.pack(anchor="w", pady=(4, 0))
                for label, service, args in r.actions:
                    ttk.Button(bar, text=label,
                               command=lambda s=service, a=args, b=bar: self._run_action(s, a, b)
                               ).pack(side="left", padx=(0, 6))
        self.bell()

    def _run_action(self, service: str, args: tuple, bar: ttk.Frame) -> None:
        try:
            self.api.call(service, *args)
        except Exception as exc:
            log.exception("Reminder action failed: %s", service)
            messagebox.showerror("Couldn't do that", str(exc), parent=self._rem_win or self)
            return
        for w in bar.winfo_children():
            w.state(["disabled"])
        ttk.Label(bar, text="Done ✓", style="Muted.TLabel").pack(side="left")


ACTION_TARGETS = {  # action name -> (tab title, method to run on that tab, or None to just show it)
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
    ("Ctrl+1 … Ctrl+4", "Go to Dashboard, Calendar, Tasks or Money"),
    ("Ctrl+N", "New item in the current tab: event, task or transaction"),
    ("F1 or Ctrl+/", "Show this list"),
    ("Enter, double-click", "Open the selected item"),
    ("Delete", "Delete the selected item"),
    ("Space (Tasks)", "Complete or reopen the selected task"),
    ("← → and T (Calendar)", "Previous or next period, or jump to today"),
    ("Drag (Calendar)", "Move an event to another time or day"),
    ("Esc", "Close a dialog"),
]


class ShortcutsDialog(tk.Toplevel):
    def __init__(self, parent: tk.Misc):
        super().__init__(parent)
        self.title("Keyboard shortcuts")
        self.configure(bg=T.BG)
        self.resizable(False, False)
        frm = ttk.Frame(self, padding=22)
        frm.pack()
        ttk.Label(frm, text="Keyboard shortcuts", style="Title.TLabel").grid(row=0, column=0, columnspan=2, sticky="w")
        for i, (keys, what) in enumerate(SHORTCUTS, start=1):
            ttk.Label(frm, text=keys, style="Muted.TLabel", width=22).grid(row=i, column=0, sticky="w", pady=4)
            ttk.Label(frm, text=what).grid(row=i, column=1, sticky="w", padx=(10, 0), pady=4)
        ttk.Button(frm, text="Close", command=self.destroy).grid(row=len(SHORTCUTS) + 1, column=1, sticky="e", pady=(12, 0))
        self.bind("<Escape>", lambda _e: self.destroy())
        self.transient(parent.winfo_toplevel())
        T.center(self, parent)
        self.wait_visibility()
        self.grab_set()
