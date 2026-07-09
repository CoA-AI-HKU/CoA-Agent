from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


REGISTRY_PATH = Path("~/.nanobot/data/private/user_registry.json").expanduser()


def normalize_sender_id(sender_id: str | None) -> str:
    normalized = str(sender_id or "").strip()
    if normalized.startswith("+"):
        normalized = normalized[1:]
    suffix = "@s.whatsapp.net"
    if normalized.lower().endswith(suffix):
        normalized = normalized[: -len(suffix)]
    return normalized.strip()


def _registry_path() -> Path:
    return Path(os.getenv("USER_REGISTRY_PATH") or REGISTRY_PATH).expanduser()


def load_user_registry() -> dict[str, Any]:
    path = _registry_path()
    if not path.exists():
        return {"users": {}}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"users": {}}
    if not isinstance(data, dict):
        return {"users": {}}
    users = data.get("users")
    if not isinstance(users, dict):
        data["users"] = {}
    return data


def get_user_record(sender_id: str | None) -> dict[str, Any]:
    normalized_sender_id = normalize_sender_id(sender_id)
    if not normalized_sender_id:
        return {}
    users = load_user_registry().get("users", {})
    if not isinstance(users, dict):
        return {}
    record = users.get(normalized_sender_id, {})
    return record if isinstance(record, dict) else {}


def get_user_role(sender_id: str | None) -> str:
    role = str(get_user_record(sender_id).get("role") or "unknown").strip().lower()
    return role if role in {"caregiver", "user", "admin"} else "unknown"


def get_linked_user_id(sender_id: str | None) -> str | None:
    linked_user_ids = get_linked_user_ids(sender_id)
    if linked_user_ids:
        return linked_user_ids[0]
    normalized_sender_id = normalize_sender_id(sender_id)
    return normalized_sender_id or None


def get_linked_user_ids(sender_id: str | None) -> list[str]:
    record = get_user_record(sender_id)
    linked = record.get("linked_user_ids")
    if linked is None:
        linked = record.get("linked_user_id")
    if linked is None:
        linked = record.get("user_id")
    if linked is None:
        return []
    values = linked if isinstance(linked, list) else [linked]
    linked_ids: list[str] = []
    for value in values:
        linked_id = str(value or "").strip()
        if linked_id and linked_id not in linked_ids:
            linked_ids.append(linked_id)
    return linked_ids


def get_display_name(sender_id: str | None) -> str:
    display_name = str(get_user_record(sender_id).get("display_name") or "").strip()
    return display_name


def get_registry_user_id(sender_id: str | None) -> str | None:
    user_id = str(get_user_record(sender_id).get("user_id") or "").strip()
    return user_id or None


def get_caregiver_records_for_user(user_id: str | None) -> list[tuple[str, dict[str, Any]]]:
    target_user_id = str(user_id or "").strip()
    if not target_user_id:
        return []
    users = load_user_registry().get("users", {})
    if not isinstance(users, dict):
        return []
    caregivers: list[tuple[str, dict[str, Any]]] = []
    for sender_id, record in users.items():
        if not isinstance(record, dict):
            continue
        if str(record.get("role") or "").strip().lower() != "caregiver":
            continue
        normalized_sender_id = normalize_sender_id(sender_id)
        if target_user_id in get_linked_user_ids(normalized_sender_id):
            caregivers.append((normalized_sender_id, record))
    return caregivers
