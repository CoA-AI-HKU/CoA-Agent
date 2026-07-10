from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REGISTRY_PATH = PROJECT_ROOT / "data" / "private" / "user_registry.json"


def normalize_sender_id(sender_id: str | None) -> str:
    normalized = str(sender_id or "").strip()
    if normalized.startswith("+"):
        normalized = normalized[1:]
    suffix = "@s.whatsapp.net"
    if normalized.lower().endswith(suffix):
        normalized = normalized[: -len(suffix)]
    return normalized.strip()


def _registry_path() -> Path:
    return Path(os.getenv("USER_REGISTRY_PATH") or DEFAULT_REGISTRY_PATH)


def load_user_registry() -> dict[str, Any]:
    path = _registry_path()
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def get_user_record(sender_id: str) -> dict[str, Any]:
    return get_sender_record(sender_id)


def get_sender_record(sender_id: str) -> dict[str, Any]:
    registry = load_user_registry()
    users = registry.get("users", {})
    if not isinstance(users, dict):
        return {}
    record = users.get(normalize_sender_id(sender_id), {})
    return record if isinstance(record, dict) else {}


def iter_sender_records() -> list[tuple[str, dict[str, Any]]]:
    registry = load_user_registry()
    users = registry.get("users", {})
    if not isinstance(users, dict):
        return []
    records: list[tuple[str, dict[str, Any]]] = []
    for sender_id, record in users.items():
        if isinstance(record, dict):
            records.append((normalize_sender_id(sender_id), record))
    return records


def get_user_role(sender_id: str) -> str:
    role = str(get_user_record(sender_id).get("role") or "unknown").strip().lower()
    return role if role in {"caregiver", "user"} else "unknown"


def get_linked_user_id(sender_id: str) -> str | None:
    linked_user_ids = get_linked_user_ids(sender_id)
    return linked_user_ids[0] if linked_user_ids else None


def get_linked_user_ids(sender_id: str) -> list[str]:
    record = get_user_record(sender_id)
    linked = record.get("linked_user_ids")
    if linked is None:
        linked = record.get("linked_user_id")
    if linked is None:
        return []
    values = linked if isinstance(linked, list) else [linked]
    linked_ids: list[str] = []
    for value in values:
        linked_id = str(value or "").strip()
        if linked_id and linked_id not in linked_ids:
            linked_ids.append(linked_id)
    return linked_ids


def get_display_name(sender_id: str) -> str | None:
    display_name = get_user_record(sender_id).get("display_name")
    return str(display_name).strip() if display_name else None


def get_registry_user_id(sender_id: str) -> str | None:
    user_id = get_user_record(sender_id).get("user_id")
    return str(user_id).strip() if user_id else None


def get_user_record_by_user_id(user_id: str | None) -> tuple[str | None, dict[str, Any]]:
    target_user_id = str(user_id or "").strip()
    if not target_user_id:
        return None, {}
    for sender_id, record in iter_sender_records():
        if str(record.get("role") or "").strip().lower() != "user":
            continue
        if str(record.get("user_id") or "").strip() == target_user_id:
            return sender_id, record
    return None, {}


def get_caregiver_records_for_user(user_id: str | None) -> list[tuple[str, dict[str, Any]]]:
    target_user_id = str(user_id or "").strip()
    if not target_user_id:
        return []
    caregivers: list[tuple[str, dict[str, Any]]] = []
    for sender_id, record in iter_sender_records():
        if str(record.get("role") or "").strip().lower() != "caregiver":
            continue
        if target_user_id in get_linked_user_ids(sender_id):
            caregivers.append((sender_id, record))
    return caregivers
