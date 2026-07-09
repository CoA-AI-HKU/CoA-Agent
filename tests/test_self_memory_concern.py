from __future__ import annotations

import json
from pathlib import Path

from src.message_router import handle_incoming_message
from src.orchestrator import handle_dementia_user_message


BLOCKED = [
    "來源",
    ".md",
    "根據資料庫",
    "資料庫指出",
    "你有腦退化症",
    "作為腦退化症患者",
    "腦退化症嘅一部分",
]


def _assert_clean(answer: str) -> None:
    for phrase in BLOCKED:
        assert phrase not in answer


def test_forgetfulness_routes_to_self_memory_concern_without_rag() -> None:
    result = handle_dementia_user_message("最近覺得很多事情好像都有點記不住")

    assert result["route"] == "self_memory_concern"
    assert result["intent"] == "self_memory_concern"
    assert result["sources"] == []
    assert result["rag_called"] is False
    assert "不一定代表是腦退化症" in result["answer"]
    assert "醫生" in result["answer"] or "醫護人員" in result["answer"]
    _assert_clean(result["answer"])


def test_am_i_dementia_question_is_non_diagnostic() -> None:
    result = handle_dementia_user_message("我是不是有腦退化症？")

    assert result["route"] == "self_memory_concern"
    assert result["sources"] == []
    assert result["rag_called"] is False
    assert "不一定代表是腦退化症" in result["answer"]
    assert "醫生" in result["answer"] or "醫護人員" in result["answer"]
    assert "你有腦退化症" not in result["answer"]
    _assert_clean(result["answer"])


def test_dementia_definition_can_use_rag_but_hides_sources(monkeypatch) -> None:
    def fake_answer_question(message, config):
        return {
            "answer": "腦退化症是一類會影響記憶、思考和日常功能的疾病。\n來源：abc.md",
            "answer_with_sources": "腦退化症是一類會影響記憶、思考和日常功能的疾病。\n來源：abc.md",
            "sources": ["abc.md"],
            "found": True,
            "debug": {"retrieved_count": 1},
        }

    monkeypatch.setattr("src.agents.rag_evidence_agent.answer_question", fake_answer_question)

    result = handle_dementia_user_message("腦退化症是什麼？")

    assert result["route"] == "rag_qa"
    assert result["rag_called"] is True
    assert result["sources"] == ["abc.md"]
    _assert_clean(result["answer"])


def test_caregiver_memory_risk_question_gets_guidance_not_screening(tmp_path, monkeypatch) -> None:
    registry_path = tmp_path / "user_registry.json"
    events_path = tmp_path / "events.jsonl"
    registry_path.write_text(
        json.dumps(
            {
                "users": {
                    "17736844460": {
                        "role": "caregiver",
                        "linked_user_id": "patient_001",
                        "display_name": "Ling",
                    }
                }
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("USER_REGISTRY_PATH", str(registry_path))
    monkeypatch.setenv("EVENTS_LOG_PATH", str(events_path))

    result = handle_incoming_message("我媽媽最近好多嘢記唔住，係咪有腦退化症？", "17736844460", "whatsapp")

    assert result["role"] == "caregiver"
    assert result["route"] == "caregiver_guidance"
    assert result["intent"] == "caregiver_guidance"
    assert result["rag_called"] is False
    assert result["debug"]["caregiver_manager"]["command"] != "screening"
    assert "screening_classification" not in result or result["debug"].get("screening_classification") is None
    assert "家人" in result["answer"]
    _assert_clean(result["answer"])

    logged = events_path.read_text(encoding="utf-8")
    assert "caregiver_guidance" in logged
    assert "cognitive_screening" not in logged
