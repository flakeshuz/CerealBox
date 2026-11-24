# Goals module scaffold
from ..base import Module


class GoalsModule(Module):
    name = "goals"
    title = "Goals"

    def setup(self):
        self.goals = self.col("goals")

    def services(self):
        return {
            "list_goals": self.list_goals,
            "add_goal": self.add_goal,
            "weekly_review": self.weekly_review,
        }

    def list_goals(self):
        return self.goals.all() or []

    def add_goal(self, title: str, target: str) -> dict:
        gid = f"goal_{title.lower().replace(' ', '_')}"
        rec = {"id": gid, "title": title, "target": target}
        self.goals.put(gid, rec)
        return rec

    def weekly_review(self):
        goals = self.list_goals() or []
        return {"count": len(goals), "goals": goals}
