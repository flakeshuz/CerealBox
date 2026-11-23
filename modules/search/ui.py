"""Search UI scaffold"""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk

class SearchView(ttk.Frame):
    def __init__(self, parent, mod):
        super().__init__(parent)
        self.mod = mod
        ttk.Label(self, text="Search", style="Title.TLabel").pack(anchor="w")
        self.entry = ttk.Entry(self)
        self.entry.pack(fill="x" , padx=4, pady=4)
        self.btn = ttk.Button(self, text="Go", command=self.run)
        self.btn.pack()
        self.results = tk.Listbox(self)
        self.results.pack(fill="both", expand=True, pady=4)
    def run(self):
        term = self.entry.get()
        res = self.mod.global_search(term)
        self.results.delete(0, tk.END)
        for r in (res or []):
            self.results.insert(tk.END, str(r))
