"""Modules registry"""
from __future__ import annotations

from .base import Module


def default_modules() -> list[Module]:
    from .calendar import CalendarModule
    from .contacts import ContactsModule
    from .dashboard import DashboardModule
    from .docsvault import DocsVaultModule
    from .email import EmailModule
    from .goals import GoalsModule
    from .habits import HabitsModule
    from .health import HealthModule
    from .home import HomeModule
    from .money import MoneyModule
    from .notes import NotesModule
    from .passwords import PasswordsModule
    from .search import SearchModule
    from .tasks import TasksModule
    from .taxes import TaxesModule

    return [DashboardModule(), CalendarModule(), TasksModule(), MoneyModule(), TaxesModule(), DocsVaultModule(), NotesModule(), ContactsModule(), HabitsModule(), HealthModule(), HomeModule(), PasswordsModule(), GoalsModule(), SearchModule(), EmailModule()]

__all__ = ["Module", "default_modules"]
