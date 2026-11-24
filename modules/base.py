"""The contract every life-area module follows."""
from __future__ import annotations

from collections.abc import Callable
from typing import Any

from ..core.api import Collection, LifeAPI


class Module:
    name: str = ""  # short, unique, lowercase - also the namespace for storage and services
    title: str = ""  # shown on the tab
    show_in_navigation: bool = False

    api: LifeAPI

    def attach(self, api: LifeAPI) -> None:
        self.api = api

    def col(self, name: str) -> Collection:
        """This module's own namespaced collection, e.g. col('events') -> 'calendar.events'."""
        return self.api.collection(f"{self.name}.{name}")

    def setup(self) -> None:
        """Load data, subscribe to events. Called once after attach()."""

    def services(self) -> dict[str, Callable[..., Any]]:
        """Callables other modules may use, exposed as '<module name>.<key>'."""
        return {}
