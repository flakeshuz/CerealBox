"""Sortable, collision-resistant IDs: <prefix>_<48-bit ms timestamp><40 random bits>."""
import secrets
import time


def new_id(prefix: str = "") -> str:
    raw = f"{int(time.time() * 1000):012x}{secrets.token_hex(5)}"
    return f"{prefix}_{raw}" if prefix else raw
