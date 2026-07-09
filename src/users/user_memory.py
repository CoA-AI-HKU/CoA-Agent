from __future__ import annotations

from typing import Any


def build_memory_for_user_id(user_id: str | None) -> dict[str, Any]:
    """Return an empty, non-persistent memory shape for a resolved user ID."""
    return _empty_memory(user_id)


def build_user_memory(user_id: str | None = None) -> dict[str, Any]:
    """Return an empty, non-persistent memory shape for a sender/user ID."""
    return _empty_memory(user_id)


def _empty_memory(user_id: str | None) -> dict[str, Any]:
    return {
        "user_id": user_id,
        "profile": {},
        "routines": [],
        "reminders": [],
        "preferences": [],
        "notes": [],
    }
