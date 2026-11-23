"""Email UI scaffold"""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk


class EmailView(ttk.Frame):
    def __init__(self, parent, mod):
        super().__init__(parent)
        self.mod = mod
        ttk.Label(self, text="Email", style="Title.TLabel").pack(anchor="w")
        self.listbox = tk.Listbox(self)
        self.listbox.pack(fill="both", expand=True, pady=4)
        frm = ttk.Frame(self)
        frm.pack(anchor="e")
        ttk.Button(frm, text="Receive Sample", command=self._receive_sample).pack(side="left")
        ttk.Button(frm, text="Refresh", command=self.refresh).pack(side="left", padx=6)
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
