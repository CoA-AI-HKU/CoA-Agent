from __future__ import annotations

from typing import Any

from src.user_registry import (
    get_caregiver_records_for_user,
    get_linked_user_ids,
    get_user_record,
    get_user_record_by_user_id,
    get_user_role,
    normalize_sender_id,
)


def build_user_memory(sender_id: str) -> dict[str, Any]:
    """Build privacy-preserving role memory from the registry.

    This intentionally stores no raw conversation text. It only exposes the
    structured identity and care-link data needed for routing.
    """
    normalized_sender_id = normalize_sender_id(sender_id)
    role = get_user_role(normalized_sender_id)
    record = get_user_record(normalized_sender_id)

    if role == "caregiver":
        return _caregiver_memory(normalized_sender_id, record)
    if role == "user":
        return _patient_user_memory(normalized_sender_id, record)
    return {
        "sender_id": normalized_sender_id,
        "role": "unknown",
        "user_id": None,
        "linked_user_id": None,
        "linked_user_ids": [],
        "display_name": None,
        "caregivers": [],
        "linked_users": [],
        "privacy": {"stores_raw_conversations": False},
    }


def build_memory_for_user_id(user_id: str | None) -> dict[str, Any]:
    sender_id, record = get_user_record_by_user_id(user_id)
    if sender_id and record:
        return _patient_user_memory(sender_id, record)
    clean_user_id = str(user_id or "").strip() or None
    return {
        "sender_id": None,
        "role": "user",
        "user_id": clean_user_id,
        "linked_user_id": None,
        "linked_user_ids": [],
        "display_name": None,
        "caregivers": _caregiver_summaries(clean_user_id),
        "linked_users": [],
        "privacy": {"stores_raw_conversations": False},
    }


def get_primary_linked_user_id(sender_id: str) -> str | None:
    linked_user_ids = get_linked_user_ids(sender_id)
    return linked_user_ids[0] if linked_user_ids else None


def _caregiver_memory(sender_id: str, record: dict[str, Any]) -> dict[str, Any]:
    linked_user_ids = get_linked_user_ids(sender_id)
    linked_users = [_linked_user_summary(user_id) for user_id in linked_user_ids]
    return {
        "sender_id": sender_id,
        "role": "caregiver",
        "user_id": None,
        "linked_user_id": linked_user_ids[0] if linked_user_ids else None,
        "linked_user_ids": linked_user_ids,
        "display_name": _clean(record.get("display_name")),
        "relationship": _clean(record.get("relationship")),
        "caregivers": [],
        "linked_users": linked_users,
        "privacy": {"stores_raw_conversations": False},
    }


def _patient_user_memory(sender_id: str, record: dict[str, Any]) -> dict[str, Any]:
    user_id = _clean(record.get("user_id")) or sender_id
    return {
        "sender_id": sender_id,
        "role": "user",
        "user_id": user_id,
        "linked_user_id": None,
        "linked_user_ids": [],
        "display_name": _clean(record.get("display_name")),
        "caregivers": _caregiver_summaries(user_id),
        "linked_users": [],
        "privacy": {"stores_raw_conversations": False},
    }


def _linked_user_summary(user_id: str) -> dict[str, Any]:
    user_sender_id, user_record = get_user_record_by_user_id(user_id)
    return {
        "user_id": user_id,
        "sender_id": user_sender_id,
        "display_name": _clean(user_record.get("display_name")),
    }


def _caregiver_summaries(user_id: str | None) -> list[dict[str, Any]]:
    caregivers: list[dict[str, Any]] = []
    for caregiver_sender_id, caregiver_record in get_caregiver_records_for_user(user_id):
        caregivers.append(
            {
                "sender_id": caregiver_sender_id,
                "display_name": _clean(caregiver_record.get("display_name")),
                "relationship": _clean(caregiver_record.get("relationship")),
            }
        )
    return caregivers


def _clean(value: Any) -> str | None:
    text = str(value or "").strip()
    return text or None
