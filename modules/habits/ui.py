"""Habits UI scaffold"""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from ...ui.components import configure_listbox, page_header


class HabitsView(ttk.Frame):
    def __init__(self, parent, mod):
        super().__init__(parent)
        self.mod = mod
        header, actions = page_header(self, "Habits")
        self.checkin_btn = ttk.Button(actions, text="Check-in", command=self.check_in_selected)
        self.checkin_btn.pack(side="left", padx=(0, 6))
        ttk.Button(actions, text="Add Habit", style="Accent.TButton", command=self.add).pack(side="left")
        self.listbox = tk.Listbox(self)
        configure_listbox(self.listbox)
        self.listbox.pack(fill="both", expand=True, padx=24, pady=(4, 8))
        self.checkins_frame = ttk.Frame(self)
        self.checkins_frame.pack(fill="both", expand=True, pady=(6,0))
        ttk.Label(self.checkins_frame, text="Recent check-ins:", style="Muted.TLabel").pack(anchor="w")
        self.checkins_list = tk.Listbox(self.checkins_frame)
        configure_listbox(self.checkins_list)
        self.checkins_list.pack(fill="both", expand=True, pady=4)
        self.refresh()
        self.listbox.bind("<<ListboxSelect>>", lambda e: self._refresh_checkins())

    def refresh(self):
        self.listbox.delete(0, tk.END)
        self._habits = self.mod.list_habits() or []
        for h in self._habits:
            self.listbox.insert(tk.END, h.get("title", "Habit"))
        self._refresh_checkins()

    def _selected_habit_id(self):
        idxs = self.listbox.curselection()
        if not idxs:
            return None
        idx = idxs[0]
        if idx < len(self._habits):
            return self._habits[idx]["id"]
        return None

    def _refresh_checkins(self):
        self.checkins_list.delete(0, tk.END)
        hid = self._selected_habit_id()
        if not hid:
            return
        checks = self.mod.list_checkins(hid) or []
        for c in checks:
            self.checkins_list.insert(tk.END, c.get("date", ""))

    def check_in_selected(self):
        hid = self._selected_habit_id()
        if not hid:
            return
        self.mod.check_in(hid)
        self._refresh_checkins()
        self.refresh()

    def add(self):
        dlg = tk.Toplevel(self)
        dlg.title("Add Habit")
        frm = ttk.Frame(dlg, padding=12)
        frm.pack()
        tk.Label(frm, text="Title").grid(row=0, column=0, sticky="e")
        title_var = tk.StringVar()
        ttk.Entry(frm, textvariable=title_var).grid(row=0, column=1)
        def save():
            t = title_var.get().strip()
            if t:
                self.mod.add_habit(t)
                self.refresh()
                dlg.destroy()
        ttk.Button(frm, text="Save", command=save).grid(row=1, column=0, columnspan=2)
        dlg.transient(self.winfo_toplevel())
        dlg.grab_set(); dlg.focus_set(); dlg.wait_window()
