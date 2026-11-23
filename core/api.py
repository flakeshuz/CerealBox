"""The common API: the one object every module talks to.

* Storage    - modules get namespaced Collections ("calendar.events"), never the raw vault.
* Services   - modules expose named callables ("calendar.add_event") that other modules
               (or the UI) can call without importing each other's internals.
* Events     - modules publish/subscribe to topics ("calendar.event.saved").
* Settings   - small key/value store, encrypted along with everything else.
* Import/export of the whole vault as plain JSON.
"""
from __future__ import annotations

import json
import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from .storage import Vault

if TYPE_CHECKING:
    from ..modules.base import Module

log = logging.getLogger("lifeos")


@dataclass(frozen=True)
class Reminder:
    """Anything any module wants to nag the user about. The shell polls for these."""

    source: str  # module name
    title: str
    at: datetime  # when the reminder fires
    due: datetime  # when the thing itself happens
    detail: str = ""
    # (label, service name, args) buttons the popup can offer, e.g. ("Mark paid", "money.mark_paid", (bill_id,))
    actions: tuple = ()


class Collection:
    """A namespaced view of one vault collection."""

    def __init__(self, vault: Vault, name: str):
        self._vault, self.name = vault, name

    def get(self, key: str) -> dict | None:
        return self._vault.get(self.name, key)

    def put(self, key: str, record: dict) -> None:
        self._vault.put(self.name, key, record)

    def delete(self, key: str) -> bool:
        return self._vault.delete(self.name, key)

    def all(self) -> list[dict]:
        return self._vault.all(self.name)


class LifeAPI:
    def __init__(self, vault: Vault):
        self.vault = vault
        self.modules: dict[str, Module] = {}
        self._services: dict[str, Callable[..., Any]] = {}
        self._handlers: list[tuple[str, Callable[..., None]]] = []

    # ---- modules ---------------------------------------------------------------------
    def register(self, module: Module) -> Module:
        if not module.name or module.name in self.modules:
            raise ValueError(f"Bad or duplicate module name: {module.name!r}")
        module.attach(self)
        self.modules[module.name] = module
        module.setup()
        for svc, fn in module.services().items():
            self.expose(f"{module.name}.{svc}", fn)
        return module

    # ---- storage ---------------------------------------------------------------------
    def collection(self, name: str) -> Collection:
        return Collection(self.vault, name)

    # ---- services --------------------------------------------------------------------
    def expose(self, name: str, fn: Callable[..., Any]) -> None:
        self._services[name] = fn

    def has_service(self, name: str) -> bool:
        return name in self._services

    def call(self, name: str, *args: Any, **kwargs: Any) -> Any:
        try:
            fn = self._services[name]
        except KeyError:
            raise LookupError(f"No service called '{name}'.") from None
        return fn(*args, **kwargs)

    def call_all(self, suffix: str, *args: Any, **kwargs: Any) -> list[Any]:
        """Call '<any module>.<suffix>' on every module that has it; concatenate the lists."""
        out: list[Any] = []
        for name, fn in list(self._services.items()):
            if name.endswith("." + suffix):
                try:
                    out.extend(fn(*args, **kwargs) or [])
                except Exception:
                    log.exception("Service %s failed", name)
        return out

    # ---- events ----------------------------------------------------------------------
    def on(self, pattern: str, handler: Callable[..., None]) -> None:
        """pattern is an exact topic or a prefix ending in '*' (e.g. 'calendar.*')."""
        self._handlers.append((pattern, handler))

    def off(self, pattern: str, handler: Callable[..., None]) -> None:
        """Remove a subscription. Views call this when they are closed so they stop receiving events."""
        self._handlers = [(p, h) for p, h in self._handlers if not (p == pattern and h is handler)]

    def emit(self, topic: str, **payload: Any) -> None:
        for pattern, fn in list(self._handlers):
            if pattern == topic or (pattern.endswith("*") and topic.startswith(pattern[:-1])):
                try:
                    fn(topic=topic, **payload)
                except Exception:
                    log.exception("Handler for %s failed", topic)

    # ---- settings ----------------------------------------------------------------------
    def setting(self, key: str, default: Any = None) -> Any:
        rec = self.collection("core.settings").get(key)
        return rec["value"] if rec else default

    def set_setting(self, key: str, value: Any) -> None:
        self.collection("core.settings").put(key, {"value": value})

    # ---- whole-vault import/export (plain JSON; the file is NOT encrypted) ---------------
    def export_json(self, path: str | Path) -> None:
        Path(path).write_text(json.dumps(self.vault.export_data(), indent=2, ensure_ascii=False), encoding="utf-8")

    def import_json(self, path: str | Path, replace: bool = False) -> None:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        self.vault.import_data(payload, replace=replace)
        self.emit("vault.reloaded")
