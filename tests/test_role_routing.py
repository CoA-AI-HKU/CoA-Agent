from __future__ import annotations

import json
from pathlib import Path

from src.message_router import handle_incoming_message
from src.metrics import log_event
from src.user_registry import get_user_role, normalize_sender_id


def _write_registry(path: Path) -> None:
    path.write_text(
        json.dumps(
            {
                "users": {
                    "17736844460": {
                        "role": "caregiver",
                        "linked_user_id": "patient_001",
                        "display_name": "Ling",
                    },
                    "85244924928": {
                        "role": "user",
                        "user_id": "patient_001",
                        "display_name": "陳太",
                    },
                }
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


def test_caregiver_summary_routes_to_caregiver_mode(tmp_path, monkeypatch) -> None:
    registry_path = tmp_path / "user_registry.json"
    events_path = tmp_path / "events.jsonl"
    _write_registry(registry_path)
    monkeypatch.setenv("USER_REGISTRY_PATH", str(registry_path))
    monkeypatch.setenv("EVENTS_LOG_PATH", str(events_path))

    result = handle_incoming_message("/summary", "17736844460", "whatsapp")

    assert result["role"] == "caregiver"
    assert result["route"] == "caregiver_mode"
    assert "摘要" in result["answer"]
    assert result["rag_called"] is False


def test_user_routes_to_user_mode(tmp_path, monkeypatch) -> None:
    registry_path = tmp_path / "user_registry.json"
    events_path = tmp_path / "events.jsonl"
    _write_registry(registry_path)
    monkeypatch.setenv("USER_REGISTRY_PATH", str(registry_path))
    monkeypatch.setenv("EVENTS_LOG_PATH", str(events_path))

    def fake_handle(message, user_id=None, show_sources=False):
        return {
            "answer": "短回答",
            "route": "rag_qa",
            "intent": "knowledge_qa",
            "sources": [],
            "debug": {},
            "rag_called": True,
            "safety_level": "normal",
        }

    monkeypatch.setattr("src.agents.patient_user_manager_agent.handle_dementia_user_message", fake_handle)

    result = handle_incoming_message("腦退化症是什麼", "85244924928", "whatsapp")

    assert result["role"] == "user"
    assert result["user_id"] == "patient_001"
    assert result["manager"] == "patient_user_manager"
    assert result["route"] == "rag_qa"
    assert result["rag_called"] is True


def test_unknown_sender_defaults_to_neutral_user_mode(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("USER_REGISTRY_PATH", str(tmp_path / "missing_registry.json"))
    monkeypatch.setenv("EVENTS_LOG_PATH", str(tmp_path / "events.jsonl"))

    result = handle_incoming_message("你好", "999", "telegram")

    assert result["role"] == "unknown"
    assert result["sender_id"] == "999"
    assert "腦退化" not in result["answer"]
    assert "/summary" not in result["answer"]
    assert "/alerts" not in result["answer"]


def test_caregiver_summary_does_not_include_raw_conversation_text(tmp_path, monkeypatch) -> None:
    registry_path = tmp_path / "user_registry.json"
    events_path = tmp_path / "events.jsonl"
    _write_registry(registry_path)
    monkeypatch.setenv("USER_REGISTRY_PATH", str(registry_path))
    monkeypatch.setenv("EVENTS_LOG_PATH", str(events_path))
    log_event(
        "patient_001",
        {
            "user_id": "patient_001",
            "sender_id": "85244924928",
            "role": "user",
            "route": "supportive",
            "intent": "emotional_support",
            "event_type": "emotional_support_signal",
            "raw_text": "我今日好唔開心",
        },
    )

    result = handle_incoming_message("/summary", "+17736844460", "whatsapp")

    assert "情緒支援訊號：1" in result["answer"]
    assert "我今日好唔開心" not in result["answer"]
    assert "raw_text" not in result["answer"]


def test_sender_normalization_works(tmp_path, monkeypatch) -> None:
    registry_path = tmp_path / "user_registry.json"
    _write_registry(registry_path)
    monkeypatch.setenv("USER_REGISTRY_PATH", str(registry_path))

    assert normalize_sender_id("+17736844460") == "17736844460"
    assert normalize_sender_id("17736844460@s.whatsapp.net") == "17736844460"
    assert get_user_role("+17736844460") == "caregiver"
    assert get_user_role("17736844460@s.whatsapp.net") == "caregiver"


def test_event_logging_does_not_store_raw_text(tmp_path, monkeypatch) -> None:
    registry_path = tmp_path / "user_registry.json"
    events_path = tmp_path / "events.jsonl"
    _write_registry(registry_path)
    monkeypatch.setenv("USER_REGISTRY_PATH", str(registry_path))
    monkeypatch.setenv("EVENTS_LOG_PATH", str(events_path))

    handle_incoming_message("你好", "999", "telegram")

    content = events_path.read_text(encoding="utf-8")
    assert "你好" not in content
    assert "raw_text" not in content
    assert "sender_id" in content
