"""Shows one screen at a time. It has the same small surface as ttk.Notebook (add, select, tab, tabs, index)
so screens and tests don't need to care, but it draws no tab row: the sidebar is the navigation."""
from __future__ import annotations

import tkinter as tk

from . import theme as T


class Pager(tk.Frame):
    def __init__(self, parent: tk.Misc):
        super().__init__(parent, bg=T.BG)
        self._pages: list[dict] = []
        self._current: dict | None = None
        self._listeners: list = []

    def add(self, widget: tk.Misc, text: str = "") -> None:
        self._pages.append({"name": str(widget), "text": text, "widget": widget})
        widget.pack_forget()
        if self._current is None:
            self.select(widget)

    def tabs(self) -> list[str]:
        return [p["name"] for p in self._pages]

    def _page(self, key) -> dict:
        name = str(key)
        for p in self._pages:
            if p["name"] == name:
                return p
        raise KeyError(name)

    def tab(self, key, option: str | None = None, **_kw):
        if option == "text":
            return self._page(key)["text"]
        return None

    def index(self, key) -> int:
        return self.tabs().index(str(key))

    def select(self, key=None):
        if key is None:
            return self._current["name"] if self._current else ""
        page = self._page(key)
        if page is not self._current:
            if self._current:
                self._current["widget"].pack_forget()
            page["widget"].pack(fill="both", expand=True)
            self._current = page
            for fn in list(self._listeners):
                fn()
        return None

    def bind(self, sequence=None, func=None, add=None):
        if sequence == "<<NotebookTabChanged>>":
            self._listeners.append(lambda: func(None))
            return None
        return super().bind(sequence, func, add)
