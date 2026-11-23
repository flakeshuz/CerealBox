"""Money screen: month navigation, accounts, budgets, transactions, and the dialogs that edit them."""
from __future__ import annotations

import tkinter as tk
from datetime import date
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from ...core import dates as D
from ...core.rrule import FREQ_BY_LABEL as FREQ
from ...core.rrule import LABEL_BY_FREQ as CHOICE_OF_FREQ
from ...core.rrule import REPEAT_CHOICES, REPEAT_NONE, build_rrule, parse_rrule
from ...core.rrule import REPEAT_CUSTOM as CUSTOM
from ...ui import theme as T
from . import csvimport
from .models import (
    ACCOUNT_KINDS,
    INCOME,
    TRANSFER,
    Account,
    Bill,
    Category,
    Transaction,
    fmt_money,
    parse_amount,
)

ALL_ACCOUNTS = "All accounts"


def _modal(win: tk.Toplevel, parent: tk.Misc) -> None:
    win.transient(parent.winfo_toplevel())
    T.center(win, parent)
    win.wait_visibility()
    win.grab_set()


def _month_label(d: date) -> str:
    return f"{d:%B %Y}"


class MoneyView(ttk.Frame):
    def __init__(self, parent: tk.Misc, mod):
        super().__init__(parent)
        self.mod = mod
        self.month = date.today().replace(day=1)
        self.account_var = tk.StringVar(value=ALL_ACCOUNTS)
        self._subs = [("money.*", self._on_change), ("vault.reloaded", self._on_change)]
        for pattern, handler in self._subs:
            mod.api.on(pattern, handler)
        self.bind("<Destroy>", self._cleanup, add="+")

        bar = ttk.Frame(self, padding=(14, 12, 14, 8))
        bar.pack(fill="x")
        ttk.Button(bar, text="‹", width=3, command=lambda: self.step(-1)).pack(side="left")
        ttk.Button(bar, text="This month", command=self.go_today).pack(side="left", padx=6)
        ttk.Button(bar, text="›", width=3, command=lambda: self.step(1)).pack(side="left")
        self.title_var = tk.StringVar()
        ttk.Label(bar, textvariable=self.title_var, style="Title.TLabel").pack(side="left", padx=16)
        self.account_box = ttk.Combobox(bar, textvariable=self.account_var, state="readonly", width=20)
        self.account_box.pack(side="left", padx=(8, 0))
        self.account_box.bind("<<ComboboxSelected>>", lambda _e: self.refresh())

        right = ttk.Frame(bar)
        right.pack(side="right")
        ttk.Button(right, text="New transaction", style="Accent.TButton", command=self.new_txn).pack(side="left")
        ttk.Button(right, text="Transfer…", command=self.new_transfer).pack(side="left", padx=6)
        ttk.Button(right, text="Import bank CSV", command=self.import_csv).pack(side="left", padx=6)
        ttk.Button(right, text="Bills", command=self.open_bills).pack(side="left")
        more = ttk.Menubutton(right, text="Manage")
        more.pack(side="left", padx=6)
        menu = tk.Menu(more, tearoff=False)
        more["menu"] = menu
        menu.add_command(label="Accounts…", command=self.open_accounts)
        menu.add_command(label="Categories and budgets…", command=self.open_categories)
        menu.add_command(label="Auto-categorise rules…", command=self.open_rules)

        body = ttk.Frame(self, padding=(14, 0, 14, 8))
        body.pack(fill="both", expand=True)
        left = ttk.Frame(body, width=340)
        left.pack(side="left", fill="y", padx=(0, 14))
        left.pack_propagate(False)

        ttk.Label(left, text="Accounts", style="Muted.TLabel").pack(anchor="w")
        self.acc_tree = self._tree(left, (("name", "Account", 200, True), ("bal", "Balance", 110, False)), 6)
        ttk.Label(left, text="Budget this month", style="Muted.TLabel").pack(anchor="w", pady=(12, 0))
        self.bud_tree = self._tree(left, (("name", "Category", 140, True), ("spent", "Spent", 90, False),
                                          ("left", "Left", 90, False)), 12)
        self.bud_tree.tag_configure("over", foreground=T.NOW)
        self.bud_tree.tag_configure("plain", foreground=T.INK)

        right_col = ttk.Frame(body)
        right_col.pack(side="left", fill="both", expand=True)
        self.summary = ttk.Label(right_col, style="Muted.TLabel")
        self.summary.pack(anchor="w", pady=(0, 6))
        self.txn_tree = self._tree(right_col, (("day", "Date", 90, False), ("payee", "Payee", 260, True),
                                               ("cat", "Category", 150, False), ("amt", "Amount", 110, False),
                                               ("acc", "Account", 140, False)), 20, expand=True)
        self.txn_tree.tag_configure("in", foreground=T.SUCCESS)
        self.empty = ttk.Label(self.txn_tree.master, style="Muted.TLabel", justify="center", wraplength=360)
        self.txn_tree.bind("<Double-1>", lambda _e: self.edit_selected())
        self.txn_tree.bind("<Return>", lambda _e: self.edit_selected())
        self.txn_tree.bind("<Delete>", lambda _e: self.delete_selected())
        self.txn_tree.bind("<BackSpace>", lambda _e: self.delete_selected())
        actions = ttk.Frame(right_col)
        actions.pack(fill="x", pady=(8, 0))
        ttk.Button(actions, text="Edit", command=self.edit_selected).pack(side="left")
        ttk.Button(actions, text="Delete", style="Danger.TButton", command=self.delete_selected).pack(side="left", padx=6)
        self._refresh_accounts_box()
        self.refresh()

    def _tree(self, parent, cols, height, expand=False):
        frame = ttk.Frame(parent)
        frame.pack(fill="both" if expand else "x", expand=expand)
        tree = ttk.Treeview(frame, columns=[c[0] for c in cols], show="headings", height=height,
                            selectmode="extended")
        for key, text, width, stretch in cols:
            tree.heading(key, text=text, anchor="e" if key in ("bal", "spent", "left", "amt") else "w")
            tree.column(key, width=width, stretch=stretch,
                        anchor="e" if key in ("bal", "spent", "left", "amt") else "w")
        vsb = ttk.Scrollbar(frame, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=vsb.set)
        tree.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")
        return tree

    # ---- lifecycle -------------------------------------------------------------------------------
    def _cleanup(self, event) -> None:
        if event.widget is self:
            for pattern, handler in self._subs:
                self.mod.api.off(pattern, handler)

    def _on_change(self, topic: str = "", **_) -> None:
        self._refresh_accounts_box()
        self.refresh()

    def _refresh_accounts_box(self) -> None:
        names = [ALL_ACCOUNTS] + [a.name for a in self.mod.accounts()]
        self.account_box.config(values=names)
        if self.account_var.get() not in names:
            self.account_var.set(ALL_ACCOUNTS)

    def _selected_account_id(self) -> str | None:
        name = self.account_var.get()
        if name == ALL_ACCOUNTS:
            return None
        return next((a.id for a in self.mod.accounts() if a.name == name), None)

    # ---- navigation -------------------------------------------------------------------------------
    def step(self, n: int) -> None:
        y, m = self.month.year, self.month.month + n
        self.month = date(y + (m - 1) // 12, (m - 1) % 12 + 1, 1)
        self.refresh()

    def go_today(self) -> None:
        self.month = date.today().replace(day=1)
        self.refresh()

    # ---- drawing ------------------------------------------------------------------------------------
    def refresh(self) -> None:
        m = self.month
        self.title_var.set(_month_label(m))
        acc_id = self._selected_account_id()

        self.acc_tree.delete(*self.acc_tree.get_children())
        for a in self.mod.accounts():
            self.acc_tree.insert("", "end", iid=a.id, values=(a.name, fmt_money(self.mod.balance(a.id))))

        summary = self.mod.month_summary(m.year, m.month)
        self.bud_tree.delete(*self.bud_tree.get_children())
        for i, row in enumerate(summary["categories"]):
            if row["budget"] is not None:
                left = row["budget"] - row["spent"]
                left_text = fmt_money(left)
                tag = "over" if left < 0 else "plain"
            else:
                left_text, tag = "no budget", "plain"
            self.bud_tree.insert("", "end", iid=f"b{i}", tags=(tag,),
                                 values=(row["name"], fmt_money(row["spent"]), left_text))
        self.summary.config(text=f"In {fmt_money(summary['income'])}   ·   Out {fmt_money(summary['spent'])}"
                                 f"   ·   Net {fmt_money(summary['net'], signed=True)}")

        self.txn_tree.delete(*self.txn_tree.get_children())
        for t in self.mod.list_transactions(acc_id, m.year, m.month):
            acc = self.mod.account(t.account_id)
            cat = self.mod.category(t.category_id)
            tags = ("in",) if t.amount_cents > 0 else ()
            self.txn_tree.insert("", "end", iid=t.id, tags=tags, values=(
                f"{t.day:%b} {t.day.day}", t.payee, cat.name if cat else "—",
                fmt_money(t.amount_cents, signed=True), acc.name if acc else ""))
        if not self.txn_tree.get_children():
            if not self.mod.accounts():
                text = "Add an account to start. Manage → Accounts."
            else:
                text = "No transactions this month. Press New transaction, or import a bank CSV."
            self.empty.config(text=text)
            self.empty.place(relx=0.5, rely=0.42, anchor="center")
        else:
            self.empty.place_forget()

    # ---- actions ---------------------------------------------------------------------------------------
    def new_txn(self) -> None:
        if not self.mod.accounts():
            messagebox.showinfo("Add an account first", "Create an account under Manage → Accounts.", parent=self)
            return
        TransactionDialog(self, self.mod, default_account=self._selected_account_id(), day=date.today())

    def new_transfer(self) -> None:
        if len(self.mod.accounts()) < 2:
            messagebox.showinfo("Transfers", "A transfer needs at least two accounts.", parent=self)
            return
        TransferDialog(self, self.mod, default_from=self._selected_account_id())

    def edit_selected(self) -> None:
        sel = self.txn_tree.selection()
        if len(sel) == 1:
            t = self.mod.get_transaction(sel[0])
            if t and t.transfer_id:
                messagebox.showinfo("Transfer", "Transfers can't be edited. Delete it and enter it again.",
                                    parent=self)
            elif t:
                TransactionDialog(self, self.mod, t)

    def delete_selected(self) -> None:
        sel = self.txn_tree.selection()
        if sel and messagebox.askyesno("Delete", f"Delete {len(sel)} transaction(s)?", parent=self):
            for iid in sel:
                self.mod.delete_transaction(iid)

    def import_csv(self) -> None:
        ImportDialog(self, self.mod)

    def open_bills(self) -> None:
        BillsWindow(self, self.mod)

    def open_accounts(self) -> None:
        AccountsWindow(self, self.mod)

    def open_categories(self) -> None:
        CategoriesWindow(self, self.mod)

    def open_rules(self) -> None:
        RulesWindow(self, self.mod)


# ---- dialogs ---------------------------------------------------------------------------------------------
def _form(win: tk.Toplevel):
    frm = ttk.Frame(win, padding=20)
    frm.pack()
    return frm


class TransactionDialog(tk.Toplevel):
    def __init__(self, parent, mod, txn: Transaction | None = None, default_account: str | None = None,
                 day: date | None = None):
        super().__init__(parent)
        self.mod, self.txn = mod, txn
        self.title("Edit transaction" if txn else "New transaction")
        self.configure(bg=T.BG)
        self.resizable(False, False)
        accounts = mod.accounts()
        self._acc_ids = {a.name: a.id for a in accounts}
        self._cat_ids = {c.name: c.id for c in mod.categories()}
        self._cat_ids["(automatic)"] = None
        cat_names = ["(automatic)"] + [c.name for c in mod.categories()]

        acc_id = txn.account_id if txn else default_account
        amount = abs(txn.amount_cents) if txn else 0
        cat = mod.category(txn.category_id) if txn else None
        self.payee_var = tk.StringVar(value=txn.payee if txn else "")
        self.date_var = tk.StringVar(value=f"{(txn.day if txn else day or date.today()):%m/%d/%Y}")
        self.amount_var = tk.StringVar(value=f"{amount / 100:.2f}" if txn else "")
        self.dir_var = tk.StringVar(value="Received" if txn and txn.amount_cents > 0 else "Spent")
        self.acc_var = tk.StringVar(value=next((a.name for a in accounts if a.id == acc_id), accounts[0].name if accounts else ""))
        self.cat_var = tk.StringVar(value=cat.name if cat else "(automatic)")

        frm = _form(self)
        rows = [("Payee", ttk.Entry(frm, textvariable=self.payee_var, width=36)),
                ("Date", ttk.Entry(frm, textvariable=self.date_var, width=14)),
                ("Amount", self._amount_row(frm)),
                ("Account", ttk.Combobox(frm, textvariable=self.acc_var, values=list(self._acc_ids),
                                         state="readonly", width=24)),
                ("Category", ttk.Combobox(frm, textvariable=self.cat_var, values=cat_names,
                                          state="readonly", width=24)),
                ("Memo", ttk.Entry(frm, width=36))]
        self.memo = rows[-1][1]
        if txn:
            self.memo.insert(0, txn.memo)
        for i, (text, widget) in enumerate(rows):
            ttk.Label(frm, text=text, style="Muted.TLabel").grid(row=i, column=0, sticky="e", padx=(0, 12), pady=5)
            widget.grid(row=i, column=1, sticky="w", pady=5)
        btns = ttk.Frame(frm)
        btns.grid(row=len(rows), column=0, columnspan=2, sticky="e", pady=(14, 0))
        if txn:
            ttk.Button(btns, text="Delete", style="Danger.TButton", command=self._delete).pack(side="left")
        ttk.Button(btns, text="Save", style="Accent.TButton", command=self._save).pack(side="right")
        ttk.Button(btns, text="Cancel", command=self.destroy).pack(side="right", padx=8)
        self.bind("<Escape>", lambda _e: self.destroy())
        self.bind("<Control-Return>", lambda _e: self._save())
        _modal(self, parent)

    def _amount_row(self, frm):
        box = ttk.Frame(frm)
        ttk.Entry(box, textvariable=self.amount_var, width=14).pack(side="left")
        ttk.Combobox(box, textvariable=self.dir_var, values=["Spent", "Received"], state="readonly",
                     width=10).pack(side="left", padx=6)
        return box

    def _save(self) -> None:
        try:
            payee = self.payee_var.get().strip()
            if not payee:
                raise ValueError("Enter a payee or description.")
            day = D.parse_date(self.date_var.get())
            cents = abs(parse_amount(self.amount_var.get()))
            if cents == 0:
                raise ValueError("The amount can't be zero.")
            if self.dir_var.get() == "Spent":
                cents = -cents
            acc_id = self._acc_ids.get(self.acc_var.get())
            if not acc_id:
                raise ValueError("Choose an account.")
        except ValueError as exc:
            messagebox.showerror("Check the transaction", str(exc), parent=self)
            return
        cat_name = self.cat_var.get()
        cat_id = self._cat_ids.get(cat_name)
        t = self.txn.copy() if self.txn else Transaction.new(acc_id, day, cents)
        t.account_id, t.day, t.amount_cents, t.payee = acc_id, day, cents, payee
        t.memo = self.memo.get().strip()
        if cat_name == "(automatic)":
            cat_id = None if self.txn is None or self.txn.payee != payee else self.txn.category_id
        t.category_id = cat_id
        self.mod.save_transaction(t)
        self.destroy()

    def _delete(self) -> None:
        if messagebox.askyesno("Delete", "Delete this transaction?", parent=self):
            self.mod.delete_transaction(self.txn.id)
            self.destroy()


class TransferDialog(tk.Toplevel):
    def __init__(self, parent, mod, default_from: str | None = None):
        super().__init__(parent)
        self.mod = mod
        self.title("New transfer")
        self.configure(bg=T.BG)
        self.resizable(False, False)
        accounts = mod.accounts()
        self._ids = {a.name: a.id for a in accounts}
        names = list(self._ids)
        first = next((a.name for a in accounts if a.id == default_from), names[0])
        self.from_var = tk.StringVar(value=first)
        self.to_var = tk.StringVar(value=next((n for n in names if n != first), first))
        self.amount_var = tk.StringVar()
        self.date_var = tk.StringVar(value=f"{date.today():%m/%d/%Y}")
        self.memo_var = tk.StringVar()
        frm = _form(self)
        rows = [("From", ttk.Combobox(frm, textvariable=self.from_var, values=names, state="readonly", width=24)),
                ("To", ttk.Combobox(frm, textvariable=self.to_var, values=names, state="readonly", width=24)),
                ("Amount", ttk.Entry(frm, textvariable=self.amount_var, width=14)),
                ("Date", ttk.Entry(frm, textvariable=self.date_var, width=14)),
                ("Memo", ttk.Entry(frm, textvariable=self.memo_var, width=30))]
        for i, (text, widget) in enumerate(rows):
            ttk.Label(frm, text=text, style="Muted.TLabel").grid(row=i, column=0, sticky="e", padx=(0, 12), pady=5)
            widget.grid(row=i, column=1, sticky="w", pady=5)
        ttk.Label(frm, text="Records both sides. Transfers don't count as spending.", style="Muted.TLabel").grid(
            row=len(rows), column=1, sticky="w")
        btns = ttk.Frame(frm)
        btns.grid(row=len(rows) + 1, column=0, columnspan=2, sticky="e", pady=(12, 0))
        ttk.Button(btns, text="Save", style="Accent.TButton", command=self._save).pack(side="right")
        ttk.Button(btns, text="Cancel", command=self.destroy).pack(side="right", padx=8)
        self.bind("<Escape>", lambda _e: self.destroy())
        _modal(self, parent)

    def _save(self) -> None:
        try:
            src, dst = self._ids.get(self.from_var.get()), self._ids.get(self.to_var.get())
            if not src or not dst:
                raise ValueError("Choose both accounts.")
            cents = abs(parse_amount(self.amount_var.get()))
            day = D.parse_date(self.date_var.get())
            self.mod.add_transfer(src, dst, cents, day, self.memo_var.get().strip())
        except ValueError as exc:
            messagebox.showerror("Check the transfer", str(exc), parent=self)
            return
        self.destroy()


class ImportDialog(tk.Toplevel):
    def __init__(self, parent, mod):
        super().__init__(parent)
        self.mod = mod
        self.title("Import bank CSV")
        self.configure(bg=T.BG)
        self.resizable(False, False)
        accounts = mod.accounts()
        self._acc_ids = {a.name: a.id for a in accounts}
        self.acc_var = tk.StringVar(value=accounts[0].name if accounts else "")
        self.flip_var = tk.BooleanVar(value=False)
        self.path_var = tk.StringVar(value="No file chosen")
        self._text: str | None = None

        frm = _form(self)
        ttk.Label(frm, text="Import bank CSV", style="Title.TLabel").grid(row=0, column=0, columnspan=2, sticky="w")
        ttk.Label(frm, text="Download a statement as CSV from your bank and choose it here. Rows you have already "
                            "imported are skipped, so it's safe to re-import an overlapping range.",
                  style="Muted.TLabel", wraplength=460, justify="left").grid(
            row=1, column=0, columnspan=2, sticky="w", pady=(4, 14))
        ttk.Label(frm, text="Account", style="Muted.TLabel").grid(row=2, column=0, sticky="e", padx=(0, 12), pady=5)
        ttk.Combobox(frm, textvariable=self.acc_var, values=list(self._acc_ids), state="readonly",
                     width=26).grid(row=2, column=1, sticky="w", pady=5)
        ttk.Label(frm, text="File", style="Muted.TLabel").grid(row=3, column=0, sticky="e", padx=(0, 12), pady=5)
        fbox = ttk.Frame(frm)
        fbox.grid(row=3, column=1, sticky="w", pady=5)
        ttk.Button(fbox, text="Choose file…", command=self.choose).pack(side="left")
        ttk.Label(fbox, textvariable=self.path_var, style="Muted.TLabel").pack(side="left", padx=8)
        ttk.Checkbutton(frm, text="Purchases show as positive numbers (typical for credit cards)",
                        variable=self.flip_var).grid(row=4, column=1, sticky="w", pady=5)
        self.result = ttk.Label(frm, text="", justify="left", wraplength=460)
        self.result.grid(row=5, column=0, columnspan=2, sticky="w", pady=(8, 0))
        btns = ttk.Frame(frm)
        btns.grid(row=6, column=0, columnspan=2, sticky="e", pady=(14, 0))
        ttk.Button(btns, text="Close", command=self.destroy).pack(side="right")
        self.import_btn = ttk.Button(btns, text="Import", style="Accent.TButton", command=self.run, state="disabled")
        self.import_btn.pack(side="right", padx=8)
        self.bind("<Escape>", lambda _e: self.destroy())
        _modal(self, parent)

    def choose(self) -> None:
        path = filedialog.askopenfilename(parent=self, title="Choose bank CSV",
                                          filetypes=[("CSV", "*.csv"), ("All files", "*.*")])
        if not path:
            return
        try:
            self._text = Path(path).read_text(encoding="utf-8-sig", errors="replace")
            rows, skipped = csvimport.parse_statement(self._text, flip=False)
        except (ValueError, OSError) as exc:
            self._text = None
            self.import_btn.state(["disabled"])
            self.result.config(text=f"That file couldn't be read.\n{exc}")
            return
        self.path_var.set(Path(path).name)
        preview = f"Found {len(rows)} transactions" + (f" ({len(skipped)} unreadable rows will be skipped)" if skipped else "")
        if rows:
            preview += f"\nFrom {min(r.day for r in rows):%b %d, %Y} to {max(r.day for r in rows):%b %d, %Y}"
        self.result.config(text=preview)
        self.import_btn.state(["!disabled"])

    def run(self) -> None:
        if self._text is None:
            return
        acc_id = self._acc_ids.get(self.acc_var.get())
        if not acc_id:
            messagebox.showerror("Import", "Create an account first.", parent=self)
            return
        try:
            res = self.mod.import_csv(self._text, acc_id, flip=self.flip_var.get())
        except ValueError as exc:
            messagebox.showerror("Import failed", str(exc), parent=self)
            return
        self.result.config(text=res.summary())
        self.import_btn.state(["disabled"])
        self._text = None


class AccountDialog(tk.Toplevel):
    def __init__(self, parent, mod, acc: Account | None = None):
        super().__init__(parent)
        self.mod, self.acc = mod, acc
        self.title("Edit account" if acc else "New account")
        self.configure(bg=T.BG)
        self.resizable(False, False)
        self.name_var = tk.StringVar(value=acc.name if acc else "")
        self.kind_var = tk.StringVar(value=acc.kind if acc else "Checking")
        self.open_var = tk.StringVar(value=f"{acc.opening_cents / 100:.2f}" if acc else "0.00")
        frm = _form(self)
        for i, (text, widget) in enumerate([
            ("Name", ttk.Entry(frm, textvariable=self.name_var, width=30)),
            ("Type", ttk.Combobox(frm, textvariable=self.kind_var, values=list(ACCOUNT_KINDS), state="readonly", width=28)),
            ("Opening balance", ttk.Entry(frm, textvariable=self.open_var, width=14)),
        ]):
            ttk.Label(frm, text=text, style="Muted.TLabel").grid(row=i, column=0, sticky="e", padx=(0, 12), pady=5)
            widget.grid(row=i, column=1, sticky="w", pady=5)
        btns = ttk.Frame(frm)
        btns.grid(row=3, column=0, columnspan=2, sticky="e", pady=(14, 0))
        ttk.Button(btns, text="Save", style="Accent.TButton", command=self._save).pack(side="right")
        ttk.Button(btns, text="Cancel", command=self.destroy).pack(side="right", padx=8)
        self.bind("<Escape>", lambda _e: self.destroy())
        _modal(self, parent)

    def _save(self) -> None:
        try:
            name = self.name_var.get().strip()
            if not name:
                raise ValueError("Give the account a name.")
            opening = parse_amount(self.open_var.get() or "0")
        except ValueError as exc:
            messagebox.showerror("Check the account", str(exc), parent=self)
            return
        if self.acc:
            a = Account(self.acc.id, name, self.kind_var.get(), opening, self.acc.archived)
        else:
            a = Account.new(name, self.kind_var.get(), opening)
        self.mod.save_account(a)
        self.destroy()


class AccountsWindow(tk.Toplevel):
    def __init__(self, parent, mod):
        super().__init__(parent)
        self.mod = mod
        self.title("Accounts")
        self.configure(bg=T.BG)
        frm = _form(self)
        ttk.Label(frm, text="Accounts", style="Title.TLabel").pack(anchor="w")
        self.tree = ttk.Treeview(frm, columns=("name", "kind", "state"), show="headings", height=8, selectmode="browse")
        for key, text, w in (("name", "Name", 220), ("kind", "Type", 120), ("state", "Status", 90)):
            self.tree.heading(key, text=text, anchor="w")
            self.tree.column(key, width=w, anchor="w")
        self.tree.pack(fill="x", pady=8)
        row = ttk.Frame(frm)
        row.pack(fill="x")
        ttk.Button(row, text="Add account", style="Accent.TButton", command=self.add).pack(side="left")
        ttk.Button(row, text="Edit", command=self.edit).pack(side="left", padx=6)
        ttk.Button(row, text="Archive / restore", command=self.toggle_archive).pack(side="left")
        ttk.Button(row, text="Delete", style="Danger.TButton", command=self.delete).pack(side="left", padx=6)
        ttk.Button(frm, text="Close", command=self.destroy).pack(anchor="e", pady=(12, 0))
        self.tree.bind("<Double-1>", lambda _e: self.edit())
        self.bind("<Escape>", lambda _e: self.destroy())
        self.refresh()
        _modal(self, parent)

    def refresh(self) -> None:
        self.tree.delete(*self.tree.get_children())
        for a in self.mod.accounts(include_archived=True):
            self.tree.insert("", "end", iid=a.id, values=(a.name, a.kind, "archived" if a.archived else "active"))

    def _sel(self) -> Account | None:
        sel = self.tree.selection()
        return self.mod.account(sel[0]) if sel else None

    def add(self) -> None:
        AccountDialog(self, self.mod)

    def edit(self) -> None:
        a = self._sel()
        if a:
            AccountDialog(self, self.mod, a)

    def toggle_archive(self) -> None:
        a = self._sel()
        if a:
            a = Account(a.id, a.name, a.kind, a.opening_cents, not a.archived)
            self.mod.save_account(a)

    def delete(self) -> None:
        a = self._sel()
        if not a:
            return
        if not self.mod.delete_account(a.id):
            messagebox.showinfo("Can't delete", f"“{a.name}” has transactions. Archive it instead.", parent=self)
        self.refresh()


class CategoryDialog(tk.Toplevel):
    def __init__(self, parent, mod, cat: Category | None = None):
        super().__init__(parent)
        self.mod, self.cat = mod, cat
        self.title("Edit category" if cat else "New category")
        self.configure(bg=T.BG)
        self.resizable(False, False)
        self.name_var = tk.StringVar(value=cat.name if cat else "")
        self.budget_var = tk.StringVar(value=f"{cat.budget_cents / 100:.2f}" if cat and cat.budget_cents else "")
        frm = _form(self)
        ttk.Label(frm, text="Name", style="Muted.TLabel").grid(row=0, column=0, sticky="e", padx=(0, 12), pady=5)
        ttk.Entry(frm, textvariable=self.name_var, width=28).grid(row=0, column=1, sticky="w", pady=5)
        ttk.Label(frm, text="Monthly budget", style="Muted.TLabel").grid(row=1, column=0, sticky="e", padx=(0, 12), pady=5)
        ttk.Entry(frm, textvariable=self.budget_var, width=14).grid(row=1, column=1, sticky="w", pady=5)
        ttk.Label(frm, text="leave blank for no budget", style="Muted.TLabel").grid(row=2, column=1, sticky="w")
        btns = ttk.Frame(frm)
        btns.grid(row=3, column=0, columnspan=2, sticky="e", pady=(14, 0))
        ttk.Button(btns, text="Save", style="Accent.TButton", command=self._save).pack(side="right")
        ttk.Button(btns, text="Cancel", command=self.destroy).pack(side="right", padx=8)
        self.bind("<Escape>", lambda _e: self.destroy())
        _modal(self, parent)

    def _save(self) -> None:
        try:
            name = self.name_var.get().strip()
            if not name:
                raise ValueError("Give the category a name.")
            budget = parse_amount(self.budget_var.get()) if self.budget_var.get().strip() else None
            if budget is not None and budget < 0:
                raise ValueError("A budget can't be negative.")
        except ValueError as exc:
            messagebox.showerror("Check the category", str(exc), parent=self)
            return
        c = Category(self.cat.id, name, budget) if self.cat else Category.new(name, budget)
        self.mod.save_category(c)
        self.destroy()


class CategoriesWindow(tk.Toplevel):
    def __init__(self, parent, mod):
        super().__init__(parent)
        self.mod = mod
        self.title("Categories and budgets")
        self.configure(bg=T.BG)
        frm = _form(self)
        ttk.Label(frm, text="Categories and monthly budgets", style="Title.TLabel").pack(anchor="w")
        self.tree = ttk.Treeview(frm, columns=("name", "budget"), show="headings", height=12, selectmode="browse")
        self.tree.heading("name", text="Category", anchor="w")
        self.tree.heading("budget", text="Monthly budget", anchor="e")
        self.tree.column("name", width=240, anchor="w")
        self.tree.column("budget", width=140, anchor="e")
        self.tree.pack(fill="x", pady=8)
        row = ttk.Frame(frm)
        row.pack(fill="x")
        ttk.Button(row, text="Add", style="Accent.TButton", command=self.add).pack(side="left")
        ttk.Button(row, text="Edit", command=self.edit).pack(side="left", padx=6)
        ttk.Button(row, text="Delete", style="Danger.TButton", command=self.delete).pack(side="left")
        ttk.Button(frm, text="Close", command=self.destroy).pack(anchor="e", pady=(12, 0))
        self.tree.bind("<Double-1>", lambda _e: self.edit())
        self.bind("<Escape>", lambda _e: self.destroy())
        self._sub = ("money.*", self._refresh)
        mod.api.on(*self._sub)
        self.bind("<Destroy>", lambda e: mod.api.off(*self._sub) if e.widget is self else None, add="+")
        self._refresh()
        _modal(self, parent)

    def _refresh(self, *_a, **_k) -> None:
        if not self.winfo_exists():
            return
        self.tree.delete(*self.tree.get_children())
        for c in self.mod.categories():
            budget = fmt_money(c.budget_cents) if c.budget_cents is not None else "—"
            self.tree.insert("", "end", iid=c.id, values=(c.name, budget))

    def _sel(self) -> Category | None:
        sel = self.tree.selection()
        return self.mod.category(sel[0]) if sel else None

    def add(self) -> None:
        CategoryDialog(self, self.mod)

    def edit(self) -> None:
        c = self._sel()
        if c:
            CategoryDialog(self, self.mod, c)

    def delete(self) -> None:
        c = self._sel()
        if c and c.id not in (INCOME, TRANSFER) and messagebox.askyesno(
                "Delete category", f"Delete “{c.name}”? Its transactions become uncategorised.", parent=self):
            self.mod.delete_category(c.id)


class RulesWindow(tk.Toplevel):
    def __init__(self, parent, mod):
        super().__init__(parent)
        self.mod = mod
        self.title("Auto-categorise rules")
        self.configure(bg=T.BG)
        frm = _form(self)
        ttk.Label(frm, text="Rules", style="Title.TLabel").pack(anchor="w")
        ttk.Label(frm, text="If a payee contains the words, the transaction gets that category.",
                  style="Muted.TLabel").pack(anchor="w", pady=(2, 8))
        self.tree = ttk.Treeview(frm, columns=("kw", "cat"), show="headings", height=10, selectmode="browse")
        self.tree.heading("kw", text="Payee contains", anchor="w")
        self.tree.heading("cat", text="Category", anchor="w")
        self.tree.column("kw", width=240, anchor="w")
        self.tree.column("cat", width=180, anchor="w")
        self.tree.pack(fill="x")
        add = ttk.Frame(frm)
        add.pack(fill="x", pady=8)
        self.kw_var = tk.StringVar()
        self.cat_var = tk.StringVar()
        ttk.Entry(add, textvariable=self.kw_var, width=26).pack(side="left")
        self.cat_box = ttk.Combobox(add, textvariable=self.cat_var, state="readonly", width=18)
        self.cat_box.pack(side="left", padx=6)
        ttk.Button(add, text="Add rule", style="Accent.TButton", command=self.add).pack(side="left")
        ttk.Button(frm, text="Delete selected", style="Danger.TButton", command=self.delete).pack(anchor="w")
        ttk.Button(frm, text="Close", command=self.destroy).pack(anchor="e", pady=(12, 0))
        self.bind("<Escape>", lambda _e: self.destroy())
        self._sub = ("money.*", self._refresh)
        mod.api.on(*self._sub)
        self.bind("<Destroy>", lambda e: mod.api.off(*self._sub) if e.widget is self else None, add="+")
        self._refresh()
        _modal(self, parent)

    def _refresh(self, *_a, **_k) -> None:
        if not self.winfo_exists():
            return
        self.tree.delete(*self.tree.get_children())
        for r in self.mod.rules():
            cat = self.mod.category(r.category_id)
            self.tree.insert("", "end", iid=r.id, values=(r.keyword, cat.name if cat else "—"))
        names = [c.name for c in self.mod.categories()]
        self.cat_box.config(values=names)
        if not self.cat_var.get() and names:
            self.cat_var.set(names[0])

    def add(self) -> None:
        cat = next((c for c in self.mod.categories() if c.name == self.cat_var.get()), None)
        kw = self.kw_var.get().strip()
        if not kw or not cat:
            messagebox.showerror("Add rule", "Enter the words to match and choose a category.", parent=self)
            return
        self.mod.add_rule(kw, cat.id)
        self.kw_var.set("")

    def delete(self) -> None:
        sel = self.tree.selection()
        if sel:
            self.mod.delete_rule(sel[0])


class BillDialog(tk.Toplevel):
    def __init__(self, parent, mod, bill: Bill | None = None):
        super().__init__(parent)
        self.mod, self.bill = mod, bill
        self.title("Edit bill" if bill else "New bill")
        self.configure(bg=T.BG)
        self.resizable(False, False)
        self._acc_ids = {a.name: a.id for a in mod.accounts()}
        self._acc_ids["(none)"] = None
        self._cat_ids = {c.name: c.id for c in mod.categories() if c.id not in (INCOME, TRANSFER)}
        self._cat_ids["(none)"] = None
        b = bill
        self.name_var = tk.StringVar(value=b.name if b else "")
        self.amount_var = tk.StringVar(value=f"{b.amount_cents / 100:.2f}" if b else "")
        self.due_var = tk.StringVar(value=f"{b.due:%m/%d/%Y}" if b else f"{date.today():%m/%d/%Y}")
        self.rep_var = tk.StringVar(value=REPEAT_NONE)
        self._loaded_rep = REPEAT_NONE
        if b and b.rrule:
            p = parse_rrule(b.rrule)
            self._loaded_rep = CUSTOM if p.custom else CHOICE_OF_FREQ.get(p.freq, REPEAT_NONE)
            self.rep_var.set(self._loaded_rep)
        self.rem_var = tk.StringVar(value=", ".join(str(x) for x in b.reminder_days) if b else "3, 0")
        self.acc_var = tk.StringVar(value=next((n for n, i in self._acc_ids.items() if b and i == b.account_id), "(none)"))
        self.cat_var = tk.StringVar(value=next((n for n, i in self._cat_ids.items() if b and i == b.category_id), "(none)"))
        frm = _form(self)
        choices = REPEAT_CHOICES + ([CUSTOM] if self._loaded_rep == CUSTOM else [])
        rows = [
            ("Bill", ttk.Entry(frm, textvariable=self.name_var, width=30)),
            ("Amount", ttk.Entry(frm, textvariable=self.amount_var, width=14)),
            ("Due date", ttk.Entry(frm, textvariable=self.due_var, width=14)),
            ("Repeat", ttk.Combobox(frm, textvariable=self.rep_var, values=choices, state="readonly", width=22)),
            ("Remind (days before)", ttk.Entry(frm, textvariable=self.rem_var, width=18)),
            ("Pay from", ttk.Combobox(frm, textvariable=self.acc_var, values=list(self._acc_ids), state="readonly", width=22)),
            ("Category", ttk.Combobox(frm, textvariable=self.cat_var, values=list(self._cat_ids), state="readonly", width=22)),
        ]
        for i, (text, widget) in enumerate(rows):
            ttk.Label(frm, text=text, style="Muted.TLabel").grid(row=i, column=0, sticky="e", padx=(0, 12), pady=5)
            widget.grid(row=i, column=1, sticky="w", pady=5)
        btns = ttk.Frame(frm)
        btns.grid(row=len(rows), column=0, columnspan=2, sticky="e", pady=(14, 0))
        ttk.Button(btns, text="Save", style="Accent.TButton", command=self._save).pack(side="right")
        ttk.Button(btns, text="Cancel", command=self.destroy).pack(side="right", padx=8)
        self.bind("<Escape>", lambda _e: self.destroy())
        _modal(self, parent)

    def _save(self) -> None:
        try:
            name = self.name_var.get().strip()
            if not name:
                raise ValueError("Give the bill a name.")
            amount = abs(parse_amount(self.amount_var.get()))
            due = D.parse_date(self.due_var.get())
            days = sorted({int(x) for x in self.rem_var.get().replace(";", ",").split(",") if x.strip()})
            if any(x < 0 for x in days):
                raise ValueError("Reminder days can't be negative.")
            rep = self.rep_var.get()
            rrule = None
            if rep != REPEAT_NONE:
                if rep == CUSTOM or (rep == self._loaded_rep and self.bill and self.bill.rrule):
                    rrule = self.bill.rrule
                else:
                    rrule = build_rrule(FREQ[rep])
        except ValueError as exc:
            messagebox.showerror("Check the bill", str(exc), parent=self)
            return
        start_changed = self.bill is None or due != self.bill.due or rrule != (self.bill.rrule if self.bill else None)
        b = self.bill.copy() if self.bill else Bill.new(name, amount, due)
        b.name, b.amount_cents, b.due, b.rrule = name, amount, due, rrule
        b.series_start = due if (rrule and start_changed) else b.series_start
        b.reminder_days = days
        b.account_id, b.category_id = self._acc_ids[self.acc_var.get()], self._cat_ids[self.cat_var.get()]
        self.mod.save_bill(b)
        self.destroy()


class BillsWindow(tk.Toplevel):
    def __init__(self, parent, mod):
        super().__init__(parent)
        self.mod = mod
        self.title("Bills")
        self.configure(bg=T.BG)
        frm = _form(self)
        ttk.Label(frm, text="Bills", style="Title.TLabel").pack(anchor="w")
        ttk.Label(frm, text="Marking a bill paid records it as a transaction and moves a repeating bill "
                            "to its next due date.", style="Muted.TLabel", wraplength=560, justify="left").pack(
            anchor="w", pady=(2, 8))
        self.tree = ttk.Treeview(frm, columns=("name", "due", "amount", "status"), show="headings", height=12,
                                 selectmode="browse")
        for key, text, w, anchor in (("name", "Bill", 220, "w"), ("due", "Due", 130, "w"),
                                     ("amount", "Amount", 110, "e"), ("status", "Status", 110, "w")):
            self.tree.heading(key, text=text, anchor=anchor)
            self.tree.column(key, width=w, anchor=anchor)
        self.tree.tag_configure("late", foreground=T.NOW)
        self.tree.pack(fill="x")
        row = ttk.Frame(frm)
        row.pack(fill="x", pady=8)
        ttk.Button(row, text="New bill", style="Accent.TButton", command=self.add).pack(side="left")
        ttk.Button(row, text="Edit", command=self.edit).pack(side="left", padx=6)
        ttk.Button(row, text="Mark paid", command=self.pay).pack(side="left")
        ttk.Button(row, text="Delete", style="Danger.TButton", command=self.delete).pack(side="left", padx=6)
        ttk.Button(frm, text="Close", command=self.destroy).pack(anchor="e", pady=(10, 0))
        self.tree.bind("<Double-1>", lambda _e: self.edit())
        self.bind("<Escape>", lambda _e: self.destroy())
        self._sub = ("money.*", self._refresh)
        mod.api.on(*self._sub)
        self.bind("<Destroy>", lambda e: mod.api.off(*self._sub) if e.widget is self else None, add="+")
        self._refresh()
        _modal(self, parent)

    def _refresh(self, *_a, **_k) -> None:
        if not self.winfo_exists():
            return
        self.tree.delete(*self.tree.get_children())
        today = date.today()
        for b in self.mod.bills(include_done=False):
            late = b.due < today
            status = "overdue" if late else ("due today" if b.due == today else "upcoming")
            self.tree.insert("", "end", iid=b.id, tags=("late",) if late else (), values=(
                b.name + ("  ↻" if b.rrule else ""), f"{b.due:%a %b} {b.due.day}, {b.due.year}",
                fmt_money(b.amount_cents), status))

    def _sel(self) -> Bill | None:
        sel = self.tree.selection()
        return self.mod.bill(sel[0]) if sel else None

    def add(self) -> None:
        BillDialog(self, self.mod)

    def edit(self) -> None:
        b = self._sel()
        if b:
            BillDialog(self, self.mod, b)

    def pay(self) -> None:
        b = self._sel()
        if b and messagebox.askyesno("Mark paid", f"Record {b.name} ({fmt_money(b.amount_cents)}) as paid today?",
                                     parent=self):
            self.mod.mark_paid(b.id)

    def delete(self) -> None:
        b = self._sel()
        if b and messagebox.askyesno("Delete bill", f"Delete “{b.name}”?", parent=self):
            self.mod.delete_bill(b.id)
