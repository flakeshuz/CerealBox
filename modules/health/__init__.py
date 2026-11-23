# Health module scaffold
from ..base import Module


class HealthModule(Module):
    name = "health"
    title = "Health"

    def setup(self):
        self.appointments = self.col("health.appointments")
        self.medications = self.col("health.medications")
        self.docs = self.col("health.docs")

    def services(self):
        return {
            "list_appointments": self.list_appointments,
            "add_appointment": self.add_appointment,
            "list_medications": self.list_medications,
            "add_medication": self.add_medication,
            "list_docs": self.list_docs,
            "link_document": self.link_document,
        }

    def create_view(self, parent):
        from .ui import HealthView
        return HealthView(parent, self)

    def list_appointments(self):
        return self.appointments.all() or []

    def add_appointment(self, title: str, date: str) -> dict:
        a = {"id": f"appt_{title}", "title": title, "date": date}
        self.appointments.put(a["id"], a)
        return a

    def list_medications(self):
        return self.medications.all() or []

    def add_medication(self, name: str, dose: str):
        med = {"id": f"med_{name}", "name": name, "dose": dose}
        self.medications.put(med["id"], med)
        return med

    def list_docs(self):
        return self.docs.all() or []

    def link_document(self, health_id: str, doc_id: str) -> dict:
        rec = {"health_id": health_id, "doc_id": doc_id}
        self.docs.put(doc_id, rec)
        return rec
