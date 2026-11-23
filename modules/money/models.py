"""Money data models. Amounts are integer cents, so totals never drift from float rounding.

Sign convention: money in is positive, money out is negative.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field, replace
from datetime import date, datetime
from decimal import Decimal

from ...core import dates as D
from ...core.ids import new_id

TRANSFER = "cat_transfer"  # transfers between your own accounts: excluded from spending totals
INCOME = "cat_income"
DEFAULT_CATEGORIES = [  # (id, name, monthly budget in cents or None)
    (INCOME, "Income", None),
    (TRANSFER, "Transfer", None),
    ("cat_housing", "Housing", 185000),
    ("cat_groceries", "Groceries", 60000),
    ("cat_dining", "Dining out", 20000),
    ("cat_utilities", "Utilities", 25000),
    ("cat_transport", "Transport", 15000),
    ("cat_health", "Health", 10000),
    ("cat_shopping", "Shopping", 20000),
    ("cat_fun", "Entertainment", 10000),
    ("cat_other", "Other", None),
]
ACCOUNT_KINDS = ("Checking", "Savings", "Credit card", "Cash", "Other")


# ---- amounts ----------------------------------------------------------------------------
def parse_amount(text: str) -> int:
    """'$1,234.50' -> 123450, '(12.00)' -> -1200, '-3' -> -300, '+4.5' -> 450."""
    s = text.strip().replace("\u2212", "-").replace("$", "").replace(",", "").replace(" ", "")
    if not s:
        raise ValueError("Enter an amount.")
    neg = False
    if s.startswith("(") and s.endswith(")"):
        neg, s = True, s[1:-1]
    if s.startswith("-"):
        neg, s = (not neg), s[1:]
    elif s.startswith("+"):
        s = s[1:]
    if not re.fullmatch(r"(\d+(\.\d{0,2})?|\.\d{1,2})", s):
        raise ValueError(f"I can't read the amount '{text}'. Use a form like 12.50 or -12.50.")
    cents = int((Decimal(s) * 100).to_integral_value())
    return -cents if neg else cents


def fmt_money(cents: int, signed: bool = False) -> str:
    sign = "-" if cents < 0 else ("+" if signed and cents > 0 else "")
    whole, frac = divmod(abs(int(cents)), 100)
    return f"{sign}${whole:,}.{frac:02d}"


def parse_day(text: str) -> date:
    return D.parse_date(text)


# ---- records ----------------------------------------------------------------------------
def _d(v: str | None) -> date | None:
    return date.fromisoformat(v) if v else None


@dataclass
class Account:
    id: str
    name: str
    kind: str = "Checking"
    opening_cents: int = 0
    archived: bool = False

    @classmethod
    def new(cls, name: str, kind: str = "Checking", opening_cents: int = 0) -> Account:
        return cls(new_id("acc"), name, kind, opening_cents)

    def to_dict(self) -> dict:
        return {"id": self.id, "name": self.name, "kind": self.kind, "opening_cents": self.opening_cents,
                "archived": self.archived}

    @classmethod
    def from_dict(cls, d: dict) -> Account:
        return cls(d["id"], d["name"], d.get("kind", "Other"), int(d.get("opening_cents", 0)), bool(d.get("archived")))


@dataclass
class Category:
    id: str
    name: str
    budget_cents: int | None = None  # monthly budget; None = no budget

    @classmethod
    def new(cls, name: str, budget_cents: int | None = None) -> Category:
        return cls(new_id("cat"), name, budget_cents)

    def to_dict(self) -> dict:
        return {"id": self.id, "name": self.name, "budget_cents": self.budget_cents}

    @classmethod
    def from_dict(cls, d: dict) -> Category:
        b = d.get("budget_cents")
        return cls(d["id"], d["name"], int(b) if b is not None else None)


@dataclass
class Transaction:
    id: str
    account_id: str
    day: date
    amount_cents: int
    payee: str = ""
    category_id: str | None = None
    memo: str = ""
    import_key: str | None = None  # dedupe key for imported rows: "<hash>#<n>"
    created: datetime | None = None
    transfer_id: str | None = None  # both legs of a transfer share this id

    @classmethod
    def new(cls, account_id: str, day: date, amount_cents: int, payee: str = "", **kw) -> Transaction:
        return cls(new_id("txn"), account_id, day, amount_cents, payee, **kw)

    def copy(self) -> Transaction:
        return replace(self)

    def to_dict(self) -> dict:
        return {"id": self.id, "account_id": self.account_id, "day": self.day.isoformat(),
                "amount_cents": self.amount_cents, "payee": self.payee, "category_id": self.category_id,
                "memo": self.memo, "import_key": self.import_key,
                "created": D.to_iso(self.created) if self.created else None, "transfer_id": self.transfer_id}

    @classmethod
    def from_dict(cls, d: dict) -> Transaction:
        return cls(d["id"], d["account_id"], date.fromisoformat(d["day"]), int(d["amount_cents"]),
                   d.get("payee", ""), d.get("category_id"), d.get("memo", ""), d.get("import_key"),
                   D.from_iso(d["created"]) if d.get("created") else None, d.get("transfer_id"))


@dataclass
class Bill:
    id: str
    name: str
    amount_cents: int  # positive: what you pay
    due: date
    rrule: str | None = None  # repeat; `due` is the current occurrence
    series_start: date | None = None
    reminder_days: list[int] = field(default_factory=list)  # remind this many days before, at 9 AM
    account_id: str | None = None
    category_id: str | None = None
    done: bool = False  # one-off bills are done once paid
    last_paid: date | None = None

    @classmethod
    def new(cls, name: str, amount_cents: int, due: date, **kw) -> Bill:
        return cls(new_id("bill"), name, amount_cents, due, **kw)

    def copy(self) -> Bill:
        return replace(self, reminder_days=list(self.reminder_days))

    def to_dict(self) -> dict:
        iso = lambda v: v.isoformat() if v else None
        return {"id": self.id, "name": self.name, "amount_cents": self.amount_cents, "due": iso(self.due),
                "rrule": self.rrule, "series_start": iso(self.series_start),
                "reminder_days": list(self.reminder_days), "account_id": self.account_id,
                "category_id": self.category_id, "done": self.done, "last_paid": iso(self.last_paid)}

    @classmethod
    def from_dict(cls, d: dict) -> Bill:
        return cls(d["id"], d["name"], int(d["amount_cents"]), _d(d["due"]), d.get("rrule") or None,
                   _d(d.get("series_start")), [int(x) for x in d.get("reminder_days", [])],
                   d.get("account_id"), d.get("category_id"), bool(d.get("done")), _d(d.get("last_paid")))


@dataclass
class Rule:
    """Auto-categorise: if a payee contains `keyword` (case-insensitive), use `category_id`."""
    id: str
    keyword: str
    category_id: str

    @classmethod
    def new(cls, keyword: str, category_id: str) -> Rule:
        return cls(new_id("rule"), keyword.strip().lower(), category_id)

    def to_dict(self) -> dict:
        return {"id": self.id, "keyword": self.keyword, "category_id": self.category_id}

    @classmethod
    def from_dict(cls, d: dict) -> Rule:
        return cls(d["id"], d["keyword"], d["category_id"])
