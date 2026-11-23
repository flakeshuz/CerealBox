"""Keyboard-accessible, filterable navigation for the workspace."""
from __future__ import annotations

import tkinter as tk
from . import theme as T

WIDTH = 224
GROUPS = (("DAILY", ("Dashboard", "Calendar", "Tasks", "Notes", "Habits", "Goals")),
          ("PERSONAL", ("Money", "Taxes", "Health", "Home", "Contacts")))


class Sidebar(tk.Frame):
    def __init__(self, parent, titles, on_select):
        super().__init__(parent, bg=T.SURFACE, width=WIDTH)
        self.pack_propagate(False)
        self._active = -1
        self._rows = []
        self._titles = titles
        tk.Label(self, text="CerealBox", bg=T.SURFACE, fg=T.INK,
                 font=(T.FAMILY, 21, "bold"), anchor="w").pack(fill="x", padx=22, pady=(24, 0))
        tk.Label(self, text="Start your day, sorted.", bg=T.SURFACE, fg=T.MUTED,
                 anchor="w").pack(fill="x", padx=22, pady=(4, 20))
        self.query = tk.StringVar()
        entry = tk.Entry(self, textvariable=self.query, relief="flat", bg=T.CONTROL,
                         fg=T.INK, insertbackground=T.INK, font=(T.FAMILY, 11))
        entry.pack(fill="x", padx=16, ipady=8)
        tk.Label(self, text="Filter spaces", bg=T.SURFACE, fg=T.MUTED,
                 anchor="w").pack(fill="x", padx=22, pady=(4, 12))
        canvas = tk.Canvas(self, bg=T.SURFACE, highlightthickness=0, width=WIDTH)
        canvas.pack(fill="both", expand=True)
        body = tk.Frame(canvas, bg=T.SURFACE)
        window = canvas.create_window(0, 0, window=body, anchor="nw")
        canvas.bind("<Configure>", lambda e: canvas.itemconfigure(window, width=e.width))
        body.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind("<MouseWheel>", lambda e: canvas.yview_scroll(-int(e.delta / 120), "units"))
        self._sections = []
        used = set()
        for heading, names in (*GROUPS, ("LIBRARY", tuple(t for t in titles if not any(t in n for _, n in GROUPS)))):
            indices = [i for i, title in enumerate(titles) if title in names and i not in used]
            if not indices:
                continue
            label = tk.Label(body, text=heading, bg=T.SURFACE, fg=T.MUTED,
                             font=(T.FAMILY, 8, "bold"), anchor="w")
            label.pack(fill="x", padx=22, pady=(12, 5))
            rows = []
            for i in indices:
                used.add(i)
                row = tk.Button(body, text="Today" if titles[i] == "Dashboard" else titles[i],
                                anchor="w", relief="flat", bd=0, padx=14, pady=7,
                                bg=T.SURFACE, fg=T.MUTED, activebackground=T.ACCENT_SOFT,
                                activeforeground=T.ACCENT_INK, font=(T.FAMILY, 10),
                                cursor="hand2", command=lambda n=i: on_select(n))
                row.pack(fill="x", padx=12, pady=1)
                self._rows.append((i, row))
                rows.append((i, row))
            self._sections.append((label, rows))
        self.query.trace_add("write", self._filter)
        tk.Label(self, text="LOCAL & FRESH\nYour life stays yours.", justify="left", anchor="w",
                 bg=T.SURFACE, fg=T.MUTED, font=(T.FAMILY, 9)).pack(fill="x", padx=22, pady=18)

    def _filter(self, *_):
        query = self.query.get().strip().casefold()
        for label, rows in self._sections:
            label.pack_forget()
            for _, row in rows:
                row.pack_forget()
            matches = [(i, row) for i, row in rows if query in (self._titles[i] + " " + row.cget("text")).casefold()]
            if matches:
                label.pack(fill="x", padx=22, pady=(12, 5))
                for _, row in matches:
                    row.pack(fill="x", padx=12, pady=1)

    def set_active(self, index):
        self._active = index
        for i, row in self._rows:
            row.configure(bg=T.ACCENT_SOFT if i == index else T.SURFACE,
                          fg=T.ACCENT_INK if i == index else T.MUTED,
                          font=(T.FAMILY, 10, "bold" if i == index else "normal"))
