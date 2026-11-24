"""Money module: accounts, transactions, monthly budgets, auto-categorising rules, bills and CSV import.

Services for other modules:
    api.call("money.add_transaction", account_id, -1250, "Coffee", date(2026, 11, 18), category_id="cat_dining")
    api.call("money.month_summary", 2026, 11)
"""
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date, datetime, time, timedelta

from ...core import dates as D
from ...core.api import Reminder
from ...core.ids import new_id
from ...core.rrule import compile_rule
from ..base import Module
from . import csvimport
from .models import (
    DEFAULT_CATEGORIES,
    INCOME,
    TRANSFER,
    Account,
    Bill,
    Category,
    Rule,
    Transaction,
    fmt_money,
)

BILL_HOUR = time(9, 0)  # bills remind at 9 AM on the reminder days


class MoneyModule(Module):
    name = "money"
    title = "Money"
    show_in_navigation = True

    # ---- lifecycle -------------------------------------------------------------------------
    def setup(self) -> None:
        self._acc = self.col("accounts")
        self._txn = self.col("transactions")
        self._cat = self.col("categories")
        self._bill = self.col("bills")
        self._rule = self.col("rules")
        if not self._cat.all():
            with self.api.vault.batch():
                for cid, name, budget in DEFAULT_CATEGORIES:
                    self._cat.put(cid, Category(cid, name, budget).to_dict())
        self._load()
        self.api.on("vault.reloaded", lambda **_: self._load())

    def _load(self) -> None:
        self._accounts = {d["id"]: Account.from_dict(d) for d in self._acc.all()}
        self._txns = {d["id"]: Transaction.from_dict(d) for d in self._txn.all()}
        self._cats = {d["id"]: Category.from_dict(d) for d in self._cat.all()}
        self._bills = {d["id"]: Bill.from_dict(d) for d in self._bill.all()}
        self._rules = [Rule.from_dict(d) for d in self._rule.all()]

    def services(self):
        return {
            "add_transaction": self.add_transaction,
            "balance": self.balance,
            "month_summary": self.month_summary,
            "reminders_due": self.due_reminders,
            "mark_paid": self.mark_paid,
            "accounts": self.account_summaries,
            "bills_due": self.bills_due,
            "add_transfer": self.add_transfer,
        }

    # ---- accounts ----------------------------------------------------------------------------
    def accounts(self, include_archived: bool = False) -> list[Account]:
        return sorted((a for a in self._accounts.values() if include_archived or not a.archived),
                      key=lambda a: a.name.lower())

    def account(self, account_id: str) -> Account | None:
        return self._accounts.get(account_id)

    def save_account(self, a: Account) -> None:
        self._acc.put(a.id, a.to_dict())
        self._accounts[a.id] = a
        self.api.emit("money.changed", what="accounts")

    def delete_account(self, account_id: str) -> bool:
        """Only accounts with no transactions can be deleted; otherwise archive them."""
        if any(t.account_id == account_id for t in self._txns.values()):
            return False
        self._acc.delete(account_id)
        self._accounts.pop(account_id, None)
        self.api.emit("money.changed", what="accounts")
        return True

    def balance(self, account_id: str) -> int:
        a = self._accounts.get(account_id)
        if not a:
            return 0
        return a.opening_cents + sum(t.amount_cents for t in self._txns.values() if t.account_id == account_id)

    # ---- categories and budgets --------------------------------------------------------------------
    def categories(self) -> list[Category]:
        return sorted(self._cats.values(), key=lambda c: (c.id not in (INCOME, TRANSFER), c.name.lower()))

    def category(self, cat_id: str | None) -> Category | None:
        return self._cats.get(cat_id) if cat_id else None

    def save_category(self, c: Category) -> None:
        self._cat.put(c.id, c.to_dict())
        self._cats[c.id] = c
        self.api.emit("money.changed", what="categories")

    def delete_category(self, cat_id: str) -> None:
        if cat_id in (INCOME, TRANSFER):
            return
        with self.api.vault.batch():
            for t in list(self._txns.values()):
                if t.category_id == cat_id:
                    t.category_id = None
                    self._put_txn(t)
            for r in self._rules:
                if r.category_id == cat_id:
                    self._rule.delete(r.id)
            self._rules = [r for r in self._rules if r.category_id != cat_id]
            self._cat.delete(cat_id)
        self._cats.pop(cat_id, None)
        self.api.emit("money.changed", what="categories")

    def month_summary(self, year: int, month: int) -> dict:
        """Income, spending and per-category totals for one month. Transfers are left out."""
        income, spent = 0, 0
        by_cat: dict[str | None, int] = defaultdict(int)
        for t in self._txns.values():
            if t.day.year != year or t.day.month != month or t.category_id == TRANSFER:
                continue
            if t.amount_cents > 0:
                income += t.amount_cents
            else:
                spent += -t.amount_cents
                by_cat[t.category_id] += -t.amount_cents
        rows = []
        for cat in self.categories():
            if cat.id in (INCOME, TRANSFER):
                continue
            s = by_cat.get(cat.id, 0)
            if s or cat.budget_cents:
                rows.append({"id": cat.id, "name": cat.name, "spent": s, "budget": cat.budget_cents})
        rows.sort(key=lambda r: -r["spent"])
        uncategorised = by_cat.get(None, 0)
        if uncategorised:
            rows.append({"id": None, "name": "Uncategorised", "spent": uncategorised, "budget": None})
        return {"year": year, "month": month, "income": income, "spent": spent, "net": income - spent,
                "categories": rows}

    # ---- transactions --------------------------------------------------------------------------------
    def _put_txn(self, t: Transaction) -> None:
        t.created = t.created or D.now()
        self._txn.put(t.id, t.to_dict())
        self._txns[t.id] = t.copy()

    def get_transaction(self, txn_id: str) -> Transaction | None:
        t = self._txns.get(txn_id)
        return t.copy() if t else None

    def list_transactions(self, account_id: str | None = None, year: int | None = None,
                          month: int | None = None, search: str = "") -> list[Transaction]:
        q = search.strip().lower()
        out = []
        for t in self._txns.values():
            if account_id and t.account_id != account_id:
                continue
            if year and (t.day.year != year or t.day.month != month):
                continue
            if q and q not in t.payee.lower() and q not in t.memo.lower():
                continue
            out.append(t.copy())
        return sorted(out, key=lambda t: (t.day, t.created or D.now()), reverse=True)

    def categorize(self, payee: str) -> str | None:
        p = payee.lower()
        for r in self._rules:
            if r.keyword and r.keyword in p:
                return r.category_id
        return None

    def save_transaction(self, t: Transaction) -> Transaction:
        if t.id in self._txns and self._txns[t.id].transfer_id:
            raise ValueError("Transfers can't be edited. Delete the transfer and enter it again.")
        if t.category_id is None:
            t.category_id = self.categorize(t.payee)
        self._put_txn(t)
        self.api.emit("money.changed", what="transactions")
        return t

    def add_transaction(self, account_id: str, amount_cents: int, payee: str, day: date,
                        category_id: str | None = None, memo: str = "") -> str:
        t = Transaction.new(account_id, day, int(amount_cents), payee, category_id=category_id, memo=memo)
        return self.save_transaction(t).id

    def add_transfer(self, from_id: str, to_id: str, cents: int, day: date, memo: str = "") -> str:
        """Record money moving between two of your accounts as two linked entries that don't count as spending."""
        src, dst = self.account(from_id), self.account(to_id)
        if not src or not dst or from_id == to_id:
            raise ValueError("Choose two different accounts.")
        if cents <= 0:
            raise ValueError("A transfer amount must be more than zero.")
        link = new_id("xfr")
        out_leg = Transaction.new(from_id, day, -int(cents), f"Transfer to {dst.name}",
                                  category_id=TRANSFER, memo=memo, transfer_id=link)
        in_leg = Transaction.new(to_id, day, int(cents), f"Transfer from {src.name}",
                                 category_id=TRANSFER, memo=memo, transfer_id=link)
        with self.api.vault.batch():
            self._put_txn(out_leg)
            self._put_txn(in_leg)
        self.api.emit("money.changed", what="transactions")
        return link

    def delete_transaction(self, txn_id: str) -> None:
        """Deleting one side of a transfer deletes both sides."""
        ids = {txn_id}
        t = self._txns.get(txn_id)
        if t and t.transfer_id:
            ids |= {x.id for x in self._txns.values() if x.transfer_id == t.transfer_id}
        with self.api.vault.batch():
            for i in ids:
                self._txn.delete(i)
                self._txns.pop(i, None)
        self.api.emit("money.changed", what="transactions")

    # ---- rules ----------------------------------------------------------------------------------------
    def rules(self) -> list[Rule]:
        return list(self._rules)

    def add_rule(self, keyword: str, category_id: str) -> None:
        r = Rule.new(keyword, category_id)
        if not r.keyword:
            return
        self._rule.put(r.id, r.to_dict())
        self._rules.append(r)
        self.api.emit("money.changed", what="rules")

    def delete_rule(self, rule_id: str) -> None:
        self._rule.delete(rule_id)
        self._rules = [r for r in self._rules if r.id != rule_id]
        self.api.emit("money.changed", what="rules")

    # ---- bills --------------------------------------------------------------------------------------
    def bills(self, include_done: bool = False) -> list[Bill]:
        out = [b.copy() for b in self._bills.values() if include_done or not b.done]
        return sorted(out, key=lambda b: (b.done, b.due))

    def account_summaries(self) -> list[dict]:
        return [{"id": a.id, "name": a.name, "kind": a.kind, "balance": self.balance(a.id)} for a in self.accounts()]

    def bills_due(self, days: int = 14, today: date | None = None) -> list[Bill]:
        """Unpaid bills due within `days` (overdue ones included), soonest first."""
        today = today or date.today()
        horizon = today + timedelta(days=days)
        return [b for b in self.bills() if b.due <= horizon]

    def bill(self, bill_id: str) -> Bill | None:
        b = self._bills.get(bill_id)
        return b.copy() if b else None

    def save_bill(self, b: Bill) -> None:
        if b.rrule and not b.series_start:
            b.series_start = b.due
        self._bill.put(b.id, b.to_dict())
        self._bills[b.id] = b.copy()
        self.api.emit("money.changed", what="bills")

    def delete_bill(self, bill_id: str) -> None:
        self._bill.delete(bill_id)
        self._bills.pop(bill_id, None)
        self.api.emit("money.changed", what="bills")

    def mark_paid(self, bill_id: str, day: date | None = None) -> None:
        """Record a payment as a transaction, then move a repeating bill to its next due date."""
        b = self._bills[bill_id].copy()
        day = day or D.now().date()
        account_id = b.account_id or self._default_account_id()
        if not account_id:
            raise ValueError("Create an account before recording bill payments.")
        with self.api.vault.batch():
            self.save_transaction(Transaction.new(account_id, day,
                                                  -b.amount_cents, b.name, category_id=b.category_id,
                                                  memo="Bill payment"))
            b.last_paid = day
            if b.rrule:
                nxt = self._next_bill_due(b, max(b.due, day))
                if nxt:
                    b.due = nxt
                else:
                    b.done = True
            else:
                b.done = True
            self.save_bill(b)

    def _next_bill_due(self, b: Bill, after: date) -> date | None:
        rule = compile_rule(b.rrule, datetime.combine(b.series_start or b.due, BILL_HOUR))
        nxt = rule.after(datetime.combine(after, BILL_HOUR), inc=False)
        return nxt.date() if nxt else None

    def _default_account_id(self) -> str | None:
        active = self.accounts()
        return active[0].id if active else None

    def due_reminders(self, since: datetime, until: datetime) -> list[Reminder]:
        out = []
        for b in self._bills.values():
            if b.done:
                continue
            due_at = datetime.combine(b.due, BILL_HOUR)
            for m in b.reminder_days:
                at = due_at - timedelta(days=m)
                if since < at <= until:
                    out.append(Reminder("money", f"{b.name}: {fmt_money(b.amount_cents)}", at, due_at,
                                        f"due {b.due:%a %b} {b.due.day}",
                                        actions=(("Mark paid", "money.mark_paid", (b.id,)),)))
        return sorted(out, key=lambda r: r.at)

    # ---- import -------------------------------------------------------------------------------------
    def import_csv(self, text: str, account_id: str, flip: bool = False) -> csvimport.ImportResult:
        rows, skipped = csvimport.parse_statement(text, flip)
        res = csvimport.ImportResult(skipped=skipped)
        existing = Counter(t.import_key.split("#")[0] for t in self._txns.values()
                           if t.account_id == account_id and t.import_key)
        seen: Counter = Counter()
        with self.api.vault.batch():
            for row in rows:
                base = csvimport.dedupe_base(account_id, row)
                seen[base] += 1
                if seen[base] <= existing[base]:
                    res.duplicates += 1
                    continue
                cat = self.categorize(row.payee)
                res.categorised += bool(cat)
                t = Transaction.new(account_id, row.day, row.amount_cents, row.payee, category_id=cat,
                                    import_key=f"{base}#{seen[base]}")
                self._put_txn(t)
                res.added += 1
        self.api.emit("money.changed", what="transactions")
        return res
