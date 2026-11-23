"""Taxes UI scaffold"""
from __future__ import annotations

from tkinter import ttk

class TaxesView(ttk.Frame):
    def __init__(self, parent, mod):
        super().__init__(parent)
        self.mod = mod
        ttk.Label(self, text="Taxes", style="Title.TLabel").pack(anchor="w")
        self.tree = ttk.Treeview(self, columns=("name","rate"), show="headings")
        self.tree.heading("name", text="Category")
        self.tree.heading("rate", text="Rate")
        self.tree.pack(fill="both", expand=True, pady=4)
        # Minimal UI: scaffold
