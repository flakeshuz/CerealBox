"""Money screen: accounts, budgets, transactions, bills, rules, and CSV import."""
from __future__ import annotations

from datetime import date
from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QKeySequence, QShortcut
from PyQt6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFileDialog, QFormLayout, QMenu,
    QHBoxLayout, QLabel, QLineEdit, QMessageBox, QPushButton, QRadioButton,
    QTableWidget, QTableWidgetItem, QTextEdit, QVBoxLayout, QWidget,
)

from ....core import dates as D
from ....core.rrule import FREQ_BY_LABEL as FREQ
from ....core.rrule import LABEL_BY_FREQ as CHOICE_OF_FREQ
from ....core.rrule import REPEAT_CHOICES, REPEAT_NONE, build_rrule, parse_rrule
from ....core.rrule import REPEAT_CUSTOM as CUSTOM
from CerealBox.frontends.qt import theme as T
from CerealBox.modules.money import csvimport
from CerealBox.modules.money.models import (
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


def _show(dlg: QDialog, parent: QWidget) -> None:
    dlg.setModal(True)
    dlg.setWindowModality(Qt.WindowModality.WindowModal)
    dlg.show()
    dlg.raise_()
    dlg.activateWindow()


def _table(parent, headers, widths=None, selection=QTableWidget.SelectionMode.ExtendedSelection):
    table = QTableWidget(0, len(headers), parent)
    table.setHorizontalHeaderLabels(headers)
    table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
    table.setSelectionMode(selection)
    table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
    table.horizontalHeader().setStretchLastSection(True)
    for i, width in enumerate(widths or []):
        table.setColumnWidth(i, width)
    return table


def _fill(table, rows):
    table.setRowCount(len(rows))
    for r, values in enumerate(rows):
        for c, value in enumerate(values):
            item = QTableWidgetItem(str(value))
            if isinstance(value, tuple):
                item.setText(value[0])
                item.setData(Qt.ItemDataRole.UserRole, value[1])
            table.setItem(r, c, item)


def _selected_id(table):
    row = table.currentRow()
    if row < 0 or table.columnCount() == 0:
        return None
    item = table.item(row, 0)
    if item is None:
        return None
    value = item.data(Qt.ItemDataRole.UserRole)
    return value if value is not None else item.text()


def _buttons(parent, actions):
    row = QHBoxLayout()
    for text, callback in actions:
        button = QPushButton(text, parent)
        button.clicked.connect(callback)
        row.addWidget(button)
    return row


class MoneyView(QWidget):
    def __init__(self, parent: QWidget, mod):
        super().__init__(parent)
        self.mod = mod
        self.month = date.today().replace(day=1)
        self._subs = [("money.*", self._on_change), ("vault.reloaded", self._on_change)]
        for pattern, handler in self._subs:
            mod.api.on(pattern, handler)
        self.destroyed.connect(self._cleanup)
        root = QVBoxLayout(self)
        bar = QHBoxLayout()
        root.addLayout(bar)
        self._button(bar, "‹", lambda: self.step(-1))
        self._button(bar, "This month", self.go_today)
        self._button(bar, "›", lambda: self.step(1))
        self.title = QLabel()
        self.title.setStyleSheet("font-size: 19px; font-weight: 600")
        bar.addWidget(self.title)
        self.account_box = QComboBox()
        bar.addWidget(self.account_box)
        self.account_box.currentTextChanged.connect(self.refresh)
        bar.addStretch(1)
        self._button(bar, "New transaction", self.new_txn)
        self._button(bar, "Transfer…", self.new_transfer)
        self._button(bar, "Import bank CSV", self.import_csv)
        self._button(bar, "Bills", self.open_bills)
        manage = QPushButton("Manage")
        menu = QMenu(manage)
        manage.setMenu(menu)
        menu.addAction("Accounts…", self.open_accounts)
        menu.addAction("Categories and budgets…", self.open_categories)
        menu.addAction("Auto-categorise rules…", self.open_rules)
        bar.addWidget(manage)
        content = QHBoxLayout()
        root.addLayout(content, 1)
        left = QVBoxLayout()
        content.addLayout(left)
        left.addWidget(QLabel("Accounts"))
        self.acc_table = _table(self, ["Account", "Balance"], [200, 110], QTableWidget.SelectionMode.SingleSelection)
        left.addWidget(self.acc_table)
        left.addWidget(QLabel("Budget this month"))
        self.bud_table = _table(self, ["Category", "Spent", "Left"], [140, 90, 90],
                                QTableWidget.SelectionMode.SingleSelection)
        left.addWidget(self.bud_table, 1)
        right = QVBoxLayout()
        content.addLayout(right, 1)
        self.summary = QLabel()
        right.addWidget(self.summary)
        self.empty = QLabel()
        self.empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        right.addWidget(self.empty)
        self.txn_table = _table(self, ["Date", "Payee", "Category", "Amount", "Account"],
                                [90, 260, 150, 110, 140])
        self.txn_table.cellDoubleClicked.connect(lambda *_: self.edit_selected())
        self.txn_table.itemActivated.connect(lambda *_: self.edit_selected())
        self._shortcuts = []
        for sequence, callback in (("Return", self.edit_selected), ("Delete", self.delete_selected),
                                   ("Backspace", self.delete_selected)):
            shortcut = QShortcut(QKeySequence(sequence), self.txn_table)
            shortcut.setContext(Qt.ShortcutContext.WidgetShortcut)
            shortcut.activated.connect(callback)
            self._shortcuts.append(shortcut)
        right.addWidget(self.txn_table, 1)
        right.addLayout(_buttons(self, [("Edit", self.edit_selected), ("Delete", self.delete_selected)]))
        self._refresh_accounts_box()
        self.refresh()

    @staticmethod
    def _button(layout, text, callback):
        b = QPushButton(text)
        b.clicked.connect(callback)
        layout.addWidget(b)
        return b

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace):
            self.delete_selected()
        elif event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self.edit_selected()
        else:
            super().keyPressEvent(event)

    def _cleanup(self, *_args):
        for pattern, handler in self._subs:
            self.mod.api.off(pattern, handler)

    def _on_change(self, *_args, **_kwargs):
        self._refresh_accounts_box()
        self.refresh()

    def _refresh_accounts_box(self):
        names = [ALL_ACCOUNTS] + [a.name for a in self.mod.accounts()]
        selected = self.account_box.currentText()
        self.account_box.blockSignals(True)
        self.account_box.clear()
        self.account_box.addItems(names)
        self.account_box.setCurrentText(selected if selected in names else ALL_ACCOUNTS)
        self.account_box.blockSignals(False)

    def _selected_account_id(self):
        name = self.account_box.currentText()
        return None if name == ALL_ACCOUNTS else next((a.id for a in self.mod.accounts() if a.name == name), None)

    def step(self, n):
        y, m = self.month.year, self.month.month + n
        self.month = date(y + (m - 1) // 12, (m - 1) % 12 + 1, 1)
        self.refresh()

    def go_today(self):
        self.month = date.today().replace(day=1)
        self.refresh()

    def refresh(self, *_args):
        m = self.month
        self.title.setText(f"{m:%B %Y}")
        _fill(self.acc_table, [(a.name, fmt_money(self.mod.balance(a.id))) for a in self.mod.accounts()])
        summary = self.mod.month_summary(m.year, m.month)
        budget_rows = []
        for row in summary["categories"]:
            left = row["budget"] - row["spent"] if row["budget"] is not None else None
            budget_rows.append((row["name"], fmt_money(row["spent"]), fmt_money(left) if left is not None else "no budget"))
        _fill(self.bud_table, budget_rows)
        self.summary.setText(f"In {fmt_money(summary['income'])}   ·   Out {fmt_money(summary['spent'])}"
                             f"   ·   Net {fmt_money(summary['net'], signed=True)}")
        rows = []
        for t in self.mod.list_transactions(self._selected_account_id(), m.year, m.month):
            acc, cat = self.mod.account(t.account_id), self.mod.category(t.category_id)
            rows.append((f"{t.day:%b} {t.day.day}", t.payee, cat.name if cat else "—",
                         fmt_money(t.amount_cents, signed=True), acc.name if acc else ""))
        _fill(self.txn_table, rows)
        for r, t in enumerate(self.mod.list_transactions(self._selected_account_id(), m.year, m.month)):
            self.txn_table.item(r, 0).setData(Qt.ItemDataRole.UserRole, t.id)
            if t.amount_cents > 0:
                for c in range(self.txn_table.columnCount()):
                    self.txn_table.item(r, c).setForeground(QColor(T.SUCCESS))
        if not rows:
            self.empty.setText("Add an account to start. Manage → Accounts." if not self.mod.accounts()
                               else "No transactions this month. Press New transaction, or import a bank CSV.")
            self.empty.show()
        else:
            self.empty.hide()

    def theme_changed(self) -> None:
        self.refresh()

    def new_txn(self):
        if not self.mod.accounts():
            QMessageBox.information(self, "Add an account first", "Create an account under Manage → Accounts.")
            return
        TransactionDialog(self, self.mod, default_account=self._selected_account_id(), day=date.today())

    def new_transfer(self):
        if len(self.mod.accounts()) < 2:
            QMessageBox.information(self, "Transfers", "A transfer needs at least two accounts.")
            return
        TransferDialog(self, self.mod, default_from=self._selected_account_id())

    def edit_selected(self):
        txn_id = _selected_id(self.txn_table)
        if txn_id:
            t = self.mod.get_transaction(txn_id)
            if t and t.transfer_id:
                QMessageBox.information(self, "Transfer", "Transfers can't be edited. Delete it and enter it again.")
            elif t:
                TransactionDialog(self, self.mod, t)

    def delete_selected(self):
        ids = sorted({self.txn_table.item(r, 0).data(Qt.ItemDataRole.UserRole)
                      for r in {i.row() for i in self.txn_table.selectedIndexes()}})
        if ids and QMessageBox.question(self, "Delete", f"Delete {len(ids)} transaction(s)?") == QMessageBox.StandardButton.Yes:
            for txn_id in ids:
                self.mod.delete_transaction(txn_id)

    def import_csv(self): ImportDialog(self, self.mod)
    def open_bills(self): BillsWindow(self, self.mod)
    def open_accounts(self): AccountsWindow(self, self.mod)
    def open_categories(self): CategoriesWindow(self, self.mod)
    def open_rules(self): RulesWindow(self, self.mod)


class _FormDialog(QDialog):
    def __init__(self, parent, title):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setModal(True)
        self.root = QVBoxLayout(self)
        self.form = QFormLayout()
        self.root.addLayout(self.form)
        self.buttons = QDialogButtonBox()
        self.save_button = self.buttons.addButton("Save", QDialogButtonBox.ButtonRole.AcceptRole)
        self.buttons.addButton(QDialogButtonBox.StandardButton.Cancel)
        self.save_button.clicked.connect(self._save)
        self.buttons.rejected.connect(self.reject)
        self.root.addWidget(self.buttons)
        shortcut = QShortcut(QKeySequence("Ctrl+Return"), self)
        shortcut.activated.connect(self._save)

    def _present(self, parent):
        _show(self, parent)


class TransactionDialog(_FormDialog):
    def __init__(self, parent, mod, txn: Transaction | None = None, default_account: str | None = None,
                 day: date | None = None):
        self.mod, self.txn = mod, txn
        super().__init__(parent, "Edit transaction" if txn else "New transaction")
        accounts = mod.accounts()
        self.acc_ids = {a.name: a.id for a in accounts}
        self.cat_ids = {c.name: c.id for c in mod.categories()}
        self.cat_ids["(automatic)"] = None
        self.payee = QLineEdit(txn.payee if txn else "")
        self.day = QLineEdit(f"{(txn.day if txn else day or date.today()):%m/%d/%Y}")
        self.amount = QLineEdit(f"{abs(txn.amount_cents)/100:.2f}" if txn else "")
        self.direction = QComboBox(); self.direction.addItems(["Spent", "Received"])
        self.direction.setCurrentText("Received" if txn and txn.amount_cents > 0 else "Spent")
        self.account = QComboBox(); self.account.addItems(list(self.acc_ids))
        acc_id = txn.account_id if txn else default_account
        self.account.setCurrentText(next((n for n,i in self.acc_ids.items() if i==acc_id), next(iter(self.acc_ids),"")))
        self.category = QComboBox(); self.category.addItems(["(automatic)"] + [c.name for c in mod.categories()])
        self.category.setCurrentText(mod.category(txn.category_id).name if txn and mod.category(txn.category_id)
                                     else "(automatic)")
        self.memo = QLineEdit(txn.memo if txn else "")
        for label, field in (("Payee", self.payee), ("Date", self.day), ("Amount", self.amount),
                             ("Direction", self.direction), ("Account", self.account),
                             ("Category", self.category), ("Memo", self.memo)):
            self.form.addRow(label, field)
        self.delete_button = None
        if txn:
            self.delete_button = self.buttons.addButton("Delete", QDialogButtonBox.ButtonRole.DestructiveRole)
            self.delete_button.clicked.connect(self._delete)
        self._present(parent)

    def _save(self):
        try:
            payee = self.payee.text().strip()
            if not payee: raise ValueError("Enter a payee or description.")
            day = D.parse_date(self.day.text())
            cents = abs(parse_amount(self.amount.text()))
            if cents == 0: raise ValueError("The amount can't be zero.")
            if self.direction.currentText() == "Spent": cents = -cents
            acc_id = self.acc_ids.get(self.account.currentText())
            if not acc_id: raise ValueError("Choose an account.")
        except ValueError as exc:
            QMessageBox.critical(self, "Check the transaction", str(exc)); return
        cat_name = self.category.currentText()
        cat_id = self.cat_ids.get(cat_name)
        t = self.txn.copy() if self.txn else Transaction.new(acc_id, day, cents)
        t.account_id, t.day, t.amount_cents, t.payee = acc_id, day, cents, payee
        t.memo = self.memo.text().strip()
        if cat_name == "(automatic)":
            cat_id = None if self.txn is None or self.txn.payee != payee else self.txn.category_id
        t.category_id = cat_id
        self.mod.save_transaction(t); self.accept()

    def _delete(self):
        if QMessageBox.question(self, "Delete", "Delete this transaction?") == QMessageBox.StandardButton.Yes:
            self.mod.delete_transaction(self.txn.id); self.accept()


class TransferDialog(_FormDialog):
    def __init__(self,parent,mod,default_from=None):
        self.mod=mod;super().__init__(parent,"New transfer")
        accounts=mod.accounts();self.ids={a.name:a.id for a in accounts};names=list(self.ids)
        first=next((a.name for a in accounts if a.id==default_from),names[0])
        self.source=QComboBox();self.source.addItems(names);self.source.setCurrentText(first)
        self.target=QComboBox();self.target.addItems(names);self.target.setCurrentText(next((n for n in names if n!=first),first))
        self.amount=QLineEdit();self.day=QLineEdit(f"{date.today():%m/%d/%Y}");self.memo=QLineEdit()
        for label,field in (("From",self.source),("To",self.target),("Amount",self.amount),("Date",self.day),("Memo",self.memo)):
            self.form.addRow(label,field)
        self.form.addRow("",QLabel("Records both sides. Transfers don't count as spending."))
        self._present(parent)

    def _save(self):
        try:
            src,dst=self.ids.get(self.source.currentText()),self.ids.get(self.target.currentText())
            if not src or not dst:raise ValueError("Choose both accounts.")
            cents=abs(parse_amount(self.amount.text()));day=D.parse_date(self.day.text())
            self.mod.add_transfer(src,dst,cents,day,self.memo.text().strip())
        except ValueError as exc:
            QMessageBox.critical(self,"Check the transfer",str(exc));return
        self.accept()


class ImportDialog(QDialog):
    def __init__(self,parent,mod):
        super().__init__(parent);self.mod=mod;self.setWindowTitle("Import bank CSV");self.setModal(True)
        self.text=None;accounts=mod.accounts();self.acc_ids={a.name:a.id for a in accounts}
        root=QVBoxLayout(self);root.addWidget(QLabel("Download a statement as CSV. Previously imported rows are skipped, so overlapping ranges are safe."))
        self.account=QComboBox();self.account.addItems(list(self.acc_ids));root.addWidget(self.account)
        self.choose_button=QPushButton("Choose file…");self.choose_button.clicked.connect(self.choose);root.addWidget(self.choose_button)
        self.file_label=QLabel("No file chosen");root.addWidget(self.file_label)
        self.flip=QCheckBox("Purchases show as positive numbers (typical for credit cards)");root.addWidget(self.flip)
        self.result=QLabel();self.result.setWordWrap(True);root.addWidget(self.result)
        row=QHBoxLayout();root.addLayout(row)
        self.import_button=QPushButton("Import");self.import_button.setEnabled(False);self.import_button.clicked.connect(self.run)
        close=QPushButton("Close");close.clicked.connect(self.reject);row.addWidget(self.import_button);row.addWidget(close)
        _show(self,parent)

    def choose(self):
        path,_=QFileDialog.getOpenFileName(self,"Choose bank CSV","","CSV (*.csv);;All files (*)")
        if not path:return
        try:
            self.text=Path(path).read_text(encoding="utf-8-sig",errors="replace")
            rows,skipped=csvimport.parse_statement(self.text,flip=False)
        except (ValueError,OSError) as exc:
            self.text=None;self.import_button.setEnabled(False);self.result.setText(f"That file couldn't be read.\n{exc}");return
        self.file_label.setText(Path(path).name)
        preview=f"Found {len(rows)} transactions"+(f" ({len(skipped)} unreadable rows will be skipped)" if skipped else "")
        if rows:preview+=f"\nFrom {min(r.day for r in rows):%b %d, %Y} to {max(r.day for r in rows):%b %d, %Y}"
        self.result.setText(preview);self.import_button.setEnabled(True)

    def run(self):
        if self.text is None:return
        acc=self.acc_ids.get(self.account.currentText())
        if not acc:QMessageBox.critical(self,"Import","Create an account first.");return
        try:res=self.mod.import_csv(self.text,acc,flip=self.flip.isChecked())
        except ValueError as exc:QMessageBox.critical(self,"Import failed",str(exc));return
        self.result.setText(res.summary());self.import_button.setEnabled(False);self.text=None


class AccountDialog(_FormDialog):
    def __init__(self,parent,mod,acc=None):
        self.mod,self.acc=mod,acc;super().__init__(parent,"Edit account" if acc else "New account")
        self.name=QLineEdit(acc.name if acc else "")
        self.kind=QComboBox();self.kind.addItems(list(ACCOUNT_KINDS));self.kind.setCurrentText(acc.kind if acc else "Checking")
        self.opening=QLineEdit(f"{acc.opening_cents/100:.2f}" if acc else "0.00")
        for label,field in (("Name",self.name),("Type",self.kind),("Opening balance",self.opening)):self.form.addRow(label,field)
        self._present(parent)
    def _save(self):
        try:
            name=self.name.text().strip()
            if not name:raise ValueError("Give the account a name.")
            opening=parse_amount(self.opening.text() or "0")
        except ValueError as exc:QMessageBox.critical(self,"Check the account",str(exc));return
        a=Account(self.acc.id,name,self.kind.currentText(),opening,self.acc.archived) if self.acc else Account.new(name,self.kind.currentText(),opening)
        self.mod.save_account(a);self.accept()


class AccountsWindow(QDialog):
    def __init__(self,parent,mod):
        super().__init__(parent);self.mod=mod;self.setWindowTitle("Accounts");root=QVBoxLayout(self)
        self.table=_table(self,["Name","Type","Status"],[220,120,90],QTableWidget.SelectionMode.SingleSelection);root.addWidget(self.table)
        row=QHBoxLayout();root.addLayout(row)
        for text,fn in (("Add account",self.add),("Edit",self.edit),("Archive / restore",self.toggle_archive),("Delete",self.delete),("Close",self.accept)):
            b=QPushButton(text);b.clicked.connect(fn);row.addWidget(b)
        self.table.cellDoubleClicked.connect(lambda *_:self.edit());self.refresh();_show(self,parent)
    def refresh(self):
        items=self.mod.accounts(include_archived=True);_fill(self.table,[(a.name,a.kind,"archived" if a.archived else "active") for a in items])
        for r,a in enumerate(items):self.table.item(r,0).setData(Qt.ItemDataRole.UserRole,a.id)
    def _sel(self):return self.mod.account(_selected_id(self.table)) if _selected_id(self.table) else None
    def add(self):AccountDialog(self,self.mod)
    def edit(self):
        a=self._sel()
        if a:AccountDialog(self,self.mod,a)
    def toggle_archive(self):
        a=self._sel()
        if a:self.mod.save_account(Account(a.id,a.name,a.kind,a.opening_cents,not a.archived));self.refresh()
    def delete(self):
        a=self._sel()
        if a:
            if not self.mod.delete_account(a.id):QMessageBox.information(self,"Can't delete",f"“{a.name}” has transactions. Archive it instead.")
            self.refresh()


class CategoryDialog(_FormDialog):
    def __init__(self,parent,mod,cat=None):
        self.mod,self.cat=mod,cat;super().__init__(parent,"Edit category" if cat else "New category")
        self.name=QLineEdit(cat.name if cat else "")
        self.budget=QLineEdit(f"{cat.budget_cents/100:.2f}" if cat and cat.budget_cents else "")
        self.form.addRow("Name",self.name);self.form.addRow("Monthly budget",self.budget);self.form.addRow("",QLabel("leave blank for no budget"))
        self._present(parent)
    def _save(self):
        try:
            name=self.name.text().strip()
            if not name:raise ValueError("Give the category a name.")
            budget=parse_amount(self.budget.text()) if self.budget.text().strip() else None
            if budget is not None and budget<0:raise ValueError("A budget can't be negative.")
        except ValueError as exc:QMessageBox.critical(self,"Check the category",str(exc));return
        cat=Category(self.cat.id,name,budget) if self.cat else Category.new(name,budget)
        self.mod.save_category(cat);self.accept()


class CategoriesWindow(QDialog):
    def __init__(self,parent,mod):
        super().__init__(parent);self.mod=mod;self.setWindowTitle("Categories and budgets");root=QVBoxLayout(self)
        self.table=_table(self,["Category","Monthly budget"],[240,140],QTableWidget.SelectionMode.SingleSelection);root.addWidget(self.table)
        root.addLayout(_buttons(self,[("Add",self.add),("Edit",self.edit),("Delete",self.delete),("Close",self.accept)]))
        self.table.cellDoubleClicked.connect(lambda *_:self.edit())
        self._sub=("money.*",self._refresh);mod.api.on(*self._sub);self.finished.connect(lambda:mod.api.off(*self._sub))
        self.refresh();_show(self,parent)
    def refresh(self):
        cats=self.mod.categories();_fill(self.table,[(c.name,fmt_money(c.budget_cents) if c.budget_cents is not None else "—") for c in cats])
        for r,c in enumerate(cats):self.table.item(r,0).setData(Qt.ItemDataRole.UserRole,c.id)
    def _refresh(self,*_a,**_k):self.refresh()
    def _sel(self):return self.mod.category(_selected_id(self.table)) if _selected_id(self.table) else None
    def add(self):CategoryDialog(self,self.mod)
    def edit(self):
        c=self._sel()
        if c:CategoryDialog(self,self.mod,c)
    def delete(self):
        c=self._sel()
        if c and c.id not in (INCOME,TRANSFER) and QMessageBox.question(self,"Delete category",f"Delete “{c.name}”? Its transactions become uncategorised.")==QMessageBox.StandardButton.Yes:self.mod.delete_category(c.id)


class RulesWindow(QDialog):
    def __init__(self,parent,mod):
        super().__init__(parent);self.mod=mod;self.setWindowTitle("Auto-categorise rules");root=QVBoxLayout(self)
        root.addWidget(QLabel("If a payee contains the words, the transaction gets that category."))
        self.table=_table(self,["Payee contains","Category"],[240,180],QTableWidget.SelectionMode.SingleSelection);root.addWidget(self.table)
        add=QHBoxLayout();root.addLayout(add);self.keyword=QLineEdit();self.keyword.setPlaceholderText("Words to match");add.addWidget(self.keyword)
        self.category=QComboBox();add.addWidget(self.category);b=QPushButton("Add rule");b.clicked.connect(self.add);add.addWidget(b)
        root.addLayout(_buttons(self,[("Delete selected",self.delete),("Close",self.accept)]))
        self._sub=("money.*",self._refresh);mod.api.on(*self._sub);self.finished.connect(lambda:mod.api.off(*self._sub))
        self.refresh();_show(self,parent)
    def refresh(self):
        rules=self.mod.rules();_fill(self.table,[(r.keyword,self.mod.category(r.category_id).name if self.mod.category(r.category_id) else "—") for r in rules])
        for row,r in enumerate(rules):self.table.item(row,0).setData(Qt.ItemDataRole.UserRole,r.id)
        current=self.category.currentText();self.category.clear();self.category.addItems([c.name for c in self.mod.categories()])
        if current:self.category.setCurrentText(current)
    def _refresh(self,*_a,**_k):self.refresh()
    def add(self):
        cat=next((c for c in self.mod.categories() if c.name==self.category.currentText()),None);kw=self.keyword.text().strip()
        if not kw or not cat:QMessageBox.critical(self,"Add rule","Enter the words to match and choose a category.");return
        self.mod.add_rule(kw,cat.id);self.keyword.clear()
    def delete(self):
        rule_id=_selected_id(self.table)
        if rule_id:self.mod.delete_rule(rule_id)


class BillDialog(_FormDialog):
    def __init__(self,parent,mod,bill:Bill|None=None):
        self.mod,self.bill=mod,bill;super().__init__(parent,"Edit bill" if bill else "New bill")
        self.acc_ids={a.name:a.id for a in mod.accounts()};self.acc_ids["(none)"]=None
        self.cat_ids={c.name:c.id for c in mod.categories() if c.id not in (INCOME,TRANSFER)};self.cat_ids["(none)"]=None
        b=bill;self.name=QLineEdit(b.name if b else "");self.amount=QLineEdit(f"{b.amount_cents/100:.2f}" if b else "")
        self.due=QLineEdit(f"{b.due:%m/%d/%Y}" if b else f"{date.today():%m/%d/%Y}")
        self.repeat=QComboBox();self.loaded_repeat=REPEAT_NONE
        if b and b.rrule:
            parsed=parse_rrule(b.rrule);self.loaded_repeat=CUSTOM if parsed.custom else CHOICE_OF_FREQ.get(parsed.freq,REPEAT_NONE)
        self.repeat.addItems(REPEAT_CHOICES+([CUSTOM] if self.loaded_repeat==CUSTOM else []));self.repeat.setCurrentText(self.loaded_repeat)
        self.reminders=QLineEdit(", ".join(str(x) for x in b.reminder_days) if b else "3, 0")
        self.account=QComboBox();self.account.addItems(list(self.acc_ids))
        self.account.setCurrentText(next((n for n,i in self.acc_ids.items() if b and i==b.account_id),"(none)"))
        self.category=QComboBox();self.category.addItems(list(self.cat_ids))
        self.category.setCurrentText(next((n for n,i in self.cat_ids.items() if b and i==b.category_id),"(none)"))
        for label,field in (("Bill",self.name),("Amount",self.amount),("Due date",self.due),("Repeat",self.repeat),
                            ("Remind (days before)",self.reminders),("Pay from",self.account),("Category",self.category)):
            self.form.addRow(label,field)
        self._present(parent)
    def _save(self):
        try:
            name=self.name.text().strip()
            if not name:raise ValueError("Give the bill a name.")
            amount=abs(parse_amount(self.amount.text()));due=D.parse_date(self.due.text())
            days=sorted({int(x) for x in self.reminders.text().replace(";",",").split(",") if x.strip()})
            if any(x<0 for x in days):raise ValueError("Reminder days can't be negative.")
            rep=self.repeat.currentText();rrule=None
            if rep!=REPEAT_NONE:
                if rep==CUSTOM or (rep==self.loaded_repeat and self.bill and self.bill.rrule):rrule=self.bill.rrule
                else:rrule=build_rrule(FREQ[rep])
        except ValueError as exc:QMessageBox.critical(self,"Check the bill",str(exc));return
        changed=self.bill is None or due!=self.bill.due or rrule!=(self.bill.rrule if self.bill else None)
        b=self.bill.copy() if self.bill else Bill.new(name,amount,due)
        b.name,b.amount_cents,b.due,b.rrule=name,amount,due,rrule
        b.series_start=due if rrule and changed else b.series_start;b.reminder_days=days
        b.account_id,b.category_id=self.acc_ids[self.account.currentText()],self.cat_ids[self.category.currentText()]
        self.mod.save_bill(b);self.accept()


class BillsWindow(QDialog):
    def __init__(self,parent,mod):
        super().__init__(parent);self.mod=mod;self.setWindowTitle("Bills");root=QVBoxLayout(self)
        root.addWidget(QLabel("Marking a bill paid records it as a transaction and moves a repeating bill to its next due date."))
        self.table=_table(self,["Bill","Due","Amount","Status"],[220,130,110,110],QTableWidget.SelectionMode.SingleSelection);root.addWidget(self.table)
        row=QHBoxLayout();root.addLayout(row)
        for text,fn in (("New bill",self.add),("Edit",self.edit),("Mark paid",self.pay),("Delete",self.delete),("Close",self.accept)):
            b=QPushButton(text);b.clicked.connect(fn);row.addWidget(b)
        self.table.cellDoubleClicked.connect(lambda *_:self.edit())
        self._sub=("money.*",self._refresh);mod.api.on(*self._sub);self.finished.connect(lambda:mod.api.off(*self._sub))
        self.refresh();_show(self,parent)
    def refresh(self):
        today=date.today();bills=self.mod.bills(include_done=False);rows=[]
        for b in bills:
            status="overdue" if b.due<today else ("due today" if b.due==today else "upcoming")
            rows.append((b.name+("  ↻" if b.rrule else ""),f"{b.due:%a %b} {b.due.day}, {b.due.year}",fmt_money(b.amount_cents),status))
        _fill(self.table,rows)
        for row,b in enumerate(bills):self.table.item(row,0).setData(Qt.ItemDataRole.UserRole,b.id)
    def _refresh(self,*_a,**_k):self.refresh()
    def _sel(self):return self.mod.bill(_selected_id(self.table)) if _selected_id(self.table) else None
    def add(self):BillDialog(self,self.mod)
    def edit(self):
        b=self._sel()
        if b:BillDialog(self,self.mod,b)
    def pay(self):
        b=self._sel()
        if b and QMessageBox.question(self,"Mark paid",f"Record {b.name} ({fmt_money(b.amount_cents)}) as paid today?")==QMessageBox.StandardButton.Yes:self.mod.mark_paid(b.id)
    def delete(self):
        b=self._sel()
        if b and QMessageBox.question(self,"Delete bill",f"Delete “{b.name}”?")==QMessageBox.StandardButton.Yes:self.mod.delete_bill(b.id)
