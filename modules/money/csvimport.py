"""Read bank CSV exports. Finds the header row and the date/description/amount columns by name,
handles a single Amount column or separate Debit/Credit columns, and builds dedupe keys so that
importing the same statement twice adds nothing new.
"""
from __future__ import annotations

import csv
import hashlib
import io
import re
from dataclasses import dataclass, field
from datetime import date

from ...core import dates as D
from .models import parse_amount

ALIASES = {
    "date": ("date", "posted date", "transaction date", "posting date", "trans date", "trans. date",
             "value date", "booking date", "post date", "date posted"),
    "payee": ("description", "original description", "transaction description", "payee", "payee name",
              "merchant", "merchant name", "name", "details", "narrative", "memo"),
    "amount": ("amount", "transaction amount", "amt"),
    "debit": ("debit", "debit amount", "withdrawal", "withdrawals", "money out", "paid out"),
    "credit": ("credit", "credit amount", "deposit", "deposits", "money in", "paid in"),
    "type": ("transaction type", "type", "dr/cr"),
}


def normalize_header(h: str) -> str:
    """'Withdrawal (-)' -> 'withdrawal', 'Amount (USD)' -> 'amount', '  Posting   Date ' -> 'posting date'."""
    return " ".join(re.sub(r"\s*\([^)]*\)", "", h).split()).lower()


@dataclass
class Row:
    day: date
    amount_cents: int
    payee: str


@dataclass
class ImportResult:
    added: int = 0
    duplicates: int = 0
    skipped: list[str] = field(default_factory=list)  # reasons for rows that couldn't be read
    categorised: int = 0

    def summary(self) -> str:
        text = f"{self.added} added, {self.duplicates} already imported"
        if self.categorised:
            text += f", {self.categorised} categorised automatically"
        if self.skipped:
            text += f"\n{len(self.skipped)} rows skipped, e.g. {self.skipped[0]}"
        return text


def read_table(text: str) -> tuple[list[str], list[list[str]]]:
    sample = text[:4096]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t")
    except csv.Error:
        dialect = csv.excel
    rows = [r for r in csv.reader(io.StringIO(text), dialect) if any(c.strip() for c in r)]
    for i, r in enumerate(rows[:25]):  # banks often put a title or balance block above the table
        names = [normalize_header(c) for c in r]
        if any(n in ALIASES["date"] for n in names):
            return names, rows[i + 1:]
    raise ValueError("I couldn't find a header row with a date column. Expect headings like "
                     "Date, Description and Amount.")


def find_columns(header: list[str]) -> dict[str, int | None]:
    def find(key: str) -> int | None:
        for alias in ALIASES[key]:
            if alias in header:
                return header.index(alias)
        return None

    cols = {k: find(k) for k in ALIASES}
    if cols["date"] is None:
        raise ValueError("I couldn't find a date column.")
    if cols["amount"] is None and cols["debit"] is None and cols["credit"] is None:
        raise ValueError("I couldn't find an amount column (Amount, or Debit and Credit).")
    return cols


def parse_row(r: list[str], cols: dict[str, int | None], flip: bool) -> Row:
    def cell(key: str) -> str:
        i = cols[key]
        return r[i].strip() if i is not None and i < len(r) else ""

    day = D.parse_date(cell("date"))
    if cell("amount"):
        cents = parse_amount(cell("amount"))
    elif cell("debit") or cell("credit"):
        out = abs(parse_amount(cell("debit"))) if cell("debit") else 0
        into = abs(parse_amount(cell("credit"))) if cell("credit") else 0
        cents = into - out
    else:
        raise ValueError("no amount")
    kind = cell("type").lower()
    if kind and cents:  # some exports always show amounts as positive and say "debit" or "credit" separately
        if "debit" in kind or kind == "dr":
            cents = -abs(cents)
        elif "credit" in kind or kind == "cr":
            cents = abs(cents)
    if flip:  # some card statements show purchases as positive numbers
        cents = -cents
    return Row(day, cents, cell("payee") or "Unknown")


def dedupe_base(account_id: str, row: Row) -> str:
    raw = f"{account_id}|{row.day.isoformat()}|{row.amount_cents}|{row.payee.lower()}"
    return hashlib.sha256(raw.encode()).hexdigest()[:20]


def parse_statement(text: str, flip: bool) -> tuple[list[Row], list[str]]:
    """-> (readable rows, reasons for skipped rows)."""
    header, body = read_table(text)
    cols = find_columns(header)
    rows, skipped = [], []
    for n, r in enumerate(body, start=1):
        try:
            rows.append(parse_row(r, cols, flip))
        except ValueError as exc:
            skipped.append(f"row {n}: {exc}")
    return rows, skipped
