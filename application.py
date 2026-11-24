"""Application composition, independent of any presentation frontend."""
from __future__ import annotations

from .core import LifeAPI, Vault
from .modules import default_modules


def create_workspace(vault: Vault) -> LifeAPI:
    """Create the shared service API and register all built-in business modules."""
    api = LifeAPI(vault)
    for module in default_modules():
        api.register(module)
    return api
