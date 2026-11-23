"""Health UI scaffold"""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk


class HealthView(ttk.Frame):
    def __init__(self, parent, mod):
        super().__init__(parent)
        self.mod = mod
        header = ttk.Frame(self)
        header.pack(fill="x")
        ttk.Label(header, text="Health", style="Title.TLabel").pack(side="left", anchor="w")
        ttk.Button(header, text="Add appointment", command=self.add_appointment).pack(side="right", padx=6)
        self.appt_frame = ttk.Frame(self)
        self.appt_frame.pack(fill="both", expand=True, pady=4)
        ttk.Label(self.appt_frame, text="Appointments", style="Muted.TLabel").pack(anchor="w")
        self.appt_list = tk.Listbox(self.appt_frame)
        self.appt_list.pack(fill="both", expand=True, pady=4)
        self.med_frame = ttk.Frame(self)
        self.med_frame.pack(fill="both", expand=True, pady=4)
        ttk.Label(self.med_frame, text="Medications", style="Muted.TLabel").pack(anchor="w")
        self.med_list = tk.Listbox(self.med_frame)
        self.med_list.pack(fill="both", expand=True, pady=4)
        self.refresh()

    def refresh(self):
        self._refresh_appointments()
        self._refresh_medications()

    def _refresh_appointments(self):
        self.appt_list.delete(0, tk.END)
        for a in (self.mod.list_appointments() or []):
            self.appt_list.insert(tk.END, f"{a.get('title','')} - {a.get('date','')}" )

    def _refresh_medications(self):
        self.med_list.delete(0, tk.END)
        for m in (self.mod.list_medications() or []):
            self.med_list.insert(tk.END, f"{m.get('name','')} - {m.get('dose','')}" )

    def add_appointment(self):
        dlg = tk.Toplevel(self)
        dlg.title("Add appointment")
        frm = ttk.Frame(dlg, padding=12)
        frm.pack()
        tk.Label(frm, text="Title").grid(row=0, column=0, sticky="e")
        title_var = tk.StringVar()
        ttk.Entry(frm, textvariable=title_var).grid(row=0, column=1)
        tk.Label(frm, text="Date").grid(row=1, column=0, sticky="e")
        date_var = tk.StringVar()
        ttk.Entry(frm, textvariable=date_var).grid(row=1, column=1)
        def save():
            t = title_var.get().strip()
            d = date_var.get().strip()
            if t and d:
                self.mod.add_appointment(t, d)
                self._refresh_appointments()
                dlg.destroy()
        ttk.Button(frm, text="Save", command=save).grid(row=2, column=0, columnspan=2)
        dlg.transient(self.winfo_toplevel())
        dlg.grab_set(); dlg.focus_set(); dlg.wait_window()
