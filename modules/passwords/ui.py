"""Passwords UI scaffold"""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from ...ui.components import configure_listbox, page_header


class PasswordsView(ttk.Frame):
    def __init__(self, parent, mod):
        super().__init__(parent)
        self.mod = mod
        header, actions = page_header(self, "Passwords")
        ttk.Button(actions, text="Store", style="Accent.TButton", command=self.store).pack(side="left")
        ttk.Button(actions, text="Refresh", command=self.refresh).pack(side="left", padx=(6, 0))
        self.listbox = tk.Listbox(self)
        configure_listbox(self.listbox)
        self.listbox.pack(fill="both", expand=True, padx=24, pady=(4, 24))
        self.refresh()

    def refresh(self):
        self.listbox.delete(0, tk.END)
        for c in (self.mod.list_credentials() or self.mod.list_credentials() or []):
            # show the key for the credential; value is hidden in UI for safety
            self.listbox.insert(tk.END, c.get("key", "secret"))

    def store(self):
        dlg = tk.Toplevel(self)
        dlg.title("Store Credential")
        frm = ttk.Frame(dlg, padding=12)
        frm.pack()
        tk.Label(frm, text="Key").grid(row=0, column=0)
        key_var = tk.StringVar()
        ttk.Entry(frm, textvariable=key_var).grid(row=0, column=1)
        tk.Label(frm, text="Value").grid(row=1, column=0)
        val_var = tk.StringVar()
        ttk.Entry(frm, textvariable=val_var).grid(row=1, column=1)
        def save():
            key = key_var.get()
            val = val_var.get()
            if key:
                self.mod.store_credential(key, val)
                self.refresh()
                dlg.destroy()
        ttk.Button(frm, text="Save", command=save).grid(row=2, column=0, columnspan=2)
        dlg.transient(self.winfo_toplevel())
        dlg.grab_set(); dlg.focus_set(); dlg.wait_window()
