"""Qt views for the UI-independent CerealBox modules."""

from __future__ import annotations

from importlib import import_module
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from PyQt6.QtWidgets import QWidget
    from ....modules.base import Module


_VIEW_TYPES = {
    "calendar": ("calendar", "CalendarView"),
    "contacts": ("contacts", "ContactsView"),
    "dashboard": ("dashboard", "DashboardView"),
    "docsvault": ("docsvault", "DocsVaultView"),
    "email": ("email", "EmailView"),
    "goals": ("goals", "GoalsView"),
    "habits": ("habits", "HabitsView"),
    "health": ("health", "HealthView"),
    "home": ("home", "HomeView"),
    "money": ("money", "MoneyView"),
    "notes": ("notes", "NotesView"),
    "passwords": ("passwords", "PasswordsView"),
    "search": ("search", "SearchView"),
    "tasks": ("tasks", "TasksView"),
    "taxes": ("taxes", "TaxesView"),
}


def create_view(module: Module, parent: QWidget) -> QWidget:
    try:
        module_name, view_name = _VIEW_TYPES[module.name]
    except KeyError:
        raise LookupError(f"The Qt frontend has no view for module {module.name!r}.") from None
    views = import_module(f"{__name__}.{module_name}")
    view_type = getattr(views, view_name)
    return view_type(parent, module)


def supported_modules() -> frozenset[str]:
    return frozenset(_VIEW_TYPES)
