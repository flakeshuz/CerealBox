# Home module scaffold
from ..base import Module


class HomeModule(Module):
    name = "home"
    title = "Home"

    def setup(self):
        self.maint = self.col("home.maintenance")

    def services(self):
        return {"list_maintenance": self.list_maintenance, "add_maintenance": self.add_maintenance}

    def list_maintenance(self):
        return self.maint.all() or []

    def add_maintenance(self, title: str, due: str) -> dict:
        it = {"id": f"maint_{title}", "title": title, "due": due}
        self.maint.put(it["id"], it)
        return it
