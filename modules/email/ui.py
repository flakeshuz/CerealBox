"""Email UI scaffold"""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from ...ui.components import configure_listbox, page_header


class EmailView(ttk.Frame):
    def __init__(self, parent, mod):
        super().__init__(parent)
        self.mod = mod
        header, actions = page_header(self, "Email")
        ttk.Button(actions, text="Receive sample", command=self._receive_sample).pack(side="left")
        ttk.Button(actions, text="Refresh", style="Accent.TButton", command=self.refresh).pack(side="left", padx=(6, 0))
        self.listbox = tk.Listbox(self)
        configure_listbox(self.listbox)
        self.listbox.pack(fill="both", expand=True, padx=24, pady=(4, 24))
        self.refresh()

    def refresh(self):
        self.listbox.delete(0, tk.END)
        for e in (self.mod.list_inbox() or []):
            subj = e.get("subject", "No subject")
            status = "Read" if e.get("read") else "Unread"
            self.listbox.insert(tk.END, f"{subj} — {status}")

    def _receive_sample(self):
        self.mod.receive_email("bot@example.com", "me@example.com", "Sample", "Body of sample email")
        self.refresh()
