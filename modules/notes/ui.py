""""Notes UI scaffold"""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from ...ui.components import configure_listbox, page_header


class NotesView(ttk.Frame):
    def __init__(self, parent, mod):
        super().__init__(parent)
        self.mod = mod
        header, actions = page_header(self, "Notes")
        ttk.Button(actions, text="Add Note", style="Accent.TButton", command=self.add).pack(side="left")
        self.listbox = tk.Listbox(self)
        configure_listbox(self.listbox)
        self.listbox.pack(fill="both", expand=True, padx=24, pady=(4, 24))
        self.refresh()

    def refresh(self):
        self.listbox.delete(0, tk.END)
        for n in (self.mod.list_notes() or []):
            self.listbox.insert(tk.END, n.get("title", "Untitled"))

    def add(self):
        dlg = tk.Toplevel(self)
        dlg.title("Add Note")
        frm = ttk.Frame(dlg, padding=12)
        frm.pack()
        tk.Label(frm, text="Title").grid(row=0, column=0, sticky="e")
        title_var = tk.StringVar()
        ttk.Entry(frm, textvariable=title_var).grid(row=0, column=1)
        tk.Label(frm, text="Content").grid(row=1, column=0, sticky="ne")
        content_var = tk.StringVar()
        ttk.Entry(frm, textvariable=content_var, width=40).grid(row=1, column=1)
        def save():
            title = title_var.get().strip()
            content = content_var.get()
            if title:
                self.mod.add_note(title, content)
                self.refresh()
                dlg.destroy()
        ttk.Button(frm, text="Save", command=save).grid(row=2, column=0, columnspan=2)
        dlg.transient(self.winfo_toplevel())
        dlg.grab_set()
        dlg.focus_set()
        dlg.wait_window()
