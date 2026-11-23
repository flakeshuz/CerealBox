# Habits module scaffold
from ..base import Module


class HabitsModule(Module):
    name = "habits"
    title = "Habits"

    def setup(self):
        self.habits = self.col("habits")
        self.checkins = self.col("habits.checkins")

    def services(self):
        return {
            "list_habits": self.list_habits,
            "add_habit": self.add_habit,
            "check_in": self.check_in,
            "list_checkins": self.list_checkins,
        }

    def create_view(self, parent):
        from .ui import HabitsView
        return HabitsView(parent, self)

    def list_habits(self):
        return self.habits.all() or []

    def add_habit(self, title: str, streak: int = 0) -> dict:
        hid = f"habit_{title.lower().replace(' ', '_')}"
        rec = {"id": hid, "title": title, "streak": streak}
        self.habits.put(hid, rec)
        return rec

    def check_in(self, habit_id: str, at: str | None = None) -> dict:
        import datetime as _dt
        from datetime import date as Date
        date_str = at if at is not None else _dt.date.today().isoformat()
        cid = f"chk_{habit_id}_{date_str}"
        rec = {"id": cid, "habit_id": habit_id, "date": date_str}
        self.checkins.put(cid, rec)
        return rec

    def list_checkins(self, habit_id: str | None = None):
        items = self.checkins.all() or []
        if habit_id is not None:
            items = [c for c in items if c.get("habit_id") == habit_id]
        return items
