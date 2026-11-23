"""Design system for CerealBox.

The look is deliberately quiet: one warm neutral page, white sheets for content, one accent colour
used only for things you can act on, and type that does the hierarchy work instead of borders and boxes.

Every colour and size lives here. Screens use the style names defined below and the constants,
so changing a value here changes the whole app.
"""
from __future__ import annotations

import contextlib
import tkinter as tk
from tkinter import font as tkfont
from tkinter import ttk

# ---- colour -----------------------------------------------------------------------------
BG = "#FFF7E6"  # warm milk-and-cereal page background
SURFACE = "#FFFCF5"  # content sheets
DIM = "#F7EFD9"  # oat dim
TODAY_BG = "#FFF0B8"
INK = "#33261C"  # primary text
MUTED = "#716151"  # secondary text
FAINT = "#A9957D"  # tertiary text and disabled states
LINE = "#E8DDBF"  # soft cereal-box hairlines
LINE_SOFT = "#F1E7C9"
CONTROL = "#F7EFD9"  # secondary buttons and segmented controls
CONTROL_HOVER = "#ECDEB7"
ACCENT = "#D94B2B"  # red cereal-box accent
ACCENT_SOFT = "#FFE3CF"
ACCENT_INK = "#A52F18"  # accent text on soft background
NOW = "#B42318"  # overdue, errors, destructive actions
SUCCESS = "#5C7D3A"

FAMILY = "TkDefaultFont"
SIZE = 10  # body text; screens are built around this
_PREFERRED = ("SF Pro Display", "SF Pro Text", ".AppleSystemUIFont", "Segoe UI Variable Text", "Segoe UI",
              "Helvetica Neue", "Noto Sans", "Ubuntu", "DejaVu Sans")


def apply(root: tk.Misc) -> None:
    global FAMILY
    available = set(tkfont.families(root))
    FAMILY = next((f for f in _PREFERRED if f in available), FAMILY)
    for name in ("TkDefaultFont", "TkTextFont", "TkMenuFont", "TkHeadingFont", "TkCaptionFont"):
        with contextlib.suppress(tk.TclError):
            tkfont.nametofont(name).configure(family=FAMILY, size=SIZE)
    root.configure(bg=BG)
    root.option_add("*Menu.font", (FAMILY, SIZE))
    root.option_add("*Menu.background", SURFACE)
    root.option_add("*Menu.foreground", INK)
    root.option_add("*Menu.activeBackground", ACCENT_SOFT)
    root.option_add("*Menu.activeForeground", INK)
    root.option_add("*Menu.borderWidth", 0)
    root.option_add("*TCombobox*Listbox.font", (FAMILY, SIZE))
    root.option_add("*TCombobox*Listbox.background", SURFACE)

    s = ttk.Style(root)
    if root.tk.call("tk", "windowingsystem") == "x11":
        s.theme_use("clam")  # the default X11 theme draws heavy bevels; clam takes flat colours cleanly

    # base
    s.configure(".", background=BG, foreground=INK, font=(FAMILY, SIZE), focuscolor=BG, bordercolor=LINE)
    s.configure("TFrame", background=BG)
    s.configure("Page.TFrame", background=BG)
    s.configure("Surface.TFrame", background=SURFACE)
    s.configure("TLabel", background=BG, foreground=INK)
    s.configure("Display.TLabel", font=(FAMILY, 28, "bold"))
    s.configure("Title.TLabel", font=(FAMILY, 18, "bold"))
    s.configure("Muted.TLabel", foreground=MUTED)
    s.configure("Error.TLabel", foreground=NOW)
    s.configure("Empty.TLabel", background=BG, foreground=MUTED, font=(FAMILY, 11))

    # buttons: a secondary button is a quiet grey pill; the primary one is the only solid colour on screen
    s.configure("TButton", padding=(14, 6), background=CONTROL, foreground=INK, bordercolor=CONTROL,
                relief="flat", focusthickness=0, focuscolor=CONTROL)
    s.map("TButton", background=[("active", CONTROL_HOVER), ("pressed", CONTROL_HOVER), ("disabled", LINE_SOFT)],
          foreground=[("disabled", FAINT)])
    s.configure("Accent.TButton", background=ACCENT, foreground="#FFFFFF", bordercolor=ACCENT)
    s.map("Accent.TButton", background=[("active", "#2259C4"), ("pressed", "#1D4DAB"), ("disabled", "#A9C2F2")],
          foreground=[("disabled", "#FFFFFF")])
    s.configure("Danger.TButton", foreground=NOW)
    s.configure("Small.TButton", padding=(8, 2), font=(FAMILY, 9))
    s.configure("Quiet.TButton", background=BG, bordercolor=BG, foreground=MUTED, padding=(8, 4))
    s.map("Quiet.TButton", background=[("active", LINE_SOFT)], foreground=[("active", INK)])

    # segmented control (Month | Week | Day, Open | Today | Done)
    s.configure("Segment.Toolbutton", padding=(14, 5), background=CONTROL, foreground=MUTED, bordercolor=CONTROL,
                relief="flat", focuscolor=CONTROL)
    s.map("Segment.Toolbutton", background=[("selected", SURFACE), ("active", CONTROL_HOVER)],
          foreground=[("selected", INK), ("active", INK)])

    # fields: flat white with a hairline
    s.configure("TEntry", fieldbackground=SURFACE, bordercolor=LINE, lightcolor=LINE, darkcolor=LINE, padding=6,
                insertcolor=INK)
    s.configure("TCombobox", fieldbackground=SURFACE, bordercolor=LINE, padding=6, arrowcolor=MUTED,
                selectbackground=SURFACE, selectforeground=INK)
    s.map("TCombobox", fieldbackground=[("readonly", SURFACE)], selectbackground=[("readonly", SURFACE)])
    s.configure("TSpinbox", fieldbackground=SURFACE, bordercolor=LINE, padding=5, arrowcolor=MUTED)
    s.configure("TCheckbutton", background=BG)
    s.configure("TRadiobutton", background=BG)
    s.configure("TMenubutton", padding=(12, 6), background=CONTROL, bordercolor=CONTROL, arrowcolor=MUTED)

    # lists
    s.configure("Treeview", rowheight=34, background=SURFACE, fieldbackground=SURFACE, foreground=INK,
                bordercolor=SURFACE, borderwidth=0, relief="flat")
    s.map("Treeview", background=[("selected", ACCENT_SOFT)], foreground=[("selected", INK)])
    s.configure("Treeview.Heading", background=SURFACE, foreground=MUTED, relief="flat", borderwidth=0,
                font=(FAMILY, 9, "bold"), padding=(8, 8))
    s.map("Treeview.Heading", background=[("active", SURFACE)])
    s.configure("Vertical.TScrollbar", background="#D6D6DA", troughcolor=BG, bordercolor=BG, lightcolor="#D6D6DA",
                darkcolor="#D6D6DA", arrowcolor=BG, gripcount=0, relief="flat")
    s.map("Vertical.TScrollbar", background=[("active", "#C4C4CA")])

    # content sheets (dashboard cards, panels): white, borderless, separated by the page colour
    s.configure("Card.TFrame", background=SURFACE, borderwidth=0, relief="flat")
    s.configure("CardInner.TFrame", background=SURFACE, borderwidth=0)
    s.configure("CardTitle.TLabel", background=SURFACE, foreground=MUTED, font=(FAMILY, 9, "bold"))
    s.configure("Card.TLabel", background=SURFACE, foreground=INK)
    s.configure("CardSub.TLabel", background=SURFACE, foreground=INK, font=(FAMILY, 10, "bold"))
    s.configure("CardMuted.TLabel", background=SURFACE, foreground=MUTED)
    s.configure("CardDanger.TLabel", background=SURFACE, foreground=NOW)
    s.configure("CardBig.TLabel", background=SURFACE, foreground=INK, font=(FAMILY, 20, "bold"))
    s.configure("Budget.Horizontal.TProgressbar", background=ACCENT, troughcolor=LINE_SOFT, bordercolor=LINE_SOFT,
                lightcolor=ACCENT, darkcolor=ACCENT, thickness=6)

    # status line at the foot of the window
    s.configure("Status.TLabel", background=BG, foreground=MUTED, padding=(20, 6))


def font(size: int = SIZE, bold: bool = False) -> tkfont.Font:
    return tkfont.Font(family=FAMILY, size=size, weight="bold" if bold else "normal")


# ---- colour helpers (Tk canvases have no alpha, so blend by hand) ----------------------------
def _rgb(h: str) -> tuple[int, int, int]:
    h = h.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def tint(h: str, amount: float) -> str:
    """Blend toward white: amount 0 = original colour, 1 = white."""
    r, g, b = (round(c + (255 - c) * amount) for c in _rgb(h))
    return f"#{r:02x}{g:02x}{b:02x}"


def shade(h: str, amount: float) -> str:
    """Blend toward black."""
    r, g, b = (round(c * (1 - amount)) for c in _rgb(h))
    return f"#{r:02x}{g:02x}{b:02x}"


def on_color(h: str) -> str:
    """Readable text colour (white or ink) for a given fill."""
    r, g, b = _rgb(h)
    return "#FFFFFF" if (0.299 * r + 0.587 * g + 0.114 * b) < 160 else INK


def luminance(h: str) -> float:
    def ch(c: int) -> float:
        c = c / 255
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = _rgb(h)
    return 0.2126 * ch(r) + 0.7152 * ch(g) + 0.0722 * ch(b)


def contrast(a: str, b: str) -> float:
    """WCAG contrast ratio between two colours (4.5 or more is readable for body text)."""
    hi, lo = sorted((luminance(a), luminance(b)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


def center(win: tk.Toplevel | tk.Tk, parent: tk.Misc | None = None) -> None:
    win.update_idletasks()
    w, h = win.winfo_reqwidth(), win.winfo_reqheight()
    if parent is not None and parent.winfo_viewable():
        top = parent.winfo_toplevel()
        x = top.winfo_rootx() + (top.winfo_width() - w) // 2
        y = top.winfo_rooty() + (top.winfo_height() - h) // 3
    else:
        x, y = (win.winfo_screenwidth() - w) // 2, (win.winfo_screenheight() - h) // 3
    win.geometry(f"+{max(x, 0)}+{max(y, 0)}")


# Density management for comfortable vs compact CerealBox UI
CURRENT_DENSITY = "comfortable"
DENSITY_OPTIONS = ("comfortable", "dense")


def set_density(root: tk.Misc, density: str) -> None:
    """Adjust typography and widget density for the given root window.
    density: 'comfortable' or 'dense'
    This updates ttk.Style configurations in-place to affect existing and future widgets.
    """
    global CURRENT_DENSITY
    if density not in DENSITY_OPTIONS:
        density = "comfortable"
    CURRENT_DENSITY = density
    s = ttk.Style(root)
    # Apply density presets
    if density == "dense":
        s.configure("Display.TLabel", font=(FAMILY, 22, "bold"))
        s.configure("Title.TLabel", font=(FAMILY, 14, "bold"))
        s.configure("CardBig.TLabel", font=(FAMILY, 18, "bold"))
        s.configure("Treeview", rowheight=28)
        s.configure("Budget.Horizontal.TProgressbar", thickness=4)
        s.configure("Card.TFrame", padding=(12, 12))
    else:  # comfortable
        s.configure("Display.TLabel", font=(FAMILY, 28, "bold"))
        s.configure("Title.TLabel", font=(FAMILY, 18, "bold"))
        s.configure("CardBig.TLabel", font=(FAMILY, 20, "bold"))
        s.configure("Treeview", rowheight=34)
        s.configure("Budget.Horizontal.TProgressbar", thickness=6)
        s.configure("Card.TFrame", padding=(22, 18))
    # Re-tune a few color-sensitive widgets for density changes
    s.configure("CardTitle.TLabel", font=(FAMILY, 9, "bold"))
    s.configure("CardSub.TLabel", font=(FAMILY, 10, "bold"))
    s.configure("Status.TLabel", padding=(20, 6))

