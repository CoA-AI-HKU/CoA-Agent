from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from src.user.user_memory import build_user_memory
from src.user.user_registry import (
    get_linked_user_ids,
    get_registry_user_id,
    get_user_record,
    get_user_role,
    normalize_sender_id,
)


@dataclass(frozen=True)
class UserContext:
    sender_id: str
    user_id: str
    role: str
    profile: dict[str, Any]
    preferred_language: str | None
    linked_user_ids: tuple[str, ...]
    history: dict[str, Any]


class UserContextService:
    """Loads the account and retained context needed before each turn."""

    def load(self, sender_id: str) -> UserContext:
        sender_id = normalize_sender_id(sender_id)
        profile = get_user_record(sender_id)
        return UserContext(
            sender_id=sender_id,
            user_id=get_registry_user_id(sender_id) or sender_id,
            role=get_user_role(sender_id),
            profile=profile,
            preferred_language=str(profile.get("preferred_language") or "").strip() or None,
            linked_user_ids=tuple(get_linked_user_ids(sender_id)),
            history=build_user_memory(sender_id),
        )
