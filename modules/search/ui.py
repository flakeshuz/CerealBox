"""Search UI scaffold"""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from ...ui.components import configure_listbox, page_header

class SearchView(ttk.Frame):
    def __init__(self, parent, mod):
        super().__init__(parent)
        self.mod = mod
        header, actions = page_header(self, "Search")
        self.entry = ttk.Entry(self)
        self.entry.pack(fill="x", padx=24, pady=(4, 8))
        self.btn = ttk.Button(actions, text="Search", style="Accent.TButton", command=self.run)
        self.btn.pack(side="left")
        self.results = tk.Listbox(self)
        configure_listbox(self.results)
        self.results.pack(fill="both", expand=True, padx=24, pady=(4, 24))
    def run(self):
        term = self.entry.get()
        res = self.mod.global_search(term)
        self.results.delete(0, tk.END)
        for r in (res or []):
            self.results.insert(tk.END, str(r))
