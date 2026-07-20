from __future__ import annotations

import os
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any

from src.user.user_registry import load_user_registry, save_user_registry


SCREENING_VERSION = "cognitive_concern_screening_v1"
DEFAULT_PUBLIC_URL = "https://ako-saka.github.io/CoA-Agent/screening/"


def create_screening_token(
    user_id: str,
    created_by: str,
    caregiver_id: str | None = None,
    lifetime_minutes: int | None = None,
) -> dict[str, Any]:
    creator = created_by if created_by in {"self", "caregiver", "system"} else "system"
    minutes = lifetime_minutes if lifetime_minutes is not None else (24 * 60 if creator == "caregiver" else 30)
    now = datetime.now(timezone.utc)
    token = secrets.token_urlsafe(24)
    entry = {
        "token": token,
        "user_id": str(user_id),
        "created_by": creator,
        "caregiver_id": str(caregiver_id or ""),
        "created_at": now.isoformat(),
        "expires_at": (now + timedelta(minutes=minutes)).isoformat(),
        "used": False,
        "purpose": "screening",
        "screening_version": SCREENING_VERSION,
    }
    registry = load_user_registry()
    registry.setdefault("screening_tokens", {})[token] = entry
    save_user_registry(registry)
    return entry


def get_screening_token(token: str, *, allow_used: bool = False) -> dict[str, Any] | None:
    entry = load_user_registry().get("screening_tokens", {}).get(str(token or "").strip())
    if not isinstance(entry, dict) or entry.get("purpose") != "screening":
        return None
    try:
        expires_at = datetime.fromisoformat(str(entry.get("expires_at") or "").replace("Z", "+00:00"))
    except ValueError:
        return None
    if expires_at.astimezone(timezone.utc) <= datetime.now(timezone.utc):
        return None
    if entry.get("used") and not allow_used:
        return None
    return dict(entry)


def mark_screening_token_used(token: str) -> dict[str, Any] | None:
    registry = load_user_registry()
    tokens = registry.get("screening_tokens", {})
    entry = get_screening_token(token)
    if entry is None or not isinstance(tokens, dict):
        return None
    entry["used"] = True
    tokens[token] = entry
    save_user_registry(registry)
    return entry


def screening_url(token: str) -> str:
    base = os.getenv("SCREENING_PUBLIC_URL", DEFAULT_PUBLIC_URL)
    separator = "&" if "?" in base else "?"
    return f"{base}{separator}token={token}"
