"""Contacts UI scaffold"""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from ...ui.components import configure_listbox, page_header

class ContactsView(ttk.Frame):
    def __init__(self, parent, mod):
        super().__init__(parent)
        self.mod = mod
        header, actions = page_header(self, "Contacts")
        ttk.Button(actions, text="Birthdays", command=self.toggle_birthdays).pack(side="left", padx=(0, 6))
        ttk.Button(actions, text="Add Contact", style="Accent.TButton", command=self.add).pack(side="left")
        self.listbox = tk.Listbox(self)
        configure_listbox(self.listbox)
        self.listbox.pack(fill="both", expand=True, padx=24, pady=(4, 24))
        self.birthdays_visible = False
        self.birthdays_frame = ttk.Frame(self)
        self.birthdays_frame.pack(fill="x", padx=4, pady=4)
        self.birthdays_frame.pack_forget()
        ttk.Label(self.birthdays_frame, text="Birthdays this year:", style="Muted.TLabel").pack(anchor="w")
        self.birthdays_list = tk.Listbox(self.birthdays_frame)
        configure_listbox(self.birthdays_list)
        self.birthdays_list.pack(fill="both", expand=True)
        self.refresh()

    def toggle_birthdays(self):
        self.birthdays_visible = not self.birthdays_visible
        if self.birthdays_visible:
            self.birthdays_frame.pack(fill="x", padx=4, pady=4)
            self._refresh_birthdays()
        else:
            self.birthdays_frame.pack_forget()

    def _refresh_birthdays(self):
        self.birthdays_list.delete(0, tk.END)
        for b in (self.mod.birthdays_entries() or []):
            name = b.get("name", "")
            when = b.get("birthday", "")
            self.birthdays_list.insert(tk.END, f"{name} - {when}")

    def refresh(self):
        self.listbox.delete(0, tk.END)
        for c in (self.mod.list_contacts() or []):
            self.listbox.insert(tk.END, c.get("name", "Unknown"))
        self._refresh_birthdays()

    def add(self):
        dlg = tk.Toplevel(self)
        dlg.title("Add Contact")
        frm = ttk.Frame(dlg, padding=12)
        frm.pack()
        tk.Label(frm, text="Name").grid(row=0, column=0, sticky="e")
        name_var = tk.StringVar()
        ttk.Entry(frm, textvariable=name_var).grid(row=0, column=1)
        def save():
            name = name_var.get().strip()
            if name:
                self.mod.add_contact(name)
                self.refresh()
                dlg.destroy()
        ttk.Button(frm, text="Save", command=save).grid(row=1, column=0, columnspan=2)
        dlg.transient(self.winfo_toplevel())
        dlg.grab_set(); dlg.focus_set(); dlg.wait_window()
