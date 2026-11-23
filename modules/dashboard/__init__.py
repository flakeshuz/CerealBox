# Minimal Dashboard module scaffold with test-friendly surface
from __future__ import annotations

# Public surface expected by tests
CATALOG = {
    "quick": ("Quick",),
    "tasks": ("Tasks",),
    "week": ("Week",),
    "today": ("Today",),
    "budget": ("Budget",),
    "links": ("Links",),
    "bills": ("Bills",),
}

DEFAULT_LAYOUT = [
    {"key": "quick", "span": 1, "shown": True},
    {"key": "tasks", "span": 1, "shown": True},
    {"key": "week", "span": 1, "shown": False},
    {"key": "today", "span": 1, "shown": True},
    {"key": "budget", "span": 1, "shown": False},
    {"key": "links", "span": 1, "shown": False},
    {"key": "bills", "span": 1, "shown": False},
]

from ..base import Module


class DashboardModule(Module):
    name = "dashboard"
    title = "Dashboard"

    def setup(self):
        self._layout = self._read_layout()

    def services(self):
        return {}

    def create_view(self, parent):
        from .ui import DashboardView
        return DashboardView(parent, self)

    def _read_layout(self) -> list[dict[str, object]]:
        try:
            items = list(self.col("layout").all()) or []
            if not items:
                return list(DEFAULT_LAYOUT)
            lay = items[0].get("layout") if isinstance(items[0], dict) else None
            if isinstance(lay, list):
                return normalise_layout(lay)
            return list(DEFAULT_LAYOUT)
        except (ValueError, TypeError):
            return list(DEFAULT_LAYOUT)

    def _write_layout(self, lay: list[dict[str, object]]):
        self.col("layout").put("layout", {"id": "layout", "layout": lay})

    def layout(self) -> list[dict[str, object]]:
        self._layout = self._read_layout()
        return list(self._layout)

    def save_layout(self, lay: list[dict[str, object]]):
        self._layout = lay
        self._write_layout(lay)

    def reset_layout(self):
        self._layout = list(DEFAULT_LAYOUT)
        self._write_layout(self._layout)


def default_layout() -> list[dict[str, object]]:
    return list(DEFAULT_LAYOUT)


def normalise_layout(stored: list[dict[str, object]] | None) -> list[dict[str, object]]:
    base_keys = list(CATALOG.keys())
    if not stored:
        return default_layout()
    seen = set()
    ordered = []
    for d in stored:
        if isinstance(d, dict) and "key" in d:
            k = d["key"]
            if k in base_keys and k not in seen:
                ordered.append(d)
                seen.add(k)
    out: list[dict[str, object]] = []
    for d in ordered:
        item = d.copy()
        if "span" not in item:
            item["span"] = 1
        if "shown" not in item:
            item["shown"] = False
        out.append(item)
    for k in base_keys:
        if k not in seen:
            out.append({"key": k, "span": 1, "shown": False})
    return out


def move(layout: list[dict[str, object]], key: str, delta: int) -> list[dict[str, object]]:
    shown_keys = [d["key"] for d in layout if d.get("shown")]
    if key not in shown_keys:
        return layout
    idx = shown_keys.index(key)
    new_idx = max(0, min(len(shown_keys) - 1, idx + delta))
    if new_idx == idx:
        return layout
    shown_keys.pop(idx)
    shown_keys.insert(new_idx, key)
    order = []
    for k in shown_keys:
        found = next((d for d in layout if d.get("key") == k), None)
        if not found:
            found = {"key": k, "span": 1, "shown": True}
        order.append(dict(found))
    hidden = [d for d in layout if not d.get("shown")]
    return order + hidden


def set_shown(layout: list[dict[str, object]], key: str, shown: bool) -> list[dict[str, object]]:
    new = []
    for d in layout:
        if d.get("key") == key:
            nd = dict(d)
            nd["shown"] = shown
            new.append(nd)
        else:
            new.append(dict(d))
    return new


def set_span(layout: list[dict[str, object]], key: str, span: int) -> list[dict[str, object]]:
    if span not in (1, 2):
        span = 1
    new = []
    for d in layout:
        if d.get("key") == key:
            nd = dict(d)
            nd["span"] = span
            new.append(nd)
        else:
            new.append(dict(d))
    return new
