"""Shared UI building blocks used across CerealBox screens."""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from . import theme as T


def page_header(parent: tk.Misc, title: str) -> tuple[ttk.Frame, ttk.Frame]:
    header = ttk.Frame(parent, style="Page.TFrame", padding=(24, 16, 24, 10))
    header.pack(fill="x")
    ttk.Label(header, text=title, style="Title.TLabel").pack(side="left")
    actions = ttk.Frame(header, style="Page.TFrame")
    actions.pack(side="right")
    return header, actions


def page_surface(parent: tk.Misc) -> ttk.Frame:
    surface = ttk.Frame(parent, style="Surface.TFrame", padding=(24, 18))
    surface.pack(fill="both", expand=True)
    return surface


def configure_listbox(widget: tk.Listbox) -> None:
    widget.configure(
        relief="flat",
        bd=0,
        highlightthickness=1,
        highlightbackground=T.LINE,
        highlightcolor=T.ACCENT,
        background=T.SURFACE,
        foreground=T.INK,
        selectbackground=T.ACCENT_SOFT,
        selectforeground=T.ACCENT_INK,
        activestyle="dotbox",
    )
