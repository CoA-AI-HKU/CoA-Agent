
from __future__ import annotations

# Mode-command routing

import json
from pathlib import Path

from src.user.message_router import handle_incoming_message


def _write_mode_registry(path: Path) -> None:
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
    _write_mode_registry(registry_path)
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


# Role-based message routing

import json
from pathlib import Path

from src.user.message_router import handle_incoming_message
from src.metrics import log_event
from src.user.user_registry import get_user_role, normalize_sender_id


def _write_role_registry(path: Path) -> None:
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
    _write_role_registry(registry_path)
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
    _write_role_registry(registry_path)
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
    _write_role_registry(registry_path)
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
    _write_role_registry(registry_path)
    monkeypatch.setenv("USER_REGISTRY_PATH", str(registry_path))

    assert normalize_sender_id("+17736844460") == "17736844460"
    assert normalize_sender_id("17736844460@s.whatsapp.net") == "17736844460"
    assert get_user_role("+17736844460") == "caregiver"
    assert get_user_role("17736844460@s.whatsapp.net") == "caregiver"


def test_event_logging_does_not_store_raw_text(tmp_path, monkeypatch) -> None:
    registry_path = tmp_path / "user_registry.json"
    events_path = tmp_path / "events.jsonl"
    _write_role_registry(registry_path)
    monkeypatch.setenv("USER_REGISTRY_PATH", str(registry_path))
    monkeypatch.setenv("EVENTS_LOG_PATH", str(events_path))

    handle_incoming_message("你好", "999", "telegram")

    content = events_path.read_text(encoding="utf-8")
    assert "你好" not in content
    assert "raw_text" not in content
    assert "sender_id" in content


# User registry and privacy-preserving memory

import json
from pathlib import Path

from src.user.message_router import handle_incoming_message
from src.user.user_memory import build_memory_for_user_id, build_user_memory
from src.user.user_registry import get_caregiver_records_for_user, get_linked_user_id, get_linked_user_ids


def _write_memory_registry(path: Path) -> None:
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
    _write_memory_registry(registry_path)
    monkeypatch.setenv("USER_REGISTRY_PATH", str(registry_path))

    assert get_linked_user_id("+17736844460") == "patient_001"
    assert get_linked_user_ids("17736844460@s.whatsapp.net") == ["patient_001"]
    caregivers = get_caregiver_records_for_user("patient_001")
    assert caregivers[0][0] == "17736844460"


def test_user_memory_contains_bidirectional_link_without_raw_text(tmp_path, monkeypatch) -> None:
    registry_path = tmp_path / "user_registry.json"
    _write_memory_registry(registry_path)
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
    _write_memory_registry(registry_path)
    monkeypatch.setenv("USER_REGISTRY_PATH", str(registry_path))
    monkeypatch.setenv("EVENTS_LOG_PATH", str(events_path))

    result = handle_incoming_message("/summary", "17736844460", "whatsapp")

    assert result["role"] == "caregiver"
    assert result["linked_user_id"] == "patient_001"
    assert result["memory"]["sender"]["role"] == "caregiver"
    assert result["memory"]["sender"]["linked_user_id"] == "patient_001"
    assert result["memory"]["linked_user"]["caregivers"][0]["sender_id"] == "17736844460"


# Self-reported memory concerns

import json
from pathlib import Path

from src.user.message_router import handle_incoming_message
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

    assert result["route"] == "memory_concern"
    assert result["intent"] == "self_memory_concern"
    assert result["sources"] == []
    assert result["rag_called"] is False
    assert "記不住事情會令人很困擾" in result["answer"]
    assert "手機提醒" in result["answer"]
    assert "醫生" in result["answer"] or "醫護人員" in result["answer"]
    _assert_clean(result["answer"])


def test_am_i_dementia_question_is_non_diagnostic() -> None:
    result = handle_dementia_user_message("我是不是有腦退化症？")

    assert result["route"] == "memory_concern"
    assert result["sources"] == []
    assert result["rag_called"] is False
    assert "不能判斷是不是腦退化症" in result["answer"]
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


# Screening responses

from src.intent_router import classify_intent
from src.orchestrator import handle_dementia_user_message


def _assert_no_diagnosis(answer: str) -> None:
    blocked = ["你有腦退化症", "你可能有腦退化症", "你很可能有腦退化症", "風險百分比", "risk score"]
    for phrase in blocked:
        assert phrase not in answer


def test_self_screening_question_routes_to_check_in() -> None:
    intent = classify_intent("我是不是有腦退化症？")
    result = handle_dementia_user_message("我是不是有腦退化症？")

    assert intent.intent == "self_memory_concern"
    assert result["route"] == "memory_concern"
    assert result["intent"] == "self_memory_concern"
    assert "不能判斷是不是腦退化症" in result["answer"]
    assert "醫生或記憶診所" in result["answer"]
    _assert_no_diagnosis(result["answer"])


def test_caregiver_screening_question_uses_family_framing() -> None:
    result = handle_dementia_user_message("我媽媽最近成日唔記得嘢，係咪腦退化？")

    assert result["route"] == "screening"
    assert "你的家人" in result["answer"] or "家人" in result["answer"]
    assert "你可以觀察" in result["answer"]
    assert "影響日常生活或安全" in result["answer"]
    assert "醫生或記憶診所評估" in result["answer"]
    assert "你有腦退化症" not in result["answer"]


def test_urgent_red_flag_gets_safety_escalation() -> None:
    result = handle_dementia_user_message("爸爸今天突然很混亂，還說看見不存在的人")

    assert result["route"] == "safety"
    assert result["safety_level"] == "urgent_boundary"
    assert "請盡快求醫" in result["answer"] or "緊急服務" in result["answer"]
    assert "不應只當作一般記憶問題處理" in result["answer"]


def test_stress_related_memory_concern_does_not_over_pathologize() -> None:
    result = handle_dementia_user_message("我最近壓力好大，偶爾忘記東西")

    assert result["route"] == "screening"
    assert "未必一定是腦退化症" in result["answer"]
    assert "壓力" in result["answer"]
    assert "睡眠不足" in result["answer"]
    assert "持續或變嚴重" in result["answer"]
    _assert_no_diagnosis(result["answer"])


def test_formal_test_request_offers_check_in_not_score() -> None:
    result = handle_dementia_user_message("我想做一個腦退化症測試")

    assert result["route"] == "screening"
    assert "我不能判斷你是否有腦退化症" in result["answer"]
    assert "進一步評估" in result["answer"]
    assert "1." in result["answer"]
    assert "分數" not in result["answer"]
    assert "風險" not in result["answer"]
    _assert_no_diagnosis(result["answer"])


# Primary orchestrator behavior

from src.orchestrator import handle_dementia_user_message


def test_knowledge_question_calls_rag(monkeypatch) -> None:
    calls = []

    def fake_answer_question(message, config):
        calls.append((message, config))
        return {
            "answer": "腦退化症可能影響記憶、思考和日常生活。",
            "found": True,
            "sources": ["dementia.md"],
            "debug": {"retrieved_count": 1},
        }

    monkeypatch.setattr("src.agents.rag_evidence_agent.answer_question", fake_answer_question)

    result = handle_dementia_user_message("腦退化症有什麼症狀？")

    assert calls
    assert result["intent"] == "knowledge_qa"
    assert result["rag_called"] is True
    assert result["safety_level"] == "normal"
    assert result["debug"]["source_count"] == 1


def test_medication_question_does_not_call_normal_rag(monkeypatch) -> None:
    def fail_answer_question(message, config):
        raise AssertionError("Medication boundary route must not call normal RAG")

    monkeypatch.setattr("src.agents.rag_evidence_agent.answer_question", fail_answer_question)

    result = handle_dementia_user_message("我可不可以幫媽媽停藥？")

    assert result["intent"] == "medication_or_diagnosis"
    assert result["rag_called"] is False
    assert result["safety_level"] == "medical_boundary"
    assert result["sources"] == []


def test_english_medication_question_does_not_call_normal_rag(monkeypatch) -> None:
    def fail_answer_question(message, config):
        raise AssertionError("Medication boundary route must not call normal RAG")

    monkeypatch.setattr("src.agents.rag_evidence_agent.answer_question", fail_answer_question)

    result = handle_dementia_user_message("Can I take aspirin?")

    assert result["rag_called"] is False
    assert result["safety_level"] == "medical_boundary"
    assert result["answer_language"] == "en"
    assert "any medication advice" in result["answer"]


def test_safety_question_does_not_call_normal_rag(monkeypatch) -> None:
    def fail_answer_question(message, config):
        raise AssertionError("Safety boundary route must not call normal RAG")

    monkeypatch.setattr("src.agents.rag_evidence_agent.answer_question", fail_answer_question)

    result = handle_dementia_user_message("媽媽走失了，我找不到她")

    assert result["intent"] == "safety_sensitive"
    assert result["rag_called"] is False
    assert result["safety_level"] == "urgent_boundary"
    assert result["sources"] == []


def test_cognitive_activity_returns_activity_response(monkeypatch) -> None:
    def fail_answer_question(message, config):
        raise AssertionError("Activity placeholder route must not call normal RAG")

    monkeypatch.setattr("src.agents.rag_evidence_agent.answer_question", fail_answer_question)

    result = handle_dementia_user_message("我好悶，有什麼可以做？")

    assert result["intent"] == "cognitive_activity"
    assert result["rag_called"] is False
    assert "三種水果" in result["answer"]
    assert result["answer_language"] == "zh-Hant"


def test_static_responses_follow_simplified_input(monkeypatch) -> None:
    def fail_answer_question(message, config):
        raise AssertionError("Static activity route must not call normal RAG")

    monkeypatch.setattr("src.agents.rag_evidence_agent.answer_question", fail_answer_question)

    result = handle_dementia_user_message("我好无聊，有什么可以做？")

    assert result["intent"] == "cognitive_activity"
    assert result["answer_language"] == "zh-Hans"
    assert "三种水果" in result["answer"]
    assert result["debug"]["answer_language"] == "zh-Hans"


def test_static_responses_follow_english_input(monkeypatch) -> None:
    def fail_answer_question(message, config):
        raise AssertionError("Static activity route must not call normal RAG")

    monkeypatch.setattr("src.agents.rag_evidence_agent.answer_question", fail_answer_question)

    result = handle_dementia_user_message("I am bored, what can I do?")

    assert result["intent"] == "cognitive_activity"
    assert result["answer_language"] == "en"
    assert "three fruits" in result["answer"]


def test_unknown_does_not_invent_dementia_knowledge(monkeypatch) -> None:
    def fail_answer_question(message, config):
        raise AssertionError("Unknown route must not call normal RAG")

    monkeypatch.setattr("src.agents.rag_evidence_agent.answer_question", fail_answer_question)

    result = handle_dementia_user_message("幫我寫一首歌")

    assert result["intent"] == "unknown"
    assert result["rag_called"] is False
    assert result["found"] is False
    assert "腦退化" not in result["answer"]


# Multi-agent orchestration

from src.orchestrator import handle_dementia_user_message


def test_knowledge_question_routes_to_rag(monkeypatch) -> None:
    def fake_answer_question(message, config):
        return {
            "answer": "腦退化症會影響記憶和日常生活。",
            "found": True,
            "sources": ["dementia.md"],
            "debug": {"retrieved_count": 1},
        }

    monkeypatch.setattr("src.agents.rag_evidence_agent.answer_question", fake_answer_question)

    result = handle_dementia_user_message("腦退化症是什麼？")

    assert result["route"] == "rag_qa"
    assert result["rag_called"] is True
    assert result["debug"]["coordinator"]["route"] == "rag_qa"


def test_medication_question_routes_to_medical_boundary(monkeypatch) -> None:
    monkeypatch.setattr(
        "src.agents.rag_evidence_agent.answer_question",
        lambda message, config: (_ for _ in ()).throw(AssertionError("RAG must not run")),
    )

    result = handle_dementia_user_message("我可不可以幫媽媽停藥？")

    assert result["route"] == "medical_boundary"
    assert result["rag_called"] is False
    assert result["safety_level"] == "medical_boundary"


def test_safety_question_routes_to_safety(monkeypatch) -> None:
    monkeypatch.setattr(
        "src.agents.rag_evidence_agent.answer_question",
        lambda message, config: (_ for _ in ()).throw(AssertionError("RAG must not run")),
    )

    result = handle_dementia_user_message("媽媽走失了，我找不到她")

    assert result["route"] == "safety"
    assert result["rag_called"] is False
    assert result["safety_level"] == "urgent_boundary"


def test_reminder_question_routes_to_routine_placeholder() -> None:
    result = handle_dementia_user_message("提醒我下午三點飲水")

    assert result["route"] == "routine"
    assert result["rag_called"] is False


def test_personal_memory_routes_to_memory_placeholder() -> None:
    result = handle_dementia_user_message("我女兒叫什麼名字？")

    assert result["route"] == "memory"
    assert result["rag_called"] is False


def test_activity_routes_to_activity_agent() -> None:
    result = handle_dementia_user_message("我好悶，有什麼可以做？")

    assert result["route"] == "activity"
    assert result["rag_called"] is False


def test_unknown_does_not_call_rag(monkeypatch) -> None:
    monkeypatch.setattr(
        "src.agents.rag_evidence_agent.answer_question",
        lambda message, config: (_ for _ in ()).throw(AssertionError("RAG must not run")),
    )

    result = handle_dementia_user_message("幫我寫一首歌")

    assert result["route"] == "unknown"
    assert result["rag_called"] is False


def test_simplifier_preserves_medical_boundary() -> None:
    result = handle_dementia_user_message("我可以食多一粒藥嗎？")

    assert result["route"] == "medical_boundary"
    assert "不能提供" in result["answer"]
    assert "醫生" in result["answer"]
    assert "藥劑師" in result["answer"]
    assert result["debug"]["simplifier_applied"] is True


# Assumption and bias guards

from src.agents.coordinator_agent import infer_user_role
from src.orchestrator import handle_dementia_user_message


BLOCKED_ASSUMPTIONS = [
    "因為你有腦退化症",
    "你的腦退化症",
    "作為腦退化症患者",
    "因為你記性不好",
    "你的照顧者",
    "你有記憶力問題",
    "你需要照顧者",
    "你不能自己",
    "你無能力",
]


def _assert_no_blocked_assumptions(answer: str) -> None:
    for phrase in BLOCKED_ASSUMPTIONS:
        assert phrase not in answer


def test_user_role_defaults_to_unknown() -> None:
    assert infer_user_role("") == "unknown"
    assert infer_user_role("下午三點") == "unknown"
    assert infer_user_role("我唔記得我食咗藥未") == "unknown"
    assert infer_user_role("我忘記了今天要做什麼") == "unknown"


def test_general_dementia_question_does_not_assume_user_has_dementia(monkeypatch) -> None:
    def fake_answer_question(message, config):
        return {
            "answer": "腦退化症會影響記憶和日常生活。你有腦退化症時，你的照顧者可以協助。",
            "found": True,
            "sources": ["dementia.md"],
            "debug": {"retrieved_count": 1},
        }

    monkeypatch.setattr("src.agents.rag_evidence_agent.answer_question", fake_answer_question)

    result = handle_dementia_user_message("腦退化症是什麼？")

    assert "腦退化症" in result["answer"]
    _assert_no_blocked_assumptions(result["answer"])
    assert "你有腦退化症" not in result["answer"]
    assert result["debug"]["coordinator"]["user_role"] == "general_user"


def test_older_adult_daily_question_stays_neutral() -> None:
    result = handle_dementia_user_message("我今日要做咩？")

    _assert_no_blocked_assumptions(result["answer"])
    assert "腦退化" not in result["answer"]
    assert result["debug"]["coordinator"]["user_role"] == "unknown"


def test_caregiver_question_refers_to_family_not_speaker(monkeypatch) -> None:
    def fake_answer_question(message, config):
        return {
            "answer": "如果這是腦退化症照顧情境，家人重複提問時可以保持平靜，回應媽媽的感受。",
            "found": True,
            "sources": ["care.md"],
            "debug": {"retrieved_count": 1},
        }

    monkeypatch.setattr("src.agents.rag_evidence_agent.answer_question", fake_answer_question)

    result = handle_dementia_user_message("我媽媽成日重複問同一條問題，我應該點做？")

    assert "媽媽" in result["answer"] or "家人" in result["answer"]
    assert "你有腦退化症" not in result["answer"]
    assert "你的腦退化症" not in result["answer"]
    assert result["debug"]["coordinator"]["user_role"] == "caregiver_or_family"


def test_medication_uncertainty_does_not_invent_dementia_context() -> None:
    result = handle_dementia_user_message("我唔知我食咗藥未")

    _assert_no_blocked_assumptions(result["answer"])
    assert (
        "不要自行再服一次" in result["answer"]
        or "唔好自行補食" in result["answer"]
        or "不要自行补吃" in result["answer"]
    )
    assert "藥劑師" in result["answer"] or "药剂师" in result["answer"]
    assert "醫生" in result["answer"] or "医生" in result["answer"]


def test_explicit_self_disclosure_can_be_acknowledged_without_stigma(monkeypatch) -> None:
    def fake_answer_question(message, config):
        return {
            "answer": "你有腦退化症這個情況時，可以用固定時間和清楚提示幫自己記得食飯。因為你記性不好，要小心。",
            "found": True,
            "sources": ["routine.md"],
            "debug": {"retrieved_count": 1},
        }

    monkeypatch.setattr("src.agents.rag_evidence_agent.answer_question", fake_answer_question)

    result = handle_dementia_user_message("醫生話我有腦退化症，我成日唔記得食飯")

    assert "你有腦退化症" in result["answer"]
    assert "因為你記性不好" not in result["answer"]
    assert "可以" in result["answer"]
    assert result["debug"]["coordinator"]["user_role"] == "self_with_cognitive_concern"


def test_final_answer_removes_memory_caregiver_and_capacity_assumptions(monkeypatch) -> None:
    def fake_answer_question(message, config):
        return {
            "answer": (
                "你有記憶力問題，所以你需要照顧者。"
                "你不能自己處理這件事，因為你無能力判斷。"
            ),
            "found": True,
            "sources": ["care.md"],
            "debug": {"retrieved_count": 1},
        }

    monkeypatch.setattr("src.agents.rag_evidence_agent.answer_question", fake_answer_question)

    result = handle_dementia_user_message("記憶力有什麼支援方法？")

    _assert_no_blocked_assumptions(result["answer"])
    assert "如有需要，可以請家人、照顧者或醫護人員協助" in result["answer"]


def test_memory_concern_uses_neutral_template_without_sources() -> None:
    result = handle_dementia_user_message("我最近覺得很多事情好像都有點記不住")
    answer = result["answer"]

    assert result["route"] == "memory_concern"
    assert "來源" not in answer
    assert ".md" not in answer
    assert "資料庫" not in answer
    assert "腦退化症好常見" not in answer
    assert "病情" not in answer
    assert "你之前都問過" not in answer
    assert "手機提醒" in answer
    assert "固定位置" in answer
    assert "醫生" in answer or "醫護人員" in answer
    assert "影響日常生活" in answer


def test_repeated_memory_concern_is_not_called_out() -> None:
    handle_dementia_user_message("我最近覺得很多事情好像都有點記不住")
    second = handle_dementia_user_message("我最近覺得很多事情好像都有點記不住")

    assert "你之前都問過" not in second["answer"]
    assert "你重複問" not in second["answer"]
    assert "重複" not in second["answer"]


def test_am_i_dementia_is_non_diagnostic_and_recommends_assessment() -> None:
    result = handle_dementia_user_message("我是不是有腦退化症？")
    answer = result["answer"]

    assert "不能判斷" in answer
    assert "醫生" in answer or "記憶診所" in answer
    assert "作評估" in answer or "評估" in answer
    assert "你有腦退化症" not in answer
    assert "確診" not in answer


def test_explicit_disclosure_memory_concern_has_no_source_or_stigma() -> None:
    result = handle_dementia_user_message("醫生話我有腦退化症，我最近成日唔記得嘢")
    answer = result["answer"]

    assert "來源" not in answer
    assert ".md" not in answer
    assert "資料庫" not in answer
    assert "作為腦退化症患者" not in answer
    assert "病情" not in answer
    assert "你之前都問過" not in answer


# Intent classification and boundary routing

from src.intent_router import IntentResult, classify_intent
from src.dementia_rag import search_dementia_knowledge
from src.pipeline.rag_agent import SAFETY_SENSITIVE_RESPONSE, answer_question


def test_classify_intent_returns_intent_result() -> None:
    result = classify_intent("腦退化症有什麼症狀？")

    assert isinstance(result, IntentResult)


def test_knowledge_qa() -> None:
    assert classify_intent("腦退化症有什麼症狀？").intent == "knowledge_qa"


def test_safety_sensitive_wandering() -> None:
    assert classify_intent("媽媽走失了，我找不到她").intent == "safety_sensitive"


def test_medication_boundary() -> None:
    assert classify_intent("我可不可以幫她停藥？").intent == "medication_or_diagnosis"


def test_reminder_request() -> None:
    assert classify_intent("提醒我下午三點飲水").intent == "reminder_request"


def test_cognitive_activity() -> None:
    assert classify_intent("我好悶，有什麼可以做？").intent == "cognitive_activity"


def test_emotional_support() -> None:
    assert classify_intent("我覺得好孤單").intent == "emotional_support"


def test_personal_memory() -> None:
    assert classify_intent("我女兒叫什麼名字？").intent == "personal_memory"


def test_unknown() -> None:
    assert classify_intent("幫我寫一首歌").intent == "unknown"


def test_safety_priority_over_knowledge() -> None:
    assert classify_intent("腦退化症患者走失了怎麼辦？").intent == "safety_sensitive"


def test_prevention_safety_question_stays_knowledge_qa() -> None:
    assert classify_intent("如何預防腦退化症患者走失？").intent == "knowledge_qa"


def test_medication_priority_over_reminder() -> None:
    assert classify_intent("提醒我停藥").intent == "medication_or_diagnosis"


def test_english_terms() -> None:
    assert classify_intent("What are dementia symptoms?").intent == "knowledge_qa"
    assert classify_intent("Please remind me about my appointment").intent == "reminder_request"


def test_debug_fields_include_matches_and_reason() -> None:
    result = classify_intent("媽媽走失了，我找不到她")

    assert result.confidence > 0.0
    assert result.matched_terms == ["走失", "找不到"]
    assert result.reason


def test_rag_answer_question_includes_intent_for_empty_message(tmp_path) -> None:
    result = answer_question("", {"chroma_dir": tmp_path / "chroma", "auto_index": False})

    assert result["intent"] == "unknown"
    assert result["intent_debug"]["confidence"] == 0.0
    assert result["debug"]["intent"] == "unknown"
    assert result["debug"]["intent_debug"]["reason"]


def test_rag_answer_question_handles_medication_without_retrieval(tmp_path, monkeypatch) -> None:
    def fail_build_runtime_agent(config):
        raise AssertionError("Boundary handlers must run before RAG retrieval")

    monkeypatch.setattr("src.pipeline.rag_agent._build_runtime_agent", fail_build_runtime_agent)

    result = answer_question(
        "我可不可以幫她停藥？",
        {
            "chroma_dir": tmp_path / "chroma",
            "auto_index": False,
            "patient_profile": {"preferred_name": "眉眉婆婆", "caregivers": [{"name": "Maria"}]},
        },
    )

    assert "不能提供關於" in result["answer"]
    assert "Maria" in result["answer"]
    assert result["found"] is False
    assert result["sources"] == []
    assert result["debug"]["boundary_handler"] == "medication_safety"
    assert result["debug"]["normal_rag_skipped"] is True


def test_rag_answer_question_handles_urgent_safety_without_retrieval(tmp_path, monkeypatch) -> None:
    def fail_build_runtime_agent(config):
        raise AssertionError("Boundary handlers must run before RAG retrieval")

    monkeypatch.setattr("src.pipeline.rag_agent._build_runtime_agent", fail_build_runtime_agent)

    result = answer_question("媽媽走失了，我找不到她", {"chroma_dir": tmp_path / "chroma", "auto_index": False})

    assert result["answer"] == SAFETY_SENSITIVE_RESPONSE
    assert result["found"] is False
    assert result["sources"] == []
    assert result["debug"]["boundary_handler"] == "safety_sensitive"


def test_search_wrapper_includes_intent_for_empty_message() -> None:
    result = search_dementia_knowledge("")

    assert result["intent"] == "unknown"
    assert result["intent_debug"]["confidence"] == 0.0
    assert result["debug"]["intent"] == "unknown"


def test_search_wrapper_returns_boundary_context(monkeypatch) -> None:
    monkeypatch.setattr(
        "src.dementia_rag.shared_answer_question",
        lambda question, config: {
            "found": False,
            "answer": SAFETY_SENSITIVE_RESPONSE,
            "sources": [],
            "context_used": "",
            "intent": "safety_sensitive",
            "intent_debug": {"confidence": 0.95, "matched_terms": ["走失"], "reason": "test"},
            "debug": {"boundary_handler": "safety_sensitive"},
        },
    )

    result = search_dementia_knowledge("媽媽走失了")

    assert result["context"] == SAFETY_SENSITIVE_RESPONSE
    assert result["risk_level"] == "high"
    assert result["sources"] == []
