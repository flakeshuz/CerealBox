"""Home UI scaffold"""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk


class HomeView(ttk.Frame):
    def __init__(self, parent, mod):
        super().__init__(parent)
        self.mod = mod
        header = ttk.Frame(self)
        header.pack(fill="x")
        ttk.Label(header, text="Home", style="Title.TLabel").pack(side="left", anchor="w")
        ttk.Button(header, text="Add maintenance", command=self.add).pack(side="right")
        self.maint_frame = ttk.Frame(self)
        self.maint_frame.pack(fill="both", expand=True, pady=4)
        self.listbox = tk.Listbox(self.maint_frame)
        self.listbox.pack(fill="both", expand=True, pady=4)
        self.refresh()

    def refresh(self):
        self.listbox.delete(0, tk.END)
        for m in (self.mod.list_maintenance() or []):
            self.listbox.insert(tk.END, m.get("title", "Maintenance"))

    def add(self):
        dlg = tk.Toplevel(self)
        dlg.title("Add maintenance")
        frm = ttk.Frame(dlg, padding=12)
        frm.pack()
        tk.Label(frm, text="Title").grid(row=0, column=0, sticky="e")
        t_var = tk.StringVar()
        ttk.Entry(frm, textvariable=t_var).grid(row=0, column=1)
        tk.Label(frm, text="Due").grid(row=1, column=0, sticky="e")
        d_var = tk.StringVar()
        ttk.Entry(frm, textvariable=d_var).grid(row=1, column=1)
        def save():
            t = t_var.get().strip()
            d = d_var.get().strip()
            if t:
                self.mod.add_maintenance(t, d)
                self.refresh()
                dlg.destroy()
        ttk.Button(frm, text="Save", command=save).grid(row=2, column=0, columnspan=2)
        dlg.transient(self.winfo_toplevel())
        dlg.grab_set(); dlg.focus_set(); dlg.wait_window()
