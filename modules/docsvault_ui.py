from __future__ import annotations

import base64
import tkinter as tk
from tkinter import ttk


class DocsVaultView(ttk.Frame):
    def __init__(self, parent, module):
        super().__init__(parent)
        self.module = module
        ttk.Label(self, text="Document Vault").pack(anchor="w")
        self.tree = ttk.Treeview(self, columns=("name","size"), show="headings")
        self.tree.heading("name", text="Name")
        self.tree.heading("size", text="Size (bytes)")
        self.tree.pack(fill="both", expand=True)
        frm = ttk.Frame(self)
        frm.pack(anchor="e")
        ttk.Button(frm, text="Add", command=self._add).pack(side="left")
        ttk.Button(frm, text="Refresh", command=self._refresh).pack(side="left", padx=6)
        self._refresh()

    def _refresh(self):
        for i in self.tree.get_children():
            self.tree.delete(i)
        for d in (self.module.docs.all() or []):
            name = d.get("name","")
            data = d.get("data","")
            self.tree.insert("", "end", values=(name, len(data)))

    def _add(self):
        # Minimal add: ask for name and raw data via simple dialog
        win = tk.Toplevel(self)
        win.title("Add Document")
        ttk.Label(win, text="Name").grid(row=0, column=0)
        name_var = tk.StringVar()
        ttk.Entry(win, textvariable=name_var).grid(row=0, column=1)
        ttk.Label(win, text="Data (text)" ).grid(row=1, column=0)
        data_var = tk.StringVar()
        ttk.Entry(win, textvariable=data_var).grid(row=1, column=1)
        def save():
            name = name_var.get()
            data = data_var.get().encode()
            if name:
                # ensure we write via docs store

                self.module.docs.put(name, {"id": f"doc_{name}","name": name,"data": base64.b64encode(data).decode()})
                self._refresh()
            win.destroy()
        ttk.Button(win, text="Save", command=save).grid(row=2, column=0, columnspan=2)
        win.transient(self.winfo_toplevel())
        win.grab_set(); win.focus_set(); win.wait_window()
