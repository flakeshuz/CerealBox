"""Password prompts: unlock an existing vault, create a new one, or change the password."""
from __future__ import annotations

import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk

from ..core import Vault, VaultError, WrongPassword
from . import theme as T

MIN_LENGTH = 8


class PasswordDialog(tk.Toplevel):
    """mode: 'unlock' | 'create' | 'change'. After wait_window(), `.password` is the text or None."""

    def __init__(self, parent: tk.Misc, mode: str, path: Path | None = None, error: str = ""):
        super().__init__(parent)
        self.password: str | None = None
        self.mode = mode
        titles = {"unlock": "Unlock LifeOS", "create": "Create your vault", "change": "Change password"}
        self.title(titles[mode])
        self.resizable(False, False)
        self.configure(bg=T.BG)
        body = ttk.Frame(self, padding=24)
        body.pack()

        ttk.Label(body, text=titles[mode], style="Title.TLabel").grid(row=0, column=0, sticky="w")
        blurb = {
            "unlock": f"Enter your password to open {path.name if path else 'your vault'}.",
            "create": "Choose a password. It encrypts everything LifeOS stores.\nThere is no recovery: if you forget it, "
                      "your data can't be read.",
            "change": "Choose a new password for this vault.",
        }[mode]
        ttk.Label(body, text=blurb, style="Muted.TLabel", justify="left").grid(row=1, column=0, sticky="w", pady=(4, 14))

        self.pw1, self.pw2 = tk.StringVar(), tk.StringVar()
        ttk.Label(body, text="New password" if mode == "change" else "Password").grid(row=2, column=0, sticky="w")
        self.e1 = ttk.Entry(body, textvariable=self.pw1, show="•", width=34)
        self.e1.grid(row=3, column=0, sticky="ew", pady=(2, 10))
        if mode != "unlock":
            ttk.Label(body, text="Confirm password").grid(row=4, column=0, sticky="w")
            self.e2 = ttk.Entry(body, textvariable=self.pw2, show="•", width=34)
            self.e2.grid(row=5, column=0, sticky="ew", pady=(2, 10))
            self.e2.bind("<Return>", lambda _e: self._ok())
        else:
            self.e1.bind("<Return>", lambda _e: self._ok())

        self.msg = ttk.Label(body, text=error, style="Error.TLabel", wraplength=320, justify="left")
        self.msg.grid(row=6, column=0, sticky="w")
        btns = ttk.Frame(body)
        btns.grid(row=7, column=0, sticky="e", pady=(10, 0))
        ttk.Button(btns, text="Cancel", command=self.destroy).pack(side="left", padx=(0, 8))
        ttk.Button(btns, text={"unlock": "Unlock", "create": "Create vault", "change": "Change password"}[mode],
                   style="Accent.TButton", command=self._ok).pack(side="left")

        self.bind("<Escape>", lambda _e: self.destroy())
        T.center(self, parent)
        self.deiconify()
        self.wait_visibility()
        self.grab_set()
        self.e1.focus_set()

    def _ok(self) -> None:
        pw = self.pw1.get()
        if self.mode != "unlock":
            if len(pw) < MIN_LENGTH:
                return self.msg.config(text=f"Use at least {MIN_LENGTH} characters.")
            if pw != self.pw2.get():
                return self.msg.config(text="The two passwords don't match.")
        elif not pw:
            return self.msg.config(text="Enter your password.")
        self.password = pw
        self.destroy()
        return None


def unlock_vault(root: tk.Misc, path: Path) -> Vault | None:
    """Create or open the vault at `path`, prompting as needed. None means the user cancelled."""
    creating = not Vault.exists(path)
    error = ""
    while True:
        dlg = PasswordDialog(root, "create" if creating else "unlock", path, error)
        root.wait_window(dlg)
        if dlg.password is None:
            return None
        try:
            return Vault.create(path, dlg.password) if creating else Vault.open(path, dlg.password)
        except WrongPassword:
            error = "That password didn't work. If you're sure it's right, the file may be damaged - " \
                    f"a previous copy may exist at {path.name}.bak."
        except (VaultError, OSError, ValueError) as exc:
            messagebox.showerror("Can't open vault", str(exc), parent=root)
            return None


def ask_new_password(root: tk.Misc) -> str | None:
    dlg = PasswordDialog(root, "change")
    root.wait_window(dlg)
    return dlg.password
