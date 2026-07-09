from __future__ import annotations

import json
from pathlib import Path

from src.message_router import handle_incoming_message


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


def _setup_registry(tmp_path, monkeypatch) -> None:
    registry_path = tmp_path / "user_registry.json"
    events_path = tmp_path / "events.jsonl"
    _write_registry(registry_path)
    monkeypatch.setenv("USER_REGISTRY_PATH", str(registry_path))
    monkeypatch.setenv("EVENTS_LOG_PATH", str(events_path))


def test_whichroleami_for_caregiver(tmp_path, monkeypatch) -> None:
    _setup_registry(tmp_path, monkeypatch)

    result = handle_incoming_message("/whichroleami", "+17736844460", "whatsapp")

    assert result["role"] == "caregiver"
    assert result["route"] == "mode_info"
    assert "照顧者模式" in result["answer"]
    assert "/summary" in result["answer"]
    assert "/alerts" in result["answer"]
    assert "linked_user_id：patient_001" in result["answer"]


def test_whichroleami_for_user(tmp_path, monkeypatch) -> None:
    _setup_registry(tmp_path, monkeypatch)

    result = handle_incoming_message("/whichroleami", "85244924928", "whatsapp")

    assert result["role"] == "user"
    assert "使用者模式" in result["answer"]
    assert "日常支援" in result["answer"]
    assert "user_id：patient_001" in result["answer"]
    assert "/summary" not in result["answer"]
    assert "/alerts" not in result["answer"]


def test_whichroleami_for_unknown(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("USER_REGISTRY_PATH", str(tmp_path / "missing_registry.json"))
    monkeypatch.setenv("EVENTS_LOG_PATH", str(tmp_path / "events.jsonl"))

    result = handle_incoming_message("\\whichroleami", "999", "telegram")

    assert result["role"] == "unknown"
    assert "未登記使用者" in result["answer"]
    assert "照顧者設定、摘要和提醒功能只開放給已登記帳號" in result["answer"]
    assert "你有腦退化症" not in result["answer"]


def test_caregiver_summary_routes_to_caregiver_manager(tmp_path, monkeypatch) -> None:
    _setup_registry(tmp_path, monkeypatch)

    result = handle_incoming_message("/summary", "17736844460", "whatsapp")

    assert result["role"] == "caregiver"
    assert result["manager"] == "caregiver_manager"
    assert result["route"] == "caregiver_mode"


def test_user_normal_question_routes_to_patient_user_manager(tmp_path, monkeypatch) -> None:
    _setup_registry(tmp_path, monkeypatch)

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
    assert result["manager"] == "patient_user_manager"
    assert result["user_id"] == "patient_001"


def test_unknown_normal_question_routes_to_patient_user_manager(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("USER_REGISTRY_PATH", str(tmp_path / "missing_registry.json"))
    monkeypatch.setenv("EVENTS_LOG_PATH", str(tmp_path / "events.jsonl"))

    result = handle_incoming_message("你好", "999", "telegram")

    assert result["role"] == "unknown"
    assert result["manager"] == "patient_user_manager"
    assert "腦退化" not in result["answer"]


def test_caregiver_free_text_can_get_guidance(tmp_path, monkeypatch) -> None:
    _setup_registry(tmp_path, monkeypatch)

    def fake_handle(message, user_id=None, show_sources=False):
        return {
            "answer": "家人重複提問時，可以先保持平靜，簡短回應，並留意是否影響生活或安全。",
            "route": "rag_qa",
            "intent": "knowledge_qa",
            "sources": ["care.md"],
            "debug": {},
            "rag_called": True,
            "safety_level": "normal",
        }

    monkeypatch.setattr("src.agents.caregiver_manager_agent.handle_dementia_user_message", fake_handle)

    result = handle_incoming_message("媽媽成日重複問同一條問題，我應該點做？", "17736844460", "whatsapp")

    assert result["role"] == "caregiver"
    assert result["manager"] == "caregiver_manager"
    assert "家人" in result["answer"] or "媽媽" in result["answer"]
    assert ".md" not in result["answer"]
    assert "來源" not in result["answer"]
    assert "你有腦退化症" not in result["answer"]
