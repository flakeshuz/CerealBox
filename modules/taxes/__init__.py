"""Taxes module scaffold"""
from datetime import date as Date

from ...core.ids import new_id
from ..base import Module


class TaxesModule(Module):
    name = "taxes"
    title = "Taxes"

    def setup(self):
        self.categories = self.col("categories")
        self.records = self.col("records")

    def services(self):
        return {
            "list_categories": self.list_categories,
            "add_category": self.add_category,
            "update_category": self.update_category,
            "delete_category": self.delete_category,
            "new_record": self.new_record,
            "list_records": self.list_records,
            # Milestone 2 enhancements
            "list_deadlines": self.list_deadlines,
            "add_deadline": self.add_deadline,
            "deductible_by_year": self.deductible_by_year,
            "export_tax_summary": self.export_tax_summary,
        }

    def list_categories(self):
        return self.categories.all()

    def add_category(self, name: str, rate: float) -> dict:
        cid = new_id("cat")
        rec = {"id": cid, "name": name, "rate": rate}
        self.categories.put(cid, rec)
        return rec

    def update_category(self, cid: str, **fields) -> dict:
        cur = self.categories.get(cid)
        if cur is None:
            raise ValueError(f"Unknown tax category: {cid}")
        cur.update(fields)
        cur["id"] = cid
        self.categories.put(cid, cur)
        return cur

    def delete_category(self, cid: str) -> bool:
        return self.categories.delete(cid)

    def new_record(self, date: str, category_id: str | None, amount: float, notes: str = "") -> dict:
        Date.fromisoformat(date)
        rid = new_id("rec")
        rec = {"id": rid, "date": date, "category_id": category_id, "amount": amount, "notes": notes}
        self.records.put(rid, rec)
        return rec

    def list_records(self, year: int | None = None, month: int | None = None):
        out = []
        for r in self.records.all():
            try:
                day = Date.fromisoformat(r["date"])
            except (KeyError, TypeError, ValueError):
                continue
            if year is not None and day.year != year:
                continue
            if month is not None and day.month != month:
                continue
            out.append(r)
        return out

    # Milestone 2: deadlines and deductible support
    def list_deadlines(self, year: int | None = None, month: int | None = None):
        out = []
        for d in (self.col("deadlines").all() or []):
            try:
                day = Date.fromisoformat(d["date"])
            except (ValueError, TypeError, KeyError):
                continue
            if year is not None and day.year != year:
                continue
            if month is not None and day.month != month:
                continue
            out.append(d)
        return out

    def add_deadline(self, date: str, label: str) -> dict:
        did = new_id("dl")
        rec = {"id": did, "date": date, "label": label}
        self.col("deadlines").put(did, rec)
        return rec

    def deductible_by_year(self, year: int) -> dict:
        total = {}
        for r in self.list_records(year=year):
            cat = r.get("category_id")
            amt = r.get("amount", 0)
            total[cat] = total.get(cat, 0) + amt
        return total

    def export_tax_summary(self, year: int | None = None) -> dict:
        return {
            "year": year,
            "categories": self.list_categories(),
            "deductions": self.deductible_by_year(year) if year else {},
            "records": self.list_records(year),
        }
