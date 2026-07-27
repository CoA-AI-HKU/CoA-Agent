from __future__ import annotations

from src.agents.coordinator_agent import coordinate_message
from src.intent_router import classify_intent
from src.orchestrator import handle_dementia_user_message


def test_required_intent_routes() -> None:
    cases = {
        "腦退化症是什麼？": ("dementia_knowledge", "rag_qa", True),
        "我想出去走走，可以嗎？": ("daily_life_support", "daily_life", False),
        "你好": ("casual_conversation", "general", False),
        "我很孤單": ("emotional_support", "supportive", False),
        "我最近成日唔記得嘢": ("memory_concern", "memory_concern", False),
        "我應該食幾多粒藥？": ("medication_or_diagnosis", "medical_boundary", False),
    }
    for message, expected in cases.items():
        intent, route, rag_required = expected
        assert classify_intent(message).intent == intent
        decision = coordinate_message(message)
        assert (decision.intent, decision.route, decision.rag_required) == expected


def test_daily_life_route_does_not_call_rag(monkeypatch) -> None:
    def fail_if_called(*args, **kwargs):
        raise AssertionError("knowledge retrieval must not run for daily-life support")

    monkeypatch.setattr("src.orchestrator.answer_with_dementia_evidence", fail_if_called)
    result = handle_dementia_user_message("我想出去走走，可以嗎？", "route-test")
    assert result["intent"] == "daily_life_support"
    assert result["route"] == "daily_life"
    assert result["rag_called"] is False
    assert result["found"] is False
    assert result["fallback_reason"] == "none"
    assert "找不到足夠資料" not in result["answer"]
    assert "腦退化" not in result["answer"]


def test_daily_life_examples_are_non_rag() -> None:
    for message in (
        "我想自己去買東西。", "我找不到鎖匙。", "我今天可以煮飯嗎？",
        "我想搭巴士去公園。", "我想打電話給女兒。",
    ):
        decision = coordinate_message(message)
        assert decision.intent == "daily_life_support"
        assert decision.route == "daily_life"
        assert decision.rag_required is False
