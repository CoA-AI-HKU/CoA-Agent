from __future__ import annotations

import json
from pathlib import Path

from src.users.message_router import handle_incoming_message
from src.users.user_memory import build_memory_for_user_id, build_user_memory
from src.users.user_registry import get_caregiver_records_for_user, get_linked_user_id, get_linked_user_ids


def _write_registry(path: Path) -> None:
    path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "users": {
                    "17736844460": {
                        "role": "caregiver",
                        "linked_user_id": "patient_001",
                        "linked_user_ids": ["patient_001"],
                        "display_name": "Ling",
                        "relationship": "daughter",
                    },
                    "85244924928": {
                        "role": "user",
                        "user_id": "patient_001",
                        "display_name": "Chan Tai",
                    },
                },
                "memory_policy": {
                    "stores_raw_conversations": False,
                    "purpose": "test routing only",
                },
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


def test_registry_resolves_caregiver_to_linked_user(tmp_path, monkeypatch) -> None:
    registry_path = tmp_path / "user_registry.json"
    _write_registry(registry_path)
    monkeypatch.setenv("USER_REGISTRY_PATH", str(registry_path))

    assert get_linked_user_id("+17736844460") == "patient_001"
    assert get_linked_user_ids("17736844460@s.whatsapp.net") == ["patient_001"]
    caregivers = get_caregiver_records_for_user("patient_001")
    assert caregivers[0][0] == "17736844460"


def test_user_memory_contains_bidirectional_link_without_raw_text(tmp_path, monkeypatch) -> None:
    registry_path = tmp_path / "user_registry.json"
    _write_registry(registry_path)
    monkeypatch.setenv("USER_REGISTRY_PATH", str(registry_path))

    caregiver_memory = build_user_memory("17736844460")
    patient_memory = build_memory_for_user_id("patient_001")

    assert caregiver_memory["role"] == "caregiver"
    assert caregiver_memory["linked_user_id"] == "patient_001"
    assert caregiver_memory["linked_users"][0]["sender_id"] == "85244924928"
    assert patient_memory["role"] == "user"
    assert patient_memory["caregivers"][0]["sender_id"] == "17736844460"
    assert caregiver_memory["privacy"]["stores_raw_conversations"] is False
    assert "raw_text" not in str(caregiver_memory)


def test_router_attaches_memory_for_caregiver_message(tmp_path, monkeypatch) -> None:
    registry_path = tmp_path / "user_registry.json"
    events_path = tmp_path / "events.jsonl"
    _write_registry(registry_path)
    monkeypatch.setenv("USER_REGISTRY_PATH", str(registry_path))
    monkeypatch.setenv("EVENTS_LOG_PATH", str(events_path))

    result = handle_incoming_message("/summary", "17736844460", "whatsapp")

    assert result["role"] == "caregiver"
    assert result["linked_user_id"] == "patient_001"
    assert result["memory"]["sender"]["role"] == "caregiver"
    assert result["memory"]["sender"]["linked_user_id"] == "patient_001"
    assert result["memory"]["linked_user"]["caregivers"][0]["sender_id"] == "17736844460"
